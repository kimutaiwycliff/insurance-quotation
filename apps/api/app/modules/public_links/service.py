"""Public links (ADR-0014).

* Tokens are 32 random bytes (base64url, 43 chars); only SHA-256(token) is stored. URLs carry no internal ids.
* Anonymous requests have no tenant: the token hash is resolved by ``app.resolve_public_link()``, a narrow
  SECURITY DEFINER function, and everything after that runs under RLS for the link's tenant.
* Unknown → 404; expired or revoked → 410. Revocation is immediate (checked on every request).
* What a link shows is provided by a **target** registered per entity type. This module ships the
  ``document`` target; quotes, invoices and receipts register theirs in later milestones.
"""

import base64
import hashlib
import hmac
import re
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any, Protocol

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.integrations.storage.s3 import S3Storage
from app.modules.documents import service as documents
from app.modules.messaging import service as messaging
from app.modules.notifications import service as notifications
from app.modules.public_links.models import LinkEvent, PublicLink
from app.modules.public_links.schemas import LinkCreate, SendTo
from app.modules.tenancy import service as tenancy
from app.platform import audit
from app.platform.deps import TenantContext

__all__ = [
    "LinkCreate",
    "LinkGoneError",
    "PublicContent",
    "PublicLink",
    "SendTo",
    "create_link",
    "link_url",
    "register_actions",
    "register_target",
    "revoke_for_entity",
]

TOKEN_BYTES = 32
_TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_BOTS = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|slack|discord|skype|"
    r"linkedin|embedly|headless|curl|wget|python-|httpx|go-http|java/|okhttp|scanner|monitor",
    re.IGNORECASE,
)


class LinkGoneError(AppError):
    status = HTTPStatus.GONE
    code = "link_gone"
    title = "This link has expired or was withdrawn"


class LinkScopeError(AppError):
    status = HTTPStatus.FORBIDDEN
    code = "link_scope"
    title = "This link does not allow that action"


@dataclass(frozen=True, slots=True)
class PublicContent:
    title: str
    kind: str
    html: Callable[[], Awaitable[str]] | None = None  # self-contained HTML (template engine)
    download: Callable[[], Awaitable[str]] | None = None  # presigned URL
    choices: list[dict[str, Any]] = field(default_factory=list)  # e.g. quote options to accept
    state: str | None = None  # e.g. sent | accepted | declined | expired


class ActionHandler(Protocol):
    async def __call__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        link: PublicLink,
        action: str,
        body: dict[str, Any],
        evidence: dict[str, Any],
    ) -> str: ...


_ACTIONS: dict[str, ActionHandler] = {}


def register_actions(entity_type: str, handler: ActionHandler) -> None:
    """Handle ``accept``/``decline`` on links to ``entity_type``; returns the new state."""
    _ACTIONS[entity_type] = handler


async def perform(
    session: AsyncSession,
    settings: Settings,
    link: PublicLink,
    action: str,
    body: dict[str, Any],
    *,
    ip_hash: str | None,
    user_agent: str | None,
) -> str:
    if "accept" not in link.scopes:
        raise LinkScopeError()
    handler = _ACTIONS.get(link.entity_type)
    if handler is None:
        raise LinkScopeError("Nothing to accept here")
    evidence = {
        "ip_hash": ip_hash,
        "user_agent": (user_agent or "")[:300],
        "at": datetime.now(UTC).isoformat(),
    }
    state = await handler(
        session=session, settings=settings, link=link, action=action, body=body, evidence=evidence
    )
    await record_event(
        session,
        link,
        "accepted" if action == "accept" else "declined",
        ip_hash=ip_hash,
        user_agent=user_agent,
        details={k: v for k, v in body.items() if k in {"option", "reason"}},
    )
    return state


async def revoke_for_entity(ctx: TenantContext, entity_type: str, entity_id: uuid.UUID) -> int:
    links = (
        await ctx.session.scalars(
            select(PublicLink).where(
                PublicLink.entity_type == entity_type,
                PublicLink.entity_id == entity_id,
                PublicLink.revoked_at.is_(None),
            )
        )
    ).all()
    for link in links:
        await revoke(ctx, link.id)
    return len(links)


TargetResolver = Callable[[AsyncSession, S3Storage, Settings, PublicLink], Awaitable[PublicContent]]
_TARGETS: dict[str, TargetResolver] = {}


def register_target(entity_type: str, resolver: TargetResolver) -> None:
    _TARGETS[entity_type] = resolver


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def is_bot(user_agent: str | None) -> bool:
    return not user_agent or bool(_BOTS.search(user_agent))


def hash_ip(ip: str | None, settings: Settings) -> str | None:
    if not ip:
        return None
    key = settings.signing_secret.get_secret_value().encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()[:32]


async def create_link(
    ctx: TenantContext, data: LinkCreate, settings: Settings, storage: S3Storage
) -> tuple[PublicLink, str]:
    resolver = _TARGETS.get(data.entity_type)
    if resolver is None:
        raise NotFoundError(f"Links to {data.entity_type!r} are not supported")
    if data.entity_type == "document":
        await documents.get_document(ctx.session, data.entity_id)  # 404 across tenants
    token = base64.urlsafe_b64encode(secrets.token_bytes(TOKEN_BYTES)).rstrip(b"=").decode()
    days = data.expires_in_days or settings.public_link_default_ttl_days
    link = PublicLink(
        tenant_id=ctx.tenant_id,
        token_hash=hash_token(token),
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        scopes=list(dict.fromkeys(data.scopes)),
        expires_at=datetime.now(UTC) + timedelta(days=days),
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(link)
    await ctx.session.flush()
    await ctx.session.refresh(link)
    ctx.session.add(LinkEvent(tenant_id=ctx.tenant_id, link_id=link.id, event_type="created"))
    if data.send_to is not None:
        tenant = await tenancy.get_tenant(ctx.session, ctx.tenant_id)
        shared = await content(ctx.session, storage, settings, link)
        message = await messaging.queue_email(
            ctx.session,
            tenant_id=ctx.tenant_id,
            event="document.shared",
            to=str(data.send_to.email),
            context={
                "recipient_name": data.send_to.name,
                "tenant_name": tenant.name,
                "sender_name": ctx.principal.name or tenant.name,
                "document_title": shared.title,
                "link_url": link_url(token, settings),
                "message": data.send_to.message,
            },
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            actor=ctx.principal.user_id,
        )
        ctx.session.add(
            LinkEvent(
                tenant_id=ctx.tenant_id,
                link_id=link.id,
                event_type="sent",
                details={"message_id": str(message.id)},
            )
        )
        link.sent_message_id = message.id
    await audit.record(
        ctx,
        "public_link.created",
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        changes={
            "link_id": str(link.id),
            "scopes": link.scopes,
            "expires_at": link.expires_at.isoformat(),
        },
    )
    return link, token


def link_url(token: str, settings: Settings) -> str:
    return f"{settings.public_base_url.rstrip('/')}/d/{token}"


async def list_links(
    session: AsyncSession, entity_type: str | None, entity_id: uuid.UUID | None
) -> list[PublicLink]:
    stmt = select(PublicLink).order_by(PublicLink.id.desc()).limit(200)
    if entity_type is not None:
        stmt = stmt.where(PublicLink.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(PublicLink.entity_id == entity_id)
    return list((await session.scalars(stmt)).all())


async def _get(session: AsyncSession, link_id: uuid.UUID) -> PublicLink:
    link = await session.get(PublicLink, link_id)
    if link is None:
        raise NotFoundError("Link not found")
    return link


async def revoke(ctx: TenantContext, link_id: uuid.UUID) -> PublicLink:
    link = await _get(ctx.session, link_id)
    if link.revoked_at is None:
        link.revoked_at = datetime.now(UTC)
        ctx.session.add(LinkEvent(tenant_id=ctx.tenant_id, link_id=link.id, event_type="revoked"))
        await audit.record(
            ctx,
            "public_link.revoked",
            entity_type=link.entity_type,
            entity_id=link.entity_id,
            changes={"link_id": str(link.id)},
        )
        await ctx.session.flush()
    return link


async def events(session: AsyncSession, link_id: uuid.UUID) -> list[LinkEvent]:
    await _get(session, link_id)
    stmt = (
        select(LinkEvent)
        .where(LinkEvent.link_id == link_id)
        .order_by(LinkEvent.id.desc())
        .limit(500)
    )
    return list((await session.scalars(stmt)).all())


# ---------------------------------------------------------------- anonymous side


async def resolve(session: AsyncSession, token: str) -> tuple[uuid.UUID, uuid.UUID]:
    """(tenant_id, link_id) for a token, before any tenant context exists."""
    if not _TOKEN_SHAPE.match(token):
        raise NotFoundError("Link not found")
    row = (
        await session.execute(
            text("SELECT tenant_id, link_id FROM app.resolve_public_link(:hash)"),
            {"hash": hash_token(token)},
        )
    ).first()
    if row is None:
        raise NotFoundError("Link not found")
    return row[0], row[1]


async def load_active(session: AsyncSession, link_id: uuid.UUID) -> PublicLink:
    link = await _get(session, link_id)
    if link.revoked_at is not None or link.expires_at <= datetime.now(UTC):
        raise LinkGoneError()
    return link


async def content(
    session: AsyncSession, storage: S3Storage, settings: Settings, link: PublicLink
) -> PublicContent:
    resolver = _TARGETS.get(link.entity_type)
    if resolver is None:  # pragma: no cover - creation refuses unknown types
        raise NotFoundError("Link not found")
    return await resolver(session, storage, settings, link)


async def record_event(
    session: AsyncSession,
    link: PublicLink,
    event_type: str,
    *,
    ip_hash: str | None,
    user_agent: str | None,
    details: dict[str, object] | None = None,
    storage: S3Storage | None = None,
    settings: Settings | None = None,
) -> None:
    bot = is_bot(user_agent)
    session.add(
        LinkEvent(
            tenant_id=link.tenant_id,
            link_id=link.id,
            event_type=event_type,
            ip_hash=ip_hash,
            user_agent=(user_agent or "")[:300] or None,
            is_bot=bot,
            details=details or {},
        )
    )
    if event_type == "viewed" and not bot:
        first_view = link.view_count == 0
        await session.execute(
            update(PublicLink)
            .where(PublicLink.id == link.id)
            .values(view_count=PublicLink.view_count + 1, last_viewed_at=datetime.now(UTC))
        )
        if first_view and link.created_by and storage is not None and settings is not None:
            title = (await content(session, storage, settings, link)).title
            await notifications.notify(
                session,
                settings,
                tenant_id=link.tenant_id,
                user_ids=[link.created_by],
                kind="link.viewed",
                title=f"Your client opened {title}",
                body="They viewed it just now.",
                link=f"/links/{link.id}",
            )


# ---------------------------------------------------------------- built-in target: documents


async def _document_target(
    session: AsyncSession, storage: S3Storage, settings: Settings, link: PublicLink
) -> PublicContent:
    document = await documents.get_document(session, link.entity_id)

    async def download() -> str:
        url = await documents.download_url(session, document.id, storage, settings, inline=True)
        return url.url

    return PublicContent(title=document.title, kind="document", download=download)


register_target("document", _document_target)
