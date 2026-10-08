"""Home dashboard: what needs the agent's attention today (scoped to what the member may see)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.money import AmountStr
from app.core.permissions import Perm
from app.modules.clients import service as clients
from app.modules.commissions import service as commissions
from app.modules.documents import service as documents
from app.modules.leads import service as leads
from app.modules.leads.service import Pipeline
from app.modules.policies import service as policies
from app.modules.policies.service import BookStats
from app.modules.tasks import service as tasks
from app.modules.tasks.service import TaskCounts
from app.modules.tenancy import service as tenancy
from app.platform.deps import TenantContext, require_permission

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def insurers_can_see_commission(perms: frozenset[str] | set[str]) -> bool:
    return Perm.COMMISSION_READ_ALL in perms or Perm.COMMISSION_READ_OWN in perms


class Dashboard(BaseModel):
    clients: int
    new_clients_30d: int
    tasks: TaskCounts | None
    pipeline: Pipeline | None
    documents_expiring_30d: int
    policies_active: int
    renewals_due_30d: int
    premiums_to_remit: int
    book: BookStats = Field(
        description="This year: premium written and unpaid, renewals won and lost"
    )
    commission_received: AmountStr | None = Field(
        description="Net commission received this year; null without commission access"
    )


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
    book = await policies.counts(ctx)
    year_start = (await tenancy.today(ctx.session, ctx.tenant_id)).replace(month=1, day=1)
    stats = await policies.book_stats(ctx, year_start)
    if not insurers_can_see_commission(perms):
        stats = stats.model_copy(update={"expected_commission": None})
    return Dashboard(
        clients=await clients.count_clients(ctx),
        new_clients_30d=await clients.count_clients(
            ctx, since=datetime.now(UTC) - timedelta(days=30)
        ),
        tasks=TaskCounts(**await tasks.counts(ctx)) if can_tasks else None,
        pipeline=await leads.pipeline(ctx, tenant.default_currency) if can_leads else None,
        documents_expiring_30d=len(expiring) if Perm.DOCUMENT_READ in perms else 0,
        policies_active=book["active"],
        renewals_due_30d=book["renewals_due_30d"],
        premiums_to_remit=book["premiums_to_remit"],
        book=stats,
        commission_received=await commissions.received_since(ctx, year_start)
        if insurers_can_see_commission(perms)
        else None,
    )
