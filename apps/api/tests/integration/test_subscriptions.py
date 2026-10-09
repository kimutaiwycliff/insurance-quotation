"""Plans (docs/PRICING.md): trial, prices with the founding discount, paying by M-Pesa (simulator), Free limits,
read-only after a lapsed period, seats."""

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import psycopg
import time_machine

from app.core.tenancy import tenant_id_for_org
from tests.support import Org, new_id


async def _sql(owner_conn: psycopg.AsyncConnection, org: Org, statement: str, *args: Any) -> None:
    await owner_conn.execute(
        "SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id_for_org(org.org_id)),)
    )
    await owner_conn.execute(statement, args)


async def _client(api: httpx.AsyncClient, org: Org, n: int) -> httpx.Response:
    return await api.post(
        "/api/v1/clients",
        json={"first_name": "Client", "last_name": f"Number{n}", "phone": f"0711 {100000 + n}"},
        headers=org.headers(),
    )


async def test_trial_prices_and_paying_by_mpesa(api: httpx.AsyncClient, ready_org: Org) -> None:
    h = ready_org.headers()
    me = (await api.get("/api/v1/me", headers=h)).json()
    assert (me["plan"], me["read_only"]) == ("agency", False)  # 30 days of everything
    assert "commission" in me["features"]
    sub = (await api.get("/api/v1/subscription", headers=h)).json()
    assert sub["status"] == "trialing"
    assert sub["paid_plan"] == "free"
    assert 29 <= (datetime.fromisoformat(sub["trial_ends_at"]) - datetime.now(UTC)).days <= 30
    assert sub["usage"] == {"clients": 0, "documents_this_month": 0, "seats_used": 1}

    plans = {p["code"]: p for p in (await api.get("/api/v1/subscription/plans", headers=h)).json()}
    assert set(plans) == {"free", "agent", "agency", "business"}
    agent = {p["cycle"]: p for p in plans["agent"]["prices"]}
    assert (agent["monthly"]["list_price"], agent["monthly"]["price"]) == (
        "1500",
        "750",
    )  # founding 50%
    assert agent["yearly"]["list_price"] == "15000"
    assert plans["free"]["limits"] == {"clients": 50, "documents_per_month": 10}
    assert "insurance" not in plans["business"]["features"]

    paid = await api.post(
        "/api/v1/subscription/checkout",
        json={"plan": "agent", "cycle": "monthly", "phone": "0712 345 678"},
        headers=h,
    )
    assert paid.status_code == 201, paid.text
    payment = paid.json()
    assert (payment["status"], payment["amount"], payment["discount_percent"]) == (
        "pending",
        "750",
        50,
    )
    again = await api.post(
        "/api/v1/subscription/checkout",
        json={"plan": "agent", "cycle": "monthly", "phone": "0712 345 678"},
        headers=h,
    )
    assert again.status_code == 409  # one prompt at a time
    with time_machine.travel(datetime.now(ZoneInfo("Africa/Nairobi")) + timedelta(seconds=15)):
        done = (
            await api.get(
                f"/api/v1/subscription/payments/{payment['id']}", headers=ready_org.headers()
            )
        ).json()
    assert done["status"] == "paid"
    assert done["receipt"].startswith("SIM")
    sub = (await api.get("/api/v1/subscription", headers=h)).json()
    assert (sub["plan"], sub["status"], sub["founding_member"], sub["discount_percent"]) == (
        "agent",
        "active",
        True,
        50,
    )
    assert sub["period_end"] >= str(datetime.now(UTC).date() + timedelta(days=27))
    me = (await api.get("/api/v1/me", headers=h)).json()
    assert me["plan"] == "agent"
    assert "team" not in me["features"]


async def test_free_plan_features_and_limits(
    api: httpx.AsyncClient, ready_org: Org, owner_conn: psycopg.AsyncConnection
) -> None:
    h = ready_org.headers()
    await _sql(
        owner_conn,
        ready_org,
        "UPDATE app.subscriptions SET trial_ends_at = now() - interval '1 day'",
    )
    me = (await api.get("/api/v1/me", headers=h)).json()
    assert me["plan"] == "free"
    assert (await api.get("/api/v1/insurers", headers=h)).status_code == 200  # insurance is in Free
    blocked = await api.get("/api/v1/commissions/summary", headers=h)
    assert (blocked.status_code, blocked.json()["code"]) == (402, "plan_feature")
    assert (
        await api.patch("/api/v1/branding", json={"primary_color": "#123456"}, headers=h)
    ).status_code == 402
    etag = (await api.get("/api/v1/organization", headers=h)).headers["ETag"]
    emails = await api.patch(
        "/api/v1/organization", json={"renewal_client_emails": True}, headers=h | {"If-Match": etag}
    )
    assert emails.json()["code"] == "plan_feature"

    for n in range(50):
        assert (await _client(api, ready_org, n)).status_code == 201
    over = await _client(api, ready_org, 50)
    assert (over.status_code, over.json()["code"]) == (402, "plan_limit")
    assert "50 clients" in over.json()["detail"]

    client_id = (await api.get("/api/v1/clients", params={"limit": 1}, headers=h)).json()["items"][
        0
    ]["id"]
    line = {"description": "Service", "quantity": "1", "unit_price": "100", "tax_code": "exempt"}
    for n in range(11):
        draft = (
            await api.post(
                "/api/v1/invoices", json={"client_id": client_id, "lines": [line]}, headers=h
            )
        ).json()
        issued = await api.post(
            f"/api/v1/billing-documents/{draft['id']}/issue", json={}, headers=h
        )
        assert issued.status_code == (200 if n < 10 else 402), (n, issued.text)


async def test_lapsed_subscription_is_read_only_until_renewed(
    api: httpx.AsyncClient, ready_org: Org, owner_conn: psycopg.AsyncConnection
) -> None:
    h = ready_org.headers()
    await _sql(
        owner_conn,
        ready_org,
        "UPDATE app.subscriptions SET plan = 'agent', trial_ends_at = NULL, current_period_end = %s",
        datetime.now(UTC).date() - timedelta(days=10),
    )
    me = (await api.get("/api/v1/me", headers=h)).json()
    assert me["read_only"] is True
    refused = await _client(api, ready_org, 1)
    assert (refused.status_code, refused.json()["code"]) == (402, "subscription_inactive")
    assert (await api.get("/api/v1/clients", headers=h)).status_code == 200  # reading still works
    assert (await api.get("/api/v1/subscription", headers=h)).json()["status"] == "read_only"
    renew = await api.post(
        "/api/v1/subscription/checkout", json={"plan": "agent", "phone": "0712345678"}, headers=h
    )
    assert renew.status_code == 201  # paying is allowed while read-only

    await _sql(
        owner_conn,
        ready_org,
        "UPDATE app.subscriptions SET current_period_end = %s",
        datetime.now(UTC).date() - timedelta(days=3),
    )
    assert (await api.get("/api/v1/subscription", headers=h)).json()["status"] == "past_due"
    assert (await _client(api, ready_org, 2)).status_code == 201  # grace period: full access


async def test_seats_are_checked_before_invitations(
    api: httpx.AsyncClient,
    ready_org: Org,
    service_headers: dict[str, str],
    owner_conn: psycopg.AsyncConnection,
) -> None:
    body = {"org_id": ready_org.org_id, "user_id": new_id("usr")}
    assert (
        await api.post("/internal/v1/seats/check", json=body, headers=service_headers)
    ).status_code == 204
    await _sql(
        owner_conn,
        ready_org,
        "UPDATE app.subscriptions SET trial_ends_at = now() - interval '1 day'",
    )
    full = await api.post("/internal/v1/seats/check", json=body, headers=service_headers)
    assert (full.status_code, full.json()["code"]) == (
        402,
        "plan_limit",
    )  # Free: one seat, the owner's
    owner = {"org_id": ready_org.org_id, "user_id": ready_org.owner_id}
    assert (
        await api.post("/internal/v1/seats/check", json=owner, headers=service_headers)
    ).status_code == 204
