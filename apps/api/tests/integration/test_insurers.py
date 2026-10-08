"""Insurers, products and the premium calculator through the API (KE pack)."""

from typing import Any

import httpx

from tests.support import Org


async def _insurer(api: httpx.AsyncClient, org: Org, name: str) -> dict[str, Any]:
    response = await api.post(
        "/api/v1/insurers", json={"name": name, "mpesa_paybill": "123456"}, headers=org.headers()
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _motor(
    api: httpx.AsyncClient, org: Org, insurer_id: str, rate: str, **extra: Any
) -> dict[str, Any]:
    body = {
        "insurer_id": insurer_id,
        "class_code": "motor_private",
        "name": f"Motor comprehensive {rate}",
        "rating_basis": "rate_on_sum_insured",
        "rate": rate,
        "min_premium": "37500",
        "commission_rate_new": "0.10",
        "commission_rate_renewal": "0.075",
        "benefits": [
            {
                "code": "excess_protector",
                "name": "Excess protector",
                "basis": "rate_on_sum_insured",
                "value": "0.0025",
            },
            {
                "code": "pvt",
                "name": "Political violence",
                "basis": "rate_on_sum_insured",
                "value": "0.0025",
                "selected_by_default": True,
            },
        ],
        **extra,
    }
    response = await api.post("/api/v1/products", json=body, headers=org.headers())
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_pack_and_classes(api: httpx.AsyncClient, ready_org: Org) -> None:
    pack = (await api.get("/api/v1/jurisdiction-pack", headers=ready_org.headers())).json()
    assert (pack["code"], pack["signed"]) == ("ke", False)
    assert "motor_private" in {c["code"] for c in pack["classes"]}


async def test_calculate_product_with_levies_and_commission(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    insurer = await _insurer(api, ready_org, "Example General")
    product = await _motor(api, ready_org, insurer["id"], "0.04")
    result = (
        await api.post(
            "/api/v1/premium/calculate",
            json={"product_id": product["id"], "sum_insured": "2000000", "on": "2026-10-08"},
            headers=ready_org.headers(),
        )
    ).json()
    lines = {line["code"]: line["amount"] for line in result["lines"]}
    # 80,000 + PVT 5,000 (default-selected) = 85,000; training 170; PCF 212.50; stamp 40
    assert lines["basic_premium"] == "80000.00"
    assert lines["benefit.pvt"] == "5000.00"
    assert "benefit.excess_protector" not in lines
    assert result["client_total"] == "85422.50"
    assert result["commission"]["gross"] == "8500.00"
    assert result["commission"]["wht"] == "850.00"  # agent: 10%
    assert result["pack"] == {"code": "ke", "version": "2026.1", "signed": False}
    renewal = (
        await api.post(
            "/api/v1/premium/calculate",
            json={
                "product_id": product["id"],
                "sum_insured": "2000000",
                "renewal": True,
                "benefit_codes": ["excess_protector", "pvt"],
            },
            headers=ready_org.headers(),
        )
    ).json()
    assert renewal["client_total"] == "90445.00"
    assert renewal["commission"]["rate"] == "0.075"


async def test_commission_is_hidden_from_assistants(api: httpx.AsyncClient, ready_org: Org) -> None:
    insurer = await _insurer(api, ready_org, "Hidden Commission Insurer")
    product = await _motor(api, ready_org, insurer["id"], "0.04")
    headers = ready_org.headers("assistant")
    calc = (
        await api.post(
            "/api/v1/premium/calculate",
            json={"product_id": product["id"], "sum_insured": "1000000"},
            headers=headers,
        )
    ).json()
    assert calc["commission"] is None
    listed = (await api.get("/api/v1/products", headers=headers)).json()
    assert listed[0]["commission_rate_new"] is None
    agent = (
        await api.post(
            "/api/v1/premium/calculate",
            json={"product_id": product["id"], "sum_insured": "1000000"},
            headers=ready_org.headers("agent"),
        )
    ).json()
    assert agent["commission"] is not None


async def test_compare_insurers_cheapest_first(api: httpx.AsyncClient, ready_org: Org) -> None:
    a = await _motor(api, ready_org, (await _insurer(api, ready_org, "Insurer A"))["id"], "0.045")
    b = await _motor(api, ready_org, (await _insurer(api, ready_org, "Insurer B"))["id"], "0.035")
    comparison = (
        await api.post(
            "/api/v1/premium/compare",
            json={"product_ids": [a["id"], b["id"]], "sum_insured": "2000000", "benefit_codes": []},
            headers=ready_org.headers(),
        )
    ).json()
    assert [r["product"]["insurer_name"] for r in comparison["results"]] == [
        "Insurer B",
        "Insurer A",
    ]
    assert comparison["results"][0]["client_total"] == "70355.00"  # 70,000 + 140 + 175 + 40


async def test_validation_and_permissions(api: httpx.AsyncClient, ready_org: Org) -> None:
    insurer = await _insurer(api, ready_org, "Validating Insurer")
    headers = ready_org.headers()
    base = {"insurer_id": insurer["id"], "name": "X", "class_code": "motor_private"}
    for body, code in (
        ({**base, "rating_basis": "rate_on_sum_insured"}, 422),  # no rate
        ({**base, "rating_basis": "flat", "flat_premium": 1000.5}, 422),  # float money
        ({**base, "rating_basis": "flat", "flat_premium": "1000", "class_code": "space"}, 422),
    ):
        response = await api.post("/api/v1/products", json=body, headers=headers)
        assert response.status_code == code, (body, response.text)
    assert (
        await api.post("/api/v1/insurers", json={"name": "Validating Insurer"}, headers=headers)
    ).status_code == 409
    agent = await api.post(
        "/api/v1/insurers", json={"name": "Agent's insurer"}, headers=ready_org.headers("agent")
    )
    assert agent.status_code == 403
    product = await _motor(api, ready_org, insurer["id"], "0.04")
    missing = await api.post(
        "/api/v1/premium/calculate", json={"product_id": product["id"]}, headers=headers
    )
    assert missing.status_code == 422
    assert missing.json()["code"] == "premium_input"


async def test_per_member_medical_and_update(api: httpx.AsyncClient, ready_org: Org) -> None:
    insurer = await _insurer(api, ready_org, "Medical Insurer")
    body = {
        "insurer_id": insurer["id"],
        "class_code": "medical_individual",
        "name": "Family cover",
        "rating_basis": "per_member",
        "member_tiers": [
            {"label": "Principal", "amount": "45000"},
            {"label": "Spouse", "amount": "40000"},
            {"label": "Child", "amount": "15000"},
        ],
    }
    product = (await api.post("/api/v1/products", json=body, headers=ready_org.headers())).json()
    result = (
        await api.post(
            "/api/v1/premium/calculate",
            json={
                "product_id": product["id"],
                "members": [
                    {"label": "Principal", "count": 1},
                    {"label": "Spouse", "count": 1},
                    {"label": "Child", "count": 2},
                ],
            },
            headers=ready_org.headers(),
        )
    ).json()
    assert result["client_total"] == "115557.50"
    update = {k: v for k, v in body.items() if k != "insurer_id"} | {"min_premium": "200000"}
    saved = await api.put(
        f"/api/v1/products/{product['id']}",
        json=update,
        headers=ready_org.headers() | {"If-Match": 'W/"1"'},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["min_premium"] == "200000.0000"


async def test_other_agency_cannot_use_products(
    api: httpx.AsyncClient, ready_org: Org, other_org: Org
) -> None:
    product = await _motor(
        api, ready_org, (await _insurer(api, ready_org, "Private Insurer"))["id"], "0.04"
    )
    response = await api.post(
        "/api/v1/premium/calculate",
        json={"product_id": product["id"], "sum_insured": "1"},
        headers=other_org.headers(),
    )
    assert response.status_code == 404
