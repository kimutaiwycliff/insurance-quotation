"""Organization settings and branches: optimistic concurrency, idempotency, audit trail, tenant isolation."""

import asyncio
import uuid

import httpx

from tests.support import Org


def _key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


class TestOrganization:
    async def test_update_requires_current_version(
        self, api: httpx.AsyncClient, ready_org: Org
    ) -> None:
        headers = ready_org.headers()
        current = await api.get("/api/v1/organization", headers=headers)
        etag = current.headers["ETag"]
        body = {
            "legal_name": "Wanjiku Agencies Ltd",
            "tax_pin": "p051234567x",
            "timezone": "Africa/Kampala",
        }

        missing = await api.patch("/api/v1/organization", json=body, headers=headers)
        assert missing.status_code == 428

        ok = await api.patch(
            "/api/v1/organization", json=body, headers=headers | {"If-Match": etag}
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["tax_pin"] == "P051234567X"
        assert ok.headers["ETag"] != etag

        stale = await api.patch(
            "/api/v1/organization", json=body, headers=headers | {"If-Match": etag}
        )
        assert stale.status_code == 412
        assert stale.json()["code"] == "version_conflict"

        events = (await api.get("/api/v1/audit-events", headers=headers)).json()["items"]
        assert events[0]["action"] == "organization.updated"
        assert events[0]["changes"]["legal_name"] == {"from": None, "to": "Wanjiku Agencies Ltd"}

    async def test_validation(self, api: httpx.AsyncClient, ready_org: Org) -> None:
        headers = ready_org.headers() | {"If-Match": 'W/"1"'}
        for body in ({"timezone": "Mars/Base"}, {"default_currency": "XXX"}, {"unknown": 1}):
            response = await api.patch("/api/v1/organization", json=body, headers=headers)
            assert response.status_code == 422, body


class TestBranches:
    async def test_crud_and_audit(self, api: httpx.AsyncClient, ready_org: Org) -> None:
        headers = ready_org.headers()
        created = await api.post(
            "/api/v1/branches",
            json={"name": "Mombasa", "code": "msa", "is_head_office": True},
            headers=headers | _key(),
        )
        assert created.status_code == 201, created.text
        branch = created.json()
        assert branch["code"] == "MSA"

        second = await api.post(
            "/api/v1/branches",
            json={"name": "Kisumu", "code": "KSM", "is_head_office": True},
            headers=headers,
        )
        listed = (await api.get("/api/v1/branches", headers=headers)).json()
        assert [b["code"] for b in listed if b["is_head_office"]] == ["KSM"]  # only one head office

        duplicate = await api.post(
            "/api/v1/branches", json={"name": "X", "code": "MSA"}, headers=headers
        )
        assert duplicate.status_code == 409

        get = await api.get(f"/api/v1/branches/{branch['id']}", headers=headers)
        archived = await api.patch(
            f"/api/v1/branches/{branch['id']}",
            json={"archived": True},
            headers=headers | {"If-Match": get.headers["ETag"]},
        )
        assert archived.status_code == 200, archived.text
        assert archived.json()["archived_at"] is not None
        active = (await api.get("/api/v1/branches", headers=headers)).json()
        assert branch["id"] not in {b["id"] for b in active}
        everything = (
            await api.get("/api/v1/branches?include_archived=true", headers=headers)
        ).json()
        assert branch["id"] in {b["id"] for b in everything}

        trail = (
            await api.get(f"/api/v1/audit-events?entity_id={branch['id']}", headers=headers)
        ).json()["items"]
        assert [e["action"] for e in trail] == ["branch.updated", "branch.created"]
        assert second.status_code == 201

    async def test_other_tenants_branch_is_not_found(
        self, api: httpx.AsyncClient, ready_org: Org, other_org: Org
    ) -> None:
        branch = (
            await api.post(
                "/api/v1/branches", json={"name": "A", "code": "A"}, headers=ready_org.headers()
            )
        ).json()
        response = await api.get(f"/api/v1/branches/{branch['id']}", headers=other_org.headers())
        assert response.status_code == 404
        patch = await api.patch(
            f"/api/v1/branches/{branch['id']}",
            json={"name": "stolen"},
            headers=other_org.headers() | {"If-Match": 'W/"1"'},
        )
        assert patch.status_code == 404


class TestIdempotency:
    async def test_retry_replays_the_first_response(
        self, api: httpx.AsyncClient, ready_org: Org
    ) -> None:
        headers = ready_org.headers() | _key()
        body = {"name": "Nakuru", "code": "NKR"}
        first = await api.post("/api/v1/branches", json=body, headers=headers)
        retry = await api.post("/api/v1/branches", json=body, headers=headers)
        assert first.status_code == retry.status_code == 201
        assert retry.json() == first.json()
        assert retry.headers["Idempotent-Replayed"] == "true"
        listed = (await api.get("/api/v1/branches", headers=ready_org.headers())).json()
        assert [b["code"] for b in listed].count("NKR") == 1

    async def test_same_key_different_body(self, api: httpx.AsyncClient, ready_org: Org) -> None:
        headers = ready_org.headers() | _key()
        await api.post("/api/v1/branches", json={"name": "A", "code": "AAA"}, headers=headers)
        response = await api.post(
            "/api/v1/branches", json={"name": "B", "code": "BBB"}, headers=headers
        )
        assert response.status_code == 422
        assert response.json()["code"] == "idempotency_key_reused"

    async def test_concurrent_retries_create_once(
        self, api: httpx.AsyncClient, ready_org: Org
    ) -> None:
        headers = ready_org.headers() | _key()
        body = {"name": "Eldoret", "code": "ELD"}
        responses = await asyncio.gather(
            *(api.post("/api/v1/branches", json=body, headers=headers) for _ in range(5))
        )
        assert {r.status_code for r in responses} == {201}
        assert len({r.json()["id"] for r in responses}) == 1

    async def test_failed_request_does_not_burn_the_key(
        self, api: httpx.AsyncClient, ready_org: Org
    ) -> None:
        headers = ready_org.headers()
        await api.post("/api/v1/branches", json={"name": "Thika", "code": "THK"}, headers=headers)
        key = _key()
        conflict = await api.post(
            "/api/v1/branches", json={"name": "T", "code": "THK"}, headers=headers | key
        )
        assert conflict.status_code == 409
        again = await api.post(
            "/api/v1/branches", json={"name": "T", "code": "THK"}, headers=headers | key
        )
        assert again.status_code == 409  # re-executed, not replayed

    async def test_keys_are_scoped_per_tenant(
        self, api: httpx.AsyncClient, ready_org: Org, other_org: Org
    ) -> None:
        key = _key()
        body = {"name": "Nyeri", "code": "NYR"}
        a = await api.post("/api/v1/branches", json=body, headers=ready_org.headers() | key)
        b = await api.post("/api/v1/branches", json=body, headers=other_org.headers() | key)
        assert a.status_code == b.status_code == 201
        assert a.json()["id"] != b.json()["id"]

    async def test_invalid_key(self, api: httpx.AsyncClient, ready_org: Org) -> None:
        response = await api.post(
            "/api/v1/branches",
            json={"name": "A", "code": "A"},
            headers=ready_org.headers() | {"Idempotency-Key": "short"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_idempotency_key"


async def test_audit_log_pagination(api: httpx.AsyncClient, ready_org: Org) -> None:
    headers = ready_org.headers()
    for code in ("P1", "P2", "P3"):
        await api.post("/api/v1/branches", json={"name": code, "code": code}, headers=headers)
    first = (await api.get("/api/v1/audit-events?limit=2", headers=headers)).json()
    assert len(first["items"]) == 2
    rest = (
        await api.get(
            f"/api/v1/audit-events?limit=2&cursor={first['next_cursor']}", headers=headers
        )
    ).json()
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None
    bad = await api.get("/api/v1/audit-events?cursor=@@@", headers=headers)
    assert bad.status_code == 400
