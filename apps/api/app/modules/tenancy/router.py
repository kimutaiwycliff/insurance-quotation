"""Tenant endpoints: current user, organization settings, members, roles and branches."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from app.core.concurrency import etag
from app.core.permissions import ROLE_DESCRIPTIONS, ROLE_PERMISSIONS, Perm
from app.modules.tenancy import service
from app.modules.tenancy.schemas import (
    BranchCreate,
    BranchOut,
    BranchUpdate,
    MemberOut,
    MeOut,
    OrganizationOut,
    OrganizationUpdate,
    RoleOut,
    TenantSummary,
)
from app.platform.deps import ResourcesDep, TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter()
IfMatch = Annotated[str | None, Header()]

_me = require_permission(None, allow_without_mfa=True)
_branch_manage = require_permission(Perm.BRANCH_MANAGE)


@router.get("/me", operation_id="me_get", tags=["identity"])
async def me(ctx: Annotated[TenantContext, Depends(_me)], resources: ResourcesDep) -> MeOut:
    """The signed-in user in their active organization. Works before 2FA is enrolled (to prompt for it)."""
    principal = ctx.principal
    tenant = await service.get_tenant(ctx.session, principal.tenant_id)
    return MeOut(
        user_id=principal.user_id,
        email=principal.email,
        name=principal.name,
        tenant=TenantSummary(id=tenant.id, name=tenant.name, slug=tenant.slug),
        role=principal.role,
        permissions=sorted(principal.permissions),
        mfa_enrolled=principal.mfa_enrolled,
        mfa_required=principal.role in resources.settings.mfa_enforced_roles
        and not principal.mfa_enrolled,
    )


@router.get("/organization", operation_id="organization_get", tags=["organization"])
async def get_organization(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.ORG_READ))], response: Response
) -> OrganizationOut:
    tenant = await service.get_tenant(ctx.session, ctx.tenant_id)
    response.headers["ETag"] = etag(tenant.version)
    return OrganizationOut.model_validate(tenant)


@router.patch("/organization", operation_id="organization_update", tags=["organization"])
async def update_organization(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.ORG_UPDATE))],
    body: OrganizationUpdate,
    response: Response,
    if_match: IfMatch = None,
) -> OrganizationOut:
    tenant = await service.update_organization(ctx, body, if_match)
    response.headers["ETag"] = etag(tenant.version)
    return OrganizationOut.model_validate(tenant)


@router.get("/members", operation_id="members_list", tags=["members"])
async def list_members(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.MEMBER_READ))],
) -> list[MemberOut]:
    """Members are invited, removed and re-roled in the auth service; this is the API's mirror."""
    return [MemberOut.model_validate(m) for m in await service.list_members(ctx.session)]


@router.get("/roles", operation_id="roles_list", tags=["members"])
async def list_roles(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.MEMBER_READ))],
    resources: ResourcesDep,
) -> list[RoleOut]:
    return [
        RoleOut(
            key=role.value,
            description=ROLE_DESCRIPTIONS[role],
            permissions=sorted(perms),
            mfa_required=role.value in resources.settings.mfa_enforced_roles,
        )
        for role, perms in ROLE_PERMISSIONS.items()
    ]


@router.get("/branches", operation_id="branches_list", tags=["branches"])
async def list_branches(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.BRANCH_READ))],
    include_archived: Annotated[bool, Query()] = False,
) -> list[BranchOut]:
    branches = await service.list_branches(ctx.session, include_archived=include_archived)
    return [BranchOut.model_validate(b) for b in branches]


@router.post(
    "/branches",
    operation_id="branches_create",
    status_code=201,
    response_model=BranchOut,
    tags=["branches"],
)
async def create_branch(
    ctx: Annotated[TenantContext, Depends(_branch_manage)],
    body: BranchCreate,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_branch_manage))],
) -> Response:
    if (replay := await idem.replay()) is not None:
        return replay
    branch = await service.create_branch(ctx, body)
    return await idem.respond(201, BranchOut.model_validate(branch), {"ETag": etag(branch.version)})


@router.get("/branches/{branch_id}", operation_id="branches_get", tags=["branches"])
async def get_branch(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.BRANCH_READ))],
    branch_id: uuid.UUID,
    response: Response,
) -> BranchOut:
    branch = await service.get_branch(ctx.session, branch_id)
    response.headers["ETag"] = etag(branch.version)
    return BranchOut.model_validate(branch)


@router.patch("/branches/{branch_id}", operation_id="branches_update", tags=["branches"])
async def update_branch(
    ctx: Annotated[TenantContext, Depends(_branch_manage)],
    branch_id: uuid.UUID,
    body: BranchUpdate,
    response: Response,
    if_match: IfMatch = None,
) -> BranchOut:
    """Partial update. Send `archived: true` to archive (branches are never deleted)."""
    branch = await service.update_branch(ctx, branch_id, body, if_match)
    response.headers["ETag"] = etag(branch.version)
    return BranchOut.model_validate(branch)
