"""Tasks service. Members see tasks assigned to them or created by them; ``task:read:all`` sees every task.

"Today" and "overdue" use the agency's timezone. Due tasks are reminded once (in-app notification) by the
``tasks.remind_due`` periodic job.
"""

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, func, or_, select, text

from app.core.concurrency import check_version
from app.core.config import Settings
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import Perm
from app.modules.clients import service as clients
from app.modules.notifications import service as notifications
from app.modules.tasks.models import Task
from app.modules.tasks.schemas import Due, TaskCounts, TaskCreate, TaskUpdate

__all__ = ["TaskCounts", "TaskCreate", "complete_task", "counts", "create_task", "list_tasks"]
from app.modules.tenancy import service as tenancy
from app.platform import audit, events
from app.platform.deps import TenantContext, own_scope

REMIND_TASK = "tasks.remind"
OPEN, DONE = "open", "done"


def _scoped[*Ts](stmt: Select[*Ts], ctx: TenantContext) -> Select[*Ts]:
    user = own_scope(ctx.principal, Perm.TASK_READ_ALL)
    if user is None:
        return stmt
    return stmt.where(or_(Task.assignee_user_id == user, Task.created_by == user))


async def _day_bounds(ctx: TenantContext) -> tuple[datetime, datetime]:
    tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
    zone = ZoneInfo(tenant.timezone)
    today = datetime.now(zone).date()
    start = datetime.combine(today, time.min, zone)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


async def _check_assignee(ctx: TenantContext, assignee: str) -> None:
    if assignee == ctx.principal.user_id:
        return
    active = {
        m.auth_user_id for m in await tenancy.list_members(ctx.session) if m.status == "active"
    }
    if assignee not in active:
        raise NotFoundError("That person is not an active member of the agency")


async def _check_entity(
    ctx: TenantContext, entity_type: str | None, entity_id: uuid.UUID | None
) -> None:
    if (entity_type is None) != (entity_id is None):
        raise NotFoundError("Link a task to a record with both entity_type and entity_id")
    if entity_type == "client" and entity_id is not None:
        await clients.get_visible_client(ctx, entity_id)


async def create_task(ctx: TenantContext, body: TaskCreate) -> Task:
    assignee = body.assignee_user_id or ctx.principal.user_id
    await _check_assignee(ctx, assignee)
    await _check_entity(ctx, body.entity_type, body.entity_id)
    task = Task(
        tenant_id=ctx.tenant_id,
        title=body.title,
        notes=body.notes,
        due_at=body.due_at,
        assignee_user_id=assignee,
        priority=body.priority,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
    )
    ctx.session.add(task)
    await ctx.session.flush()
    await ctx.session.refresh(task)
    await audit.record(
        ctx,
        "task.created",
        entity_type="task",
        entity_id=task.id,
        changes={"assignee_user_id": assignee, "entity_id": str(body.entity_id or "")},
    )
    return task


async def get_task(ctx: TenantContext, task_id: uuid.UUID) -> Task:
    task = (await ctx.session.scalars(_scoped(select(Task).where(Task.id == task_id), ctx))).first()
    if task is None:
        raise NotFoundError("Task not found")
    return task


async def update_task(
    ctx: TenantContext, task_id: uuid.UUID, body: TaskUpdate, if_match: str | None
) -> Task:
    task = await get_task(ctx, task_id)
    check_version(if_match, task.version)
    data = body.model_dump(exclude_unset=True)
    if "assignee_user_id" in data and data["assignee_user_id"] != task.assignee_user_id:
        if (
            Perm.TASK_READ_ALL not in ctx.principal.permissions
            and task.created_by != ctx.principal.user_id
        ):
            raise PermissionDeniedError("Only the person who created the task can reassign it")
        await _check_assignee(ctx, data["assignee_user_id"])
    done = data.pop("done", None)
    if done is not None:
        task.status = DONE if done else OPEN
        task.completed_at = datetime.now(UTC) if done else None
    if "due_at" in data:
        task.reminded_at = None  # a new due date gets a new reminder
    for field, value in data.items():
        setattr(task, field, value)
    task.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(task)
    if done:
        await audit.record(ctx, "task.completed", entity_type="task", entity_id=task.id)
    return task


async def complete_task(ctx: TenantContext, task_id: uuid.UUID) -> None:
    """Close a task another module opened (e.g. "remit premium" once the remittance is recorded)."""
    task = await ctx.session.get(Task, task_id)
    if task is not None and task.status == OPEN:
        task.status, task.completed_at = DONE, datetime.now(UTC)
        task.updated_by = ctx.principal.user_id
        await ctx.session.flush()


async def list_tasks(
    ctx: TenantContext,
    *,
    due: Due,
    status: str,
    assignee: str | None,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    limit: int,
) -> list[Task]:
    stmt = _scoped(select(Task), ctx)
    if status != "all":
        stmt = stmt.where(Task.status == status)
    if assignee:
        stmt = stmt.where(Task.assignee_user_id == assignee)
    if entity_type:
        stmt = stmt.where(Task.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(Task.entity_id == entity_id)
    if due != "all":
        start, end = await _day_bounds(ctx)
        stmt = stmt.where(
            {
                "overdue": Task.due_at < start,
                "today": and_(Task.due_at >= start, Task.due_at < end),
                "upcoming": Task.due_at >= end,
                "none": Task.due_at.is_(None),
            }[due]
        )
    stmt = stmt.order_by(Task.due_at.asc().nulls_last(), Task.id.desc()).limit(limit)
    return list((await ctx.session.scalars(stmt)).all())


async def counts(ctx: TenantContext) -> dict[str, int]:
    start, end = await _day_bounds(ctx)
    base = _scoped(select(func.count()).select_from(Task).where(Task.status == OPEN), ctx)
    return {
        "overdue": int(await ctx.session.scalar(base.where(Task.due_at < start)) or 0),
        "today": int(
            await ctx.session.scalar(base.where(Task.due_at >= start, Task.due_at < end)) or 0
        ),
        "upcoming": int(await ctx.session.scalar(base.where(Task.due_at >= end)) or 0),
    }


# ---------------------------------------------------------------- reminders (jobs)


async def enqueue_due_reminders(session: Any, *, horizon_minutes: int = 15) -> int:
    """Cross-tenant scan through the narrow SECURITY DEFINER function, then one job per task (ADR-0003 §8)."""
    rows = (
        await session.execute(
            text(
                "SELECT tenant_id, task_id FROM app.tasks_due_for_reminder(now() + make_interval(mins => :m))"
            ),
            {"m": horizon_minutes},
        )
    ).all()
    for tenant_id, task_id in rows:
        await events.enqueue(
            session,
            REMIND_TASK,
            {"tenant_id": str(tenant_id), "task_id": str(task_id)},
            queueing_lock=f"task-remind:{task_id}",
        )
    return len(rows)


async def remind(
    session: Any, settings: Settings, tenant_id: uuid.UUID, task_id: uuid.UUID
) -> bool:
    """Notify the assignee once. Idempotent: a task already reminded (or done) is left alone."""
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None or task.status != OPEN or task.reminded_at is not None:
        return False
    await notifications.notify(
        session,
        settings,
        tenant_id=tenant_id,
        user_ids=[task.assignee_user_id],
        kind="task.due",
        title=f"Due: {task.title}",
        body=task.notes or "",
        link=f"/tasks?focus={task.id}",
    )
    task.reminded_at = datetime.now(UTC)
    return True
