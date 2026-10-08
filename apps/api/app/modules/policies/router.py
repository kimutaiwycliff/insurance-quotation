"""Policy book and renewal board endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from app.core.concurrency import etag
from app.core.permissions import Perm
from app.modules.policies import service
from app.modules.policies.schemas import (
    Activate,
    Cancel,
    CommissionIn,
    FromQuote,
    PaymentIn,
    PolicyCreate,
    PolicyOut,
    PolicySummary,
    PolicyUpdate,
    Remind,
    Reminded,
    Remitted,
    RenewalBoard,
    RenewalQuote,
    RenewalUpdate,
    VoidPayment,
)
from app.modules.quotes import service as quotes
from app.modules.quotes.service import QuoteOut
from app.platform.deps import TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(tags=["policies"])
_write = require_permission(Perm.CLIENT_WRITE)
_premium = require_permission(Perm.PREMIUM_WRITE)
Read = Annotated[
    TenantContext, Depends(require_permission((Perm.CLIENT_READ_OWN, Perm.CLIENT_READ_ALL)))
]
Write = Annotated[TenantContext, Depends(_write)]
Premium = Annotated[TenantContext, Depends(_premium)]


async def _out(ctx: TenantContext, policy: service.Policy, response: Response) -> PolicyOut:
    response.headers["ETag"] = etag(policy.version)
    return await service.to_out(ctx, policy)


@router.get("/policies", operation_id="policies_list")
async def list_policies(
    ctx: Read,
    client_id: uuid.UUID | None = None,
    status: Annotated[str | None, Query(pattern="^(pending|active|expired|cancelled)$")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    expiring_within: Annotated[int | None, Query(ge=0, le=365)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[PolicySummary]:
    return await service.list_policies(
        ctx, client_id=client_id, status=status, q=q, expiring_within=expiring_within, limit=limit
    )


@router.post("/policies", operation_id="policies_create", status_code=201, response_model=PolicyOut)
async def create_policy(
    ctx: Write,
    body: PolicyCreate,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_write))],
) -> Response:
    """Enter a policy written outside a quote (e.g. an existing client's cover)."""
    if (replay := await idem.replay()) is not None:
        return replay
    policy = await service.create_policy(ctx, body)
    return await idem.respond(
        201, await service.to_out(ctx, policy), {"ETag": etag(policy.version)}
    )


@router.post(
    "/policies/from-quote",
    operation_id="policies_from_quote",
    status_code=201,
    response_model=PolicyOut,
)
async def from_quote(
    ctx: Write,
    body: FromQuote,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_write))],
) -> Response:
    """Turn the option the client accepted into a policy (pending until the insurer confirms cover)."""
    if (replay := await idem.replay()) is not None:
        return replay
    policy = await service.create_from_quote(ctx, body)
    return await idem.respond(
        201, await service.to_out(ctx, policy), {"ETag": etag(policy.version)}
    )


@router.get("/policies/{policy_id}", operation_id="policies_get")
async def get_policy(ctx: Read, policy_id: uuid.UUID, response: Response) -> PolicyOut:
    return await _out(ctx, await service.get_policy(ctx, policy_id), response)


@router.patch("/policies/{policy_id}", operation_id="policies_update")
async def update_policy(
    ctx: Write,
    policy_id: uuid.UUID,
    body: PolicyUpdate,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> PolicyOut:
    return await _out(ctx, await service.update_policy(ctx, policy_id, body, if_match), response)


@router.post("/policies/{policy_id}/activate", operation_id="policies_activate")
async def activate(
    ctx: Write, policy_id: uuid.UUID, body: Activate, response: Response
) -> PolicyOut:
    """No premium, no cover: needs the insurer's confirmation and full payment (or a pack exception)."""
    return await _out(ctx, await service.activate(ctx, policy_id, body), response)


@router.post("/policies/{policy_id}/cancel", operation_id="policies_cancel")
async def cancel(ctx: Write, policy_id: uuid.UUID, body: Cancel, response: Response) -> PolicyOut:
    return await _out(ctx, await service.cancel(ctx, policy_id, body), response)


@router.post("/policies/{policy_id}/payments", operation_id="policies_record_payment")
async def record_payment(
    ctx: Premium, policy_id: uuid.UUID, body: PaymentIn, response: Response
) -> PolicyOut:
    """Record a premium payment (to the insurer, or to the agency when it is authorised to collect)."""
    return await _out(ctx, await service.record_payment(ctx, policy_id, body), response)


@router.post(
    "/policies/{policy_id}/payments/{payment_id}/void", operation_id="policies_void_payment"
)
async def void_payment(
    ctx: Premium, policy_id: uuid.UUID, payment_id: uuid.UUID, body: VoidPayment, response: Response
) -> PolicyOut:
    return await _out(ctx, await service.void_payment(ctx, policy_id, payment_id, body), response)


@router.post(
    "/policies/{policy_id}/payments/{payment_id}/remitted", operation_id="policies_mark_remitted"
)
async def mark_remitted(
    ctx: Premium, policy_id: uuid.UUID, payment_id: uuid.UUID, body: Remitted, response: Response
) -> PolicyOut:
    return await _out(ctx, await service.mark_remitted(ctx, policy_id, payment_id, body), response)


@router.get("/renewals", operation_id="renewals_board")
async def renewal_board(
    ctx: Read,
    window_days: Annotated[int, Query(ge=7, le=120)] = 60,
    owner: Annotated[str | None, Query(max_length=255)] = None,
) -> RenewalBoard:
    """Active policies expiring within the window (and up to 30 days past), by renewal stage."""
    return await service.renewal_board(ctx, window_days=window_days, owner=owner)


@router.post("/policies/{policy_id}/renewal", operation_id="policies_renewal_stage")
async def renewal_stage(
    ctx: Write, policy_id: uuid.UUID, body: RenewalUpdate, response: Response
) -> PolicyOut:
    return await _out(ctx, await service.update_renewal(ctx, policy_id, body), response)


@router.post("/policies/{policy_id}/remind", operation_id="policies_remind")
async def remind(ctx: Write, policy_id: uuid.UUID, body: Remind) -> Reminded:
    """Remind the client now: email it, or get a WhatsApp link to open. Logged on the client's timeline."""
    policy, whatsapp, emailed = await service.remind(ctx, policy_id, body)
    return Reminded(
        policy=await service.to_out(ctx, policy), whatsapp_url=whatsapp, emailed_to=emailed
    )


@router.post(
    "/policies/{policy_id}/renewal-quote",
    operation_id="policies_renewal_quote",
    status_code=201,
)
async def renewal_quote(ctx: Write, policy_id: uuid.UUID, body: RenewalQuote) -> QuoteOut:
    """Start a renewal quote for the same client and risk; the policy moves to "quoted"."""
    return await quotes.to_out(ctx, await service.renewal_quote(ctx, policy_id, body))


@router.put("/policies/{policy_id}/commission", operation_id="policies_set_commission")
async def set_commission(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.COMMISSION_MANAGE))],
    policy_id: uuid.UUID,
    body: CommissionIn,
    response: Response,
) -> PolicyOut:
    """Set the commission expected on a policy (rate on the premium before levies)."""
    return await _out(ctx, await service.set_commission(ctx, policy_id, body), response)
