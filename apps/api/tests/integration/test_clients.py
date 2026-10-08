"""Clients: encrypted IDs, duplicate detection, agent scoping, search, households, contacts, timeline."""

import uuid
from typing import Any

import httpx
import psycopg

from app.core.tenancy import tenant_id_for_org
from tests.integration.m2_helpers import PDF_BYTES, upload
from tests.support import Org


def wanjiku(**extra: Any) -> dict[str, Any]:
    return {
        "first_name": "Wanjiku",
        "last_name": "Kamau",
        "phone": f"07{uuid.uuid4().int % 10**8:08d}",
        **extra,
    }


async def _create(api: httpx.AsyncClient, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    response = await api.post("/api/v1/clients", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def agent(org: Org, n: int) -> dict[str, str]:
    return org.headers("agent", user_id=f"{org.org_id}-agent{n}")


async def test_create_normalises_and_encrypts(
    api: httpx.AsyncClient, ready_org: Org, owner_conn: psycopg.AsyncConnection
) -> None:
    created = await _create(
        api,
        ready_org.headers(),
        **wanjiku(
            phone="0712 345 678",
            kra_pin="a012345678z",
            id_number="12 345 678",
            tags=["VIP", "motor"],
            address={"town": "Nairobi"},
        ),
    )
    assert created["display_name"] == "Wanjiku Kamau"
    assert created["phone"] == "+254712345678"
    assert created["kra_pin"] == "A012345678Z"
    assert created["id_number_hint"] == "•••••678"
    assert created["id_type"] == "national_id"
    assert created["tags"] == ["vip", "motor"]
    assert "id_number" not in created

    await owner_conn.execute(
        "SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id_for_org(ready_org.org_id)),)
    )
    row = await (
        await owner_conn.execute(
            "SELECT id_number_enc, id_number_hash FROM app.clients WHERE id = %s", (created["id"],)
        )
    ).fetchone()
    assert row is not None
    assert "12345678" not in row[0]  # only ciphertext at rest
    assert len(row[1]) == 64

    revealed = await api.post(
        f"/api/v1/clients/{created['id']}/id-number", headers=ready_org.headers()
    )
    assert revealed.json() == {"id_number": "12 345 678"}
    trail = (
        await api.get(
            f"/api/v1/audit-events?entity_id={created['id']}", headers=ready_org.headers()
        )
    ).json()
    assert "client.id_number_viewed" in {e["action"] for e in trail["items"]}


async def test_validation(api: httpx.AsyncClient, ready_org: Org) -> None:
    for body in (
        {"first_name": "Only"},
        {"kind": "corporate"},
        {"first_name": "A", "last_name": "B", "phone": "12"},
        {"first_name": "A", "last_name": "B", "kra_pin": "123"},
        {"first_name": "A", "last_name": "B", "date_of_birth": "2999-01-01"},
    ):
        response = await api.post("/api/v1/clients", json=body, headers=ready_org.headers())
        assert response.status_code == 422, body


async def test_duplicates(api: httpx.AsyncClient, ready_org: Org) -> None:
    headers = ready_org.headers()
    first = await _create(api, headers, **wanjiku(phone="0722 000 111", id_number="A1234567"))
    again = await api.post("/api/v1/clients", json=wanjiku(phone="+254722000111"), headers=headers)
    assert again.status_code == 409
    assert again.json()["code"] == "possible_duplicate"
    assert "Wanjiku Kamau" in again.json()["detail"]

    check = (
        await api.post(
            "/api/v1/clients/duplicates",
            json={"phone": "722000111", "id_number": "a-1234567"},
            headers=headers,
        )
    ).json()
    assert check["matches"][0]["client"]["id"] == first["id"]
    assert set(check["matches"][0]["matched_on"]) == {"phone", "id_number"}

    forced = await api.post(
        "/api/v1/clients", json=wanjiku(phone="0722000111", allow_duplicate=True), headers=headers
    )
    assert forced.status_code == 201


async def test_agents_see_only_their_own_book(api: httpx.AsyncClient, ready_org: Org) -> None:
    a1, a2 = agent(ready_org, 1), agent(ready_org, 2)
    for h in (a1, a2):
        assert (await api.get("/api/v1/me", headers=h)).status_code == 200
    mine = await _create(api, a1, **wanjiku(phone="0733 111 222"))
    theirs = await _create(api, a2, **wanjiku(first_name="Achieng", phone="0733 111 333"))

    listed = {c["id"] for c in (await api.get("/api/v1/clients", headers=a1)).json()["items"]}
    assert mine["id"] in listed
    assert theirs["id"] not in listed
    assert (await api.get(f"/api/v1/clients/{theirs['id']}", headers=a1)).status_code == 404

    hidden = (
        await api.post("/api/v1/clients/duplicates", json={"phone": "0733111333"}, headers=a1)
    ).json()
    assert hidden == {"matches": [], "hidden": 1}  # told it exists, not whose

    owner_view = {
        c["id"]
        for c in (await api.get("/api/v1/clients", headers=ready_org.headers())).json()["items"]
    }
    assert {mine["id"], theirs["id"]} <= owner_view

    steal = await api.patch(
        f"/api/v1/clients/{mine['id']}",
        json={"owner_user_id": f"{ready_org.org_id}-agent2"},
        headers=a1 | {"If-Match": 'W/"1"'},
    )
    assert steal.status_code == 403
    moved = await api.patch(
        f"/api/v1/clients/{mine['id']}",
        json={"owner_user_id": f"{ready_org.org_id}-agent2"},
        headers=ready_org.headers() | {"If-Match": 'W/"1"'},
    )
    assert moved.status_code == 200
    assert (await api.get(f"/api/v1/clients/{mine['id']}", headers=a1)).status_code == 404
    bad = await api.post(
        "/api/v1/clients", json=wanjiku(owner_user_id="nobody"), headers=ready_org.headers()
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "invalid_owner"


async def test_search(api: httpx.AsyncClient, ready_org: Org) -> None:
    headers = ready_org.headers()
    client = await _create(
        api,
        headers,
        first_name="Otieno",
        last_name="Ochieng",
        phone="0711 222 333",
        kra_pin="A111222333B",
        id_number="29876543",
        email="otieno@example.com",
    )
    await _create(api, headers, first_name="Someone", last_name="Else", phone="0799 888 777")
    for q in (
        "otien",
        "Ochieng",
        "0711222333",
        "+254 711 222 333",
        "a111222333b",
        "29876543",
        "otieno@example",
    ):
        found = [
            c["id"]
            for c in (await api.get("/api/v1/clients", params={"q": q}, headers=headers)).json()[
                "items"
            ]
        ]
        assert found == [client["id"]], q


async def test_update_archive_and_concurrency(api: httpx.AsyncClient, ready_org: Org) -> None:
    headers = ready_org.headers()
    client = await _create(api, headers, **wanjiku(id_number="11112222"))
    url = f"/api/v1/clients/{client['id']}"
    updated = await api.patch(
        url, json={"last_name": "Njeri", "id_number": None}, headers=headers | {"If-Match": 'W/"1"'}
    )
    assert updated.json()["display_name"] == "Wanjiku Njeri"
    assert updated.json()["id_number_hint"] is None
    stale = await api.patch(url, json={"notes": "x"}, headers=headers | {"If-Match": 'W/"1"'})
    assert stale.status_code == 412
    archived = await api.patch(
        url, json={"archived": True}, headers=headers | {"If-Match": updated.headers["ETag"]}
    )
    assert archived.json()["status"] == "archived"
    active = {c["id"] for c in (await api.get("/api/v1/clients", headers=headers)).json()["items"]}
    assert client["id"] not in active


async def test_households_contacts_and_timeline(api: httpx.AsyncClient, ready_org: Org) -> None:
    headers = ready_org.headers()
    household = (
        await api.post("/api/v1/households", json={"name": "Kamau family"}, headers=headers)
    ).json()
    head = await _create(
        api, headers, **wanjiku(household_id=household["id"], household_role="head")
    )
    await _create(
        api,
        headers,
        **wanjiku(first_name="Baraka", household_id=household["id"], household_role="child"),
    )
    detail = (await api.get(f"/api/v1/households/{household['id']}", headers=headers)).json()
    assert len(detail["members"]) == 2

    individual_contact = await api.post(
        f"/api/v1/clients/{head['id']}/contacts", json={"name": "HR"}, headers=headers
    )
    assert individual_contact.status_code == 400
    company = await _create(
        api, headers, kind="corporate", company_name="Lakeside Logistics Ltd", phone="0720 123 456"
    )
    contact = await api.post(
        f"/api/v1/clients/{company['id']}/contacts",
        json={
            "name": "Amina Hassan",
            "role": "Finance",
            "phone": "0733 000 001",
            "is_primary": True,
        },
        headers=headers,
    )
    assert contact.json()["phone"] == "+254733000001"

    await api.post(
        f"/api/v1/clients/{head['id']}/activities",
        json={"kind": "call", "body": "Asked about medical cover"},
        headers=headers,
    )
    await upload(
        api,
        ready_org,
        "id-card.pdf",
        PDF_BYTES,
        links=[{"entity_type": "client", "entity_id": head["id"]}],
    )
    await api.post(
        "/api/v1/tasks",
        json={"title": "Send medical quote", "entity_type": "client", "entity_id": head["id"]},
        headers=headers,
    )
    kinds = [
        i["kind"]
        for i in (await api.get(f"/api/v1/clients/{head['id']}/timeline", headers=headers)).json()
    ]
    assert {"activity", "document", "task", "change"} <= set(kinds)


async def test_isolation_between_agencies(
    api: httpx.AsyncClient, ready_org: Org, other_org: Org
) -> None:
    client = await _create(api, ready_org.headers(), **wanjiku())
    for path in (f"/api/v1/clients/{client['id']}", f"/api/v1/clients/{client['id']}/timeline"):
        assert (await api.get(path, headers=other_org.headers())).status_code == 404
    check = (
        await api.post(
            "/api/v1/clients/duplicates",
            json={"phone": client["phone"]},
            headers=other_org.headers(),
        )
    ).json()
    assert check == {"matches": [], "hidden": 0}
