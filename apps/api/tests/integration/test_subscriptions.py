"""Plans (docs/PRICING.md): the 14-day trial, prices with the founding discount (monthly only), paying by M-Pesa
(simulator), read-only after the trial or a lapsed period, seats."""

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
    assert (me["plan"], me["read_only"]) == ("agency", False)  # 14 days of everything
    assert "commission" in me["features"]
    sub = (await api.get("/api/v1/subscription", headers=h)).json()
    assert sub["status"] == "trialing"
    assert sub["paid_plan"] == "trial"
    assert 13 <= (datetime.fromisoformat(sub["trial_ends_at"]) - datetime.now(UTC)).days <= 14
    assert sub["usage"] == {"clients": 0, "documents_this_month": 0, "seats_used": 1}

    plans = {p["code"]: p for p in (await api.get("/api/v1/subscription/plans", headers=h)).json()}
    assert set(plans) == {"agent", "agency", "business"}  # no free plan
    agent = {p["cycle"]: p for p in plans["agent"]["prices"]}
    assert (agent["monthly"]["list_price"], agent["monthly"]["price"]) == (
        "1500",
        "750",
    )  # founding 50%
    assert (agent["yearly"]["price"], agent["yearly"]["discount_percent"]) == (
        "15000",
        0,
    )  # the founding discount does not stack on the yearly saving
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


async def test_ended_trial_is_read_only_until_paid(
    api: httpx.AsyncClient, ready_org: Org, owner_conn: psycopg.AsyncConnection
) -> None:
    h = ready_org.headers()
    assert (await _client(api, ready_org, 1)).status_code == 201
    await _sql(
        owner_conn,
        ready_org,
        "UPDATE app.subscriptions SET trial_ends_at = now() - interval '1 day'",
    )
    me = (await api.get("/api/v1/me", headers=h)).json()
    assert (me["plan"], me["read_only"]) == ("agency", True)
    sub = (await api.get("/api/v1/subscription", headers=h)).json()
    assert (sub["status"], sub["paid_plan"]) == ("read_only", "trial")
    # Everything stays readable, including paid features; nothing can be changed.
    assert (await api.get("/api/v1/clients", headers=h)).status_code == 200
    assert (await api.get("/api/v1/commissions/summary", headers=h)).status_code == 200
    refused = await _client(api, ready_org, 2)
    assert (refused.status_code, refused.json()["code"]) == (402, "subscription_inactive")

    paid = await api.post(
        "/api/v1/subscription/checkout",
        json={"plan": "agent", "cycle": "yearly", "phone": "0712 345 678"},
        headers=h,
    )
    assert paid.status_code == 201, paid.text  # paying works while read-only
    assert (paid.json()["amount"], paid.json()["discount_percent"]) == ("15000", 0)
    with time_machine.travel(datetime.now(ZoneInfo("Africa/Nairobi")) + timedelta(seconds=15)):
        await api.get(f"/api/v1/subscription/payments/{paid.json()['id']}", headers=h)
    sub = (await api.get("/api/v1/subscription", headers=ready_org.headers())).json()
    assert (sub["plan"], sub["status"], sub["founding_member"]) == ("agent", "active", False)
    assert (await _client(api, ready_org, 3)).status_code == 201


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
    ended = await api.post("/internal/v1/seats/check", json=body, headers=service_headers)
    assert (ended.status_code, ended.json()["code"]) == (
        402,
        "subscription_inactive",
    )  # nobody new joins after the trial ends
    owner = {"org_id": ready_org.org_id, "user_id": ready_org.owner_id}
    assert (
        await api.post("/internal/v1/seats/check", json=owner, headers=service_headers)
    ).status_code == 204
    await _sql(
        owner_conn,
        ready_org,
        "UPDATE app.subscriptions SET plan = 'agent', current_period_end = %s",
        datetime.now(UTC).date() + timedelta(days=20),
    )
    full = await api.post("/internal/v1/seats/check", json=body, headers=service_headers)
    assert (full.status_code, full.json()["code"]) == (402, "plan_limit")  # Agent: one seat
