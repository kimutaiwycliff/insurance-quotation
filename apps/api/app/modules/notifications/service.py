"""Notifications service. Other modules call ``notify``; preferences decide in-app and/or email delivery."""

import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.modules.messaging import service as messaging
from app.modules.notifications.models import Notification, NotificationPreference
from app.modules.notifications.schemas import Preference
from app.modules.tenancy import service as tenancy

# kind → (description, in_app default, email default)
KINDS: dict[str, tuple[str, bool, bool]] = {
    "link.viewed": ("A client opened a document you shared", True, False),
    "document.expiring": ("A client document is about to expire", True, False),
    "member.joined": ("Someone joined your agency", True, False),
    "task.due": ("A task assigned to you is due", True, False),
    "lead.assigned": ("A lead was assigned to you", True, False),
    "quote.answered": ("A client accepted or declined a quotation", True, True),
    "policy.renewal_due": ("A policy you look after is coming up for renewal", True, True),
}


class UnknownKindError(AppError):
    code = "unknown_notification_kind"
    title = "Unknown notification kind"


async def _preferences(session: AsyncSession, user_id: str) -> dict[str, NotificationPreference]:
    rows = (
        await session.scalars(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )
    ).all()
    return {r.kind: r for r in rows}


async def notify(
    session: AsyncSession,
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    user_ids: list[str],
    kind: str,
    title: str,
    body: str = "",
    link: str | None = None,
) -> int:
    """Notify members (in the caller's transaction). Returns how many in-app notifications were created."""
    if kind not in KINDS:
        raise UnknownKindError(kind)
    _, in_app_default, email_default = KINDS[kind]
    members = {
        m.auth_user_id: m for m in await tenancy.list_members(session) if m.status == "active"
    }
    created = 0
    for user_id in dict.fromkeys(user_ids):
        member = members.get(user_id)
        if member is None:
            continue
        pref = (await _preferences(session, user_id)).get(kind)
        if pref.in_app if pref else in_app_default:
            session.add(
                Notification(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    kind=kind,
                    title=title,
                    body=body,
                    link=link,
                )
            )
            created += 1
        if pref.email if pref else email_default:
            url = f"{settings.public_base_url.rstrip('/')}{link}" if link else ""
            await messaging.queue_email(
                session,
                tenant_id=tenant_id,
                event="notification.email",
                to=member.email,
                context={"title": title, "body": body, "link_url": url},
            )
    await session.flush()
    return created


async def list_mine(
    session: AsyncSession, user_id: str, *, cursor: uuid.UUID | None, limit: int, unread_only: bool
) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        stmt = stmt.where(Notification.id < cursor)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list((await session.scalars(stmt)).all())


async def unread_count(session: AsyncSession, user_id: str) -> int:
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return int(await session.scalar(stmt) or 0)


async def mark_read(session: AsyncSession, user_id: str, notification_id: uuid.UUID | None) -> int:
    stmt = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    if notification_id is not None:
        stmt = stmt.where(Notification.id == notification_id)
    result = cast(CursorResult[object], await session.execute(stmt))
    if notification_id is not None and not result.rowcount:
        exists = await session.scalar(
            select(Notification.id).where(
                Notification.id == notification_id, Notification.user_id == user_id
            )
        )
        if exists is None:
            raise NotFoundError("Notification not found")
    return int(result.rowcount or 0)


async def get_preferences(session: AsyncSession, user_id: str) -> list[Preference]:
    saved = await _preferences(session, user_id)
    return [
        Preference(
            kind=kind,
            in_app=saved[kind].in_app if kind in saved else in_app,
            email=saved[kind].email if kind in saved else email,
            description=description,
        )
        for kind, (description, in_app, email) in KINDS.items()
    ]


async def set_preferences(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: str, prefs: list[Preference]
) -> list[Preference]:
    for pref in prefs:
        if pref.kind not in KINDS:
            raise UnknownKindError(pref.kind)
        await session.execute(
            insert(NotificationPreference)
            .values(
                tenant_id=tenant_id,
                user_id=user_id,
                kind=pref.kind,
                in_app=pref.in_app,
                email=pref.email,
            )
            .on_conflict_do_update(
                index_elements=["tenant_id", "user_id", "kind"],
                set_={"in_app": pref.in_app, "email": pref.email},
            )
        )
    return await get_preferences(session, user_id)
