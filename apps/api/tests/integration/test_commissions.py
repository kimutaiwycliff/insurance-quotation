"""Commission: expected on policies, received from insurers (WHT), statement, summary, dashboard v2."""

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from tests.support import Org


def _today() -> date:
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()


async def _book(api: httpx.AsyncClient, org: Org) -> dict[str, Any]:
    h = org.headers()
    client = (
        await api.post(
            "/api/v1/clients",
            json={"first_name": "Otieno", "last_name": "Ochieng", "phone": "0711 000 888"},
            headers=h,
        )
    ).json()
    insurer = (
        await api.post("/api/v1/insurers", json={"name": "Savanna General"}, headers=h)
    ).json()
    product = (
        await api.post(
            "/api/v1/products",
            json={
                "insurer_id": insurer["id"],
                "class_code": "motor_private",
                "name": "Motor comprehensive",
                "rating_basis": "rate_on_sum_insured",
                "rate": "0.04",
                "commission_rate_new": "0.10",
            },
            headers=h,
        )
    ).json()
    start = str(_today() - timedelta(days=20))
    with_product = await api.post(
        "/api/v1/policies",
        json={
            "client_id": client["id"],
            "product_id": product["id"],
            "description": "KDA 123A",
            "start_date": start,
            "total_premium": "35195",
            "commission_base": "35000",
        },
        headers=h,
    )
    assert with_product.status_code == 201, with_product.text
    manual = await api.post(
        "/api/v1/policies",
        json={
            "client_id": client["id"],
            "insurer_name": "Savanna General",
            "class_code": "medical_individual",
            "description": "Family medical",
            "start_date": start,
            "total_premium": "60000",
            "commission_rate": "0.125",
            "commission_base": "60000",
        },
        headers=h,
    )
    return {"client": client, "motor": with_product.json(), "medical": manual.json()}


async def test_expected_received_and_outstanding_commission(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    h = ready_org.headers()
    book = await _book(api, ready_org)
    assert book["motor"]["commission"]["gross"] == "3500.00"
    assert book["motor"]["commission"]["wht"] == "350.00"  # 10% WHT for resident agents
    assert book["motor"]["commission"]["net"] == "3150.00"
    assert book["medical"]["commission"]["net"] == "6750.00"
    no_base = await api.post(
        "/api/v1/policies",
        json={
            "client_id": book["client"]["id"],
            "insurer_name": "X",
            "class_code": "home",
            "start_date": str(_today()),
            "total_premium": "1000",
            "commission_rate": "0.1",
        },
        headers=h,
    )
    assert no_base.json()["code"] == "commission_base_required"

    statement = (await api.get("/api/v1/commissions/statement", headers=h)).json()
    assert statement["expected_net"] == "9900.00"
    assert statement["outstanding_net"] == "9900.00"

    # The insurer pays the motor commission in full and part of the medical one, with its own WHT figure.
    receipt = await api.post(
        "/api/v1/commission-receipts",
        json={
            "insurer_name": "Savanna General",
            "received_on": str(_today()),
            "reference": "EFT 4471",
            "wht_certificate": "KRAWHT0012345",
            "lines": [
                {"policy_id": book["motor"]["id"], "gross": "3500"},
                {"policy_id": book["medical"]["id"], "gross": "4000", "wht": "400"},
            ],
        },
        headers=h,
    )
    assert receipt.status_code == 201, receipt.text
    r = receipt.json()
    assert (r["gross"], r["wht"], r["net"]) == ("7500.00", "750.00", "6750.00")
    assert {line["description"] for line in r["lines"]} == {"KDA 123A", "Family medical"}

    rows = {
        row["policy_id"]: row
        for row in (await api.get("/api/v1/commissions/statement", headers=h)).json()["rows"]
    }
    assert rows[book["motor"]["id"]]["outstanding"]["net"] == "0.00"
    assert rows[book["medical"]["id"]]["outstanding"]["net"] == "3150.00"
    outstanding = (
        await api.get("/api/v1/commissions/statement", params={"outstanding": True}, headers=h)
    ).json()
    assert [row["policy_id"] for row in outstanding["rows"]] == [book["medical"]["id"]]

    summary = (await api.get("/api/v1/commissions/summary", headers=h)).json()
    assert summary["received_net"] == "6750.00"
    assert summary["wht"] == "750.00"
    assert summary["outstanding_net"] == "3150.00"
    assert summary["wht_certificates"][0]["certificate"] == "KRAWHT0012345"
    assert summary["insurers"][0]["insurer_name"] == "Savanna General"

    dashboard = (await api.get("/api/v1/dashboard", headers=h)).json()
    assert dashboard["commission_received"] == "6750.00"
    assert dashboard["book"]["written_count"] == 2
    assert dashboard["book"]["written_premium"] == "95195.00"
    assert dashboard["book"]["outstanding_premium"] == "95195.00"
    assert dashboard["book"]["expected_commission"] == "9900.00"

    voided = await api.post(
        f"/api/v1/commission-receipts/{r['id']}/void", json={"reason": "Wrong insurer"}, headers=h
    )
    assert voided.json()["void_reason"] == "Wrong insurer"
    after = (await api.get("/api/v1/commissions/statement", headers=h)).json()
    assert after["received_net"] == "0.00"
    again = await api.post(
        f"/api/v1/commission-receipts/{r['id']}/void", json={"reason": "x2"}, headers=h
    )
    assert again.status_code == 409

    corrected = await api.put(
        f"/api/v1/policies/{book['medical']['id']}/commission",
        json={"rate": "0.15", "base": "60000"},
        headers=h,
    )
    assert corrected.json()["commission"]["gross"] == "9000.00"


async def test_commission_visibility(api: httpx.AsyncClient, ready_org: Org) -> None:
    book = await _book(api, ready_org)
    await api.post(
        "/api/v1/commission-receipts",
        json={
            "insurer_name": "Savanna General",
            "received_on": str(_today()),
            "wht_certificate": "C1",
            "lines": [{"policy_id": book["motor"]["id"], "gross": "3500"}],
        },
        headers=ready_org.headers(),
    )
    agent = ready_org.headers("agent")
    await api.get("/api/v1/me", headers=agent)
    mine = (await api.get("/api/v1/commissions/summary", headers=agent)).json()
    assert mine["received_net"] == "0.00"  # not the agent's policies
    assert mine["wht_certificates"] == []
    assert (await api.get("/api/v1/commission-receipts", headers=agent)).status_code == 403
    blocked = await api.post(
        "/api/v1/commission-receipts",
        json={
            "insurer_name": "X",
            "received_on": str(_today()),
            "lines": [{"policy_id": book["motor"]["id"], "gross": "1"}],
        },
        headers=agent,
    )
    assert blocked.status_code == 403
    assistant = ready_org.headers("assistant")
    await api.get("/api/v1/me", headers=assistant)
    assert (await api.get("/api/v1/commissions/statement", headers=assistant)).status_code == 403
    board = (await api.get("/api/v1/dashboard", headers=assistant)).json()
    assert board["commission_received"] is None
    assert board["book"]["expected_commission"] is None
