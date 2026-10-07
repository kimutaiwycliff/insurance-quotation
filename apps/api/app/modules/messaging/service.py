"""Messaging service: queue emails in the business transaction, send them from a job (ADR-0024).

* From: "<Agency> via <product>" <shared address>; Reply-To: the agency (per-tenant domains come in R3).
* ``reminders`` stream: List-Unsubscribe + List-Unsubscribe-Post (RFC 8058) and the suppression list.
* Every message is logged in ``outbound_messages``; the job re-reads it and is idempotent.
"""

import base64
import hashlib
import hmac
import html
import json
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.integrations.email import EmailSender, EmailSendError, OutboundEmail
from app.integrations.email.fake import FakeSender
from app.integrations.email.smtp import SmtpSender
from app.modules.messaging import catalog
from app.modules.messaging.models import EmailSuppression, MessageTemplate, OutboundMessage
from app.modules.messaging.schemas import TemplateOut, TemplateOverride
from app.modules.tenancy import service as tenancy
from app.platform import audit, events
from app.platform.deps import TenantContext

logger = structlog.get_logger(__name__)

SEND_TASK = "messaging.send_email"
_SENT, _QUEUED, _FAILED, _SUPPRESSED = "sent", "queued", "failed", "suppressed"
_fake_sender = FakeSender()


class InvalidTemplateError(AppError):
    code = "invalid_template"
    title = "The message template does not render"


class UnknownEventError(NotFoundError):
    code = "unknown_message_event"
    title = "Unknown message event"


def sender_for(settings: Settings) -> EmailSender:
    return _fake_sender if settings.email_provider == "fake" else SmtpSender(settings)


def fake_outbox() -> FakeSender:
    return _fake_sender


# ---------------------------------------------------------------- unsubscribe tokens


def _sign(payload: bytes, settings: Settings) -> str:
    key = settings.signing_secret.get_secret_value().encode()
    return (
        base64.urlsafe_b64encode(hmac.new(key, payload, hashlib.sha256).digest()[:16])
        .rstrip(b"=")
        .decode()
    )


def unsubscribe_token(tenant_id: uuid.UUID, email: str, stream: str, settings: Settings) -> str:
    payload = json.dumps(
        {"t": str(tenant_id), "e": email.lower(), "s": stream}, separators=(",", ":")
    ).encode()
    body = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    return f"{body}.{_sign(payload, settings)}"


def read_unsubscribe_token(token: str, settings: Settings) -> tuple[uuid.UUID, str, str]:
    body, _, signature = token.partition(".")
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        if hmac.compare_digest(signature, _sign(payload, settings)):
            data = json.loads(payload)
            return uuid.UUID(data["t"]), str(data["e"]), str(data["s"])
    except ValueError, KeyError, TypeError:
        pass
    raise NotFoundError("Invalid unsubscribe link")


async def suppress(
    session: AsyncSession, tenant_id: uuid.UUID, email: str, stream: str, reason: str
) -> None:
    await session.execute(
        insert(EmailSuppression)
        .values(tenant_id=tenant_id, email=email, stream=stream, reason=reason)
        .on_conflict_do_nothing()
    )


async def _is_suppressed(session: AsyncSession, email: str, stream: str) -> bool:
    # Bounces and complaints block every stream; unsubscribes only the stream they came from.
    rows = (
        await session.scalars(select(EmailSuppression).where(EmailSuppression.email == email))
    ).all()
    return any(r.stream == stream or r.reason in {"bounced", "complaint"} for r in rows)


# ---------------------------------------------------------------- templates


async def _template(
    session: AsyncSession, event: str, locale: str
) -> tuple[catalog.EventTemplate, str, str, bool]:
    base = catalog.CATALOG.get(event)
    if base is None:
        raise UnknownEventError(f"No message template for {event!r}")
    override = await session.scalar(
        select(MessageTemplate).where(
            MessageTemplate.event == event,
            MessageTemplate.channel == "email",
            MessageTemplate.locale == locale,
        )
    )
    if override is not None:
        return base, override.subject, override.body, True
    return base, base.subject, base.body, False


async def list_templates(session: AsyncSession, locale: str = "en") -> list[TemplateOut]:
    out = []
    for event in catalog.CATALOG:
        base, subject, body, customised = await _template(session, event, locale)
        out.append(
            TemplateOut(
                event=event,
                description=base.description,
                stream=base.stream,
                locale=locale,
                subject=subject,
                body=body,
                variables=sorted(base.sample),
                customised=customised,
            )
        )
    return out


async def set_override(
    ctx: TenantContext, event: str, locale: str, data: TemplateOverride
) -> TemplateOut:
    base = catalog.CATALOG.get(event)
    if base is None:
        raise UnknownEventError(f"No message template for {event!r}")
    try:  # must render with the event's variables (and no others)
        catalog.render(data.subject, data.body, base.sample)
    except catalog.TemplateRenderError as exc:
        raise InvalidTemplateError(str(exc)) from None
    await ctx.session.execute(
        insert(MessageTemplate)
        .values(
            tenant_id=ctx.tenant_id,
            event=event,
            locale=locale,
            subject=data.subject,
            body=data.body,
            created_by=ctx.principal.user_id,
            updated_by=ctx.principal.user_id,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "event", "channel", "locale"],
            set_={
                "subject": data.subject,
                "body": data.body,
                "updated_by": ctx.principal.user_id,
                "version": MessageTemplate.version + 1,
                "updated_at": datetime.now(UTC),
            },
        )
    )
    await audit.record(
        ctx,
        "message_template.updated",
        entity_type="message_template",
        entity_id=f"{event}:{locale}",
    )
    return next(t for t in await list_templates(ctx.session, locale) if t.event == event)


async def reset_override(ctx: TenantContext, event: str, locale: str) -> None:
    row = await ctx.session.scalar(
        select(MessageTemplate).where(
            MessageTemplate.event == event, MessageTemplate.locale == locale
        )
    )
    if row is not None:
        await ctx.session.delete(row)
        await audit.record(
            ctx,
            "message_template.reset",
            entity_type="message_template",
            entity_id=f"{event}:{locale}",
        )


# ---------------------------------------------------------------- queue & send


async def queue_email(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    event: str,
    to: str,
    context: dict[str, str],
    locale: str = "en",
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor: str | None = None,
) -> OutboundMessage:
    """Render, log and enqueue an email in the caller's transaction (sent only if the transaction commits)."""
    base, subject_t, body_t, _ = await _template(session, event, locale)
    try:
        subject, body = catalog.render(subject_t, body_t, context)
    except catalog.TemplateRenderError:
        # A broken tenant override must never block business flows: fall back to the built-in template.
        logger.warning("message_template_fallback", event=event)
        subject, body = catalog.render(base.subject, base.body, context)
    suppressed = await _is_suppressed(session, to, base.stream)
    message = OutboundMessage(
        tenant_id=tenant_id,
        stream=base.stream,
        event=event,
        to_address=to,
        subject=subject,
        body_text=body,
        status=_SUPPRESSED if suppressed else _QUEUED,
        entity_type=entity_type,
        entity_id=entity_id,
        created_by=actor,
    )
    session.add(message)
    await session.flush()
    if not suppressed:
        await events.enqueue(
            session,
            SEND_TASK,
            {"tenant_id": str(tenant_id), "message_id": str(message.id)},
            queue="messaging",
            queueing_lock=f"email:{message.id}",
        )
    return message


def _html(text: str, unsubscribe_url: str | None) -> str:
    paragraphs = "".join(
        f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in text.split("\n\n") if p.strip()
    )
    footer = (
        f'<p style="color:#5b6470;font-size:12px"><a href="{html.escape(unsubscribe_url)}">Unsubscribe</a></p>'
        if unsubscribe_url
        else ""
    )
    return f'<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5">{paragraphs}{footer}</div>'


async def send_queued(
    session: AsyncSession, sender: EmailSender, settings: Settings, message_id: uuid.UUID
) -> str:
    """Send one queued message (job body). Idempotent: anything not queued is left alone."""
    message = await session.get(OutboundMessage, message_id, with_for_update=True)
    if message is None or message.status != _QUEUED:
        return message.status if message else "missing"
    tenant = await tenancy.get_tenant(session, message.tenant_id)
    headers: dict[str, str] = {"X-Entity-Ref-ID": str(message.id)}
    unsubscribe_url = None
    if message.stream == "reminders":
        token = unsubscribe_token(message.tenant_id, message.to_address, message.stream, settings)
        unsubscribe_url = (
            f"{settings.public_api_base_url.rstrip('/')}/api/v1/public/unsubscribe/{token}"
        )
        headers["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    email = OutboundEmail(
        to=message.to_address,
        subject=message.subject,
        text=message.body_text + (f"\n\nUnsubscribe: {unsubscribe_url}" if unsubscribe_url else ""),
        html=_html(message.body_text, unsubscribe_url),
        from_name=f"{tenant.name} via {settings.email_from_name}"[:120],
        from_address=settings.email_from_address,
        reply_to=tenant.email,
        headers=headers,
    )
    message.attempts += 1
    try:
        message.provider_message_id = await sender.send(email)
    except EmailSendError as exc:
        message.error = str(exc)[:500]
        message.status = _FAILED
        logger.warning("email_send_failed", message_id=str(message.id), error=message.error)
        return _FAILED
    message.status = _SENT
    message.sent_at = datetime.now(UTC)
    message.error = None
    return _SENT


async def list_messages(
    session: AsyncSession,
    *,
    cursor: uuid.UUID | None,
    limit: int,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
) -> list[OutboundMessage]:
    stmt = select(OutboundMessage).order_by(OutboundMessage.id.desc()).limit(limit + 1)
    if cursor is not None:
        stmt = stmt.where(OutboundMessage.id < cursor)
    if entity_type is not None:
        stmt = stmt.where(OutboundMessage.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(OutboundMessage.entity_id == entity_id)
    return list((await session.scalars(stmt)).all())
