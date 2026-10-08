"""Policy book: from quote or by hand, no premium no cover, recorded payments, remittance, renewals, reminders."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import text

from app.core import db
from app.core.config import Settings
from app.core.tenancy import tenant_id_for_org
from app.modules.policies import service as policies
from tests.integration.test_quotes import _quote, _setup
from tests.support import Org

pytestmark = pytest.mark.xdist_group("gotenberg")  # sending quotes renders PDFs


def _today() -> date:
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()


async def _sent_quote(api: httpx.AsyncClient, org: Org, setup: dict[str, Any]) -> dict[str, Any]:
    quote = await _quote(api, org, setup)
    sent = await api.post(f"/api/v1/quotes/{quote['id']}/send", json={}, headers=org.headers())
    assert sent.status_code == 200, sent.text
    return dict(sent.json())


async def _manual(api: httpx.AsyncClient, org: Org, client_id: str, **extra: Any) -> dict[str, Any]:
    body = {
        "client_id": client_id,
        "insurer_name": "Savanna General",
        "class_code": "motor_private",
        "description": "KDB 456B Mazda Demio",
        "start_date": str(_today() - timedelta(days=300)),
        "total_premium": "25000",
        **extra,
    }
    response = await api.post("/api/v1/policies", json=body, headers=org.headers())
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_quote_becomes_a_policy_only_with_premium(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    h = ready_org.headers()
    setup = await _setup(api, ready_org)
    sent = await _sent_quote(api, ready_org, setup)
    token = sent["url"].rsplit("/", 1)[1]
    await api.post(
        f"/api/v1/public/links/{token}/accept",
        json={"option": 1, "name": "Otieno Ochieng", "agree_terms": True},
    )
    created = await api.post(
        "/api/v1/policies/from-quote",
        json={"quote_id": sent["quote"]["id"], "start_date": str(_today())},
        headers=h,
    )
    assert created.status_code == 201, created.text
    policy = created.json()
    assert policy["status"] == "pending"
    assert policy["insurer_name"] == "Rift Assurance"
    assert policy["description"] == "KDA 123A, Toyota Axio 2019"
    assert policy["total_premium"] == "70355.00"
    assert policy["balance"] == "70355.00"
    assert policy["end_date"] == str(_today().replace(year=_today().year + 1) - timedelta(days=1))
    assert policy["commission"]["gross"] == "7000.00"
    assert policy["premium_exceptions"] == []  # motor: no premium, no cover
    again = await api.post(
        "/api/v1/policies/from-quote",
        json={"quote_id": sent["quote"]["id"], "start_date": str(_today())},
        headers=h,
    )
    assert again.json()["code"] == "policy_exists"

    url = f"/api/v1/policies/{policy['id']}"
    unpaid = await api.post(f"{url}/activate", json={"insurer_confirmed": True}, headers=h)
    assert unpaid.json()["code"] == "premium_not_paid"
    exception = await api.post(
        f"{url}/activate",
        json={
            "basis": "exception",
            "exception_id": "ke.r43.medical_instalments",
            "insurer_confirmed": True,
        },
        headers=h,
    )
    assert exception.json()["code"] == "premium_not_paid"  # not a medical policy
    paid = await api.post(
        f"{url}/payments",
        json={"amount": "70355", "paid_on": str(_today()), "reference": "SJK12AB34C"},
        headers=h,
    )
    assert paid.json()["payments"][0]["paid_to"] == "insurer"
    assert paid.json()["balance"] == "0.00"
    active = (await api.post(f"{url}/activate", json={"insurer_confirmed": True}, headers=h)).json()
    assert active["status"] == "active"
    assert active["activation"]["basis"] == "paid"
    patched = await api.patch(
        url,
        json={"policy_number": "RA/MP/2026/001"},
        headers=h | {"If-Match": f'W/"{active["version"]}"'},
    )
    assert patched.json()["policy_number"] == "RA/MP/2026/001"
    dates = await api.patch(
        url,
        json={"end_date": str(_today() + timedelta(days=30))},
        headers=h | {"If-Match": patched.headers["ETag"]},
    )
    assert dates.json()["code"] == "policy_state"

    # Accepted by phone: the agent records which option the client took.
    by_phone = await _sent_quote(api, ready_org, setup)
    policy2 = (
        await api.post(
            "/api/v1/policies/from-quote",
            json={
                "quote_id": by_phone["quote"]["id"],
                "option": 2,
                "start_date": str(_today()),
                "payment": {"amount": "80400", "paid_on": str(_today())},
                "insurer_confirmed": True,
            },
            headers=h,
        )
    ).json()
    assert policy2["insurer_name"] == "Savanna General"
    assert policy2["status"] == "active"
    quote = (await api.get(f"/api/v1/quotes/{by_phone['quote']['id']}", headers=h)).json()
    assert quote["status"] == "accepted"
    assert quote["accepted_position"] == 2
    link_token = by_phone["url"].rsplit("/", 1)[1]
    assert (await api.get(f"/api/v1/public/links/{link_token}")).status_code == 410

    listed = (await api.get("/api/v1/policies", params={"status": "active"}, headers=h)).json()
    assert {p["id"] for p in listed} == {policy["id"], policy2["id"]}
    found = (await api.get("/api/v1/policies", params={"q": "RA/MP"}, headers=h)).json()
    assert [p["id"] for p in found] == [policy["id"]]


async def test_agent_collected_premium_is_remitted_and_exceptions_apply(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    h = ready_org.headers()
    setup = await _setup(api, ready_org)
    client_id = setup["client"]["id"]
    policy = await _manual(
        api, ready_org, client_id, collection_mode="agent_collected", policy_number="SG/1"
    )
    url = f"/api/v1/policies/{policy['id']}"
    recorded = (
        await api.post(
            f"{url}/payments",
            json={"amount": "10000", "paid_on": str(_today()), "method": "cash"},
            headers=h,
        )
    ).json()
    payment = recorded["payments"][0]
    assert payment["paid_to"] == "agent"
    assert recorded["unremitted"] == "10000.00"
    assert recorded["balance"] == "15000.00"
    remit_tasks = (
        await api.get(
            "/api/v1/tasks", params={"entity_type": "policy", "entity_id": policy["id"]}, headers=h
        )
    ).json()
    assert remit_tasks[0]["title"].startswith("Remit KES 10,000.00 to Savanna General")
    assert (await api.get("/api/v1/dashboard", headers=h)).json()["premiums_to_remit"] == 1

    done = (
        await api.post(
            f"{url}/payments/{payment['id']}/remitted",
            json={"remitted_on": str(_today()), "reference": "EFT-778"},
            headers=h,
        )
    ).json()
    assert done["unremitted"] == "0.00"
    task = (
        await api.get(
            "/api/v1/tasks",
            params={"entity_type": "policy", "entity_id": policy["id"], "status": "all"},
            headers=h,
        )
    ).json()[0]
    assert task["status"] == "done"
    assert (await api.get("/api/v1/dashboard", headers=h)).json()["premiums_to_remit"] == 0

    voided = (
        await api.post(
            f"{url}/payments/{payment['id']}/void", json={"reason": "Wrong policy"}, headers=h
        )
    ).json()
    assert voided["paid"] == "0.00"
    assert voided["payments"][0]["void_reason"] == "Wrong policy"
    twice = await api.post(
        f"{url}/payments/{payment['id']}/void", json={"reason": "Again"}, headers=h
    )
    assert twice.json()["code"] == "policy_state"

    medical = await _manual(
        api,
        ready_org,
        client_id,
        class_code="medical_individual",
        description="Family medical: 4 members",
        start_date=str(_today()),
    )
    assert [e["id"] for e in medical["premium_exceptions"]] == ["ke.r43.medical_instalments"]
    active = (
        await api.post(
            f"/api/v1/policies/{medical['id']}/activate",
            json={
                "basis": "exception",
                "exception_id": "ke.r43.medical_instalments",
                "insurer_confirmed": True,
                "note": "Monthly instalments by M-Pesa",
            },
            headers=h,
        )
    ).json()
    assert active["status"] == "active"
    assert active["activation"]["source"].startswith("Insurance Regulations r.43")

    cancelled = (
        await api.post(f"{url}/cancel", json={"reason": "Client sold the car"}, headers=h)
    ).json()
    assert cancelled["status"] == "cancelled"
    late = await api.post(
        f"{url}/payments", json={"amount": "1", "paid_on": str(_today())}, headers=h
    )
    assert late.json()["code"] == "policy_state"


async def _run_reminder_job(settings: Settings, org: Org, policy_id: str) -> None:
    """The daily job reminds once for the 14-day offset (10 days left); a second run does nothing."""
    tenant_id = tenant_id_for_org(org.org_id)
    engine = db.create_engine(settings)
    factory = db.create_session_factory(engine)
    try:
        async with db.session_scope(factory) as session:
            assert await policies.enqueue_renewal_reminders(session) >= 1
        for expected in (True, False):
            async with db.tenant_scope(factory, tenant_id) as session:
                sent = await policies.send_renewal_reminder(
                    session, settings, tenant_id, uuid.UUID(policy_id), 14
                )
                assert sent is expected
        async with db.session_scope(factory) as session:
            due = await session.execute(
                text("SELECT policy_id FROM app.policies_due_for_renewal_reminder()")
            )
            assert uuid.UUID(policy_id) not in {r[0] for r in due}
    finally:
        await engine.dispose()


async def test_renewal_board_reminders_and_renewal(
    api: httpx.AsyncClient, ready_org: Org, settings: Settings
) -> None:
    h = ready_org.headers()
    setup = await _setup(api, ready_org)
    client_id = setup["client"]["id"]
    expiring = await _manual(
        api,
        ready_org,
        client_id,
        start_date=str(_today() - timedelta(days=355)),
        end_date=str(_today() + timedelta(days=10)),
        payment={"amount": "25000", "paid_on": str(_today() - timedelta(days=355))},
        insurer_confirmed=True,
        details=[{"label": "Vehicle", "value": "KDB 456B Mazda Demio"}],
    )
    assert expiring["status"] == "active"
    assert expiring["days_to_expiry"] == 10
    far = await _manual(
        api,
        ready_org,
        client_id,
        start_date=str(_today()),
        payment={"amount": "25000", "paid_on": str(_today())},
        insurer_confirmed=True,
    )

    board = (await api.get("/api/v1/renewals", headers=h)).json()
    assert [i["id"] for i in board["items"]] == [expiring["id"]]
    item = board["items"][0]
    assert item["whatsapp_url"].startswith("https://wa.me/254711000777?text=Hello%20Otieno")
    assert next(c for c in board["columns"] if c["stage"] == "due") == {
        "stage": "due",
        "count": 1,
        "premium": "25000.00",
    }
    assert (await api.get("/api/v1/dashboard", headers=h)).json()["renewals_due_30d"] == 1

    # The daily job reminds the owner once for the 14-day offset (10 days left), and emails the client
    # only when the agency has switched that on.
    etag = (await api.get("/api/v1/organization", headers=h)).headers["ETag"]
    org = await api.patch(
        "/api/v1/organization",
        json={"renewal_client_emails": True, "renewal_reminder_days": [7, 30, 14, 14]},
        headers=h | {"If-Match": etag},
    )
    assert org.json()["renewal_reminder_days"] == [30, 14, 7]
    await _run_reminder_job(settings, ready_org, expiring["id"])
    notes = (await api.get("/api/v1/notifications", headers=h)).json()["items"]
    assert any(
        n["kind"] == "policy.renewal_due" and "expires in 10 days" in n["title"] for n in notes
    )
    messages = (await api.get("/api/v1/messages", headers=h)).json()["items"]
    renewal_mail = [m for m in messages if m["event"] == "policy.renewal_due"]
    assert [m["to_address"] for m in renewal_mail] == ["otieno@example.com"]

    # The agent follows up on WhatsApp: logged on the client's timeline, stage moves to contacted.
    reminded = (
        await api.post(
            f"/api/v1/policies/{expiring['id']}/remind", json={"channel": "whatsapp"}, headers=h
        )
    ).json()
    assert reminded["whatsapp_url"].startswith("https://wa.me/")
    assert reminded["policy"]["renewal_stage"] == "contacted"
    activities = (await api.get(f"/api/v1/clients/{client_id}/activities", headers=h)).json()
    assert any("Renewal reminder" in a["body"] for a in activities)

    lost = await api.post(
        f"/api/v1/policies/{far['id']}/renewal", json={"stage": "lost"}, headers=h
    )
    assert lost.json()["code"] == "reason_required"

    # Renewal quote → accepted by phone → new policy linked to the old one.
    quote = await api.post(
        f"/api/v1/policies/{expiring['id']}/renewal-quote",
        json={"product_ids": [setup["products"][0]["id"]], "risk": {"sum_insured": "1500000"}},
        headers=h,
    )
    assert quote.status_code == 201, quote.text
    assert quote.json()["title"] == "Renewal: KDB 456B Mazda Demio"
    assert quote.json()["details"] == [{"label": "Vehicle", "value": "KDB 456B Mazda Demio"}]
    quote_id = quote.json()["id"]
    board = (await api.get("/api/v1/renewals", headers=h)).json()
    assert board["items"][0]["renewal_stage"] == "quoted"
    assert board["items"][0]["renewal_quote_status"] == "draft"
    await api.post(f"/api/v1/quotes/{quote_id}/send", json={}, headers=h)
    renewed = (
        await api.post(
            "/api/v1/policies/from-quote",
            json={
                "quote_id": quote_id,
                "option": 1,
                "start_date": str(_today() + timedelta(days=11)),
            },
            headers=h,
        )
    ).json()
    assert renewed["renewed_from_id"] == expiring["id"]
    old = (await api.get(f"/api/v1/policies/{expiring['id']}", headers=h)).json()
    assert old["renewal_stage"] == "renewed"
    assert old["renewed_to_id"] == renewed["id"]
    closed = await api.post(
        f"/api/v1/policies/{expiring['id']}/remind", json={"channel": "email"}, headers=h
    )
    assert closed.json()["code"] == "policy_state"


async def test_policy_scoping_and_permissions(
    api: httpx.AsyncClient, ready_org: Org, other_org: Org
) -> None:
    setup = await _setup(api, ready_org)
    policy = await _manual(api, ready_org, setup["client"]["id"])
    url = f"/api/v1/policies/{policy['id']}"

    agent = ready_org.headers("agent")
    await api.get("/api/v1/me", headers=agent)
    assert (await api.get(url, headers=agent)).status_code == 404  # not the agent's client
    assert (await api.get("/api/v1/policies", headers=agent)).json() == []
    assert (await api.get("/api/v1/renewals", headers=agent)).json()["items"] == []

    assistant = ready_org.headers("assistant")
    await api.get("/api/v1/me", headers=assistant)
    assert (await api.get(url, headers=assistant)).json()["commission"] is None
    blocked = await api.post(
        f"{url}/payments", json={"amount": "1", "paid_on": str(_today())}, headers=assistant
    )
    assert blocked.status_code == 403  # no money for assistants

    accounts = ready_org.headers("accounts")
    await api.get("/api/v1/me", headers=accounts)
    assert (
        await api.post(
            f"{url}/payments", json={"amount": "1", "paid_on": str(_today())}, headers=accounts
        )
    ).status_code == 200

    await api.get("/api/v1/me", headers=other_org.headers())
    assert (await api.get(url, headers=other_org.headers())).status_code == 404
    bad_client = await api.post(
        "/api/v1/policies",
        json={
            "client_id": setup["client"]["id"],
            "insurer_name": "X",
            "class_code": "motor_private",
            "start_date": str(_today()),
            "total_premium": "1",
        },
        headers=other_org.headers(),
    )
    assert bad_client.status_code == 404
    floats = await api.post(
        "/api/v1/policies",
        json={
            "client_id": setup["client"]["id"],
            "insurer_name": "X",
            "class_code": "motor_private",
            "start_date": str(_today()),
            "total_premium": 1.5,
        },
        headers=ready_org.headers(),
    )
    assert floats.status_code == 422
