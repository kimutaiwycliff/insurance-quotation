"""Audit log: ``record()`` for writers, ``GET /api/v1/audit-events`` for readers.

Rows are append-only (``app_user`` has no UPDATE/DELETE grant). ``changes`` holds a field-level diff; values
of sensitive fields are replaced by ``[REDACTED]`` before storage.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.logging import REDACTED, is_sensitive_key
from app.core.pagination import Page, PageParams, build_page, page_params
from app.core.permissions import Perm
from app.platform.deps import TenantContext, require_permission
from app.platform.models import AuditEvent

router = APIRouter(prefix="/audit-events", tags=["audit"])


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """``{field: {"from": old, "to": new}}`` for fields that changed, with sensitive values redacted."""
    changes: dict[str, Any] = {}
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        if old != new:
            if is_sensitive_key(key):
                old, new = REDACTED, REDACTED
            changes[key] = {"from": _jsonable(old), "to": _jsonable(new)}
    return changes


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str | list | dict):
        return value
    return str(value)


async def record(
    ctx: TenantContext,
    action: str,
    *,
    entity_type: str,
    entity_id: uuid.UUID | str | None,
    changes: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the current transaction (committed with the change it describes)."""
    ctx.session.add(
        AuditEvent(
            tenant_id=ctx.tenant_id,
            actor_type="user",
            actor_id=ctx.principal.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            request_id=ctx.request_id,
            changes=changes or {},
        )
    )


async def events_for(
    ctx: TenantContext, entity_type: str, entity_id: str, *, limit: int = 100
) -> list[AuditEvent]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
        .order_by(AuditEvent.id.desc())
        .limit(limit)
    )
    return list((await ctx.session.scalars(stmt)).all())


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    actor_type: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    request_id: str | None
    changes: dict[str, Any]


@router.get("", operation_id="audit_events_list")
async def list_audit_events(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.AUDIT_READ))],
    page: Annotated[PageParams, Depends(page_params)],
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
) -> Page[AuditEventOut]:
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(page.limit + 1)
    if page.cursor is not None:
        stmt = stmt.where(AuditEvent.id < page.cursor)
    if entity_type is not None:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    rows = list((await ctx.session.scalars(stmt)).all())
    return build_page(
        [AuditEventOut.model_validate(r) for r in rows], [r.id for r in rows], page.limit
    )
