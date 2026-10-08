"""Leads pipeline and conversion; tasks with timezone-aware due buckets and reminders; dashboard."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx

from app.core import db
from app.core.config import Settings
from app.core.tenancy import tenant_id_for_org
from app.modules.tasks import service as tasks
from tests.support import Org


async def test_lead_pipeline_and_conversion(api: httpx.AsyncClient, ready_org: Org) -> None:
    headers = ready_org.headers()
    assert (
        await api.post("/api/v1/leads", json={"name": "No contact"}, headers=headers)
    ).status_code == 422
    lead = (
        await api.post(
            "/api/v1/leads",
            json={
                "name": "Mercy Wambui",
                "phone": "0711 000 222",
                "source": "whatsapp",
                "interests": ["motor", "medical"],
                "estimated_premium": {"amount": "45000.00", "currency": "KES"},
            },
            headers=headers,
        )
    ).json()
    assert lead["stage"] == "new"
    assert lead["estimated_premium"] == {"amount": "45000.0000", "currency": "KES"}
    await api.post(
        "/api/v1/leads", json={"name": "Juma", "email": "juma@example.com"}, headers=headers
    )

    pipeline = (await api.get("/api/v1/leads/pipeline", headers=headers)).json()
    new = next(s for s in pipeline["stages"] if s["stage"] == "new")
    assert new["count"] == 2
    assert new["estimated_premium"] == {"amount": "45000.00", "currency": "KES"}

    url = f"/api/v1/leads/{lead['id']}"
    won = await api.patch(url, json={"stage": "won"}, headers=headers | {"If-Match": 'W/"1"'})
    assert won.status_code == 400  # must convert
    lost = await api.patch(url, json={"stage": "lost"}, headers=headers | {"If-Match": 'W/"1"'})
    assert lost.status_code == 400  # must say why

    converted = (await api.post(f"{url}/convert", json={}, headers=headers)).json()
    assert converted["lead"]["stage"] == "won"
    client = (await api.get(f"/api/v1/clients/{converted['client_id']}", headers=headers)).json()
    assert (client["first_name"], client["last_name"], client["source"]) == (
        "Mercy",
        "Wambui",
        "lead",
    )
    again = (await api.post(f"{url}/convert", json={}, headers=headers)).json()
    assert again["client_id"] == converted["client_id"]  # idempotent


async def test_assigning_a_lead_notifies_the_agent(api: httpx.AsyncClient, ready_org: Org) -> None:
    agent_id = f"{ready_org.org_id}-agent"
    agent_headers = ready_org.headers("agent")
    await api.get("/api/v1/me", headers=agent_headers)
    lead = (
        await api.post(
            "/api/v1/leads",
            json={"name": "Kiprop", "phone": "0700 111 999", "owner_user_id": agent_id},
            headers=ready_org.headers(),
        )
    ).json()
    notes = (await api.get("/api/v1/notifications", headers=agent_headers)).json()["items"]
    assert notes[0]["kind"] == "lead.assigned"
    assert [x["id"] for x in (await api.get("/api/v1/leads", headers=agent_headers)).json()] == [
        lead["id"]
    ]
    self_assign = await api.post(
        "/api/v1/leads",
        json={"name": "X", "phone": "0700 000 000", "owner_user_id": "someone-else"},
        headers=agent_headers,
    )
    assert self_assign.status_code == 403


def titles(response: httpx.Response) -> list[str]:
    return [t["title"] for t in response.json()]


async def test_task_buckets_use_agency_timezone(api: httpx.AsyncClient, ready_org: Org) -> None:
    headers = ready_org.headers()
    now = datetime.now(UTC)
    for title, due in (
        ("Overdue", now - timedelta(days=2)),
        ("Later", now + timedelta(days=3)),
        ("Someday", None),
    ):
        body = {"title": title} | ({"due_at": due.isoformat()} if due else {})
        assert (await api.post("/api/v1/tasks", json=body, headers=headers)).status_code == 201
    assert titles(await api.get("/api/v1/tasks?due=overdue", headers=headers)) == ["Overdue"]
    assert titles(await api.get("/api/v1/tasks?due=upcoming", headers=headers)) == ["Later"]
    assert titles(await api.get("/api/v1/tasks?due=none", headers=headers)) == ["Someday"]
    counts = (await api.get("/api/v1/tasks/counts", headers=headers)).json()
    assert counts["overdue"] == 1
    assert counts["upcoming"] == 1

    task = (await api.get("/api/v1/tasks?due=overdue", headers=headers)).json()[0]
    done = await api.patch(
        f"/api/v1/tasks/{task['id']}", json={"done": True}, headers=headers | {"If-Match": 'W/"1"'}
    )
    assert done.json()["status"] == "done"
    assert titles(await api.get("/api/v1/tasks?due=overdue", headers=headers)) == []


async def test_agents_see_their_own_tasks(api: httpx.AsyncClient, ready_org: Org) -> None:
    agent_headers = ready_org.headers("agent")
    await api.get("/api/v1/me", headers=agent_headers)
    await api.post("/api/v1/tasks", json={"title": "Owner's own"}, headers=ready_org.headers())
    mine = await api.post("/api/v1/tasks", json={"title": "Agent's"}, headers=agent_headers)
    assert [t["id"] for t in (await api.get("/api/v1/tasks", headers=agent_headers)).json()] == [
        mine.json()["id"]
    ]


async def test_due_tasks_are_reminded_once(
    api: httpx.AsyncClient, ready_org: Org, settings: Settings
) -> None:
    headers = ready_org.headers()
    due = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    task = (
        await api.post(
            "/api/v1/tasks", json={"title": "Call Otieno back", "due_at": due}, headers=headers
        )
    ).json()
    tenant_id = tenant_id_for_org(ready_org.org_id)
    engine = db.create_engine(settings)
    factory = db.create_session_factory(engine)
    try:
        async with db.session_scope(factory) as session:
            assert await tasks.enqueue_due_reminders(session) >= 1
        for expected in (True, False):  # second run does nothing
            async with db.tenant_scope(factory, tenant_id) as session:
                assert (
                    await tasks.remind(session, settings, tenant_id, uuid.UUID(task["id"]))
                    is expected
                )
    finally:
        await engine.dispose()
    notes = (await api.get("/api/v1/notifications", headers=headers)).json()["items"]
    assert [n["title"] for n in notes if n["kind"] == "task.due"] == ["Due: Call Otieno back"]


async def test_dashboard(api: httpx.AsyncClient, ready_org: Org) -> None:
    headers = ready_org.headers()
    await api.post(
        "/api/v1/clients",
        json={"first_name": "A", "last_name": "B", "phone": "0711 999 000"},
        headers=headers,
    )
    await api.post("/api/v1/leads", json={"name": "Lead", "phone": "0711 999 001"}, headers=headers)
    board = (await api.get("/api/v1/dashboard", headers=headers)).json()
    assert board["clients"] == 1
    assert board["new_clients_30d"] == 1
    assert next(s for s in board["pipeline"]["stages"] if s["stage"] == "new")["count"] == 1
    assert board["tasks"] == {"overdue": 0, "today": 0, "upcoming": 0}
    viewer = (await api.get("/api/v1/dashboard", headers=ready_org.headers("viewer"))).json()
    assert viewer["tasks"] is not None  # viewer has task:read:all
