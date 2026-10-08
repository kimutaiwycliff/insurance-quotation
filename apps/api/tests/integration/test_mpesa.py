"""M-Pesa Daraja collection with the simulator (no network): prompts from the app and the invoice link,
callbacks stored once and confirmed with STK Query, Paybill payments matched or queued, security."""

import os
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import time_machine
from sqlalchemy import select

from app.core import db
from app.core.config import Settings
from app.core.tenancy import tenant_id_for_org
from app.integrations.mpesa import Credentials, DarajaClient, DarajaError
from app.modules.mpesa import service as mpesa
from app.modules.mpesa.models import WebhookEvent
from tests.support import Org

pytestmark = pytest.mark.xdist_group("gotenberg")  # sending invoices renders PDFs

_SANDBOX_TRANSIENT = {429, 500, 502, 503, 504}
SIMULATOR = {
    "environment": "simulator",
    "shortcode_type": "paybill",
    "business_shortcode": "174379",
    "consumer_key": "simulator-key-0001",
    "consumer_secret": "simulator-secret-0001",
    "passkey": "simulator-passkey-0001",
}


def _later(seconds: int = 15) -> Any:
    return time_machine.travel(
        datetime.now(ZoneInfo("Africa/Nairobi")) + timedelta(seconds=seconds)
    )


async def _setup(api: httpx.AsyncClient, org: Org) -> dict[str, Any]:
    h = org.headers()
    connection = await api.put("/api/v1/mpesa/connection", json=SIMULATOR, headers=h)
    assert connection.status_code == 200, connection.text
    client = (
        await api.post(
            "/api/v1/clients",
            json={"first_name": "Wanjiru", "last_name": "Kamau", "phone": "0712 345 678"},
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
                        "description": "Service",
                        "quantity": "1",
                        "unit_price": "999.99",
                        "tax_code": "vat_standard",
                    }
                ],
            },
            headers=h,
        )
    ).json()
    invoice = (
        await api.post(f"/api/v1/billing-documents/{draft['id']}/issue", json={}, headers=h)
    ).json()
    return {"connection": connection.json(), "client": client, "invoice": invoice}


def _token(connection: dict[str, Any]) -> str:
    return str(connection["stk_callback_url"].split("/mpesa/")[1].split("/")[0])


async def _process_events(settings: Settings, org: Org) -> int:
    tenant = tenant_id_for_org(org.org_id)
    engine = db.create_engine(settings)
    factory = db.create_session_factory(engine)
    done = 0
    try:
        async with db.tenant_scope(factory, tenant) as session:
            ids = list(
                (
                    await session.scalars(
                        select(WebhookEvent.id).where(WebhookEvent.processed_at.is_(None))
                    )
                ).all()
            )
        async with httpx.AsyncClient() as http:
            for event_id in ids:
                async with db.tenant_scope(factory, tenant) as session:
                    done += await mpesa.process_event(session, settings, http, event_id)
    finally:
        await engine.dispose()
    return done


async def test_prompt_from_the_app_is_confirmed_and_recorded(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    h = ready_org.headers()
    s = await _setup(api, ready_org)
    assert s["connection"]["consumer_key_hint"] == "…0001"
    assert s["connection"]["stk_callback_url"].startswith(
        "http://localhost:8000/api/v1/webhooks/mpesa/"
    )
    assert s["invoice"]["total"] == "1159.99"

    prompt = await api.post(
        f"/api/v1/invoices/{s['invoice']['id']}/mpesa-prompt", json={}, headers=h
    )
    assert prompt.status_code == 201, prompt.text
    p = prompt.json()
    assert (p["status"], p["phone"], p["amount"]) == (
        "pending",
        "+254712345678",
        "1160",
    )  # whole shillings
    with _later():
        status = (
            await api.get(f"/api/v1/mpesa/prompts/{p['id']}", headers=ready_org.headers())
        ).json()
    assert status["status"] == "paid"
    assert status["receipt"].startswith("SIM")
    invoice = (await api.get(f"/api/v1/billing-documents/{s['invoice']['id']}", headers=h)).json()
    assert invoice["status"] == "paid"
    account = (await api.get(f"/api/v1/clients/{s['client']['id']}/account", headers=h)).json()
    assert account["credit"] == "0.01"  # the rounding-up shilling stays as the client's credit
    payments = (
        await api.get("/api/v1/payments", params={"client_id": s["client"]["id"]}, headers=h)
    ).json()
    assert (payments[0]["method"], payments[0]["reference"]) == ("mpesa", status["receipt"])
    notes = (await api.get("/api/v1/notifications", headers=h)).json()["items"]
    assert any(n["kind"] == "payment.received" for n in notes)
    again = await api.post(
        f"/api/v1/invoices/{s['invoice']['id']}/mpesa-prompt", json={}, headers=h
    )
    assert again.status_code == 409  # nothing left to pay


async def test_client_pays_from_the_invoice_link(api: httpx.AsyncClient, ready_org: Org) -> None:
    h = ready_org.headers()
    s = await _setup(api, ready_org)
    sent = (
        await api.post(f"/api/v1/billing-documents/{s['invoice']['id']}/send", json={}, headers=h)
    ).json()
    token = sent["url"].rsplit("/", 1)[1]
    view = (await api.get(f"/api/v1/public/links/{token}")).json()
    assert view["payment"] == {
        "amount": "1160",
        "currency": "KES",
        "methods": ["mpesa"],
        "coming_soon": ["card"],
    }
    bad = await api.post(f"/api/v1/public/links/{token}/pay", json={"phone": "+256772123456"})
    assert bad.json()["code"] == "mpesa_error"  # Kenyan numbers only
    attempt = (
        await api.post(f"/api/v1/public/links/{token}/pay", json={"phone": "0712345678"})
    ).json()
    assert attempt["status"] == "pending"
    with _later():
        done = (await api.get(f"/api/v1/public/links/{token}/pay/{attempt['attempt_id']}")).json()
    assert done["status"] == "paid"
    assert done["message"].startswith("Paid")
    assert (await api.get(f"/api/v1/public/links/{token}")).json()[
        "payment"
    ] is None  # nothing left to pay
    assert (await api.get(f"/api/v1/public/links/{token}")).json()["state"] == "paid"
    missing = await api.get(f"/api/v1/public/links/{token}/pay/{uuid.uuid4()}")
    assert missing.status_code == 404


async def test_callbacks_are_stored_once_and_confirmed(
    api: httpx.AsyncClient, ready_org: Org, settings: Settings
) -> None:
    h = ready_org.headers()
    s = await _setup(api, ready_org)
    token = _token(s["connection"])
    paid = (
        await api.post(f"/api/v1/invoices/{s['invoice']['id']}/mpesa-prompt", json={}, headers=h)
    ).json()

    async def checkout_id(prompt_id: str) -> str:
        tenant = tenant_id_for_org(ready_org.org_id)
        engine = db.create_engine(settings)
        try:
            async with db.tenant_scope(db.create_session_factory(engine), tenant) as session:
                request = await mpesa.get_request(session, uuid.UUID(prompt_id))
                return str(request.checkout_request_id)
        finally:
            await engine.dispose()

    callback = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "m-1",
                "CheckoutRequestID": await checkout_id(paid["id"]),
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": 1160},
                        {"Name": "MpesaReceiptNumber", "Value": "SJK12AB34C"},
                        {"Name": "TransactionDate", "Value": 20261008101530},
                        {"Name": "PhoneNumber", "Value": 254712345678},
                    ]
                },
            }
        }
    }
    for _ in range(2):  # Safaricom may retry: stored once
        response = await api.post(f"/api/v1/webhooks/mpesa/{token}/stk", json=callback)
        assert response.json() == {"ResultCode": 0, "ResultDesc": "Accepted"}
    assert await _process_events(settings, ready_org) == 1
    status = (await api.get(f"/api/v1/mpesa/prompts/{paid['id']}", headers=h)).json()
    assert (status["status"], status["receipt"]) == ("paid", "SJK12AB34C")

    second = (
        await api.post(
            "/api/v1/invoices",
            json={
                "client_id": s["client"]["id"],
                "lines": [
                    {
                        "description": "More",
                        "quantity": "1",
                        "unit_price": "100",
                        "tax_code": "exempt",
                    }
                ],
            },
            headers=h,
        )
    ).json()
    await api.post(f"/api/v1/billing-documents/{second['id']}/issue", json={}, headers=h)
    cancelled = (
        await api.post(f"/api/v1/invoices/{second['id']}/mpesa-prompt", json={}, headers=h)
    ).json()
    callback["Body"]["stkCallback"] |= {
        "CheckoutRequestID": await checkout_id(cancelled["id"]),
        "ResultCode": 1032,
        "ResultDesc": "Request cancelled by user",
    }
    await api.post(f"/api/v1/webhooks/mpesa/{token}/stk", json=callback)
    assert await _process_events(settings, ready_org) == 1
    assert (await api.get(f"/api/v1/mpesa/prompts/{cancelled['id']}", headers=h)).json()[
        "status"
    ] == "cancelled"
    assert (
        await api.post(f"/api/v1/webhooks/mpesa/{'x' * 43}/stk", json=callback)
    ).status_code == 404


async def test_paybill_payments_are_matched_or_queued(
    api: httpx.AsyncClient, ready_org: Org, settings: Settings
) -> None:
    h = ready_org.headers()
    s = await _setup(api, ready_org)
    token = _token(s["connection"])
    assert (await api.post("/api/v1/mpesa/connection/register-c2b", headers=h)).json()[
        "c2b_registered_at"
    ]
    assert (
        await api.post(f"/api/v1/webhooks/mpesa/{token}/c2b/validation", json={"TransID": "X"})
    ).json()["ResultCode"] == 0

    ref = s["invoice"]["payment_reference"]
    typed = f"{ref[:4].lower()} {ref[4:]}"  # clients type references their own way
    base = {
        "TransactionType": "Pay Bill",
        "TransTime": "20261008093000",
        "BusinessShortCode": "174379",
        "FirstName": "WANJIRU",
    }
    await api.post(
        f"/api/v1/webhooks/mpesa/{token}/c2b/confirmation",
        json=base | {"TransID": "SKA11BB22C", "TransAmount": "1159.99", "BillRefNumber": typed},
    )
    await api.post(
        f"/api/v1/webhooks/mpesa/{token}/c2b/confirmation",
        json=base | {"TransID": "SKA11BB22C", "TransAmount": "1159.99", "BillRefNumber": typed},
    )
    await api.post(
        f"/api/v1/webhooks/mpesa/{token}/c2b/confirmation",
        json=base | {"TransID": "SKB33CC44D", "TransAmount": "500", "BillRefNumber": "wanjiru"},
    )
    await api.post(
        f"/api/v1/webhooks/mpesa/{token}/c2b/confirmation",
        json=base | {"TransID": "SKC55DD66E", "TransAmount": "70", "BillRefNumber": ""},
    )
    assert await _process_events(settings, ready_org) == 3

    invoice = (await api.get(f"/api/v1/billing-documents/{s['invoice']['id']}", headers=h)).json()
    assert invoice["status"] == "paid"
    queue = (
        await api.get("/api/v1/mpesa/transactions", params={"status": "unmatched"}, headers=h)
    ).json()
    assert {t["receipt"] for t in queue} == {"SKB33CC44D", "SKC55DD66E"}
    notes = (await api.get("/api/v1/notifications", headers=h)).json()["items"]
    assert sum(n["kind"] == "payment.unmatched" for n in notes) == 2

    by_id = {t["receipt"]: t["id"] for t in queue}
    matched = await api.post(
        f"/api/v1/mpesa/transactions/{by_id['SKB33CC44D']}/match",
        json={"client_id": s["client"]["id"]},
        headers=h,
    )
    assert matched.json()["status"] == "matched"
    account = (await api.get(f"/api/v1/clients/{s['client']['id']}/account", headers=h)).json()
    assert account["credit"] == "500.00"
    ignored = await api.post(
        f"/api/v1/mpesa/transactions/{by_id['SKC55DD66E']}/ignore",
        json={"reason": "Owner's own transfer"},
        headers=h,
    )
    assert ignored.json()["status"] == "ignored"
    twice = await api.post(
        f"/api/v1/mpesa/transactions/{by_id['SKC55DD66E']}/ignore",
        json={"reason": "again"},
        headers=h,
    )
    assert twice.status_code == 409


async def test_callback_ip_allow_list_and_permissions(
    make_api: Callable[..., AsyncIterator[httpx.AsyncClient]],
    api: httpx.AsyncClient,
    ready_org: Org,
) -> None:
    s = await _setup(api, ready_org)
    token = _token(s["connection"])
    async for strict in make_api(mpesa_callback_allowed_ips="196.201.214.200"):
        refused = await strict.post(
            f"/api/v1/webhooks/mpesa/{token}/c2b/confirmation", json={"TransID": "SKZ"}
        )
        assert refused.status_code == 403
    agent = ready_org.headers("agent")
    await api.get("/api/v1/me", headers=agent)
    assert (
        await api.put("/api/v1/mpesa/connection", json=SIMULATOR, headers=agent)
    ).status_code == 403
    connection = (await api.get("/api/v1/mpesa/connection", headers=agent)).json()
    assert "consumer_key" not in connection
    assert connection["consumer_key_hint"] == "…0001"


@pytest.mark.sandbox
async def test_daraja_sandbox_accepts_a_prompt() -> None:
    """Real Safaricom sandbox (skipped without DARAJA_SANDBOX_* credentials)."""
    keys = {
        k: os.environ.get(f"DARAJA_SANDBOX_{k.upper()}")
        for k in ("consumer_key", "consumer_secret", "shortcode", "passkey")
    }
    if not all(keys.values()):
        pytest.skip("Daraja sandbox credentials are not set")
    credentials = Credentials(
        environment="sandbox",
        consumer_key=str(keys["consumer_key"]),
        consumer_secret=str(keys["consumer_secret"]),
        business_shortcode=str(keys["shortcode"]),
        passkey=str(keys["passkey"]),
        party_b=str(keys["shortcode"]),
        transaction_type="CustomerPayBillOnline",
    )
    async with httpx.AsyncClient() as http:
        client = DarajaClient(credentials, http)
        try:
            await client.check_credentials()
            accepted = await client.stk_push(
                phone="254708374149",  # Safaricom's sandbox test number
                amount=1,
                account_reference="TEST123456",
                description="Sandbox test",
                callback_url="https://example.com/api/v1/webhooks/mpesa/sandbox-test/stk",
            )
            status = await client.stk_query(accepted.checkout_request_id)
        except DarajaError as exc:
            # The shared sandbox throttles bursts and has outages; that is not a failure of ours.
            if exc.status in _SANDBOX_TRANSIENT or "spike" in exc.detail.lower():
                pytest.skip(f"Daraja sandbox unavailable: {exc.detail}")
            raise
    assert accepted.checkout_request_id.startswith("ws_CO_")
    assert status.result_code in {None, 0, 1, 1032, 1037}
