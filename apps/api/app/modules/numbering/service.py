"""Numbering service: default schemes, gapless allocation and scheme management (ADR-0010).

Allocation increments ``number_sequences`` with ``INSERT ... ON CONFLICT DO UPDATE`` inside the caller's
(issuing) transaction. The row lock serialises concurrent issuers of the same scheme and period; if the issuing
transaction rolls back, so does the increment, so numbers have no gaps. Numbers are allocated at **issue**
time, never for drafts.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import check_version
from app.core.errors import ConflictError, NotFoundError
from app.modules.numbering.models import NumberingScheme, NumberSequence
from app.modules.numbering.pattern import Pattern, ResetPeriod, period_key
from app.modules.numbering.references import generate_payment_reference
from app.modules.numbering.schemas import SchemeCreate, SchemeUpdate
from app.platform import audit
from app.platform.deps import TenantContext

__all__ = ["AllocatedNumber", "allocate_number", "generate_payment_reference"]

# Seeded for every new tenant. Generic, not jurisdictional: KRA eTIMS assigns its own control numbers.
DEFAULT_SCHEMES: dict[str, str] = {
    "quote": "QT-{YYYY}-{SEQ:5}",
    "invoice": "INV-{YYYY}-{SEQ:5}",
    "receipt": "RCT-{YYYY}-{SEQ:5}",
    "credit_note": "CN-{YYYY}-{SEQ:5}",
}


class NoNumberingSchemeError(NotFoundError):
    code = "numbering_scheme_missing"
    title = "No active numbering scheme for this document type"


@dataclass(frozen=True, slots=True)
class AllocatedNumber:
    number: str
    sequence: int
    scheme_id: uuid.UUID
    period_key: str


async def seed_default_schemes(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(
        insert(NumberingScheme)
        .values(
            [
                {"tenant_id": tenant_id, "document_type": doc_type, "pattern": pattern}
                for doc_type, pattern in DEFAULT_SCHEMES.items()
            ]
        )
        .on_conflict_do_nothing()
    )


async def _scheme_for(
    session: AsyncSession, document_type: str, branch_id: uuid.UUID | None
) -> NumberingScheme:
    """The branch's own scheme if it has one, else the tenant-wide scheme."""
    stmt = select(NumberingScheme).where(
        NumberingScheme.document_type == document_type, NumberingScheme.is_active.is_(True)
    )
    if branch_id is None:
        stmt = stmt.where(NumberingScheme.branch_id.is_(None))
    else:
        stmt = stmt.where(
            (NumberingScheme.branch_id == branch_id) | NumberingScheme.branch_id.is_(None)
        ).order_by(NumberingScheme.branch_id.is_(None))
    scheme = (await session.scalars(stmt.limit(1))).first()
    if scheme is None:
        raise NoNumberingSchemeError(f"No numbering scheme for '{document_type}'")
    return scheme


async def allocate_number(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document_type: str,
    *,
    on: date,
    branch_id: uuid.UUID | None = None,
    branch_code: str | None = None,
) -> AllocatedNumber:
    """Allocate the next number. Call inside the transaction that issues the document.

    ``on`` is the issue date **in the tenant's timezone** (it selects the period and the {YYYY}/{MM} tokens).
    """
    scheme = await _scheme_for(session, document_type, branch_id)
    pattern = Pattern.parse(scheme.pattern)
    key = period_key(ResetPeriod(scheme.reset_period), on)
    stmt = (
        insert(NumberSequence)
        .values(
            tenant_id=tenant_id, scheme_id=scheme.id, period_key=key, last_value=scheme.start_at
        )
        .on_conflict_do_update(
            index_elements=[
                NumberSequence.tenant_id,
                NumberSequence.scheme_id,
                NumberSequence.period_key,
            ],
            set_={"last_value": NumberSequence.last_value + 1},
        )
        .returning(NumberSequence.last_value)
    )
    seq = int((await session.execute(stmt)).scalar_one())
    return AllocatedNumber(
        number=pattern.format(seq=seq, on=on, branch_code=branch_code),
        sequence=seq,
        scheme_id=scheme.id,
        period_key=key,
    )


async def list_schemes(session: AsyncSession) -> list[NumberingScheme]:
    stmt = select(NumberingScheme).order_by(
        NumberingScheme.document_type, NumberingScheme.branch_id.nulls_first()
    )
    return list((await session.scalars(stmt)).all())


async def create_scheme(ctx: TenantContext, data: SchemeCreate) -> NumberingScheme:
    exists = await ctx.session.scalar(
        select(NumberingScheme.id).where(
            NumberingScheme.document_type == data.document_type,
            NumberingScheme.branch_id.is_(None)
            if data.branch_id is None
            else NumberingScheme.branch_id == data.branch_id,
        )
    )
    if exists is not None:
        raise ConflictError("A scheme for this document type and branch already exists")
    scheme = NumberingScheme(
        tenant_id=ctx.tenant_id,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
        **data.model_dump(mode="python"),
    )
    ctx.session.add(scheme)
    try:
        async with ctx.session.begin_nested():
            await ctx.session.flush()
    except IntegrityError:
        # The composite FK (tenant_id, branch_id) rejects unknown and other tenants' branches alike.
        raise NotFoundError("Branch not found") from None
    await ctx.session.refresh(scheme)
    await audit.record(
        ctx,
        "numbering_scheme.created",
        entity_type="numbering_scheme",
        entity_id=scheme.id,
        changes=audit.diff({}, data.model_dump(mode="json")),
    )
    return scheme


async def update_scheme(
    ctx: TenantContext, scheme_id: uuid.UUID, changes: SchemeUpdate, if_match: str | None
) -> NumberingScheme:
    scheme = await ctx.session.get(NumberingScheme, scheme_id)
    if scheme is None:
        raise NotFoundError("Numbering scheme not found")
    check_version(if_match, scheme.version)
    data = changes.model_dump(exclude_unset=True, exclude_none=True, mode="json")
    before = {f: getattr(scheme, f) for f in data}
    for field, value in data.items():
        setattr(scheme, field, value)
    scheme.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(scheme)
    await audit.record(
        ctx,
        "numbering_scheme.updated",
        entity_type="numbering_scheme",
        entity_id=scheme.id,
        changes=audit.diff(before, {f: getattr(scheme, f) for f in data}),
    )
    return scheme


def preview(pattern: str, on: date, branch_code: str | None) -> list[str]:
    parsed = Pattern.parse(pattern)
    return [parsed.format(seq=n, on=on, branch_code=branch_code or "HQ") for n in (1, 2, 3)]
