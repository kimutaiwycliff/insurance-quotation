"""M-Pesa endpoints: the tenant's connection, payment prompts, unmatched payments, and Safaricom callbacks."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse

from app.core.db import set_tenant_context
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import Perm
from app.modules.mpesa import service
from app.modules.mpesa.schemas import (
    ConnectionIn,
    ConnectionOut,
    IgnoreIn,
    MatchIn,
    PromptIn,
    PromptOut,
    TransactionOut,
)
from app.platform.deps import ResourcesDep, TenantContext, require_permission

router = APIRouter(tags=["mpesa"])
Settings_ = Annotated[TenantContext, Depends(require_permission(Perm.ORG_UPDATE))]
ReadSettings = Annotated[TenantContext, Depends(require_permission(Perm.ORG_READ))]
Pay = Annotated[TenantContext, Depends(require_permission(Perm.PAYMENT_WRITE))]
Read = Annotated[
    TenantContext, Depends(require_permission((Perm.CLIENT_READ_OWN, Perm.CLIENT_READ_ALL)))
]


@router.get("/mpesa/connection", operation_id="mpesa_connection_get")
async def get_connection(ctx: ReadSettings, resources: ResourcesDep) -> ConnectionOut | None:
    """The agency's M-Pesa Paybill or Till (keys are never returned), or null when not connected."""
    connection = await service.get_connection(ctx.session)
    return service.connection_out(connection, resources.settings) if connection else None


@router.put("/mpesa/connection", operation_id="mpesa_connection_save")
async def save_connection(
    ctx: Settings_, body: ConnectionIn, resources: ResourcesDep
) -> ConnectionOut:
    """Connect (or reconnect) the agency's own shortcode. The keys are checked with Safaricom first."""
    connection = await service.save_connection(ctx, body, resources.settings, resources.http)
    return service.connection_out(connection, resources.settings)


@router.post("/mpesa/connection/register-c2b", operation_id="mpesa_connection_register_c2b")
async def register_c2b(ctx: Settings_, resources: ResourcesDep) -> ConnectionOut:
    """Ask Safaricom to send Paybill/Till payments made by hand to us (C2B confirmation)."""
    connection = await service.register_c2b(ctx, resources.settings, resources.http)
    return service.connection_out(connection, resources.settings)


@router.post("/mpesa/connection/disable", operation_id="mpesa_connection_disable")
async def disable(ctx: Settings_, resources: ResourcesDep) -> ConnectionOut:
    return service.connection_out(await service.disable(ctx), resources.settings)


@router.post(
    "/invoices/{invoice_id}/mpesa-prompt", operation_id="invoices_mpesa_prompt", status_code=201
)
async def prompt(
    ctx: Pay, invoice_id: uuid.UUID, body: PromptIn, resources: ResourcesDep
) -> PromptOut:
    """Send an M-Pesa payment prompt for the invoice's balance to the client's phone."""
    return await service.prompt_from_app(
        ctx, invoice_id, body.phone, resources.settings, resources.http
    )


@router.get("/mpesa/prompts/{request_id}", operation_id="mpesa_prompt_get")
async def prompt_status(ctx: Read, request_id: uuid.UUID, resources: ResourcesDep) -> PromptOut:
    return await service.request_status(ctx, request_id, resources.settings, resources.http)


@router.get("/mpesa/transactions", operation_id="mpesa_transactions_list")
async def transactions(
    ctx: Pay,
    status: Annotated[str | None, Query(pattern="^(matched|unmatched|ignored)$")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[TransactionOut]:
    """Money received on the shortcode; `unmatched` is the queue of payments to assign."""
    return await service.list_transactions(ctx, status=status, limit=limit)


@router.post("/mpesa/transactions/{transaction_id}/match", operation_id="mpesa_transactions_match")
async def match(
    ctx: Pay, transaction_id: uuid.UUID, body: MatchIn, resources: ResourcesDep
) -> TransactionOut:
    return await service.match(ctx, transaction_id, body, resources.settings)


@router.post(
    "/mpesa/transactions/{transaction_id}/ignore", operation_id="mpesa_transactions_ignore"
)
async def ignore(ctx: Pay, transaction_id: uuid.UUID, body: IgnoreIn) -> TransactionOut:
    return await service.ignore(ctx, transaction_id, body)


# ---------------------------------------------------------------- Safaricom callbacks (anonymous)

webhook_router = APIRouter(prefix="/webhooks/mpesa", tags=["webhooks"], include_in_schema=False)
CallbackToken = Annotated[str, Path(min_length=20, max_length=100)]
_ACCEPTED = {"ResultCode": 0, "ResultDesc": "Accepted"}


def _check_ip(request: Request, allowed: str) -> None:
    ips = {ip.strip() for ip in allowed.split(",") if ip.strip()}
    client = request.client.host if request.client else ""
    if ips and client not in ips:
        raise PermissionDeniedError("Callback from an address that is not allowed")


async def _receive(
    request: Request,
    resources: ResourcesDep,
    token: str,
    kind: str,
    key: str,
    payload: dict[str, Any],
) -> JSONResponse:
    _check_ip(request, resources.settings.mpesa_callback_allowed_ips)
    async with resources.session_factory() as session, session.begin():
        resolved = await service.resolve_callback(session, token)
        if resolved is None:
            raise NotFoundError("Unknown callback")
        tenant_id, connection_id = resolved
        await set_tenant_context(session, tenant_id)
        if key:
            await service.store_event(
                session,
                tenant_id=tenant_id,
                connection_id=connection_id,
                kind=kind,
                key=key,
                payload=payload,
            )
    return JSONResponse(_ACCEPTED)


@webhook_router.post("/{token}/stk")
async def stk_callback(
    token: CallbackToken, payload: dict[str, Any], request: Request, resources: ResourcesDep
) -> JSONResponse:
    callback = payload.get("Body", {}).get("stkCallback", {})
    key = str(callback.get("CheckoutRequestID") or "")
    return await _receive(request, resources, token, "stk_callback", key, payload)


@webhook_router.post("/{token}/c2b/confirmation")
async def c2b_confirmation(
    token: CallbackToken, payload: dict[str, Any], request: Request, resources: ResourcesDep
) -> JSONResponse:
    return await _receive(
        request, resources, token, "c2b_confirmation", str(payload.get("TransID") or ""), payload
    )


@webhook_router.post("/{token}/c2b/validation")
async def c2b_validation(
    token: CallbackToken, request: Request, resources: ResourcesDep
) -> JSONResponse:
    """Accept every payment; matching happens on confirmation (a refused payment helps nobody)."""
    _check_ip(request, resources.settings.mpesa_callback_allowed_ips)
    async with resources.session_factory() as session, session.begin():
        if await service.resolve_callback(session, token) is None:
            raise NotFoundError("Unknown callback")
    return JSONResponse(_ACCEPTED)
