"""Public links: hashed tokens, scoping, tracking, revocation, rate limits, isolation."""

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import httpx
import psycopg
import pytest

from app.core.tenancy import tenant_id_for_org
from app.modules.public_links import service as links
from app.modules.public_links.service import PublicContent
from tests.integration.m2_helpers import PDF_BYTES, upload
from tests.support import Org

HUMAN = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/129 Mobile Safari/537.36"}
WHATSAPP = {"User-Agent": "WhatsApp/2.24.1 A"}


async def _link(api: httpx.AsyncClient, org: Org, **extra: object) -> dict[str, object]:
    doc = await upload(
        api, org, "quote.pdf", PDF_BYTES, category="generated", title="Quotation QT-1"
    )
    response = await api.post(
        "/api/v1/public-links",
        json={"entity_type": "document", "entity_id": doc["id"], **extra},
        headers=org.headers(),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_token_is_shown_once_and_stored_hashed(
    api: httpx.AsyncClient, ready_org: Org, owner_conn: psycopg.AsyncConnection
) -> None:
    link = await _link(api, ready_org)
    token = str(link["token"])
    assert len(token) == 43
    assert str(link["url"]).endswith(f"/d/{token}")
    assert str(link["id"]) not in str(link["url"])  # no internal ids in public URLs
    listed = (await api.get("/api/v1/public-links", headers=ready_org.headers())).json()
    assert "token" not in listed[0]
    rows = await (
        await owner_conn.execute(
            "SELECT count(*) FROM app.public_links WHERE token_hash = %s", (token.encode(),)
        )
    ).fetchone()
    assert rows == (0,)  # the raw token is not in the database


async def test_visitor_flow_and_tracking(api: httpx.AsyncClient, ready_org: Org) -> None:
    link = await _link(api, ready_org)
    base = f"/api/v1/public/links/{link['token']}"

    view = await api.get(base, headers=HUMAN)
    assert view.status_code == 200, view.text
    body = view.json()
    assert body == body | {
        "title": "Quotation QT-1",
        "kind": "document",
        "has_download": True,
        "has_web_view": False,
    }
    assert body["tenant"]["name"] == "Test Agency"
    assert view.headers["cache-control"] == "no-store"
    assert "id" not in body

    download = await api.get(f"{base}/download", headers=HUMAN)
    assert download.status_code == 302
    async with httpx.AsyncClient() as raw:
        assert (await raw.get(download.headers["location"])).content == PDF_BYTES

    assert (
        await api.post(f"{base}/beacon", json={}, headers=WHATSAPP)
    ).status_code == 204  # preview bot
    assert (
        await api.post(f"{base}/beacon", json={"duration_ms": 4200}, headers=HUMAN)
    ).status_code == 204
    assert (await api.post(f"{base}/beacon", json={}, headers=HUMAN)).status_code == 204

    detail = next(
        x
        for x in (await api.get("/api/v1/public-links", headers=ready_org.headers())).json()
        if x["id"] == link["id"]
    )
    assert detail["view_count"] == 2  # bots are recorded, not counted
    events = (
        await api.get(f"/api/v1/public-links/{link['id']}/events", headers=ready_org.headers())
    ).json()
    kinds = [e["event_type"] for e in events]
    assert kinds.count("viewed") == 3
    assert {"created", "opened", "downloaded"} <= set(kinds)
    assert any(e["is_bot"] for e in events if e["event_type"] == "viewed")

    # The agent who shared it is told once, on the first human view.
    notes = (await api.get("/api/v1/notifications", headers=ready_org.headers())).json()["items"]
    assert [n["kind"] for n in notes] == ["link.viewed"]
    assert "Quotation QT-1" in notes[0]["title"]


async def test_revocation_is_immediate(api: httpx.AsyncClient, ready_org: Org) -> None:
    link = await _link(api, ready_org)
    base = f"/api/v1/public/links/{link['token']}"
    assert (await api.get(base)).status_code == 200
    revoked = await api.post(
        f"/api/v1/public-links/{link['id']}/revoke", headers=ready_org.headers()
    )
    assert revoked.json()["revoked_at"] is not None
    for path in (base, f"{base}/download"):
        response = await api.get(path)
        assert response.status_code == 410
        assert response.json()["code"] == "link_gone"


async def test_expired_and_unknown(
    api: httpx.AsyncClient, ready_org: Org, owner_conn: psycopg.AsyncConnection
) -> None:
    link = await _link(api, ready_org, expires_in_days=1)
    tenant_id = str(tenant_id_for_org(ready_org.org_id))
    await owner_conn.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant_id,))
    await owner_conn.execute(
        "UPDATE app.public_links SET expires_at = %s WHERE id = %s",
        (datetime.now(UTC) - timedelta(minutes=1), link["id"]),
    )
    assert (await api.get(f"/api/v1/public/links/{link['token']}")).status_code == 410
    assert (await api.get(f"/api/v1/public/links/{'A' * 43}")).status_code == 404
    assert (await api.get("/api/v1/public/links/not-a-token")).status_code == 404


async def test_cannot_link_another_tenants_document(
    api: httpx.AsyncClient, ready_org: Org, other_org: Org
) -> None:
    doc = await upload(api, ready_org, "mine.pdf", PDF_BYTES)
    response = await api.post(
        "/api/v1/public-links",
        json={"entity_type": "document", "entity_id": doc["id"]},
        headers=other_org.headers(),
    )
    assert response.status_code == 404
    unknown = await api.post(
        "/api/v1/public-links",
        json={"entity_type": "spaceship", "entity_id": doc["id"]},
        headers=ready_org.headers(),
    )
    assert unknown.status_code == 404


async def test_web_view_is_sandboxed(api: httpx.AsyncClient, ready_org: Org) -> None:
    async def target(_s: object, _st: object, _se: object, link: object) -> PublicContent:
        async def html() -> str:
            return "<!doctype html><p>Quote</p>"

        return PublicContent(title="Quote", kind="quote", html=html)

    links.register_target("test_quote", target)
    created = await api.post(
        "/api/v1/public-links",
        json={"entity_type": "test_quote", "entity_id": str(uuid.uuid4())},
        headers=ready_org.headers(),
    )
    token = created.json()["token"]
    page = await api.get(f"/api/v1/public/links/{token}/html")
    assert page.status_code == 200
    csp = page.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors http://localhost:3000" in csp
    assert page.headers["x-robots-tag"] == "noindex, nofollow"


async def test_public_routes_are_rate_limited_per_ip(
    make_api: Callable[..., AsyncIterator[httpx.AsyncClient]],
    ready_org: Org,
    api: httpx.AsyncClient,
) -> None:
    link = await _link(api, ready_org)
    async for limited in make_api(public_rate_limit_per_minute=3):
        codes = [
            (await limited.get(f"/api/v1/public/links/{link['token']}")).status_code
            for _ in range(5)
        ]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


@pytest.mark.parametrize("role", ["viewer"])
async def test_viewer_cannot_create_links(
    api: httpx.AsyncClient, ready_org: Org, role: str
) -> None:
    response = await api.post(
        "/api/v1/public-links",
        json={"entity_type": "document", "entity_id": str(uuid.uuid4())},
        headers=ready_org.headers(role),
    )
    assert response.status_code == 403
