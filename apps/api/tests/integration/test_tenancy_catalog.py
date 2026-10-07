"""Catalog guard (SPEC_REVIEW §4.1 #5): every table in schema ``app`` is tenant-isolated or allow-listed.

Alembic autogenerate cannot see policies, so this is the safety net for RLS. It also checks that the database
matches the ORM models (schema drift) and that the currency table matches ``app.core.money``.
"""

import psycopg
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.all_models import Base
from app.core.config import Settings
from app.core.money import ISO_4217_MINOR_UNITS
from app.core.rls import GLOBAL_TABLES, POLICY_NAME, TENANT_KEY_OVERRIDES


async def _tables(conn: psycopg.AsyncConnection) -> dict[str, tuple[bool, bool]]:
    rows = await (
        await conn.execute(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'app' AND c.relkind IN ('r', 'p')"
        )
    ).fetchall()
    return {name: (rls, forced) for name, rls, forced in rows}


async def test_every_table_is_tenant_isolated_or_global(
    owner_conn: psycopg.AsyncConnection,
) -> None:
    tables = await _tables(owner_conn)
    assert tables, "no tables found in schema app"
    problems: list[str] = []
    for table, (rls, forced) in sorted(tables.items()):
        if table in GLOBAL_TABLES:
            continue
        key = TENANT_KEY_OVERRIDES.get(table, "tenant_id")
        if not (rls and forced):
            problems.append(f"{table}: RLS enabled={rls} forced={forced}")
        policy = await (
            await owner_conn.execute(
                "SELECT qual, with_check FROM pg_policies "
                "WHERE schemaname = 'app' AND tablename = %s AND policyname = %s",
                (table, POLICY_NAME),
            )
        ).fetchone()
        if policy is None:
            problems.append(f"{table}: no {POLICY_NAME} policy")
            continue
        for expr in policy:
            if (
                expr is None
                or f"{key} = " not in expr
                or "current_setting('app.tenant_id'" not in expr
            ):
                problems.append(f"{table}: unexpected policy expression {expr!r}")
        # Every FK to another tenant table must include the tenant key (composite FK).
        fks = await (
            await owner_conn.execute(
                "SELECT con.conname, ref.relname, "
                "  ARRAY(SELECT attname FROM pg_attribute WHERE attrelid = con.conrelid "
                "        AND attnum = ANY(con.conkey)) "
                "FROM pg_constraint con JOIN pg_class src ON src.oid = con.conrelid "
                "JOIN pg_class ref ON ref.oid = con.confrelid "
                "JOIN pg_namespace n ON n.oid = src.relnamespace "
                "WHERE con.contype = 'f' AND n.nspname = 'app' AND src.relname = %s",
                (table,),
            )
        ).fetchall()
        for name, referenced, columns in fks:
            if referenced not in GLOBAL_TABLES and key not in columns:
                problems.append(f"{table}: FK {name} → {referenced} lacks {key} {columns}")
    assert problems == []


async def test_global_tables_are_not_writable_by_the_api(
    app_user_conn: psycopg.AsyncConnection,
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await app_user_conn.execute("UPDATE app.currencies SET minor_unit = 5 WHERE code = 'KES'")


async def test_currency_table_matches_money_module(owner_conn: psycopg.AsyncConnection) -> None:
    rows = await (
        await owner_conn.execute("SELECT code, minor_unit FROM app.currencies")
    ).fetchall()
    assert dict(rows) == ISO_4217_MINOR_UNITS


def test_database_matches_models(settings: Settings) -> None:
    """Hand-written migrations and ORM models must describe the same schema."""
    assert settings.migrations_database_url is not None
    # "public" as the default schema makes reflected "app" tables carry their schema, like the models do.
    engine = create_engine(
        str(settings.migrations_database_url), connect_args={"options": "-c search_path=public"}
    )
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(
                conn,
                opts={
                    "include_schemas": True,
                    "include_name": lambda name, type_, _parent: type_ != "schema" or name == "app",
                },
            )
            diff = [
                d
                for d in compare_metadata(context, Base.metadata)
                if "alembic_version" not in str(d)
            ]
    finally:
        engine.dispose()
    assert diff == []
