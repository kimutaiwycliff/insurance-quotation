"""Client endpoints: book of clients, search, duplicates, households, contacts, activities and the 360° timeline."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel

from app.core.concurrency import etag
from app.core.pagination import Page, PageParams, build_page, page_params
from app.core.permissions import Perm
from app.modules.clients import service
from app.modules.clients.schemas import (
    ActivityIn,
    ActivityOut,
    ClientCreate,
    ClientOut,
    ClientSummary,
    ClientUpdate,
    ContactIn,
    ContactOut,
    DuplicateCheck,
    DuplicateResult,
    HouseholdDetail,
    HouseholdIn,
    HouseholdOut,
    TimelineItem,
)
from app.modules.documents import service as documents
from app.modules.messaging import service as messaging
from app.modules.tasks import service as tasks
from app.platform.deps import ResourcesDep, TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(tags=["clients"])
_write = require_permission(Perm.CLIENT_WRITE)
Read = Annotated[
    TenantContext, Depends(require_permission((Perm.CLIENT_READ_OWN, Perm.CLIENT_READ_ALL)))
]
Write = Annotated[TenantContext, Depends(_write)]
IfMatch = Annotated[str | None, Header()]


class IdNumber(BaseModel):
    id_number: str | None


@router.get("/clients", operation_id="clients_list")
async def list_clients(
    ctx: Read,
    resources: ResourcesDep,
    page: Annotated[PageParams, Depends(page_params)],
    q: Annotated[
        str | None, Query(max_length=100, description="Name, phone, email, KRA PIN or ID number")
    ] = None,
    tag: Annotated[str | None, Query(max_length=30)] = None,
    owner: Annotated[str | None, Query(max_length=255)] = None,
    household_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> Page[ClientSummary]:
    rows = await service.list_clients(
        ctx,
        resources.settings,
        q=q,
        tag=tag,
        owner_user_id=owner,
        household_id=household_id,
        include_archived=include_archived,
        cursor=page.cursor,
        limit=page.limit,
    )
    return build_page(
        [ClientSummary.model_validate(r) for r in rows], [r.id for r in rows], page.limit
    )


@router.post("/clients/duplicates", operation_id="clients_check_duplicates")
async def check_duplicates(
    ctx: Read, body: DuplicateCheck, resources: ResourcesDep
) -> DuplicateResult:
    """Look for existing clients with the same phone, email, KRA PIN or ID number before creating one."""
    return await service.find_duplicates(ctx, body, resources.settings)


@router.post("/clients", operation_id="clients_create", status_code=201, response_model=ClientOut)
async def create_client(
    ctx: Write,
    body: ClientCreate,
    resources: ResourcesDep,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_write))],
) -> Response:
    """409 `possible_duplicate` if a matching client exists; resend with `allow_duplicate: true` to proceed."""
    if (replay := await idem.replay()) is not None:
        return replay
    client = await service.create_client(ctx, body, resources.settings)
    return await idem.respond(201, ClientOut.model_validate(client), {"ETag": etag(client.version)})


@router.get("/clients/{client_id}", operation_id="clients_get")
async def get_client(ctx: Read, client_id: uuid.UUID, response: Response) -> ClientOut:
    client = await service.get_visible_client(ctx, client_id)
    response.headers["ETag"] = etag(client.version)
    return ClientOut.model_validate(client)


@router.patch("/clients/{client_id}", operation_id="clients_update")
async def update_client(
    ctx: Write,
    client_id: uuid.UUID,
    body: ClientUpdate,
    response: Response,
    resources: ResourcesDep,
    if_match: IfMatch = None,
) -> ClientOut:
    """Partial update. `archived: true` archives (clients are never deleted). `id_number: null` clears it."""
    client = await service.update_client(ctx, client_id, body, if_match, resources.settings)
    response.headers["ETag"] = etag(client.version)
    return ClientOut.model_validate(client)


@router.post("/clients/{client_id}/id-number", operation_id="clients_reveal_id_number")
async def reveal_id_number(ctx: Write, client_id: uuid.UUID, resources: ResourcesDep) -> IdNumber:
    """Show the full ID or passport number (POST because it is recorded in the audit log)."""
    return IdNumber(id_number=await service.reveal_id_number(ctx, client_id, resources.settings))


@router.get("/clients/{client_id}/timeline", operation_id="clients_timeline")
async def timeline(ctx: Read, client_id: uuid.UUID, resources: ResourcesDep) -> list[TimelineItem]:
    """Everything about the client, newest first: notes and calls, documents, tasks, messages and changes."""
    await service.get_visible_client(ctx, client_id)
    extra: list[TimelineItem] = []
    linked = await documents.list_documents(
        ctx.session,
        cursor=None,
        limit=100,
        entity=documents.EntityRef(entity_type="client", entity_id=client_id),
        category=None,
        expiring_before=None,
        include_archived=True,
    )
    extra += [
        TimelineItem(
            at=d.created_at,
            kind="document",
            title=f"Document: {d.title}",
            actor=d.created_by,
            ref={"document_id": str(d.id)},
        )
        for d in linked[:100]
    ]
    for task in await tasks.list_tasks(
        ctx,
        due="all",
        status="all",
        assignee=None,
        entity_type="client",
        entity_id=client_id,
        limit=100,
    ):
        title = f"Task done: {task.title}" if task.status == "done" else f"Task: {task.title}"
        extra.append(
            TimelineItem(
                at=task.completed_at or task.created_at,
                kind="task",
                title=title,
                detail=task.notes,
                actor=task.created_by,
                ref={"task_id": str(task.id)},
            )
        )
    for message in await messaging.list_messages(
        ctx.session, cursor=None, limit=100, entity_type="client", entity_id=client_id
    ):
        extra.append(
            TimelineItem(
                at=message.created_at,
                kind="message",
                title=f"Email: {message.subject}",
                detail=f"To {message.to_address} ({message.status})",
                ref={"message_id": str(message.id)},
            )
        )
    return await service.timeline_items(ctx, client_id, extra)


@router.get("/clients/{client_id}/activities", operation_id="clients_activities_list")
async def list_activities(ctx: Read, client_id: uuid.UUID) -> list[ActivityOut]:
    return [ActivityOut.model_validate(a) for a in await service.list_activities(ctx, client_id)]


@router.post(
    "/clients/{client_id}/activities", operation_id="clients_activities_add", status_code=201
)
async def add_activity(ctx: Write, client_id: uuid.UUID, body: ActivityIn) -> ActivityOut:
    """Log a note, call, meeting or message with the client."""
    return ActivityOut.model_validate(await service.add_activity(ctx, client_id, body))


@router.get("/clients/{client_id}/contacts", operation_id="clients_contacts_list")
async def list_contacts(ctx: Read, client_id: uuid.UUID) -> list[ContactOut]:
    return [ContactOut.model_validate(c) for c in await service.list_contacts(ctx, client_id)]


@router.post("/clients/{client_id}/contacts", operation_id="clients_contacts_add", status_code=201)
async def add_contact(ctx: Write, client_id: uuid.UUID, body: ContactIn) -> ContactOut:
    return ContactOut.model_validate(await service.add_contact(ctx, client_id, body))


@router.delete(
    "/clients/{client_id}/contacts/{contact_id}",
    operation_id="clients_contacts_remove",
    status_code=204,
)
async def remove_contact(ctx: Write, client_id: uuid.UUID, contact_id: uuid.UUID) -> None:
    await service.remove_contact(ctx, client_id, contact_id)


@router.get("/households", operation_id="households_list")
async def list_households(ctx: Read) -> list[HouseholdOut]:
    return [HouseholdOut.model_validate(h) for h in await service.list_households(ctx)]


@router.post("/households", operation_id="households_create", status_code=201)
async def create_household(ctx: Write, body: HouseholdIn) -> HouseholdOut:
    return HouseholdOut.model_validate(await service.create_household(ctx, body))


@router.get("/households/{household_id}", operation_id="households_get")
async def get_household(ctx: Read, household_id: uuid.UUID) -> HouseholdDetail:
    household, members = await service.get_household(ctx, household_id)
    return HouseholdDetail(
        **HouseholdOut.model_validate(household).model_dump(),
        members=[ClientSummary.model_validate(m) for m in members],
    )


@router.patch("/households/{household_id}", operation_id="households_update")
async def update_household(
    ctx: Write, household_id: uuid.UUID, body: HouseholdIn, if_match: IfMatch = None
) -> HouseholdOut:
    return HouseholdOut.model_validate(
        await service.update_household(ctx, household_id, body, if_match)
    )
