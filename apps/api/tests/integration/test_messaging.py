"""Email: queue in the transaction, send via SMTP to Mailpit, headers, suppression, templates; notifications."""

import os
import uuid

import httpx

from app.core import db
from app.core.config import Settings
from app.core.tenancy import tenant_id_for_org
from app.integrations.email.smtp import SmtpSender
from app.modules.messaging import service as messaging
from tests.integration.m2_helpers import PDF_BYTES, upload
from tests.support import Org

MAILPIT = os.environ.get("MAILPIT_API_URL", "http://mailpit:8025")


async def _send(settings: Settings, org: Org, message_id: str) -> str:
    engine = db.create_engine(settings)
    try:
        async with db.tenant_scope(
            db.create_session_factory(engine), tenant_id_for_org(org.org_id)
        ) as session:
            return await messaging.send_queued(
                session, SmtpSender(settings), settings, uuid.UUID(message_id)
            )
    finally:
        await engine.dispose()


async def _mail_to(address: str) -> dict[str, object]:
    async with httpx.AsyncClient() as http:
        found = (
            await http.get(f"{MAILPIT}/api/v1/search", params={"query": f"to:{address}"})
        ).json()
        assert found["messages"], f"no mail to {address}"
        message_id = found["messages"][0]["ID"]
        message = (await http.get(f"{MAILPIT}/api/v1/message/{message_id}")).json()
        headers = (await http.get(f"{MAILPIT}/api/v1/message/{message_id}/headers")).json()
    return {"message": message, "headers": headers}


async def test_shared_link_is_emailed_from_the_agency(
    api: httpx.AsyncClient, ready_org: Org, settings: Settings
) -> None:
    headers = ready_org.headers()
    etag = (await api.get("/api/v1/organization", headers=headers)).headers["ETag"]
    await api.patch(
        "/api/v1/organization",
        json={"email": "office@wanjiku.co.ke"},
        headers=headers | {"If-Match": etag},
    )
    doc = await upload(api, ready_org, "quote.pdf", PDF_BYTES, title="Quotation QT-7")
    client_email = f"client-{uuid.uuid4().hex[:8]}@example.com"
    link = (
        await api.post(
            "/api/v1/public-links",
            json={
                "entity_type": "document",
                "entity_id": doc["id"],
                "send_to": {"email": client_email, "name": "Otieno", "message": "As discussed."},
            },
            headers=headers,
        )
    ).json()
    assert link["message_id"]

    log = (await api.get("/api/v1/messages", headers=headers)).json()["items"]
    assert log[0]["status"] == "queued"
    assert await _send(settings, ready_org, link["message_id"]) == "sent"
    assert (
        await _send(settings, ready_org, link["message_id"]) == "sent"
    )  # idempotent: not sent twice

    mail = await _mail_to(client_email)
    message = mail["message"]
    assert isinstance(message, dict)
    assert message["Subject"] == "Quotation QT-7 from Test Agency"
    assert message["From"]["Name"] == "Test Agency via BrokerOS"
    assert message["ReplyTo"][0]["Address"] == "office@wanjiku.co.ke"
    assert link["url"] in message["Text"]
    assert "As discussed." in message["Text"]
    assert "List-Unsubscribe" not in dict(mail["headers"])  # type: ignore[call-overload]  # transactional

    events = (await api.get(f"/api/v1/public-links/{link['id']}/events", headers=headers)).json()
    assert "sent" in {e["event_type"] for e in events}


async def test_reminders_carry_one_click_unsubscribe(
    api: httpx.AsyncClient, ready_org: Org, settings: Settings
) -> None:
    tenant_id = tenant_id_for_org(ready_org.org_id)
    to = f"reminder-{uuid.uuid4().hex[:8]}@example.com"
    context = {
        "recipient_name": "Otieno",
        "tenant_name": "Test Agency",
        "document_title": "licence",
        "expires_on": "30 Nov 2026",
    }
    engine = db.create_engine(settings)
    try:
        factory = db.create_session_factory(engine)
        async with db.tenant_scope(factory, tenant_id) as session:
            message = await messaging.queue_email(
                session, tenant_id=tenant_id, event="document.expiring", to=to, context=context
            )
        assert await _send(settings, ready_org, str(message.id)) == "sent"

        mail = await _mail_to(to)
        headers = mail["headers"]
        assert isinstance(headers, dict)
        assert headers["List-Unsubscribe-Post"] == ["List-Unsubscribe=One-Click"]
        unsubscribe_url = headers["List-Unsubscribe"][0].strip("<>")
        path = unsubscribe_url.split("://", 1)[1].split("/", 1)[1]

        page = await api.get(f"/{path}")
        assert page.status_code == 200
        assert "<form" in page.text
        done = await api.post(f"/{path}", content="List-Unsubscribe=One-Click")
        assert done.status_code == 200
        assert (await api.post(f"/{path[:-3]}xyz")).status_code == 404  # forged

        async with db.tenant_scope(factory, tenant_id) as session:
            again = await messaging.queue_email(
                session, tenant_id=tenant_id, event="document.expiring", to=to, context=context
            )
            transactional = await messaging.queue_email(
                session,
                tenant_id=tenant_id,
                event="test.email",
                to=to,
                context={"recipient_name": "Otieno", "tenant_name": "Test Agency"},
            )
        assert again.status == "suppressed"  # unsubscribed from reminders...
        assert transactional.status == "queued"  # ...but still gets what they ask for
    finally:
        await engine.dispose()


async def test_template_overrides(
    api: httpx.AsyncClient, ready_org: Org, settings: Settings
) -> None:
    headers = ready_org.headers()
    bad = await api.put(
        "/api/v1/message-templates/test.email/en",
        json={"subject": "Hi {{ unknown }}", "body": "x"},
        headers=headers,
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == "invalid_template"
    good = await api.put(
        "/api/v1/message-templates/test.email/en",
        json={"subject": "Habari {{ recipient_name }}", "body": "Karibu {{ tenant_name }}"},
        headers=headers,
    )
    assert good.json()["customised"] is True
    sent = (await api.post("/api/v1/messages/test-email", headers=headers)).json()
    assert sent["subject"].startswith("Habari")
    assert (
        await api.delete("/api/v1/message-templates/test.email/en", headers=headers)
    ).status_code == 204
    listed = {
        t["event"]: t for t in (await api.get("/api/v1/message-templates", headers=headers)).json()
    }
    assert listed["test.email"]["customised"] is False
    assert (
        await api.put(
            "/api/v1/message-templates/nope/en", json={"subject": "a", "body": "b"}, headers=headers
        )
    ).status_code == 404
    agent = await api.put(
        "/api/v1/message-templates/test.email/en",
        json={"subject": "a", "body": "b"},
        headers=ready_org.headers("agent"),
    )
    assert agent.status_code == 403


async def test_notifications_are_private_and_preferences_apply(
    api: httpx.AsyncClient, ready_org: Org, settings: Settings
) -> None:
    from app.modules.notifications import service as notifications  # noqa: PLC0415

    agent_headers = ready_org.headers("agent")
    await api.get("/api/v1/me", headers=agent_headers)
    agent_id = f"{ready_org.org_id}-agent"
    prefs = await api.put(
        "/api/v1/notification-preferences",
        json=[{"kind": "member.joined", "in_app": True, "email": True}],
        headers=agent_headers,
    )
    assert next(p for p in prefs.json() if p["kind"] == "member.joined")["email"] is True

    tenant_id = tenant_id_for_org(ready_org.org_id)
    engine = db.create_engine(settings)
    try:
        async with db.tenant_scope(db.create_session_factory(engine), tenant_id) as session:
            created = await notifications.notify(
                session,
                settings,
                tenant_id=tenant_id,
                user_ids=[agent_id, "not-a-member"],
                kind="member.joined",
                title="Achieng joined",
                link="/settings/members",
            )
    finally:
        await engine.dispose()
    assert created == 1

    mine = (await api.get("/api/v1/notifications", headers=agent_headers)).json()["items"]
    assert [n["title"] for n in mine] == ["Achieng joined"]
    assert (await api.get("/api/v1/notifications", headers=ready_org.headers())).json()[
        "items"
    ] == []
    owner_try = await api.post(
        f"/api/v1/notifications/{mine[0]['id']}/read", headers=ready_org.headers()
    )
    assert owner_try.status_code == 404  # cannot touch someone else's notification
    assert (await api.get("/api/v1/notifications/unread-count", headers=agent_headers)).json() == {
        "unread": 1
    }
    assert (
        await api.post(f"/api/v1/notifications/{mine[0]['id']}/read", headers=agent_headers)
    ).status_code == 204
    assert (await api.get("/api/v1/notifications/unread-count", headers=agent_headers)).json() == {
        "unread": 0
    }
    emails = (await api.get("/api/v1/messages", headers=ready_org.headers())).json()["items"]
    assert any(m["event"] == "notification.email" for m in emails)  # email preference honoured
