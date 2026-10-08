"""M-Pesa Daraja collection (Plan A1.3 R2.3, ADR-0015).

Money moves from the client's phone straight to the tenant's own Paybill or Till; we never hold it.

- **Prompt (STK Push):** from the app or the client's invoice link. The amount is the invoice balance rounded up
  to whole shillings (M-Pesa takes no cents); anything over the balance is kept as the client's credit.
- **Never trust a callback alone:** a successful STK callback is confirmed with STK Query before a payment is
  recorded. Prompts whose callback is late are checked by a job every minute, and on demand when the client's
  page asks for the status.
- **C2B:** a client paying the Paybill by hand types the invoice's payment reference as the account number; a
  confirmation that matches an issued invoice is recorded against it, anything else waits in the unmatched
  queue.
- **Callbacks:** stored first (``webhook_events``, unique per provider key), acted on by a job, so duplicates
  and replays are harmless.
"""

import hashlib
import math
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import pii_cipher
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.permissions import Perm
from app.core.phone import InvalidPhoneError, to_e164
from app.integrations.mpesa import (
    Credentials,
    DarajaError,
    MpesaClient,
    client_for,
    simulated_receipt,
)
from app.modules.billing import service as billing
from app.modules.clients import service as clients
from app.modules.mpesa.models import MpesaConnection, MpesaRequest, MpesaTransaction, WebhookEvent
from app.modules.mpesa.schemas import (
    ConnectionIn,
    ConnectionOut,
    IgnoreIn,
    MatchIn,
    PromptOut,
    TransactionOut,
)
from app.modules.notifications import service as notifications
from app.modules.public_links import service as links
from app.modules.tenancy import service as tenancy
from app.platform import audit, events
from app.platform.deps import Principal, TenantContext

logger = structlog.get_logger(__name__)

PROCESS_EVENT = "mpesa.process_event"
CHECK_REQUEST = "mpesa.check_request"
PENDING, PAID, CANCELLED, FAILED, EXPIRED = "pending", "paid", "cancelled", "failed", "expired"
PROMPT_TTL = timedelta(minutes=5)  # Daraja gives up after about a minute; we wait a little longer
RECHECK_AFTER = timedelta(seconds=8)


class MpesaError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "mpesa_error"
    title = "M-Pesa could not do that"


class NotConnectedError(ConflictError):
    code = "mpesa_not_connected"
    title = "Connect your M-Pesa Paybill or Till first"


# ---------------------------------------------------------------- connection


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _urls(settings: Settings, token: str) -> dict[str, str]:
    base = f"{settings.public_api_base_url.rstrip('/')}/api/v1/webhooks/mpesa/{token}"
    return {
        "stk_callback_url": f"{base}/stk",
        "c2b_confirmation_url": f"{base}/c2b/confirmation",
        "c2b_validation_url": f"{base}/c2b/validation",
    }


async def get_connection(session: AsyncSession) -> MpesaConnection | None:
    return await session.scalar(select(MpesaConnection))


def credentials(connection: MpesaConnection, settings: Settings) -> Credentials:
    cipher = pii_cipher(settings)
    till = connection.shortcode_type == "till"
    return Credentials(
        environment=connection.environment,  # type: ignore[arg-type]
        consumer_key=cipher.decrypt(connection.consumer_key_enc),
        consumer_secret=cipher.decrypt(connection.consumer_secret_enc),
        business_shortcode=connection.business_shortcode,
        passkey=cipher.decrypt(connection.passkey_enc),
        party_b=connection.party_b,
        transaction_type="CustomerBuyGoodsOnline" if till else "CustomerPayBillOnline",
    )


def _client(
    connection: MpesaConnection, settings: Settings, http: httpx.AsyncClient
) -> MpesaClient:
    if connection.environment == "simulator" and settings.is_production:
        raise MpesaError("The M-Pesa simulator is not available in production")
    return client_for(credentials(connection, settings), http)


def _token(connection: MpesaConnection, settings: Settings) -> str:
    return pii_cipher(settings).decrypt(connection.callback_token_enc)


def connection_out(connection: MpesaConnection, settings: Settings) -> ConnectionOut:
    key = pii_cipher(settings).decrypt(connection.consumer_key_enc)
    return ConnectionOut(
        environment=connection.environment,
        shortcode_type=connection.shortcode_type,
        business_shortcode=connection.business_shortcode,
        party_b=connection.party_b,
        status=connection.status,
        consumer_key_hint=f"…{key[-4:]}",
        c2b_registered_at=connection.c2b_registered_at,
        last_error=connection.last_error,
        version=connection.version,
        **_urls(settings, _token(connection, settings)),
    )


async def save_connection(
    ctx: TenantContext, body: ConnectionIn, settings: Settings, http: httpx.AsyncClient
) -> MpesaConnection:
    """Create or replace the tenant's connection after checking the keys with Safaricom."""
    if body.environment == "simulator" and settings.is_production:
        raise MpesaError("The M-Pesa simulator is not available in production")
    if body.shortcode_type == "till" and not body.till_number:
        raise MpesaError("Give the till number as well as the store number")
    party_b = body.till_number if body.shortcode_type == "till" else body.business_shortcode
    assert party_b is not None  # noqa: S101 - checked above
    probe = Credentials(
        environment=body.environment,
        consumer_key=body.consumer_key,
        consumer_secret=body.consumer_secret,
        business_shortcode=body.business_shortcode,
        passkey=body.passkey,
        party_b=party_b,
        transaction_type="CustomerBuyGoodsOnline"
        if body.shortcode_type == "till"
        else "CustomerPayBillOnline",
    )
    try:
        await client_for(probe, http).check_credentials()
    except DarajaError as exc:
        raise MpesaError(exc.detail) from None
    cipher = pii_cipher(settings)
    token = secrets.token_urlsafe(32)
    connection = await get_connection(ctx.session)
    if connection is None:
        connection = MpesaConnection(tenant_id=ctx.tenant_id, created_by=ctx.principal.user_id)
        ctx.session.add(connection)
    connection.environment = body.environment
    connection.shortcode_type = body.shortcode_type
    connection.business_shortcode = body.business_shortcode
    connection.party_b = party_b
    connection.consumer_key_enc = cipher.encrypt(body.consumer_key)
    connection.consumer_secret_enc = cipher.encrypt(body.consumer_secret)
    connection.passkey_enc = cipher.encrypt(body.passkey)
    connection.callback_token_hash = _hash(token)  # a new secret path every time the keys change
    connection.callback_token_enc = cipher.encrypt(token)
    connection.status = "active"
    connection.c2b_registered_at = None
    connection.last_error = None
    connection.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(connection)
    await audit.record(
        ctx,
        "mpesa.connected",
        entity_type="mpesa_connection",
        entity_id=connection.id,
        changes={"environment": body.environment, "shortcode": body.business_shortcode},
    )
    return connection


async def register_c2b(
    ctx: TenantContext, settings: Settings, http: httpx.AsyncClient
) -> MpesaConnection:
    """Tell Safaricom where to send Paybill/Till confirmations for this shortcode."""
    connection = await _active(ctx.session)
    urls = _urls(settings, _token(connection, settings))
    try:
        await _client(connection, settings, http).register_c2b(
            confirmation_url=urls["c2b_confirmation_url"], validation_url=urls["c2b_validation_url"]
        )
    except DarajaError as exc:
        connection.last_error = exc.detail
        await ctx.session.flush()
        raise MpesaError(exc.detail) from None
    connection.c2b_registered_at, connection.last_error = datetime.now(UTC), None
    await ctx.session.flush()
    await ctx.session.refresh(connection)
    return connection


async def disable(ctx: TenantContext) -> MpesaConnection:
    connection = await _active(ctx.session)
    connection.status = "disabled"
    connection.updated_by = ctx.principal.user_id
    await audit.record(
        ctx, "mpesa.disabled", entity_type="mpesa_connection", entity_id=connection.id
    )
    await ctx.session.flush()
    await ctx.session.refresh(connection)
    return connection


async def _active(session: AsyncSession) -> MpesaConnection:
    connection = await get_connection(session)
    if connection is None or connection.status != "active":
        raise NotConnectedError()
    return connection


# ---------------------------------------------------------------- prompts (STK Push)


def _msisdn(phone: str) -> str:
    try:
        e164 = to_e164(phone)
    except InvalidPhoneError:
        raise MpesaError("Enter the M-Pesa number like 0712 345 678") from None
    if not e164.startswith("+254"):
        raise MpesaError("M-Pesa prompts go to Kenyan numbers only")
    return e164


def _prompt_out(request: MpesaRequest) -> PromptOut:
    return PromptOut(
        id=request.id,
        invoice_id=request.invoice_id,
        phone=request.phone,
        amount=request.amount.quantize(Decimal(1)),  # whole shillings
        status=request.status,
        result_desc=request.result_desc,
        receipt=request.receipt,
        payment_id=request.payment_id,
        created_at=request.created_at,
        completed_at=request.completed_at,
    )


async def _start(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    phone: str,
    source: str,
    actor: str | None,
) -> MpesaRequest:
    connection = await _active(session)
    due = await billing.payable(session, invoice_id)
    if due is None or due.balance <= 0:
        raise ConflictError("This invoice has nothing left to pay")
    if due.currency != "KES":
        raise MpesaError("M-Pesa takes Kenyan shillings only")
    amount = math.ceil(due.balance)  # whole shillings; any excess is kept as the client's credit
    msisdn = _msisdn(phone)
    request = MpesaRequest(
        tenant_id=tenant_id,
        connection_id=connection.id,
        invoice_id=invoice_id,
        phone=msisdn,
        amount=Decimal(amount),
        account_reference=due.payment_reference or (due.number or "")[-12:],
        source=source,
        requested_by=actor,
    )
    session.add(request)
    await session.flush()
    callback = _urls(settings, _token(connection, settings))["stk_callback_url"]
    try:
        accepted = await _client(connection, settings, http).stk_push(
            phone=msisdn.lstrip("+"),
            amount=amount,
            account_reference=request.account_reference,
            description=f"Inv {due.number or ''}",
            callback_url=callback,
        )
    except DarajaError as exc:
        request.status, request.result_desc, request.completed_at = (
            FAILED,
            exc.detail,
            datetime.now(UTC),
        )
        await session.flush()
        raise MpesaError(exc.detail) from None
    request.merchant_request_id = accepted.merchant_request_id
    request.checkout_request_id = accepted.checkout_request_id
    request.result_desc = accepted.customer_message
    await session.flush()
    await session.refresh(request)
    return request


async def prompt_from_app(
    ctx: TenantContext,
    invoice_id: uuid.UUID,
    phone: str | None,
    settings: Settings,
    http: httpx.AsyncClient,
) -> PromptOut:
    due = await billing.payable(ctx.session, invoice_id)
    if due is None:
        raise NotFoundError("Invoice not found or not issued")
    client = await clients.get_visible_client(ctx, due.client_id)
    number = phone or client.phone
    if not number:
        raise MpesaError("The client has no phone number: enter the M-Pesa number to prompt")
    request = await _start(
        ctx.session,
        settings,
        http,
        tenant_id=ctx.tenant_id,
        invoice_id=invoice_id,
        phone=number,
        source="app",
        actor=ctx.principal.user_id,
    )
    await audit.record(
        ctx,
        "mpesa.prompt_sent",
        entity_type="invoice",
        entity_id=invoice_id,
        changes={"amount": str(request.amount)},
    )
    return _prompt_out(request)


async def get_request(session: AsyncSession, request_id: uuid.UUID) -> MpesaRequest:
    request = await session.get(MpesaRequest, request_id)
    if request is None:
        raise NotFoundError("Payment prompt not found")
    return request


async def request_status(
    ctx: TenantContext, request_id: uuid.UUID, settings: Settings, http: httpx.AsyncClient
) -> PromptOut:
    request = await get_request(ctx.session, request_id)
    if request.invoice_id is not None:
        due = await billing.payable(ctx.session, request.invoice_id)
        if due is not None:
            await clients.get_visible_client(ctx, due.client_id)
    await _maybe_check(ctx.session, settings, http, request)
    return _prompt_out(request)


async def _maybe_check(
    session: AsyncSession, settings: Settings, http: httpx.AsyncClient, request: MpesaRequest
) -> None:
    """Ask M-Pesa when a pending prompt's callback is late (at most every few seconds)."""
    if request.status == PENDING and datetime.now(UTC) - request.created_at > RECHECK_AFTER:
        await check_request(session, settings, http, request.tenant_id, request.id)


# ---------------------------------------------------------------- completing payments


def _system_ctx(session: AsyncSession, tenant_id: uuid.UUID) -> TenantContext:
    """Acts for the tenant when M-Pesa tells us money arrived (no member is involved)."""
    principal = Principal(
        user_id="system:mpesa",
        email="",
        name="M-Pesa",
        tenant_id=tenant_id,
        org_id="",
        membership_id=uuid.UUID(int=0),
        role="system",
        permissions=frozenset(Perm),
        mfa_enrolled=True,
    )
    return TenantContext(session=session, principal=principal, request_id=None)


async def _record_payment(
    session: AsyncSession,
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    client_id: uuid.UUID,
    invoice_id: uuid.UUID | None,
    amount: Decimal,
    receipt: str,
    paid_on: datetime,
    notify: bool,
) -> uuid.UUID:
    ctx = _system_ctx(session, tenant_id)
    allocations: list[billing.PaymentAllocationIn] = []
    owner: str | None = None
    number = ""
    if invoice_id is not None:
        due = await billing.payable(session, invoice_id)
        if due is not None:
            owner, number = due.owner_user_id, due.number or ""
            if due.balance > 0:
                allocations = [
                    billing.PaymentAllocationIn(
                        invoice_id=invoice_id, amount=min(amount, due.balance)
                    )
                ]
    tenant = await tenancy.get_tenant(session, tenant_id)
    payment = await billing.record_payment(
        ctx,
        billing.PaymentCreate(
            client_id=client_id,
            amount=amount,
            received_on=paid_on.astimezone(ZoneInfo(tenant.timezone)).date(),
            method="mpesa",
            reference=receipt,
            allocations=allocations if invoice_id is not None else None,
        ),
    )
    if notify and owner:
        await notifications.notify(
            session,
            settings,
            tenant_id=tenant_id,
            user_ids=[owner],
            kind="payment.received",
            title=f"M-Pesa payment KES {amount:,.0f} received for {number}",
            body=f"Receipt {receipt}",
            link=f"/invoices/{invoice_id}",
        )
    return payment.id


async def _complete(
    session: AsyncSession,
    settings: Settings,
    request: MpesaRequest,
    *,
    receipt: str,
    amount: Decimal,
    paid_at: datetime,
    payer: str | None,
) -> None:
    """Record a confirmed prompt once (idempotent on the M-Pesa receipt)."""
    if request.status != PENDING:
        return
    inserted = await session.scalar(
        insert(MpesaTransaction)
        .values(
            tenant_id=request.tenant_id,
            connection_id=request.connection_id,
            receipt=receipt,
            source="stk",
            amount=amount,
            paid_at=paid_at,
            payer=payer,
            bill_reference=request.account_reference,
            status="matched",
            invoice_id=request.invoice_id,
            request_id=request.id,
        )
        .on_conflict_do_nothing()
        .returning(MpesaTransaction.id)
    )
    request.status, request.receipt, request.completed_at = PAID, receipt, datetime.now(UTC)
    if inserted is None:  # already recorded through another path (e.g. a replayed callback)
        await session.flush()
        return
    due = await billing.payable(session, request.invoice_id) if request.invoice_id else None
    client_id = due.client_id if due else None
    if client_id is None:
        await session.flush()
        return
    request.payment_id = await _record_payment(
        session,
        settings,
        tenant_id=request.tenant_id,
        client_id=client_id,
        invoice_id=request.invoice_id,
        amount=amount,
        receipt=receipt,
        paid_on=paid_at,
        notify=True,
    )
    transaction = await session.get(MpesaTransaction, inserted)
    if transaction is not None:
        transaction.payment_id = request.payment_id
    await session.flush()


def _close(request: MpesaRequest, code: int | None, desc: str) -> None:
    request.result_code, request.result_desc = code, desc
    request.status = {1032: CANCELLED, 1037: EXPIRED}.get(code or -1, FAILED)
    request.completed_at = datetime.now(UTC)


async def check_request(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> str:
    """Confirm a pending prompt with STK Query (job and on-demand). Idempotent."""
    request = await session.get(MpesaRequest, request_id, with_for_update=True)
    if request is None or request.status != PENDING or request.checkout_request_id is None:
        return request.status if request else "missing"
    connection = await session.get(MpesaConnection, request.connection_id)
    assert connection is not None  # noqa: S101 - composite FK
    try:
        result = await _client(connection, settings, http).stk_query(request.checkout_request_id)
    except DarajaError as exc:
        logger.warning("mpesa_query_failed", request_id=str(request.id), detail=exc.detail)
        result = None
    if result is not None and result.result_code == 0:
        receipt = request.receipt or (
            simulated_receipt()
            if connection.environment == "simulator"
            else f"STK{request.checkout_request_id[-9:]}"
        )
        await _complete(
            session,
            settings,
            request,
            receipt=receipt,
            amount=request.amount,
            paid_at=datetime.now(UTC),
            payer=None,
        )
    elif result is not None and result.result_code is not None:
        _close(request, result.result_code, result.result_desc)
    elif datetime.now(UTC) - request.created_at > PROMPT_TTL:
        _close(request, 1037, "No answer from the phone")
    await session.flush()
    return request.status


# ---------------------------------------------------------------- webhooks


async def resolve_callback(session: AsyncSession, token: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    row = (
        await session.execute(
            text("SELECT tenant_id, connection_id, status FROM app.resolve_mpesa_callback(:h)"),
            {"h": _hash(token)},
        )
    ).first()
    if row is None or row.status != "active":
        return None
    return row.tenant_id, row.connection_id


async def store_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
    kind: str,
    key: str,
    payload: dict[str, Any],
) -> bool:
    """Store a callback (duplicates are ignored) and queue it. Returns False for a duplicate."""
    event_id = await session.scalar(
        insert(WebhookEvent)
        .values(
            tenant_id=tenant_id,
            provider="mpesa",
            kind=kind,
            event_key=key,
            connection_id=connection_id,
            payload=payload,
        )
        .on_conflict_do_nothing()
        .returning(WebhookEvent.id)
    )
    if event_id is None:
        return False
    await events.enqueue(
        session,
        PROCESS_EVENT,
        {"tenant_id": str(tenant_id), "event_id": str(event_id)},
        queueing_lock=f"mpesa-event:{event_id}",
    )
    return True


def _items(callback: dict[str, Any]) -> dict[str, Any]:
    metadata = callback.get("CallbackMetadata") or {}
    return {
        str(i.get("Name")): i.get("Value") for i in metadata.get("Item", []) if isinstance(i, dict)
    }


def _paid_at(value: Any) -> datetime:
    try:
        return datetime.strptime(str(value), "%Y%m%d%H%M%S").replace(
            tzinfo=ZoneInfo("Africa/Nairobi")
        )
    except ValueError:
        return datetime.now(UTC)


async def _process_stk(
    session: AsyncSession, settings: Settings, http: httpx.AsyncClient, event: WebhookEvent
) -> None:
    callback = event.payload.get("Body", {}).get("stkCallback", {})
    request = await session.scalar(
        select(MpesaRequest)
        .where(MpesaRequest.checkout_request_id == str(callback.get("CheckoutRequestID")))
        .with_for_update()
    )
    if request is None or request.status != PENDING:
        return
    code = int(callback.get("ResultCode", -1))
    if code != 0:
        _close(request, code, str(callback.get("ResultDesc", "")))
        return
    items = _items(callback)
    receipt = str(items.get("MpesaReceiptNumber") or "")
    if receipt:
        request.receipt = receipt  # kept even if confirmation must wait for the next check
    paid = Decimal(str(items.get("Amount", "0")))
    if paid != request.amount:
        request.result_desc = (
            f"Callback amount {paid} differs from the prompt; confirming with M-Pesa"
        )
    await session.flush()
    # Trust, but verify: only STK Query decides that the prompt was paid.
    await check_request(session, settings, http, request.tenant_id, request.id)


async def _process_c2b(session: AsyncSession, settings: Settings, event: WebhookEvent) -> None:
    body = event.payload
    receipt = str(body.get("TransID") or "")
    if not receipt:
        return
    amount = Decimal(str(body.get("TransAmount", "0")))
    reference = str(body.get("BillRefNumber") or "").strip()
    invoice_id = await billing.find_by_payment_reference(session, reference) if reference else None
    payer = " ".join(
        str(body.get(k) or "") for k in ("FirstName", "MiddleName", "LastName")
    ).strip()
    inserted = await session.scalar(
        insert(MpesaTransaction)
        .values(
            tenant_id=event.tenant_id,
            connection_id=event.connection_id,
            receipt=receipt,
            source="c2b",
            amount=amount,
            paid_at=_paid_at(body.get("TransTime")),
            payer=payer or None,
            bill_reference=reference or None,
            status="matched" if invoice_id else "unmatched",
            invoice_id=invoice_id,
        )
        .on_conflict_do_nothing()
        .returning(MpesaTransaction.id)
    )
    if inserted is None:
        return
    transaction = await session.get(MpesaTransaction, inserted)
    assert transaction is not None  # noqa: S101 - just inserted
    if invoice_id is not None:
        due = await billing.payable(session, invoice_id)
        assert due is not None  # noqa: S101 - found as an issued invoice
        transaction.payment_id = await _record_payment(
            session,
            settings,
            tenant_id=event.tenant_id,
            client_id=due.client_id,
            invoice_id=invoice_id,
            amount=amount,
            receipt=receipt,
            paid_on=transaction.paid_at or datetime.now(UTC),
            notify=True,
        )
    else:
        members = [
            m.auth_user_id
            for m in await tenancy.list_members(session)
            if m.status == "active" and m.role in {"owner", "admin", "accounts"}
        ]
        await notifications.notify(
            session,
            settings,
            tenant_id=event.tenant_id,
            user_ids=members,
            kind="payment.unmatched",
            title=f"M-Pesa payment KES {amount:,.0f} needs matching",
            body=f"Receipt {receipt}, account '{reference or 'blank'}'",
            link="/payments?mpesa=unmatched",
        )
    await session.flush()


async def process_event(
    session: AsyncSession, settings: Settings, http: httpx.AsyncClient, event_id: uuid.UUID
) -> bool:
    """Act on one stored callback (job). Idempotent: a processed event is skipped."""
    event = await session.get(WebhookEvent, event_id, with_for_update=True)
    if event is None or event.processed_at is not None:
        return False
    event.attempts += 1
    if event.kind == "stk_callback":
        await _process_stk(session, settings, http, event)
    elif event.kind == "c2b_confirmation":
        await _process_c2b(session, settings, event)
    event.processed_at = datetime.now(UTC)
    await session.flush()
    return True


async def enqueue_checks(session: AsyncSession) -> int:
    rows = (
        await session.execute(
            text("SELECT tenant_id, request_id FROM app.mpesa_requests_to_check()")
        )
    ).all()
    for tenant_id, request_id in rows:
        await events.enqueue(
            session,
            CHECK_REQUEST,
            {"tenant_id": str(tenant_id), "request_id": str(request_id)},
            queueing_lock=f"mpesa-check:{request_id}",
        )
    return len(rows)


# ---------------------------------------------------------------- unmatched payments


def _txn_out(t: MpesaTransaction) -> TransactionOut:
    return TransactionOut(
        id=t.id,
        receipt=t.receipt,
        source=t.source,
        amount=t.amount.quantize(Decimal("0.01")),
        paid_at=t.paid_at,
        payer=t.payer,
        bill_reference=t.bill_reference,
        status=t.status,
        invoice_id=t.invoice_id,
        payment_id=t.payment_id,
        note=t.note,
        created_at=t.created_at,
    )


async def list_transactions(
    ctx: TenantContext, *, status: str | None, limit: int
) -> list[TransactionOut]:
    stmt = select(MpesaTransaction).order_by(MpesaTransaction.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(MpesaTransaction.status == status)
    return [_txn_out(t) for t in (await ctx.session.scalars(stmt)).all()]


async def _unmatched(ctx: TenantContext, transaction_id: uuid.UUID) -> MpesaTransaction:
    transaction = await ctx.session.get(MpesaTransaction, transaction_id, with_for_update=True)
    if transaction is None:
        raise NotFoundError("M-Pesa transaction not found")
    if transaction.status != "unmatched":
        raise ConflictError(f"This payment is already {transaction.status}")
    return transaction


async def match(
    ctx: TenantContext, transaction_id: uuid.UUID, body: MatchIn, settings: Settings
) -> TransactionOut:
    transaction = await _unmatched(ctx, transaction_id)
    await clients.get_visible_client(ctx, body.client_id)
    if body.invoice_id is not None:
        due = await billing.payable(ctx.session, body.invoice_id)
        if due is None or due.client_id != body.client_id:
            raise MpesaError("Choose an issued invoice of that client")
    transaction.payment_id = await _record_payment(
        ctx.session,
        settings,
        tenant_id=ctx.tenant_id,
        client_id=body.client_id,
        invoice_id=body.invoice_id,
        amount=transaction.amount,
        receipt=transaction.receipt,
        paid_on=transaction.paid_at or datetime.now(UTC),
        notify=False,
    )
    transaction.status, transaction.invoice_id = "matched", body.invoice_id
    transaction.resolved_by, transaction.resolved_at = ctx.principal.user_id, datetime.now(UTC)
    await audit.record(
        ctx,
        "mpesa.matched",
        entity_type="mpesa_transaction",
        entity_id=transaction.id,
        changes={"client_id": str(body.client_id), "invoice_id": str(body.invoice_id or "")},
    )
    await ctx.session.flush()
    return _txn_out(transaction)


async def ignore(ctx: TenantContext, transaction_id: uuid.UUID, body: IgnoreIn) -> TransactionOut:
    """Not a client payment (e.g. a transfer from the owner): kept for the record, never booked."""
    transaction = await _unmatched(ctx, transaction_id)
    transaction.status, transaction.note = "ignored", body.reason
    transaction.resolved_by, transaction.resolved_at = ctx.principal.user_id, datetime.now(UTC)
    await audit.record(
        ctx,
        "mpesa.ignored",
        entity_type="mpesa_transaction",
        entity_id=transaction.id,
        changes={"reason": body.reason},
    )
    await ctx.session.flush()
    return _txn_out(transaction)


# ---------------------------------------------------------------- paying from the invoice link


class _InvoicePayer:
    async def offer(
        self, *, session: AsyncSession, settings: Settings, link: links.PublicLink
    ) -> links.PaymentOffer | None:
        connection = await get_connection(session)
        if connection is None or connection.status != "active":
            return None
        if connection.environment == "simulator" and settings.is_production:
            return None
        due = await billing.payable(session, link.entity_id)
        if due is None or due.balance <= 0 or due.currency != "KES":
            return None
        return links.PaymentOffer(
            amount=str(math.ceil(due.balance)), currency="KES", methods=["mpesa"]
        )

    async def start(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        http: httpx.AsyncClient,
        link: links.PublicLink,
        phone: str,
    ) -> links.PaymentAttempt:
        request = await _start(
            session,
            settings,
            http,
            tenant_id=link.tenant_id,
            invoice_id=link.entity_id,
            phone=phone,
            source="link",
            actor=None,
        )
        return links.PaymentAttempt(
            attempt_id=request.id,
            status=request.status,
            message="Check your phone and enter your M-Pesa PIN",
        )

    async def status(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        http: httpx.AsyncClient,
        link: links.PublicLink,
        attempt_id: uuid.UUID,
    ) -> links.PaymentAttempt:
        request = await session.get(MpesaRequest, attempt_id)
        if request is None or request.invoice_id != link.entity_id:
            raise NotFoundError("Payment not found")
        await _maybe_check(session, settings, http, request)
        message = {
            PENDING: "Waiting for you to enter your M-Pesa PIN",
            PAID: f"Paid. M-Pesa receipt {request.receipt}"
            if request.receipt
            else "Paid. Thank you",
            CANCELLED: "You cancelled the M-Pesa prompt",
            EXPIRED: "The prompt timed out. Try again",
        }.get(request.status, request.result_desc or "The payment did not go through")
        return links.PaymentAttempt(attempt_id=request.id, status=request.status, message=message)


links.register_payer("invoice", _InvoicePayer())
