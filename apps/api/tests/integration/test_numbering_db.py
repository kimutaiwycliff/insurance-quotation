"""Gapless numbering under concurrency, rollback, resets and branch schemes (plan M1 acceptance)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import db
from app.core.config import Settings
from app.core.tenancy import tenant_id_for_org
from app.modules.numbering import service
from tests.support import Org


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = db.create_engine(settings.model_copy(update={"database_pool_size": 20}))
    yield engine
    await engine.dispose()


async def _allocate(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    on: date,
    *,
    fail: bool = False,
    branch_id: uuid.UUID | None = None,
    branch_code: str | None = None,
) -> str:
    async with db.tenant_scope(factory, tenant_id) as session:
        number = await service.allocate_number(
            session, tenant_id, "invoice", on=on, branch_id=branch_id, branch_code=branch_code
        )
        if fail:
            raise RuntimeError("issue failed")
        return number.number


async def test_fifty_concurrent_issues_are_gapless_and_unique(
    engine: AsyncEngine, ready_org: Org
) -> None:
    tenant_id = tenant_id_for_org(ready_org.org_id)
    factory = db.create_session_factory(engine)
    on = date(2026, 10, 7)
    numbers = await asyncio.gather(*(_allocate(factory, tenant_id, on) for _ in range(50)))
    assert sorted(numbers) == [f"INV-2026-{n:05d}" for n in range(1, 51)]


async def test_rolled_back_issue_returns_its_number(engine: AsyncEngine, ready_org: Org) -> None:
    tenant_id = tenant_id_for_org(ready_org.org_id)
    factory = db.create_session_factory(engine)
    on = date(2026, 1, 15)
    assert await _allocate(factory, tenant_id, on) == "INV-2026-00001"
    with pytest.raises(RuntimeError):
        await _allocate(factory, tenant_id, on, fail=True)
    assert await _allocate(factory, tenant_id, on) == "INV-2026-00002"


async def test_yearly_reset(engine: AsyncEngine, ready_org: Org) -> None:
    tenant_id = tenant_id_for_org(ready_org.org_id)
    factory = db.create_session_factory(engine)
    assert await _allocate(factory, tenant_id, date(2026, 12, 31)) == "INV-2026-00001"
    assert await _allocate(factory, tenant_id, date(2027, 1, 1)) == "INV-2027-00001"


async def test_tenants_have_independent_sequences(
    engine: AsyncEngine, api: httpx.AsyncClient, ready_org: Org, other_org: Org
) -> None:
    await api.get("/api/v1/me", headers=other_org.headers())
    factory = db.create_session_factory(engine)
    on = date(2026, 5, 1)
    a = await _allocate(factory, tenant_id_for_org(ready_org.org_id), on)
    b = await _allocate(factory, tenant_id_for_org(other_org.org_id), on)
    assert a == b == "INV-2026-00001"


async def test_branch_scheme_takes_precedence(
    engine: AsyncEngine, api: httpx.AsyncClient, ready_org: Org
) -> None:
    headers = ready_org.headers()
    branch = (
        await api.post("/api/v1/branches", json={"name": "Kisumu", "code": "KSM"}, headers=headers)
    ).json()
    created = await api.post(
        "/api/v1/numbering-schemes",
        json={
            "document_type": "invoice",
            "branch_id": branch["id"],
            "pattern": "{BRANCH}/INV/{SEQ:4}",
            "reset_period": "never",
            "start_at": 100,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    tenant_id = tenant_id_for_org(ready_org.org_id)
    factory = db.create_session_factory(engine)
    on = date(2026, 6, 1)
    branch_id = uuid.UUID(branch["id"])
    for expected in ("KSM/INV/0100", "KSM/INV/0101"):
        number = await _allocate(factory, tenant_id, on, branch_id=branch_id, branch_code="KSM")
        assert number == expected
    assert await _allocate(factory, tenant_id, on) == "INV-2026-00001"  # tenant-wide scheme


class TestSchemeEndpoints:
    async def test_defaults_are_seeded(self, api: httpx.AsyncClient, ready_org: Org) -> None:
        schemes = (await api.get("/api/v1/numbering-schemes", headers=ready_org.headers())).json()
        assert {s["document_type"]: s["pattern"] for s in schemes} == service.DEFAULT_SCHEMES

    async def test_update_and_preview(self, api: httpx.AsyncClient, ready_org: Org) -> None:
        headers = ready_org.headers()
        scheme = next(
            s
            for s in (await api.get("/api/v1/numbering-schemes", headers=headers)).json()
            if s["document_type"] == "quote"
        )
        updated = await api.patch(
            f"/api/v1/numbering-schemes/{scheme['id']}",
            json={"pattern": "Q{YY}{MM}-{SEQ:3}", "reset_period": "monthly"},
            headers=headers | {"If-Match": f'W/"{scheme["version"]}"'},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["reset_period"] == "monthly"

        bad = await api.patch(
            f"/api/v1/numbering-schemes/{scheme['id']}",
            json={"pattern": "no-seq"},
            headers=headers | {"If-Match": updated.headers["ETag"]},
        )
        assert bad.status_code == 422

        preview = await api.post(
            "/api/v1/numbering-schemes/preview",
            json={
                "pattern": "INV-{BRANCH}-{YYYY}-{SEQ:4}",
                "on": "2026-10-07",
                "branch_code": "NBO",
            },
            headers=headers,
        )
        assert preview.json()["examples"] == [
            "INV-NBO-2026-0001",
            "INV-NBO-2026-0002",
            "INV-NBO-2026-0003",
        ]

    async def test_duplicate_and_foreign_branch(
        self, api: httpx.AsyncClient, ready_org: Org, other_org: Org
    ) -> None:
        dup = await api.post(
            "/api/v1/numbering-schemes",
            json={"document_type": "invoice", "pattern": "X-{SEQ}"},
            headers=ready_org.headers(),
        )
        assert dup.status_code == 409
        foreign = (
            await api.post(
                "/api/v1/branches", json={"name": "B", "code": "B"}, headers=other_org.headers()
            )
        ).json()
        response = await api.post(
            "/api/v1/numbering-schemes",
            json={"document_type": "invoice", "branch_id": foreign["id"], "pattern": "X-{SEQ}"},
            headers=ready_org.headers(),
        )
        assert response.status_code == 404

    async def test_missing_scheme(self, engine: AsyncEngine, ready_org: Org) -> None:
        tenant_id = tenant_id_for_org(ready_org.org_id)
        async with db.tenant_scope(db.create_session_factory(engine), tenant_id) as session:
            with pytest.raises(service.NoNumberingSchemeError):
                await service.allocate_number(session, tenant_id, "policy", on=date(2026, 1, 1))
