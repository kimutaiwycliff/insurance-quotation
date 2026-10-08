"""Commission endpoints: statement (expected vs received), receipts from insurers, yearly summary."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.permissions import Perm
from app.modules.commissions import service
from app.modules.commissions.schemas import (
    ReceiptCreate,
    ReceiptOut,
    Statement,
    Summary,
    VoidReceipt,
)
from app.platform.deps import TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(tags=["commissions"])
_manage = require_permission(Perm.COMMISSION_MANAGE)
Read = Annotated[
    TenantContext,
    Depends(require_permission((Perm.COMMISSION_READ_OWN, Perm.COMMISSION_READ_ALL))),
]
ReadAll = Annotated[TenantContext, Depends(require_permission(Perm.COMMISSION_READ_ALL))]
Manage = Annotated[TenantContext, Depends(_manage)]


@router.get("/commissions/statement", operation_id="commissions_statement")
async def statement(
    ctx: Read,
    insurer: Annotated[str | None, Query(max_length=120)] = None,
    policy_id: uuid.UUID | None = None,
    outstanding: bool = False,
) -> Statement:
    """Expected vs received commission per policy (yours only, unless you see the agency's)."""
    return await service.statement(
        ctx, insurer=insurer, policy_id=policy_id, outstanding_only=outstanding
    )


@router.get("/commissions/summary", operation_id="commissions_summary")
async def summary(
    ctx: Read, year: Annotated[int | None, Query(ge=2000, le=2100)] = None
) -> Summary:
    """Expected, received and outstanding commission and WHT for a year, by month and insurer."""
    return await service.summary(ctx, year or datetime.now(UTC).year)


@router.get("/commission-receipts", operation_id="commission_receipts_list")
async def list_receipts(
    ctx: ReadAll,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ReceiptOut]:
    return await service.list_receipts(ctx, year=year, limit=limit)


@router.post(
    "/commission-receipts",
    operation_id="commission_receipts_create",
    status_code=201,
    response_model=ReceiptOut,
)
async def record_receipt(
    ctx: Manage,
    body: ReceiptCreate,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_manage))],
) -> Response:
    """Record commission an insurer paid, split across the policies it covers."""
    if (replay := await idem.replay()) is not None:
        return replay
    return await idem.respond(201, await service.record_receipt(ctx, body))


@router.post("/commission-receipts/{receipt_id}/void", operation_id="commission_receipts_void")
async def void_receipt(ctx: Manage, receipt_id: uuid.UUID, body: VoidReceipt) -> ReceiptOut:
    return await service.void_receipt(ctx, receipt_id, body)
