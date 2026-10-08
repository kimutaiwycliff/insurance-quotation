"""Quotes: frozen options, send (number + PDF + tracked link), client accept/decline, withdraw, expiry, D5."""

from typing import Any

import httpx
import psycopg
import pytest

from app.core.tenancy import tenant_id_for_org
from tests.integration.m2_helpers import pdf_text
from tests.support import Org

pytestmark = pytest.mark.xdist_group("gotenberg")  # sending renders PDFs


async def _setup(api: httpx.AsyncClient, org: Org) -> dict[str, Any]:
    h = org.headers()
    client = (
        await api.post(
            "/api/v1/clients",
            json={
                "first_name": "Otieno",
                "last_name": "Ochieng",
                "phone": "0711 000 777",
                "email": "otieno@example.com",
            },
            headers=h,
        )
    ).json()
    products = []
    for name, rate in (("Savanna General", "0.04"), ("Rift Assurance", "0.035")):
        insurer = (await api.post("/api/v1/insurers", json={"name": name}, headers=h)).json()
        products.append(
            (
                await api.post(
                    "/api/v1/products",
                    json={
                        "insurer_id": insurer["id"],
                        "class_code": "motor_private",
                        "name": "Motor comprehensive",
                        "rating_basis": "rate_on_sum_insured",
                        "rate": rate,
                        "commission_rate_new": "0.10",
                    },
                    headers=h,
                )
            ).json()
        )
    return {"client": client, "products": products}


async def _quote(
    api: httpx.AsyncClient, org: Org, setup: dict[str, Any], **extra: Any
) -> dict[str, Any]:
    body = {
        "client_id": setup["client"]["id"],
        "product_ids": [p["id"] for p in setup["products"]],
        "risk": {"sum_insured": "2000000"},
        "details": [{"label": "Vehicle", "value": "KDA 123A, Toyota Axio 2019"}],
        "recommended_product_id": setup["products"][0]["id"],
        **extra,
    }
    response = await api.post("/api/v1/quotes", json=body, headers=org.headers())
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_quote_lifecycle_and_client_acceptance(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    setup = await _setup(api, ready_org)
    quote = await _quote(api, ready_org, setup)
    assert quote["status"] == "draft"
    assert quote["number"] is None
    assert [o["insurer_name"] for o in quote["option_list"]] == [
        "Rift Assurance",
        "Savanna General",
    ]  # cheapest first
    assert quote["option_list"][0]["client_total"] == "70355.00"
    assert quote["option_list"][1]["recommended"] is True
    assert quote["option_list"][0]["commission"]["gross"] == "7000.00"
    assert quote["title"] == "Motor private quotation"

    sent = (
        await api.post(
            f"/api/v1/quotes/{quote['id']}/send",
            json={"message": "As discussed."},
            headers=ready_org.headers(),
        )
    ).json()
    assert sent["quote"]["status"] == "sent"
    assert sent["quote"]["number"].startswith("QT-")
    assert sent["emailed_to"] == "otieno@example.com"
    assert sent["whatsapp_url"].startswith("https://wa.me/254711000777?text=")
    token = sent["url"].rsplit("/", 1)[1]

    # The PDF and the public page show both insurers and never the agent's commission.
    pdf_url = (
        await api.get(f"/api/v1/quotes/{quote['id']}/pdf", headers=ready_org.headers())
    ).json()["url"]
    async with httpx.AsyncClient() as raw:
        text = pdf_text((await raw.get(pdf_url)).content)
    assert "Rift Assurance" in text
    assert "KDA 123A" in text
    assert "ommission" not in text
    public = (await api.get(f"/api/v1/public/links/{token}")).json()
    assert public["state"] == "sent"
    assert [c["position"] for c in public["choices"]] == [1, 2]
    assert "ommission" not in str(public)
    html = (await api.get(f"/api/v1/public/links/{token}/html")).text
    assert "Rift Assurance" in html
    assert "ommission" not in html

    bad = await api.post(
        f"/api/v1/public/links/{token}/accept", json={"option": 1, "name": "Otieno"}
    )
    assert bad.status_code == 422  # must agree to the terms
    accepted = await api.post(
        f"/api/v1/public/links/{token}/accept",
        json={"option": 1, "name": "Otieno Ochieng", "phone": "0711000777", "agree_terms": True},
        headers={"User-Agent": "Mozilla/5.0 (Android) Chrome/129"},
    )
    assert accepted.json() == {"state": "accepted"}
    again = await api.post(
        f"/api/v1/public/links/{token}/accept",
        json={"option": 2, "name": "Otieno", "agree_terms": True},
    )
    assert again.status_code == 409

    final = (await api.get(f"/api/v1/quotes/{quote['id']}", headers=ready_org.headers())).json()
    assert final["status"] == "accepted"
    assert final["accepted_position"] == 1
    assert final["response"]["name"] == "Otieno Ochieng"
    assert final["response"]["agreed_terms"] is True
    assert final["response"]["ip_hash"]
    notes = (await api.get("/api/v1/notifications", headers=ready_org.headers())).json()["items"]
    assert any(n["kind"] == "quote.answered" for n in notes)
    recalculated = await api.put(
        f"/api/v1/quotes/{quote['id']}/options",
        json={"product_ids": [setup["products"][0]["id"]], "risk": {"sum_insured": "1"}},
        headers=ready_org.headers() | {"If-Match": f'W/"{final["version"]}"'},
    )
    assert recalculated.status_code == 409


async def test_decline_withdraw_and_expiry(
    api: httpx.AsyncClient, ready_org: Org, owner_conn: psycopg.AsyncConnection
) -> None:
    setup = await _setup(api, ready_org)
    h = ready_org.headers()
    declined = await _quote(api, ready_org, setup)
    token = (
        (await api.post(f"/api/v1/quotes/{declined['id']}/send", json={}, headers=h))
        .json()["url"]
        .rsplit("/", 1)[1]
    )
    assert (
        await api.post(f"/api/v1/public/links/{token}/decline", json={"reason": "Too expensive"})
    ).json() == {"state": "declined"}

    withdrawn = await _quote(api, ready_org, setup)
    token = (
        (await api.post(f"/api/v1/quotes/{withdrawn['id']}/send", json={}, headers=h))
        .json()["url"]
        .rsplit("/", 1)[1]
    )
    assert (await api.post(f"/api/v1/quotes/{withdrawn['id']}/withdraw", headers=h)).json()[
        "status"
    ] == "withdrawn"
    assert (await api.get(f"/api/v1/public/links/{token}")).status_code == 410

    expired = await _quote(api, ready_org, setup, valid_days=1)
    token = (
        (await api.post(f"/api/v1/quotes/{expired['id']}/send", json={}, headers=h))
        .json()["url"]
        .rsplit("/", 1)[1]
    )
    await owner_conn.execute(
        "SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id_for_org(ready_org.org_id)),)
    )
    await owner_conn.execute(
        "UPDATE app.quotes SET valid_until = valid_until - 10 WHERE id = %s", (expired["id"],)
    )
    late = await api.post(
        f"/api/v1/public/links/{token}/accept",
        json={"option": 1, "name": "Late", "agree_terms": True},
    )
    assert late.status_code == 409
    statuses = {q["id"]: q["status"] for q in (await api.get("/api/v1/quotes", headers=h)).json()}
    assert statuses[expired["id"]] == "expired"
    assert statuses[declined["id"]] == "declined"


async def test_rules(api: httpx.AsyncClient, ready_org: Org) -> None:
    setup = await _setup(api, ready_org)
    h = ready_org.headers()
    # D5: an agency can switch comparison quotes off.
    etag = (await api.get("/api/v1/organization", headers=h)).headers["ETag"]
    await api.patch(
        "/api/v1/organization", json={"multi_insurer_quotes": False}, headers=h | {"If-Match": etag}
    )
    blocked = await api.post(
        "/api/v1/quotes",
        json={
            "client_id": setup["client"]["id"],
            "product_ids": [p["id"] for p in setup["products"]],
            "risk": {"sum_insured": "1000000"},
        },
        headers=h,
    )
    assert blocked.json()["code"] == "multi_insurer_disabled"
    single = await _quote(api, ready_org, setup, product_ids=[setup["products"][0]["id"]])
    assert len(single["option_list"]) == 1

    # Marine needs stamp duty entered before sending.
    insurer = (await api.post("/api/v1/insurers", json={"name": "Marine Co"}, headers=h)).json()
    marine = (
        await api.post(
            "/api/v1/products",
            json={
                "insurer_id": insurer["id"],
                "class_code": "marine_cargo",
                "name": "Cargo",
                "rating_basis": "rate_on_sum_insured",
                "rate": "0.003",
            },
            headers=h,
        )
    ).json()
    draft = await _quote(
        api, ready_org, setup, product_ids=[marine["id"]], recommended_product_id=None
    )
    assert draft["option_list"][0]["needs_input"] is True
    assert (await api.post(f"/api/v1/quotes/{draft['id']}/send", json={}, headers=h)).json()[
        "code"
    ] == "quote_incomplete"


async def test_agents_only_see_their_quotes(api: httpx.AsyncClient, ready_org: Org) -> None:
    setup = await _setup(api, ready_org)
    quote = await _quote(api, ready_org, setup)  # client owned by the owner
    agent = ready_org.headers("agent")
    await api.get("/api/v1/me", headers=agent)
    assert (await api.get(f"/api/v1/quotes/{quote['id']}", headers=agent)).status_code == 404
    assert (await api.get("/api/v1/quotes", headers=agent)).json() == []
