"""Tenancy service: provisioning, principal resolution, organization settings, members and branches.

All functions run inside a transaction whose RLS tenant context is already set to the tenant concerned.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import CursorResult, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import check_version
from app.core.errors import ConflictError, MembershipInactiveError, NotFoundError
from app.core.permissions import normalise_role, permissions_for
from app.core.security import AccessClaims
from app.modules.numbering import service as numbering
from app.modules.tenancy.models import Branch, Membership, Tenant
from app.modules.tenancy.schemas import (
    BranchCreate,
    BranchUpdate,
    InternalUser,
    OrganizationUpdate,
)
from app.platform import audit
from app.platform.deps import Principal, TenantContext

logger = structlog.get_logger(__name__)

ACTIVE = "active"
REMOVED = "removed"


# ---------------------------------------------------------------- provisioning


async def provision_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    org_id: str,
    name: str,
    slug: str | None,
    via: str,
) -> bool:
    """Create the tenant and its defaults if missing. Idempotent and safe under concurrency."""
    created = await session.execute(
        insert(Tenant)
        .values(
            id=tenant_id,
            auth_org_id=org_id,
            name=name or "My agency",
            slug=slug,
            provisioned_via=via,
        )
        # No conflict target: a concurrent first request may collide on id or on auth_org_id.
        .on_conflict_do_nothing()
        .returning(Tenant.id)
    )
    if created.scalar_one_or_none() is None:
        return False
    await numbering.seed_default_schemes(session, tenant_id)
    logger.info("tenant_provisioned", tenant_id=str(tenant_id), via=via)
    return True


async def upsert_membership(
    session: AsyncSession, tenant_id: uuid.UUID, user: InternalUser, role: str
) -> Membership:
    """Create or update a member from the auth service (re-activates a removed member)."""
    stmt = (
        insert(Membership)
        .values(
            tenant_id=tenant_id,
            auth_user_id=user.user_id,
            email=str(user.email),
            name=user.name,
            role=normalise_role(role),
            status=ACTIVE,
        )
        .on_conflict_do_update(
            index_elements=[Membership.tenant_id, Membership.auth_user_id],
            set_={
                "email": str(user.email),
                "name": user.name,
                "role": normalise_role(role),
                "status": ACTIVE,
                "removed_at": None,
                "version": Membership.version + 1,
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(Membership)
    )
    return (await session.execute(stmt)).scalar_one()


async def remove_membership(session: AsyncSession, tenant_id: uuid.UUID, user_id: str) -> bool:
    result = await session.execute(
        update(Membership)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.auth_user_id == user_id,
            Membership.status == ACTIVE,
        )
        .values(
            status=REMOVED,
            removed_at=datetime.now(UTC),
            version=Membership.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    return bool(cast(CursorResult[Any], result).rowcount)


async def resolve_principal(
    session: AsyncSession, claims: AccessClaims, tenant_id: uuid.UUID
) -> Principal:
    """Principal for a verified token. Provisions tenant and membership lazily if the hook was missed."""
    assert claims.org_id is not None  # noqa: S101 - guaranteed by the caller
    membership = await session.scalar(
        select(Membership).where(Membership.auth_user_id == claims.sub)
    )
    if membership is None:
        await provision_tenant(
            session,
            tenant_id=tenant_id,
            org_id=claims.org_id,
            name=claims.org_name or "",
            slug=claims.org_slug,
            via="lazy",
        )
        # Claims come from a verified token; build without re-validating the email format.
        user = InternalUser.model_construct(
            user_id=claims.sub, email=claims.email, name=claims.name
        )
        membership = await upsert_membership(session, tenant_id, user, claims.org_role or "")
    if membership.status != ACTIVE:
        raise MembershipInactiveError()
    return Principal(
        user_id=membership.auth_user_id,
        email=membership.email,
        name=membership.name,
        tenant_id=tenant_id,
        org_id=claims.org_id,
        membership_id=membership.id,
        role=membership.role,
        permissions=permissions_for(membership.role),
        mfa_enrolled=claims.mfa_enrolled,
    )


# ---------------------------------------------------------------- organization


async def today(session: AsyncSession, tenant_id: uuid.UUID) -> date:
    """Today's date in the agency's timezone."""
    tenant = await get_tenant(session, tenant_id)
    return datetime.now(ZoneInfo(tenant.timezone)).date()


async def get_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:  # pragma: no cover - a resolved principal implies the tenant exists
        raise NotFoundError("Organization not found")
    return tenant


def _snapshot(obj: Any, fields: set[str]) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in fields}


async def update_organization(
    ctx: TenantContext, changes: OrganizationUpdate, if_match: str | None
) -> Tenant:
    tenant = await get_tenant(ctx.session, ctx.tenant_id)
    check_version(if_match, tenant.version)
    data = changes.model_dump(exclude_unset=True, mode="python")
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"])
    before = _snapshot(tenant, set(data))
    for field, value in data.items():
        setattr(tenant, field, value)
    tenant.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await audit.record(
        ctx,
        "organization.updated",
        entity_type="organization",
        entity_id=tenant.id,
        changes=audit.diff(before, _snapshot(tenant, set(data))),
    )
    return tenant


# ---------------------------------------------------------------- members


async def list_members(session: AsyncSession) -> list[Membership]:
    stmt = select(Membership).order_by(Membership.status, Membership.name, Membership.email)
    return list((await session.scalars(stmt)).all())


# ---------------------------------------------------------------- branches


async def list_branches(session: AsyncSession, *, include_archived: bool) -> list[Branch]:
    stmt = select(Branch).order_by(Branch.is_head_office.desc(), Branch.name)
    if not include_archived:
        stmt = stmt.where(Branch.archived_at.is_(None))
    return list((await session.scalars(stmt)).all())


async def get_branch(session: AsyncSession, branch_id: uuid.UUID) -> Branch:
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise NotFoundError("Branch not found")
    return branch


async def _code_taken(session: AsyncSession, code: str, exclude: uuid.UUID | None = None) -> bool:
    stmt = select(Branch.id).where(Branch.code == code)
    if exclude is not None:
        stmt = stmt.where(Branch.id != exclude)
    return (await session.scalar(stmt)) is not None


async def _clear_head_office(session: AsyncSession, except_id: uuid.UUID | None) -> None:
    stmt = (
        update(Branch)
        .where(Branch.is_head_office.is_(True))
        .values(is_head_office=False, version=Branch.version + 1)
        .execution_options(synchronize_session="fetch")
    )
    if except_id is not None:
        stmt = stmt.where(Branch.id != except_id)
    await session.execute(stmt)


async def create_branch(ctx: TenantContext, data: BranchCreate) -> Branch:
    if await _code_taken(ctx.session, data.code):
        raise ConflictError(f"Branch code {data.code} is already used")
    if data.is_head_office:
        await _clear_head_office(ctx.session, None)
    values = data.model_dump(mode="python")
    if values["email"] is not None:
        values["email"] = str(values["email"])
    branch = Branch(
        tenant_id=ctx.tenant_id,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
        **values,
    )
    ctx.session.add(branch)
    await ctx.session.flush()
    await ctx.session.refresh(branch)
    await audit.record(
        ctx,
        "branch.created",
        entity_type="branch",
        entity_id=branch.id,
        changes=audit.diff({}, data.model_dump(mode="json")),
    )
    return branch


async def update_branch(
    ctx: TenantContext, branch_id: uuid.UUID, changes: BranchUpdate, if_match: str | None
) -> Branch:
    branch = await get_branch(ctx.session, branch_id)
    check_version(if_match, branch.version)
    data = changes.model_dump(exclude_unset=True, mode="python")
    if "code" in data and await _code_taken(ctx.session, data["code"], exclude=branch.id):
        raise ConflictError(f"Branch code {data['code']} is already used")
    if data.get("is_head_office"):
        await _clear_head_office(ctx.session, branch.id)
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"])
    archived = data.pop("archived", None)
    if archived is not None:
        data["archived_at"] = (branch.archived_at or datetime.now(UTC)) if archived else None
    before = _snapshot(branch, set(data))
    for field, value in data.items():
        setattr(branch, field, value)
    branch.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(branch)
    await audit.record(
        ctx,
        "branch.updated",
        entity_type="branch",
        entity_id=branch.id,
        changes=audit.diff(before, _snapshot(branch, set(data))),
    )
    return branch
