"""Sales quotes (sections, optional extras, accept on the link, convert), reminders and the billing summary."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest
import time_machine
from sqlalchemy import text

from app.core import db
from app.core.config import Settings
from app.core.tenancy import tenant_id_for_org
from app.modules.billing import service as billing
from tests.support import Org

pytestmark = pytest.mark.xdist_group("gotenberg")  # sending renders PDFs


def _today() -> date:
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()


async def _client(api: httpx.AsyncClient, org: Org) -> dict[str, Any]:
    response = await api.post(
        "/api/v1/clients",
        json={
            "first_name": "Wanjiru",
            "last_name": "Kamau",
            "phone": "0711 222 333",
            "email": "wanjiru@example.com",
        },
        headers=org.headers(),
    )
    return dict(response.json())


def _vat(desc: str, price: str, **extra: Any) -> dict[str, Any]:
    return {
        "description": desc,
        "quantity": "1",
        "unit_price": price,
        "tax_code": "vat_standard",
        **extra,
    }


async def _quote(api: httpx.AsyncClient, org: Org, client_id: str, **extra: Any) -> dict[str, Any]:
    body = {
        "client_id": client_id,
        "lines": [
            _vat("Website design", "40000", section="Design"),
            _vat("Logo", "10000", section="Design"),
            _vat("Hosting, first year", "5000", section="Extras", optional=True),
        ],
        **extra,
    }
    response = await api.post("/api/v1/sales-quotes", json=body, headers=org.headers())
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_quote_with_extras_is_accepted_and_invoiced(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    h = ready_org.headers()
    client = await _client(api, ready_org)
    quote = await _quote(api, ready_org, client["id"])
    assert quote["kind"] == "quote"
    assert quote["status"] == "draft"
    assert quote["total"] == "58000.00"  # 50,000 + 16% VAT; the optional hosting is not included
    assert quote["optional_total"] == "5800.00"
    assert [line["section"] for line in quote["lines"]] == ["Design", "Design", "Extras"]
    not_on_invoices = await api.post(
        "/api/v1/invoices",
        json={"client_id": client["id"], "lines": [_vat("X", "1", optional=True)]},
        headers=h,
    )
    assert not_on_invoices.json()["code"] == "billing_input"

    sent = await api.post(f"/api/v1/billing-documents/{quote['id']}/send", json={}, headers=h)
    assert sent.status_code == 200, sent.text
    assert sent.json()["document"]["number"].startswith("QT-")
    assert sent.json()["document"]["status"] == "sent"
    token = sent.json()["url"].rsplit("/", 1)[1]
    public = (await api.get(f"/api/v1/public/links/{token}")).json()
    assert public["state"] == "sent"
    assert public["choices"] == [
        {
            "position": 3,
            "label": "Hosting, first year",
            "amount": "5800.00",
            "currency": "KES",
            "recommended": False,
            "kind": "addon",
        }
    ]
    html = (await api.get(f"/api/v1/public/links/{token}/html")).text
    assert "Optional extras" in html
    assert "Design" in html

    bad = await api.post(
        f"/api/v1/public/links/{token}/accept",
        json={"name": "Wanjiru Kamau", "addons": [1], "agree_terms": True},
    )
    assert bad.status_code == 404  # line 1 is not an extra
    accepted = await api.post(
        f"/api/v1/public/links/{token}/accept",
        json={"name": "Wanjiru Kamau", "addons": [3], "agree_terms": True, "option": None},
    )
    assert accepted.json() == {"state": "accepted"}
    assert (
        await api.post(f"/api/v1/public/links/{token}/decline", json={"reason": "changed my mind"})
    ).status_code == 409

    invoice = await api.post(f"/api/v1/sales-quotes/{quote['id']}/convert", headers=h)
    assert invoice.status_code == 201, invoice.text
    inv = invoice.json()
    assert inv["kind"] == "invoice"
    assert inv["status"] == "draft"
    assert inv["total"] == "63800.00"  # with the hosting the client chose
    assert inv["reference"] == sent.json()["document"]["number"]
    final = (await api.get(f"/api/v1/billing-documents/{quote['id']}", headers=h)).json()
    assert final["status"] == "invoiced"
    assert final["converted_document_id"] == inv["id"]
    assert final["response"]["addons"] == [3]
    again = await api.post(f"/api/v1/sales-quotes/{quote['id']}/convert", headers=h)
    assert again.json()["code"] == "billing_state"
    void = await api.post(
        f"/api/v1/billing-documents/{quote['id']}/void", json={"reason": "x2"}, headers=h
    )
    assert void.json()["code"] == "billing_state"
    listed = (
        await api.get("/api/v1/sales-quotes", params={"status": "invoiced"}, headers=h)
    ).json()
    assert [q["id"] for q in listed] == [quote["id"]]


async def test_decline_and_expiry(api: httpx.AsyncClient, ready_org: Org) -> None:
    h = ready_org.headers()
    client = await _client(api, ready_org)
    declined = await _quote(api, ready_org, client["id"])
    token = (
        (await api.post(f"/api/v1/billing-documents/{declined['id']}/send", json={}, headers=h))
        .json()["url"]
        .rsplit("/", 1)[1]
    )
    assert (
        await api.post(f"/api/v1/public/links/{token}/decline", json={"reason": "Too dear"})
    ).json() == {"state": "declined"}

    expiring = await _quote(api, ready_org, client["id"], valid_days=5)
    token = (
        (await api.post(f"/api/v1/billing-documents/{expiring['id']}/send", json={}, headers=h))
        .json()["url"]
        .rsplit("/", 1)[1]
    )
    with time_machine.travel(datetime.now(ZoneInfo("Africa/Nairobi")) + timedelta(days=10)):
        late = await api.post(
            f"/api/v1/public/links/{token}/accept",
            json={"name": "Wanjiru Kamau", "agree_terms": True},
        )
        assert late.status_code == 409
        fresh = ready_org.headers()  # tokens are time-limited too
        statuses = {
            q["id"]: q["status"]
            for q in (await api.get("/api/v1/sales-quotes", headers=fresh)).json()
        }
    assert statuses == {declined["id"]: "declined", expiring["id"]: "expired"}


async def test_reminders_and_summary(
    api: httpx.AsyncClient, ready_org: Org, settings: Settings, owner_conn: psycopg.AsyncConnection
) -> None:
    h = ready_org.headers()
    client = await _client(api, ready_org)
    tenant = tenant_id_for_org(ready_org.org_id)

    async def invoice(due_in_days: int, overdue_by: int = 0) -> dict[str, Any]:
        draft = (
            await api.post(
                "/api/v1/invoices",
                json={
                    "client_id": client["id"],
                    "due_in_days": due_in_days,
                    "lines": [_vat("Service", "1000")],
                },
                headers=h,
            )
        ).json()
        issue_date = _today()
        if overdue_by:
            await owner_conn.execute(
                "SELECT set_config('app.tenant_id', %s, false)", (str(tenant),)
            )
            await owner_conn.execute(
                "UPDATE app.billing_documents SET due_date = %s WHERE id = %s",
                (_today() - timedelta(days=overdue_by), draft["id"]),
            )
            issue_date = _today() - timedelta(days=overdue_by + 10)
        issued = await api.post(
            f"/api/v1/billing-documents/{draft['id']}/issue",
            json={"issue_date": str(issue_date)},
            headers=h,
        )
        return dict(issued.json())

    due_soon = await invoice(2)
    overdue = await invoice(0, overdue_by=10)
    quote = await _quote(api, ready_org, client["id"], valid_days=2)
    await api.post(f"/api/v1/billing-documents/{quote['id']}/send", json={}, headers=h)

    etag = (await api.get("/api/v1/organization", headers=h)).headers["ETag"]
    org = await api.patch(
        "/api/v1/organization",
        json={"billing_reminders": True, "invoice_reminder_days_after": [14, 1, 7]},
        headers=h | {"If-Match": etag},
    )
    assert org.json()["invoice_reminder_days_after"] == [1, 7, 14]

    engine = db.create_engine(settings)
    factory = db.create_session_factory(engine)
    expected = {
        (due_soon["id"], "due", 3),
        (overdue["id"], "overdue", 7),
        (quote["id"], "quote_expiring", 3),
    }
    try:
        async with db.session_scope(factory) as session:
            assert await billing.enqueue_billing_reminders(session) >= 3
            rows = (
                await session.execute(
                    text(
                        "SELECT document_id, kind, offset_days FROM app.billing_documents_due_for_reminder()"
                    )
                )
            ).all()
            assert expected <= {(str(d), k, o) for d, k, o in rows}
        for document_id, kind, offset in sorted(expected):
            for outcome in (True, False):  # once only
                async with db.tenant_scope(factory, tenant) as session:
                    sent = await billing.send_billing_reminder(
                        session,
                        settings,
                        tenant,
                        document_id=uuid.UUID(document_id),
                        kind=kind,
                        offset_days=offset,
                    )
                    assert sent is outcome
    finally:
        await engine.dispose()
    messages = (await api.get("/api/v1/messages", headers=h)).json()["items"]
    events = sorted(
        m["event"]
        for m in messages
        if m["to_address"] == "wanjiru@example.com" and m["event"] != "document.shared"
    )
    assert events == ["invoice.reminder", "invoice.reminder", "quote.expiring"]
    overdue_mail = next(
        m
        for m in messages
        if m["event"] == "invoice.reminder" and m["subject"].startswith("Overdue")
    )
    assert overdue["number"] in overdue_mail["subject"]

    summary = (await api.get("/api/v1/billing/summary", headers=h)).json()
    assert summary["outstanding"] == "2320.00"
    assert (summary["overdue"], summary["overdue_count"]) == ("1160.00", 1)
    assert {b["label"]: b["count"] for b in summary["ageing"]}["1-30 days"] == 1
    assert (summary["quotes_awaiting"], summary["quotes_awaiting_total"]) == (1, "58000.00")
    assert summary["invoiced_this_month"] in {
        "2320.00",
        "1160.00",
    }  # the back-dated one may fall last month
    assert len(summary["months"]) == 12
