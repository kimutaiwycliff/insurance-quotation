"""Row-Level Security proofs, using raw SQL as the API role (no ORM, no API layer in between)."""

import uuid

import httpx
import psycopg
import pytest

from app.core.tenancy import tenant_id_for_org
from tests.integration.conftest import provision
from tests.support import Org


async def _set_tenant(conn: psycopg.AsyncConnection, tenant_id: uuid.UUID | None) -> None:
    await conn.execute(
        "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id) if tenant_id else "",)
    )


@pytest.fixture
async def two_tenants(
    api: httpx.AsyncClient, org: Org, other_org: Org
) -> tuple[uuid.UUID, uuid.UUID]:
    await provision(api, org)
    await provision(api, other_org)
    for o in (org, other_org):
        response = await api.post(
            "/api/v1/branches", json={"name": "Nairobi", "code": "NBO"}, headers=o.headers()
        )
        assert response.status_code == 201, response.text
    return tenant_id_for_org(org.org_id), tenant_id_for_org(other_org.org_id)


TENANT_TABLES = ["tenants", "memberships", "branches", "numbering_schemes", "audit_events"]


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_no_tenant_context_sees_nothing(
    app_user_conn: psycopg.AsyncConnection, two_tenants: object, table: str
) -> None:
    async with app_user_conn.transaction(force_rollback=True):
        row = await (await app_user_conn.execute(f"SELECT count(*) FROM app.{table}")).fetchone()  # noqa: S608
        assert row == (0,)
        await _set_tenant(app_user_conn, None)
        row = await (await app_user_conn.execute(f"SELECT count(*) FROM app.{table}")).fetchone()  # noqa: S608
        assert row == (0,)


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_tenant_sees_only_its_rows(
    app_user_conn: psycopg.AsyncConnection,
    two_tenants: tuple[uuid.UUID, uuid.UUID],
    table: str,
) -> None:
    tenant_a, tenant_b = two_tenants
    key = "id" if table == "tenants" else "tenant_id"
    async with app_user_conn.transaction(force_rollback=True):
        await _set_tenant(app_user_conn, tenant_a)
        rows = await (
            await app_user_conn.execute(f"SELECT DISTINCT {key} FROM app.{table}")  # noqa: S608
        ).fetchall()
        assert rows == [(tenant_a,)]
        assert tenant_b not in {r[0] for r in rows}


async def test_cannot_insert_rows_for_another_tenant(
    app_user_conn: psycopg.AsyncConnection, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    tenant_a, tenant_b = two_tenants
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="row-level security"):
        async with app_user_conn.transaction():
            await _set_tenant(app_user_conn, tenant_a)
            await app_user_conn.execute(
                "INSERT INTO app.branches (tenant_id, name, code) VALUES (%s, 'X', 'X')",
                (tenant_b,),
            )


async def test_cannot_move_a_row_to_another_tenant(
    app_user_conn: psycopg.AsyncConnection, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    tenant_a, tenant_b = two_tenants
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="row-level security"):
        async with app_user_conn.transaction():
            await _set_tenant(app_user_conn, tenant_a)
            await app_user_conn.execute("UPDATE app.branches SET tenant_id = %s", (tenant_b,))


async def test_composite_fk_blocks_cross_tenant_references(
    app_user_conn: psycopg.AsyncConnection, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """A row in tenant A cannot point at tenant B's branch, even knowing its id (FKs bypass RLS)."""
    tenant_a, tenant_b = two_tenants
    async with app_user_conn.transaction(force_rollback=True):
        await _set_tenant(app_user_conn, tenant_b)
        row = await (await app_user_conn.execute("SELECT id FROM app.branches")).fetchone()
        assert row is not None
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        async with app_user_conn.transaction():
            await _set_tenant(app_user_conn, tenant_a)
            await app_user_conn.execute(
                "INSERT INTO app.numbering_schemes (tenant_id, document_type, branch_id, pattern) "
                "VALUES (%s, 'invoice', %s, '{SEQ}')",
                (tenant_a, row[0]),
            )


async def test_context_does_not_leak_across_transactions(
    app_user_conn: psycopg.AsyncConnection, two_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    async with app_user_conn.transaction():
        await _set_tenant(app_user_conn, two_tenants[0])
    row = await (
        await app_user_conn.execute("SELECT current_setting('app.tenant_id', true)")
    ).fetchone()
    assert row is not None
    assert not row[0]
    await app_user_conn.rollback()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE app.audit_events SET action = 'tampered'",
        "DELETE FROM app.audit_events",
        "DELETE FROM app.branches",
        "DELETE FROM app.tenants",
    ],
)
async def test_append_only_and_no_hard_delete(
    app_user_conn: psycopg.AsyncConnection,
    two_tenants: tuple[uuid.UUID, uuid.UUID],
    statement: str,
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with app_user_conn.transaction():
            await _set_tenant(app_user_conn, two_tenants[0])
            await app_user_conn.execute(statement)
