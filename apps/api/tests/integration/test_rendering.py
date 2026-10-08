"""Templates, branding and PDFs through the real Gotenberg (plan M2 acceptance: fixture sets, XSS, SSRF)."""

import asyncio
import socket
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from app.core import db
from app.core.config import Settings
from app.core.tenancy import tenant_id_for_org
from app.integrations.pdf.gotenberg import GotenbergRenderer
from app.integrations.storage.s3 import S3Storage
from app.modules.documents.service import EntityRef
from app.modules.rendering import service as rendering
from app.modules.rendering.fixtures import VARIANTS, sample_view
from tests.integration.m2_helpers import PDF_BYTES, PNG_BYTES, pdf_text, upload
from tests.support import Org

# One Gotenberg serves the whole suite: keep its renders on a single xdist worker (--dist loadgroup).
pytestmark = pytest.mark.xdist_group("gotenberg")


async def _preview(api: httpx.AsyncClient, org: Org, key: str, **body: object) -> httpx.Response:
    response = await api.post(f"/api/v1/templates/{key}/preview", json=body, headers=org.headers())
    assert response.status_code == 200, response.text
    return response


async def test_catalogue(api: httpx.AsyncClient, ready_org: Org) -> None:
    templates = (await api.get("/api/v1/templates", headers=ready_org.headers())).json()
    assert {t["key"]: t["tier"] for t in templates} == {
        "classic": "free",
        "savanna": "premium",
        "executive": "premium",
    }


@pytest.mark.parametrize("key", ["classic", "savanna", "executive"])
@pytest.mark.parametrize("doc_type", ["quote", "invoice", "receipt", "credit_note"])
async def test_every_template_renders_a_real_pdf(
    api: httpx.AsyncClient, ready_org: Org, key: str, doc_type: str
) -> None:
    response = await _preview(api, ready_org, key, doc_type=doc_type)
    assert response.headers["content-type"] == "application/pdf"
    text = pdf_text(response.content)
    assert "Test Agency" in text  # the tenant's own name
    assert "-2026-00042" in text
    assert "Page 1 of" in text  # footer with page numbers


@pytest.mark.parametrize("variant", VARIANTS)
async def test_fixture_sets(api: httpx.AsyncClient, ready_org: Org, variant: str) -> None:
    text = pdf_text(
        (await _preview(api, ready_org, "classic", doc_type="invoice", variant=variant)).content
    )
    if variant == "many_lines":
        assert "Item 150" in text
        assert "Page 3 of" in text or "Page 4 of" in text  # header row repeats across pages
    if variant == "zero_dp":
        assert "UGX 1,850,000" in text
        assert "1,850,000.00" not in text


async def test_branding_changes_the_output(api: httpx.AsyncClient, ready_org: Org) -> None:
    logo = await upload(api, ready_org, "logo.png", PNG_BYTES, category="branding")
    headers = ready_org.headers()
    current = await api.get("/api/v1/branding", headers=headers)
    assert current.json()["templates"]["invoice"] == "classic"
    updated = await api.patch(
        "/api/v1/branding",
        json={
            "templates": {"invoice": "savanna"},
            "primary_color": "#7A1F3D",
            "logo_document_id": logo["id"],
            "footer_text": "Regulated by the Insurance Regulatory Authority",
            "payment_instructions": {"mpesa_paybill": "247247", "bank_name": "Example Bank"},
        },
        headers=headers | {"If-Match": current.headers["ETag"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["templates"]["invoice"] == "savanna"

    html = (await _preview(api, ready_org, "savanna", doc_type="invoice", format="html")).text
    assert "#7A1F3D" in html
    assert "data:image/png;base64," in html
    assert "M-Pesa Paybill" in html
    assert "247247" in html

    unsaved = (
        await _preview(
            api, ready_org, "classic", format="html", branding={"primary_color": "#00AA00"}
        )
    ).text
    assert "#00AA00" in unsaved  # live preview of unsaved changes


async def test_invalid_branding(api: httpx.AsyncClient, ready_org: Org) -> None:
    pdf_doc = await upload(api, ready_org, "not-a-logo.pdf", PDF_BYTES)
    headers = ready_org.headers()
    for body in (
        {"templates": {"invoice": "nope"}},
        {"logo_document_id": pdf_doc["id"]},
        {"logo_document_id": str(uuid.uuid4())},
        {"primary_color": "blue"},
    ):
        etag = (await api.get("/api/v1/branding", headers=headers)).headers["ETag"]
        response = await api.patch(
            "/api/v1/branding", json=body, headers=headers | {"If-Match": etag}
        )
        assert response.status_code == 422, (body, response.text)
    agent = await api.patch(
        "/api/v1/branding",
        json={"primary_color": "#000000"},
        headers=ready_org.headers("agent") | {"If-Match": 'W/"1"'},
    )
    assert agent.status_code == 403


async def test_tenant_text_is_escaped_in_html_and_pdf(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    hostile = '<script>alert(1)</script>"><img src=x onerror=alert(1)>'
    headers = ready_org.headers()
    etag = (await api.get("/api/v1/organization", headers=headers)).headers["ETag"]
    await api.patch(
        "/api/v1/organization", json={"name": hostile}, headers=headers | {"If-Match": etag}
    )

    html = (await _preview(api, ready_org, "classic", format="html")).text
    assert "<script>alert(1)" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    text = pdf_text((await _preview(api, ready_org, "classic")).content)
    assert "<script>alert(1)</script>" in text  # shown as text, never executed


@pytest.fixture
async def canary() -> AsyncIterator[tuple[str, list[bytes]]]:
    """A TCP server on this container's private IP that records every connection attempt."""
    hits: list[bytes] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hits.append(await reader.read(200))
        writer.close()

    ip = socket.gethostbyname(socket.gethostname())
    server = await asyncio.start_server(handle, ip, 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        yield f"http://{ip}:{port}", hits


async def test_gotenberg_cannot_reach_internal_hosts(
    settings: Settings, canary: tuple[str, list[bytes]]
) -> None:
    """SSRF: even HTML *without* our CSP cannot make Chromium fetch private or metadata addresses."""
    url, hits = canary
    html = (
        "<!doctype html><html><head>"
        f'<link rel="stylesheet" href="{url}/style.css"></head><body>'
        f'<img src="{url}/canary.png"><img src="http://169.254.169.254/latest/meta-data/">'
        f'<iframe src="{url}/frame"></iframe>Hello</body></html>'
    )
    async with httpx.AsyncClient() as http:
        renderer = GotenbergRenderer(settings.gotenberg_url, http, timeout=30)
        try:
            pdf = await renderer.render(html)
        except Exception:
            pdf = None
    await asyncio.sleep(0.5)
    assert hits == []
    if pdf is not None:
        assert "Hello" in pdf_text(pdf)


async def test_generated_pdfs_are_cached_per_version(settings: Settings, ready_org: Org) -> None:
    tenant_id = tenant_id_for_org(ready_org.org_id)
    engine = db.create_engine(settings)
    storage = S3Storage(settings)
    await storage.open()
    try:
        async with httpx.AsyncClient() as http:
            renderer = GotenbergRenderer(settings.gotenberg_url, http, timeout=30)
            target = EntityRef(entity_type="invoice", entity_id=uuid.uuid4())
            ids = []
            for view in (sample_view("invoice"), sample_view("invoice"), sample_view("receipt")):
                async with db.tenant_scope(db.create_session_factory(engine), tenant_id) as session:
                    doc = await rendering.generate_pdf(
                        session,
                        storage,
                        renderer,
                        tenant_id=tenant_id,
                        view=view,
                        entity=target,
                        actor=None,
                    )
                    ids.append(doc.id)
            assert ids[0] == ids[1]  # same content → same stored PDF, no re-render
            assert ids[2] != ids[0]
            async with db.tenant_scope(db.create_session_factory(engine), tenant_id) as session:
                from app.modules.documents import service as documents  # noqa: PLC0415

                data, media_type = await documents.read_current(
                    session, storage, ids[0], max_bytes=10**7
                )
            assert media_type == "application/pdf"
            assert "INV-2026-00042" in pdf_text(data)
    finally:
        await storage.close()
        await engine.dispose()
