"""Lead endpoints: list, pipeline summary, create, update (stage, owner, follow-up) and convert."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel

from app.core.concurrency import etag
from app.core.permissions import Perm
from app.modules.leads import service
from app.modules.leads.schemas import ConvertLead, LeadCreate, LeadOut, LeadUpdate, Pipeline, Stage
from app.modules.tenancy import service as tenancy
from app.platform.deps import ResourcesDep, TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(prefix="/leads", tags=["leads"])
_write = require_permission(Perm.LEAD_WRITE)
Read = Annotated[
    TenantContext, Depends(require_permission((Perm.LEAD_READ_OWN, Perm.LEAD_READ_ALL)))
]
Write = Annotated[TenantContext, Depends(_write)]


class Converted(BaseModel):
    lead: LeadOut
    client_id: uuid.UUID


@router.get("", operation_id="leads_list")
async def list_leads(
    ctx: Read,
    stage: Stage | None = None,
    owner: Annotated[str | None, Query(max_length=255)] = None,
    follow_up_due: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[LeadOut]:
    rows = await service.list_leads(
        ctx, stage=stage, owner=owner, follow_up_due=follow_up_due, q=q, limit=limit
    )
    return [service.to_out(lead) for lead in rows]


@router.get("/pipeline", operation_id="leads_pipeline")
async def pipeline(ctx: Read) -> Pipeline:
    """Counts and estimated premium per stage, in the agency's currency."""
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    return await service.pipeline(ctx, tenant.default_currency)


@router.post("", operation_id="leads_create", status_code=201, response_model=LeadOut)
async def create_lead(
    ctx: Write,
    body: LeadCreate,
    resources: ResourcesDep,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_write))],
) -> Response:
    if (replay := await idem.replay()) is not None:
        return replay
    lead = await service.create_lead(ctx, body, resources.settings)
    return await idem.respond(201, service.to_out(lead), {"ETag": etag(lead.version)})


@router.get("/{lead_id}", operation_id="leads_get")
async def get_lead(ctx: Read, lead_id: uuid.UUID, response: Response) -> LeadOut:
    lead = await service.get_lead(ctx, lead_id)
    response.headers["ETag"] = etag(lead.version)
    return service.to_out(lead)


@router.patch("/{lead_id}", operation_id="leads_update")
async def update_lead(
    ctx: Write,
    lead_id: uuid.UUID,
    body: LeadUpdate,
    response: Response,
    resources: ResourcesDep,
    if_match: Annotated[str | None, Header()] = None,
) -> LeadOut:
    lead = await service.update_lead(ctx, lead_id, body, if_match, resources.settings)
    response.headers["ETag"] = etag(lead.version)
    return service.to_out(lead)


@router.post("/{lead_id}/convert", operation_id="leads_convert")
async def convert(
    ctx: Write, lead_id: uuid.UUID, body: ConvertLead, resources: ResourcesDep
) -> Converted:
    """Win the lead: create a client from it (or link an existing one). Idempotent."""
    lead, client_id = await service.convert(ctx, lead_id, body, resources.settings)
    return Converted(lead=service.to_out(lead), client_id=client_id)
