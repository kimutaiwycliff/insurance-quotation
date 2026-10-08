"""Task endpoints."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response

from app.core.concurrency import etag
from app.core.permissions import Perm
from app.modules.tasks import service
from app.modules.tasks.schemas import Due, TaskCounts, TaskCreate, TaskOut, TaskUpdate
from app.platform.deps import TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(prefix="/tasks", tags=["tasks"])
_write = require_permission(Perm.TASK_WRITE)
# Reading tasks: your own (anyone who can work on tasks) or everyone's (task:read:all).
Read = Annotated[TenantContext, Depends(require_permission((Perm.TASK_WRITE, Perm.TASK_READ_ALL)))]
Write = Annotated[TenantContext, Depends(_write)]


@router.get("", operation_id="tasks_list")
async def list_tasks(
    ctx: Read,
    due: Due = "all",
    status: Literal["open", "done", "all"] = "open",
    assignee: Annotated[str | None, Query(max_length=255)] = None,
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[TaskOut]:
    rows = await service.list_tasks(
        ctx,
        due=due,
        status=status,
        assignee=assignee,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )
    return [TaskOut.model_validate(t) for t in rows]


@router.get("/counts", operation_id="tasks_counts")
async def task_counts(ctx: Read) -> TaskCounts:
    return TaskCounts(**await service.counts(ctx))


@router.post("", operation_id="tasks_create", status_code=201, response_model=TaskOut)
async def create_task(
    ctx: Write,
    body: TaskCreate,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_write))],
) -> Response:
    if (replay := await idem.replay()) is not None:
        return replay
    task = await service.create_task(ctx, body)
    return await idem.respond(201, TaskOut.model_validate(task), {"ETag": etag(task.version)})


@router.patch("/{task_id}", operation_id="tasks_update")
async def update_task(
    ctx: Write,
    task_id: uuid.UUID,
    body: TaskUpdate,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> TaskOut:
    """Edit, reassign or complete (`done: true`)."""
    task = await service.update_task(ctx, task_id, body, if_match)
    response.headers["ETag"] = etag(task.version)
    return TaskOut.model_validate(task)
