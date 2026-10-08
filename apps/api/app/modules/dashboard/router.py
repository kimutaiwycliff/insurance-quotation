"""Home dashboard: what needs the agent's attention today (scoped to what the member may see)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.permissions import Perm
from app.modules.clients import service as clients
from app.modules.documents import service as documents
from app.modules.leads import service as leads
from app.modules.leads.service import Pipeline
from app.modules.tasks import service as tasks
from app.modules.tasks.service import TaskCounts
from app.modules.tenancy import service as tenancy
from app.platform.deps import TenantContext, require_permission

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class Dashboard(BaseModel):
    clients: int
    new_clients_30d: int
    tasks: TaskCounts | None
    pipeline: Pipeline | None
    documents_expiring_30d: int


@router.get("", operation_id="dashboard_get")
async def dashboard(
    ctx: Annotated[
        TenantContext, Depends(require_permission((Perm.CLIENT_READ_OWN, Perm.CLIENT_READ_ALL)))
    ],
) -> Dashboard:
    perms = ctx.principal.permissions
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    can_tasks = Perm.TASK_WRITE in perms or Perm.TASK_READ_ALL in perms
    can_leads = Perm.LEAD_READ_OWN in perms or Perm.LEAD_READ_ALL in perms
    expiring = await documents.list_documents(
        ctx.session,
        cursor=None,
        limit=500,
        entity=None,
        category=None,
        expiring_before=datetime.now(UTC).date() + timedelta(days=30),
        include_archived=False,
    )
    return Dashboard(
        clients=await clients.count_clients(ctx),
        new_clients_30d=await clients.count_clients(
            ctx, since=datetime.now(UTC) - timedelta(days=30)
        ),
        tasks=TaskCounts(**await tasks.counts(ctx)) if can_tasks else None,
        pipeline=await leads.pipeline(ctx, tenant.default_currency) if can_leads else None,
        documents_expiring_30d=len(expiring) if Perm.DOCUMENT_READ in perms else 0,
    )
