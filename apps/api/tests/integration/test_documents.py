"""Documents: presigned upload → verify → download; sniffing, size, versions, links, isolation."""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import date

import httpx

from tests.integration.m2_helpers import PDF_BYTES, PNG_BYTES, entity, start_upload, upload
from tests.support import Org


async def test_upload_complete_download(api: httpx.AsyncClient, ready_org: Org) -> None:
    link = entity()
    doc = await upload(
        api, ready_org, "national-id.pdf", PDF_BYTES, links=[link], expires_on="2027-01-31"
    )
    assert doc["current_version_no"] == 1

    detail = (await api.get(f"/api/v1/documents/{doc['id']}", headers=ready_org.headers())).json()
    version = detail["versions"][0]
    assert version["status"] == "ready"
    assert version["content_type"] == "application/pdf"
    assert len(version["sha256"]) == 64
    assert detail["links"][0]["entity_id"] == link["entity_id"]

    url = (
        await api.get(f"/api/v1/documents/{doc['id']}/download", headers=ready_org.headers())
    ).json()["url"]
    async with httpx.AsyncClient() as raw:
        got = await raw.get(url)
    assert got.status_code == 200
    assert got.content == PDF_BYTES
    assert "attachment" in got.headers["content-disposition"]

    by_entity = (
        await api.get(
            "/api/v1/documents",
            params={"entity_type": "client", "entity_id": link["entity_id"]},
            headers=ready_org.headers(),
        )
    ).json()["items"]
    assert [d["id"] for d in by_entity] == [doc["id"]]
    expiring = (
        await api.get(
            "/api/v1/documents",
            params={"expiring_before": "2027-02-01"},
            headers=ready_org.headers(),
        )
    ).json()["items"]
    assert doc["id"] in {d["id"] for d in expiring}
    assert date.fromisoformat(expiring[0]["expires_on"]) <= date(2027, 2, 1)


async def test_disguised_file_is_rejected_and_deleted(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    started = await start_upload(api, ready_org, "invoice.pdf", len(PNG_BYTES))
    async with httpx.AsyncClient() as raw:
        await raw.put(
            started["upload"]["url"], content=PNG_BYTES, headers=started["upload"]["headers"]
        )
    response = await api.post(
        f"/api/v1/documents/{started['document']['id']}/versions/1/complete",
        headers=ready_org.headers(),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "upload_rejected"
    again = await api.post(
        f"/api/v1/documents/{started['document']['id']}/versions/1/complete",
        headers=ready_org.headers(),
    )
    assert again.json()["code"] == "upload_missing"  # the refused bytes were deleted


async def test_upload_must_match_signed_size_and_type(
    api: httpx.AsyncClient, ready_org: Org
) -> None:
    started = await start_upload(api, ready_org, "scan.pdf", len(PDF_BYTES))
    async with httpx.AsyncClient() as raw:
        bigger = await raw.put(
            started["upload"]["url"],
            content=PDF_BYTES + b"extra",
            headers=started["upload"]["headers"],
        )
        other_type = await raw.put(
            started["upload"]["url"], content=PDF_BYTES, headers={"Content-Type": "text/html"}
        )
    assert bigger.status_code == 403
    assert other_type.status_code == 403


async def test_limits(api: httpx.AsyncClient, ready_org: Org) -> None:
    for body in (
        {"filename": "virus.exe", "size_bytes": 10, "category": "other"},
        {"filename": "huge.pdf", "size_bytes": 10**9, "category": "other"},
    ):
        response = await api.post("/api/v1/documents", json=body, headers=ready_org.headers())
        assert response.status_code == 422, body


async def test_complete_before_upload(api: httpx.AsyncClient, ready_org: Org) -> None:
    started = await start_upload(api, ready_org, "later.pdf", 100)
    response = await api.post(
        f"/api/v1/documents/{started['document']['id']}/versions/1/complete",
        headers=ready_org.headers(),
    )
    assert response.status_code == 409


async def test_new_version_and_update(api: httpx.AsyncClient, ready_org: Org) -> None:
    doc = await upload(api, ready_org, "logbook.pdf", PDF_BYTES, category="vehicle_logbook")
    started = (
        await api.post(
            f"/api/v1/documents/{doc['id']}/versions",
            json={"filename": "logbook-2.png", "size_bytes": len(PNG_BYTES)},
            headers=ready_org.headers(),
        )
    ).json()
    async with httpx.AsyncClient() as raw:
        await raw.put(
            started["upload"]["url"], content=PNG_BYTES, headers=started["upload"]["headers"]
        )
    done = await api.post(
        f"/api/v1/documents/{doc['id']}/versions/2/complete", headers=ready_org.headers()
    )
    assert done.json()["current_version_no"] == 2

    get = await api.get(f"/api/v1/documents/{doc['id']}", headers=ready_org.headers())
    archived = await api.patch(
        f"/api/v1/documents/{doc['id']}",
        json={"archived": True, "title": "Old logbook"},
        headers=ready_org.headers() | {"If-Match": get.headers["ETag"]},
    )
    assert archived.json()["status"] == "archived"
    listed = (await api.get("/api/v1/documents", headers=ready_org.headers())).json()["items"]
    assert doc["id"] not in {d["id"] for d in listed}


async def test_link_and_unlink(api: httpx.AsyncClient, ready_org: Org) -> None:
    doc = await upload(api, ready_org, "kra-pin.pdf", PDF_BYTES, category="kyc_pin")
    ref = entity()
    link = (
        await api.post(
            f"/api/v1/documents/{doc['id']}/links", json=ref, headers=ready_org.headers()
        )
    ).json()
    again = await api.post(
        f"/api/v1/documents/{doc['id']}/links", json=ref, headers=ready_org.headers()
    )
    assert again.json()["id"] == link["id"]  # idempotent
    gone = await api.delete(
        f"/api/v1/documents/{doc['id']}/links/{link['id']}", headers=ready_org.headers()
    )
    assert gone.status_code == 204


async def test_other_tenant_cannot_see_or_download(
    api: httpx.AsyncClient, ready_org: Org, other_org: Org
) -> None:
    doc = await upload(api, ready_org, "secret.pdf", PDF_BYTES)
    for path in (f"/api/v1/documents/{doc['id']}", f"/api/v1/documents/{doc['id']}/download"):
        response = await api.get(path, headers=other_org.headers())
        assert response.status_code == 404, path


async def test_viewer_can_read_not_upload(api: httpx.AsyncClient, ready_org: Org) -> None:
    response = await api.post(
        "/api/v1/documents",
        json={"filename": "a.pdf", "size_bytes": 10, "category": "other"},
        headers=ready_org.headers("viewer"),
    )
    assert response.status_code == 403
    assert (
        await api.get("/api/v1/documents", headers=ready_org.headers("viewer"))
    ).status_code == 200


async def test_presigned_download_expires(
    make_api: Callable[..., AsyncIterator[httpx.AsyncClient]],
    ready_org: Org,
    api: httpx.AsyncClient,
) -> None:
    doc = await upload(api, ready_org, "short.pdf", PDF_BYTES)
    async for short in make_api(rate_limit_enabled=False, download_url_ttl_seconds=1):
        url = (
            await short.get(f"/api/v1/documents/{doc['id']}/download", headers=ready_org.headers())
        ).json()["url"]
    await asyncio.sleep(2.1)
    async with httpx.AsyncClient() as raw:
        assert (await raw.get(url)).status_code == 403
