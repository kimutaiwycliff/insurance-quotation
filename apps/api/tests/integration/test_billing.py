"""Invoicing core: drafts, issue (immutable), payments and allocation, credit notes, voids, ledger, PDFs."""

import random
import uuid
from decimal import Decimal
from typing import Any

import httpx
import psycopg
import pytest

from app.core.tenancy import tenant_id_for_org
from app.modules.numbering.references import is_valid_payment_reference
from tests.integration.m2_helpers import pdf_text
from tests.support import Org

D = Decimal


async def _client(api: httpx.AsyncClient, org: Org, phone: str = "0711 000 999") -> dict[str, Any]:
    response = await api.post(
        "/api/v1/clients",
        json={
            "company_name": "Acacia Traders Ltd",
            "kind": "corporate",
            "phone": phone,
            "email": "accounts@acacia.example.com",
        },
        headers=org.headers(),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _invoice(
    api: httpx.AsyncClient, org: Org, client_id: str, amount: str = "1000", *, issue: bool = True
) -> dict[str, Any]:
    h = org.headers()
    draft = await api.post(
        "/api/v1/invoices",
        json={
            "client_id": client_id,
            "lines": [
                {
                    "description": "Consulting",
                    "quantity": "1",
                    "unit_price": amount,
                    "tax_code": "vat_standard",
                }
            ],
        },
        headers=h,
    )
    assert draft.status_code == 201, draft.text
    if not issue:
        return dict(draft.json())
    issued = await api.post(
        f"/api/v1/billing-documents/{draft.json()['id']}/issue", json={}, headers=h
    )
    assert issued.status_code == 200, issued.text
    return dict(issued.json())


async def _trial_balance(owner_conn: psycopg.AsyncConnection, org: Org) -> dict[str, Decimal]:
    tenant = str(tenant_id_for_org(org.org_id))
    await owner_conn.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))
    rows = await (
        await owner_conn.execute(
            "SELECT account, sum(debit - credit) FROM app.journal_lines GROUP BY account"
        )
    ).fetchall()
    return {account: D(total) for account, total in rows}


async def test_invoice_lifecycle_with_catalogue_and_immutability(
    api: httpx.AsyncClient, ready_org: Org, app_user_conn: psycopg.AsyncConnection
) -> None:
    h = ready_org.headers()
    client = await _client(api, ready_org)
    item = await api.post(
        "/api/v1/items",
        json={
            "name": "Monthly bookkeeping",
            "unit": "month",
            "unit_price": "1500",
            "tax_code": "vat_standard",
        },
        headers=h,
    )
    assert item.status_code == 201, item.text
    bad = await api.post(
        "/api/v1/items", json={"name": "X", "unit_price": "1", "tax_code": "vat_99"}, headers=h
    )
    assert bad.json()["code"] == "unknown_tax_code"

    draft = (
        await api.post(
            "/api/v1/invoices",
            json={
                "client_id": client["id"],
                "reference": "PO-7781",
                "lines": [
                    {"item_id": item.json()["id"], "quantity": "3", "discount_rate": "0.1"},
                    {
                        "description": "Filing fee (exempt)",
                        "quantity": "1",
                        "unit_price": "2000",
                        "tax_code": "exempt",
                    },
                ],
            },
            headers=h,
        )
    ).json()
    assert draft["status"] == "draft"
    assert draft["number"] is None
    assert (draft["subtotal"], draft["tax"], draft["total"]) == ("6050.00", "648.00", "6698.00")
    assert draft["lines"][0]["description"] == "Monthly bookkeeping"
    edited = await api.patch(
        f"/api/v1/billing-documents/{draft['id']}",
        json={"prices_include_tax": True},
        headers=h | {"If-Match": f'W/"{draft["version"]}"'},
    )
    assert edited.json()["total"] == "6050.00"  # same prices, now VAT-inclusive

    issued = (
        await api.post(f"/api/v1/billing-documents/{draft['id']}/issue", json={}, headers=h)
    ).json()
    assert issued["status"] == "open"
    assert issued["number"].startswith("INV-")
    assert is_valid_payment_reference(issued["payment_reference"])
    again = await api.patch(
        f"/api/v1/billing-documents/{draft['id']}",
        json={"notes": "late change"},
        headers=h | {"If-Match": f'W/"{issued["version"]}"'},
    )
    assert again.json()["code"] == "billing_state"

    # Even straight SQL as the API role cannot change an issued invoice or its lines.
    tenant = tenant_id_for_org(ready_org.org_id)
    for statement in (
        "UPDATE app.billing_documents SET total = 1 WHERE id = %s",
        "UPDATE app.billing_lines SET unit_price = 1 WHERE document_id = %s",
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with app_user_conn.transaction():
                await app_user_conn.execute(
                    "SELECT set_config('app.tenant_id', %s, true)", (str(tenant),)
                )
                await app_user_conn.execute(statement, (draft["id"],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with app_user_conn.transaction():
            await app_user_conn.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (str(tenant),)
            )
            await app_user_conn.execute(
                "DELETE FROM app.billing_documents WHERE id = %s", (draft["id"],)
            )

    # A draft can be voided (nothing to reverse); an issued invoice without payments too.
    spare = await _invoice(api, ready_org, client["id"], issue=False)
    assert (
        await api.post(
            f"/api/v1/billing-documents/{spare['id']}/void", json={"reason": "Duplicate"}, headers=h
        )
    ).json()["status"] == "void"
    listed = (await api.get("/api/v1/invoices", params={"status": "unpaid"}, headers=h)).json()
    assert [i["id"] for i in listed] == [draft["id"]]


async def test_payments_allocation_credit_notes_and_ledger(
    api: httpx.AsyncClient, ready_org: Org, owner_conn: psycopg.AsyncConnection
) -> None:
    h = ready_org.headers()
    client = await _client(api, ready_org)
    first = await _invoice(api, ready_org, client["id"], "1000")  # 1160 incl. VAT
    second = await _invoice(api, ready_org, client["id"], "500")  # 580

    # 1,500 paid: settles the first invoice and part of the second (oldest first).
    payment = await api.post(
        "/api/v1/payments",
        json={
            "client_id": client["id"],
            "amount": "1500",
            "received_on": first["issue_date"],
            "reference": "SJK12AB34C",
        },
        headers=h,
    )
    assert payment.status_code == 201, payment.text
    p = payment.json()
    assert p["number"].startswith("RCT-")
    assert [(a["invoice_number"], a["amount"]) for a in p["allocations"]] == [
        (first["number"], "1160.00"),
        (second["number"], "340.00"),
    ]
    assert p["unallocated"] == "0.00"
    docs = {d["id"]: d for d in (await api.get("/api/v1/invoices", headers=h)).json()}
    assert docs[first["id"]]["status"] == "paid"
    assert docs[second["id"]]["status"] == "partially_paid"
    assert docs[second["id"]]["balance"] == "240.00"

    # Over-payment becomes client credit, applied to the next invoice on request.
    extra = (
        await api.post(
            "/api/v1/payments",
            json={
                "client_id": client["id"],
                "amount": "1000",
                "received_on": first["issue_date"],
                "method": "bank",
            },
            headers=h,
        )
    ).json()
    assert extra["unallocated"] == "760.00"
    third = await _invoice(api, ready_org, client["id"], "500")
    applied = (await api.post(f"/api/v1/invoices/{third['id']}/apply-credit", headers=h)).json()
    assert applied["status"] == "paid"
    account = (await api.get(f"/api/v1/clients/{client['id']}/account", headers=h)).json()
    assert (account["owed"], account["credit"]) == ("0.00", "180.00")

    # A credit note on a paid invoice turns into client credit; voiding a payment reopens what it paid.
    cn = (
        await api.post(
            "/api/v1/credit-notes",
            json={"invoice_id": first["id"], "reason": "Service not delivered"},
            headers=h,
        )
    ).json()
    assert cn["total"] == "1160.00"
    cn = (await api.post(f"/api/v1/billing-documents/{cn['id']}/issue", json={}, headers=h)).json()
    assert cn["number"].startswith("CN-")
    voided = await api.post(
        f"/api/v1/payments/{p['id']}/void", json={"reason": "Bounced cheque"}, headers=h
    )
    assert voided.json()["unallocated"] == "0.00"
    docs = {d["id"]: d for d in (await api.get("/api/v1/invoices", headers=h)).json()}
    assert docs[first["id"]]["balance"] == "1160.00"
    assert docs[second["id"]]["balance"] == "340.00"  # 240 from the bank payment stays applied
    no_void = await api.post(
        f"/api/v1/billing-documents/{third['id']}/void", json={"reason": "x2"}, headers=h
    )
    assert no_void.json()["code"] == "billing_state"  # paid from credit: credit-note it instead

    account = (await api.get(f"/api/v1/clients/{client['id']}/account", headers=h)).json()
    assert account["owed"] == "1500.00"
    assert account["credit"] == "1340.00"  # 180 left from the bank payment + the 1,160 credit note
    tb = await _trial_balance(owner_conn, ready_org)
    assert tb["receivable"] == D("1500.00")
    assert tb["client_credit"] == D("-1340.00")
    assert tb["cash"] == D("1000.00")  # the voided payment is reversed
    assert sum(tb.values()) == 0


async def test_ledger_stays_consistent_under_random_operations(
    api: httpx.AsyncClient, ready_org: Org, owner_conn: psycopg.AsyncConnection
) -> None:
    """Property (ADR-0012): receivable equals the sum of open balances, credit equals unapplied money."""
    h = ready_org.headers()
    client = await _client(api, ready_org)
    rng = random.Random(20261008)  # noqa: S311 - deterministic test data
    payments: list[str] = []
    for _ in range(14):
        op = rng.choice(["invoice", "invoice", "pay", "pay", "void_payment", "credit", "apply"])
        invoices = (
            await api.get("/api/v1/invoices", params={"client_id": client["id"]}, headers=h)
        ).json()
        open_ = [i for i in invoices if i["status"] in {"open", "partially_paid", "overdue"}]
        if op == "invoice" or not invoices:
            await _invoice(api, ready_org, client["id"], str(rng.randint(100, 3000)))
        elif op == "pay":
            r = await api.post(
                "/api/v1/payments",
                json={
                    "client_id": client["id"],
                    "amount": str(rng.randint(50, 4000)),
                    "received_on": invoices[0]["issue_date"],
                },
                headers=h,
            )
            payments.append(r.json()["id"])
        elif op == "void_payment" and payments:
            await api.post(
                f"/api/v1/payments/{payments.pop(0)}/void", json={"reason": "test"}, headers=h
            )
        elif op == "credit" and open_:
            cn = await api.post(
                "/api/v1/credit-notes",
                json={"invoice_id": open_[0]["id"], "reason": "test"},
                headers=h,
            )
            if cn.status_code == 201:  # 422 once an invoice is fully credited
                await api.post(
                    f"/api/v1/billing-documents/{cn.json()['id']}/issue", json={}, headers=h
                )
        elif op == "apply" and open_:
            await api.post(f"/api/v1/invoices/{open_[0]['id']}/apply-credit", headers=h)
    invoices = (
        await api.get("/api/v1/invoices", params={"client_id": client["id"]}, headers=h)
    ).json()
    account = (await api.get(f"/api/v1/clients/{client['id']}/account", headers=h)).json()
    open_total = sum((D(i["balance"]) for i in invoices if i["status"] != "void"), D(0))
    assert D(account["owed"]) == open_total
    unapplied = sum(
        (
            D(p["unallocated"])
            for p in (
                await api.get("/api/v1/payments", params={"client_id": client["id"]}, headers=h)
            ).json()
        ),
        D(0),
    )
    notes = (
        await api.get("/api/v1/credit-notes", params={"client_id": client["id"]}, headers=h)
    ).json()
    unapplied += sum((D(n["total"]) - D(n["paid"]) for n in notes if n["status"] == "issued"), D(0))
    assert D(account["credit"]) == unapplied
    assert sum((await _trial_balance(owner_conn, ready_org)).values()) == 0


async def test_unbalanced_journal_is_rejected_by_the_database(
    ready_org: Org, app_user_conn: psycopg.AsyncConnection
) -> None:
    tenant = tenant_id_for_org(ready_org.org_id)
    with pytest.raises(psycopg.errors.CheckViolation):
        async with app_user_conn.transaction():
            await app_user_conn.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (str(tenant),)
            )
            entry = uuid.uuid4()
            await app_user_conn.execute(
                "INSERT INTO app.journal_entries (id, tenant_id, occurred_on, source_type, source_id, memo) "
                "VALUES (%s, %s, current_date, 'test', %s, 'unbalanced')",
                (entry, tenant, uuid.uuid4()),
            )
            await app_user_conn.execute(
                "INSERT INTO app.journal_lines (tenant_id, entry_id, account, debit, credit, currency) "
                "VALUES (%s, %s, 'cash', 100, 0, 'KES')",
                (tenant, entry),
            )


@pytest.mark.xdist_group("gotenberg")
async def test_send_pdf_public_page_and_receipt(api: httpx.AsyncClient, ready_org: Org) -> None:
    h = ready_org.headers()
    client = await _client(api, ready_org)
    invoice = await _invoice(api, ready_org, client["id"], "2500")
    sent = await api.post(
        f"/api/v1/billing-documents/{invoice['id']}/send", json={"message": "Thank you"}, headers=h
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["emailed_to"] == "accounts@acacia.example.com"
    assert sent.json()["whatsapp_url"].startswith("https://wa.me/254711000999")
    token = sent.json()["url"].rsplit("/", 1)[1]
    public = (await api.get(f"/api/v1/public/links/{token}")).json()
    assert public["state"] == "open"
    html = (await api.get(f"/api/v1/public/links/{token}/html")).text
    assert invoice["number"] in html
    assert invoice["payment_reference"] in html
    pdf_url = (await api.get(f"/api/v1/billing-documents/{invoice['id']}/pdf", headers=h)).json()[
        "url"
    ]
    async with httpx.AsyncClient() as raw:
        text = pdf_text((await raw.get(pdf_url)).content)
    assert invoice["number"] in text
    assert "2,900.00" in text  # 2,500 + 16% VAT

    payment = (
        await api.post(
            "/api/v1/payments",
            json={
                "client_id": client["id"],
                "amount": "3000",
                "received_on": invoice["issue_date"],
                "reference": "QWE1RTY2UI",
            },
            headers=h,
        )
    ).json()
    receipt_url = (await api.get(f"/api/v1/payments/{payment['id']}/receipt", headers=h)).json()[
        "url"
    ]
    async with httpx.AsyncClient() as raw:
        text = pdf_text((await raw.get(receipt_url)).content)
    assert payment["number"] in text
    assert "Credit on account" in text
    assert (await api.get(f"/api/v1/public/links/{token}")).json()["state"] == "paid"


async def test_billing_permissions_and_tenancy(
    api: httpx.AsyncClient, ready_org: Org, other_org: Org
) -> None:
    client = await _client(api, ready_org)
    draft = await _invoice(api, ready_org, client["id"], issue=False)
    assistant = ready_org.headers("assistant")
    await api.get("/api/v1/me", headers=assistant)
    mine = await api.post(
        "/api/v1/invoices",
        json={
            "client_id": client["id"],
            "lines": [
                {"description": "A", "quantity": "1", "unit_price": "1", "tax_code": "exempt"}
            ],
        },
        headers=assistant,
    )
    assert mine.status_code == 201  # assistants prepare drafts...
    blocked = await api.post(
        f"/api/v1/billing-documents/{draft['id']}/issue", json={}, headers=assistant
    )
    assert blocked.status_code == 403  # ...but do not issue or take money
    agent = ready_org.headers("agent")
    await api.get("/api/v1/me", headers=agent)
    assert (
        await api.get(f"/api/v1/billing-documents/{draft['id']}", headers=agent)
    ).status_code == 404
    assert (await api.get("/api/v1/invoices", headers=agent)).json() == []
    await api.get("/api/v1/me", headers=other_org.headers())
    assert (
        await api.get(f"/api/v1/billing-documents/{draft['id']}", headers=other_org.headers())
    ).status_code == 404
    floats = await api.post(
        "/api/v1/payments",
        json={"client_id": client["id"], "amount": 10.5, "received_on": "2026-10-08"},
        headers=ready_org.headers(),
    )
    assert floats.status_code == 422
