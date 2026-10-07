"""Internal endpoints called by the auth service's organization hooks (never routed by the public ingress).

Authenticated with a short-lived service token signed by the auth service (``aud`` = AUTH_INTERNAL_AUDIENCE,
``sub`` = ``service:auth``). Every call is idempotent: hooks may be retried.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.db import tenant_scope
from app.core.security import ServiceClaims
from app.core.tenancy import tenant_id_for_org
from app.modules.tenancy import service
from app.modules.tenancy.schemas import (
    MembershipRemove,
    MembershipUpsert,
    ProvisionResult,
    TenantProvision,
)
from app.platform.deps import ResourcesDep, service_claims

router = APIRouter(prefix="/internal/v1", tags=["internal"], include_in_schema=False)
Service = Annotated[ServiceClaims, Depends(service_claims)]


@router.post("/tenants", status_code=status.HTTP_200_OK)
async def provision_tenant(
    body: TenantProvision, _: Service, resources: ResourcesDep
) -> ProvisionResult:
    tenant_id = tenant_id_for_org(body.org_id)
    async with tenant_scope(resources.session_factory, tenant_id) as session:
        created = await service.provision_tenant(
            session,
            tenant_id=tenant_id,
            org_id=body.org_id,
            name=body.name,
            slug=body.slug,
            via="hook",
        )
        await service.upsert_membership(session, tenant_id, body.owner, "owner")
    return ProvisionResult(tenant_id=tenant_id, created=created)


@router.put("/memberships", status_code=status.HTTP_204_NO_CONTENT)
async def upsert_membership(body: MembershipUpsert, _: Service, resources: ResourcesDep) -> None:
    tenant_id = tenant_id_for_org(body.org_id)
    async with tenant_scope(resources.session_factory, tenant_id) as session:
        # A member can be added before the tenant hook ran (retries arrive out of order).
        await service.provision_tenant(
            session,
            tenant_id=tenant_id,
            org_id=body.org_id,
            name=body.org_name,
            slug=body.org_slug,
            via="hook",
        )
        await service.upsert_membership(session, tenant_id, body.user, body.role)


@router.post("/memberships/remove", status_code=status.HTTP_204_NO_CONTENT)
async def remove_membership(body: MembershipRemove, _: Service, resources: ResourcesDep) -> None:
    """Takes effect on the member's next request (the mirror is read on every request)."""
    tenant_id = tenant_id_for_org(body.org_id)
    async with tenant_scope(resources.session_factory, tenant_id) as session:
        await service.remove_membership(session, tenant_id, body.user_id)
