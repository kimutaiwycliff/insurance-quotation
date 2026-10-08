"""Leads service: the sales pipeline (new → contacted → quoted → won/lost).

Scoping as for clients: ``lead:read:all`` sees every lead; otherwise only leads you own. Winning a lead
converts it into a client (or links an existing one).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select

from app.core.concurrency import check_version
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.core.money import Money, MoneyModel
from app.core.permissions import Perm
from app.modules.clients import service as clients
from app.modules.clients.service import ClientCreate
from app.modules.leads.models import Lead
from app.modules.leads.schemas import (
    STAGES,
    ConvertLead,
    LeadCreate,
    LeadOut,
    LeadUpdate,
    Pipeline,
    StageSummary,
)
from app.modules.notifications import service as notifications
from app.modules.tenancy import service as tenancy
from app.platform import audit
from app.platform.deps import TenantContext, own_scope

__all__ = ["Pipeline", "mark_quoted", "pipeline"]

OPEN_STAGES = ("new", "contacted", "quoted")


def _scoped[*Ts](stmt: Select[*Ts], ctx: TenantContext) -> Select[*Ts]:
    owner = own_scope(ctx.principal, Perm.LEAD_READ_ALL)
    return stmt if owner is None else stmt.where(Lead.owner_user_id == owner)


def to_out(lead: Lead) -> LeadOut:
    premium = (
        MoneyModel(amount=lead.estimated_premium, currency=lead.currency)
        if lead.estimated_premium is not None
        else None
    )
    data = {c: getattr(lead, c) for c in LeadOut.model_fields if c != "estimated_premium"}
    return LeadOut(**data, estimated_premium=premium)


async def get_lead(ctx: TenantContext, lead_id: uuid.UUID) -> Lead:
    lead = (await ctx.session.scalars(_scoped(select(Lead).where(Lead.id == lead_id), ctx))).first()
    if lead is None:
        raise NotFoundError("Lead not found")
    return lead


async def _check_owner(ctx: TenantContext, owner: str) -> None:
    if owner == ctx.principal.user_id:
        return
    if Perm.LEAD_READ_ALL not in ctx.principal.permissions:
        raise PermissionDeniedError("You can only assign leads to yourself")
    active = {
        m.auth_user_id for m in await tenancy.list_members(ctx.session) if m.status == "active"
    }
    if owner not in active:
        raise NotFoundError("That person is not an active member of the agency")


async def _notify_assignee(ctx: TenantContext, settings: Settings, lead: Lead) -> None:
    if lead.owner_user_id != ctx.principal.user_id:
        await notifications.notify(
            ctx.session,
            settings,
            tenant_id=ctx.tenant_id,
            user_ids=[lead.owner_user_id],
            kind="lead.assigned",
            title=f"New lead: {lead.name}",
            body=lead.notes or "",
            link=f"/leads?focus={lead.id}",
        )


def _premium(data: dict[str, Any]) -> None:
    if "estimated_premium" in data:
        value = data.pop("estimated_premium")
        data["estimated_premium"] = (
            Money.of(value["amount"], value["currency"]).amount if value else None
        )
        if value:
            data["currency"] = value["currency"]


async def create_lead(ctx: TenantContext, body: LeadCreate, settings: Settings) -> Lead:
    data = body.model_dump(exclude_unset=True)
    owner = data.pop("owner_user_id", None) or ctx.principal.user_id
    await _check_owner(ctx, owner)
    _premium(data)
    if data.get("email"):
        data["email"] = str(data["email"])
    lead = Lead(
        tenant_id=ctx.tenant_id,
        owner_user_id=owner,
        stage_changed_at=datetime.now(UTC),
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
        **data,
    )
    ctx.session.add(lead)
    await ctx.session.flush()
    await ctx.session.refresh(lead)
    await audit.record(
        ctx, "lead.created", entity_type="lead", entity_id=lead.id, changes={"owner_user_id": owner}
    )
    await _notify_assignee(ctx, settings, lead)
    return lead


async def update_lead(
    ctx: TenantContext,
    lead_id: uuid.UUID,
    body: LeadUpdate,
    if_match: str | None,
    settings: Settings,
) -> Lead:
    lead = await get_lead(ctx, lead_id)
    check_version(if_match, lead.version)
    data = body.model_dump(exclude_unset=True)
    stage = data.get("stage")
    if stage == "won" and lead.client_id is None:
        raise AppError("Convert the lead to a client to mark it won")
    if stage == "lost" and not (data.get("lost_reason") or lead.lost_reason):
        raise AppError("Say why the lead was lost, so you can learn from it")
    reassigned = "owner_user_id" in data and data["owner_user_id"] != lead.owner_user_id
    if reassigned:
        await _check_owner(ctx, data["owner_user_id"])
    _premium(data)
    if data.get("email"):
        data["email"] = str(data["email"])
    before = {"stage": lead.stage, "owner_user_id": lead.owner_user_id}
    if stage and stage != lead.stage:
        lead.stage_changed_at = datetime.now(UTC)
    for field, value in data.items():
        setattr(lead, field, value)
    lead.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(lead)
    after = {"stage": lead.stage, "owner_user_id": lead.owner_user_id}
    if before != after:
        await audit.record(
            ctx,
            "lead.updated",
            entity_type="lead",
            entity_id=lead.id,
            changes=audit.diff(before, after),
        )
    if reassigned:
        await _notify_assignee(ctx, settings, lead)
    return lead


async def convert(
    ctx: TenantContext, lead_id: uuid.UUID, body: ConvertLead, settings: Settings
) -> tuple[Lead, uuid.UUID]:
    lead = await get_lead(ctx, lead_id)
    if lead.client_id is not None:
        return lead, lead.client_id  # idempotent
    if body.client_id is not None:
        client_id = (await clients.get_visible_client(ctx, body.client_id)).id
    else:
        first, _, last = lead.name.partition(" ")
        client = await clients.create_client(
            ctx,
            ClientCreate(
                kind=body.kind,
                first_name=body.first_name or (first if body.kind == "individual" else None),
                last_name=body.last_name
                or (last.strip() or None if body.kind == "individual" else None),
                company_name=body.company_name or (lead.name if body.kind == "corporate" else None),
                phone=lead.phone,
                email=lead.email,
                source="lead",
                owner_user_id=lead.owner_user_id,
                notes=lead.notes,
                allow_duplicate=body.allow_duplicate,
            ),
            settings,
        )
        client_id = client.id
    lead.client_id = client_id
    lead.stage = "won"
    lead.stage_changed_at = datetime.now(UTC)
    lead.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(lead)
    await audit.record(
        ctx,
        "lead.converted",
        entity_type="lead",
        entity_id=lead.id,
        changes={"client_id": str(client_id)},
    )
    return lead, client_id


async def list_leads(
    ctx: TenantContext,
    *,
    stage: str | None,
    owner: str | None,
    follow_up_due: bool,
    q: str | None,
    limit: int,
) -> list[Lead]:
    stmt = _scoped(select(Lead), ctx)
    if stage:
        stmt = stmt.where(Lead.stage == stage)
    if owner:
        stmt = stmt.where(Lead.owner_user_id == owner)
    if follow_up_due:
        stmt = stmt.where(Lead.next_follow_up_at <= func.now(), Lead.stage.in_(OPEN_STAGES))
    if q:
        stmt = stmt.where(Lead.name.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(Lead.next_follow_up_at.asc().nulls_last(), Lead.id.desc()).limit(limit)
    return list((await ctx.session.scalars(stmt)).all())


async def pipeline(ctx: TenantContext, currency: str) -> Pipeline:
    rows = (
        await ctx.session.execute(
            _scoped(
                select(Lead.stage, func.count(), func.coalesce(func.sum(Lead.estimated_premium), 0))
                .where(Lead.currency == currency)
                .group_by(Lead.stage),
                ctx,
            )
        )
    ).all()
    other = (
        await ctx.session.execute(
            _scoped(
                select(Lead.stage, func.count())
                .where(Lead.currency != currency)
                .group_by(Lead.stage),
                ctx,
            )
        )
    ).all()
    counts = {stage: (count, Decimal(total or 0)) for stage, count, total in rows}
    for stage, count in other:  # leads priced in other currencies still count, without a total
        c, total = counts.get(stage, (0, Decimal(0)))
        counts[stage] = (c + count, total)
    due = await ctx.session.scalar(
        _scoped(
            select(func.count())
            .select_from(Lead)
            .where(Lead.next_follow_up_at <= func.now(), Lead.stage.in_(OPEN_STAGES)),
            ctx,
        )
    )
    return Pipeline(
        stages=[
            StageSummary(
                stage=s,
                count=counts.get(s, (0, Decimal(0)))[0],
                estimated_premium=Money.of(counts.get(s, (0, Decimal(0)))[1], currency)
                .rounded()
                .to_json(),
            )
            for s in STAGES
        ],
        follow_ups_due=int(due or 0),
    )


async def mark_quoted(ctx: TenantContext, client_id: uuid.UUID) -> None:
    """A quote was sent to this client: open leads linked to them move to "quoted"."""
    rows = (
        await ctx.session.scalars(
            select(Lead).where(Lead.client_id == client_id, Lead.stage.in_(("new", "contacted")))
        )
    ).all()
    for lead in rows:
        lead.stage, lead.stage_changed_at = "quoted", datetime.now(UTC)
