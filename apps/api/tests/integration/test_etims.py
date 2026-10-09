"""Optional eTIMS (ADR-0017): a tenant switch, CU numbers recorded on issued documents and printed."""

import secrets
from typing import Any

import httpx
import pytest

from tests.integration.m2_helpers import pdf_text
from tests.support import Org

pytestmark = pytest.mark.xdist_group("gotenberg")


async def _issued(api: httpx.AsyncClient, org: Org, *, issue: bool = True) -> dict[str, Any]:
    h = org.headers()
    client = (
        await api.post(
            "/api/v1/clients",
            json={
                "company_name": "Acacia Traders Ltd",
                "kind": "corporate",
                "phone": f"0711 {secrets.randbelow(900_000) + 100_000}",
            },
            headers=h,
        )
    ).json()
    draft = (
        await api.post(
            "/api/v1/invoices",
            json={
                "client_id": client["id"],
                "lines": [
                    {
                        "description": "Consulting",
                        "quantity": "1",
                        "unit_price": "1000",
                        "tax_code": "vat_standard",
                    }
                ],
            },
            headers=h,
        )
    ).json()
    if not issue:
        return dict(draft)
    return dict(
        (
            await api.post(f"/api/v1/billing-documents/{draft['id']}/issue", json={}, headers=h)
        ).json()
    )


async def test_etims_is_optional_and_recorded_after_issue(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    h = ready_org.headers()
    invoice = await _issued(api, ready_org)
    body = {
        "cu_invoice_number": "kramw0012345678901",
        "verification_url": "https://etims.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=P051X",
    }
    off = await api.put(f"/api/v1/billing-documents/{invoice['id']}/etims", json=body, headers=h)
    assert off.json()["code"] == "etims_disabled"
    assert (await api.get("/api/v1/billing/summary", headers=h)).json()["etims_pending"] == 0

    etag = (await api.get("/api/v1/organization", headers=h)).headers["ETag"]
    org = await api.patch(
        "/api/v1/organization", json={"etims_enabled": True}, headers=h | {"If-Match": etag}
    )
    assert org.json()["etims_enabled"] is True
    assert (await api.get("/api/v1/billing/summary", headers=h)).json()["etims_pending"] == 1

    draft = await _issued(api, ready_org, issue=False)
    not_issued = await api.put(
        f"/api/v1/billing-documents/{draft['id']}/etims", json=body, headers=h
    )
    assert not_issued.json()["code"] == "billing_state"
    for url in ("http://etims.kra.go.ke/x", "https://kra.go.ke.evil.example/x"):
        bad = await api.put(
            f"/api/v1/billing-documents/{invoice['id']}/etims",
            json=body | {"verification_url": url},
            headers=h,
        )
        assert bad.json()["code"] == "billing_input"

    recorded = await api.put(
        f"/api/v1/billing-documents/{invoice['id']}/etims", json=body, headers=h
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["etims_cu_invoice_number"] == "KRAMW0012345678901"
    assert recorded.json()["etims_recorded_at"]
    assert (await api.get("/api/v1/billing/summary", headers=h)).json()["etims_pending"] == 0

    other = await _issued(api, ready_org)
    taken = await api.put(f"/api/v1/billing-documents/{other['id']}/etims", json=body, headers=h)
    assert taken.status_code == 409

    pdf_url = (await api.get(f"/api/v1/billing-documents/{invoice['id']}/pdf", headers=h)).json()[
        "url"
    ]
    async with httpx.AsyncClient() as raw:
        text = pdf_text((await raw.get(pdf_url)).content)
    assert "KRAMW0012345678901" in text
    assert "KRA CU invoice no." in text
