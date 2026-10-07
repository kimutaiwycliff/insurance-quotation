"""Row-Level Security DDL used by migrations (ADR-0003).

Every tenant-owned table gets RLS **enabled and forced** and one ``tenant_isolation`` policy with the predicate
below. The sub-select makes Postgres evaluate the setting once per statement; ``NULLIF(..., '')`` with
``missing_ok`` makes an unset context match **no rows** instead of raising.

The catalog guard test (``tests/integration/test_tenancy_catalog.py``) checks that every table in schema ``app``
either follows this pattern or is listed in :data:`GLOBAL_TABLES`.
"""

TENANT_SETTING = "app.tenant_id"
TENANT_PREDICATE = "(SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
POLICY_NAME = "tenant_isolation"
APP_ROLE = "app_user"

# Tables in schema "app" that are intentionally not tenant-scoped. Adding to this list needs review.
GLOBAL_TABLES: frozenset[str] = frozenset(
    {
        "alembic_version",  # migration bookkeeping
        "currencies",  # ISO 4217 reference data, read-only to app_user
    }
)

# Tables whose tenant key column is not called ``tenant_id``.
TENANT_KEY_OVERRIDES: dict[str, str] = {"tenants": "id"}


def _qualified(table: str, schema: str) -> str:
    return f'"{schema}"."{table}"'


def enable_tenant_rls(table: str, *, column: str = "tenant_id", schema: str = "app") -> list[str]:
    """Statements that put ``table`` under tenant isolation."""
    qualified = _qualified(table, schema)
    predicate = f"{column} = {TENANT_PREDICATE}"
    return [
        f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {POLICY_NAME} ON {qualified} USING ({predicate}) WITH CHECK ({predicate})",
    ]


def disable_tenant_rls(table: str, *, schema: str = "app") -> list[str]:
    qualified = _qualified(table, schema)
    return [
        f"DROP POLICY IF EXISTS {POLICY_NAME} ON {qualified}",
        f"ALTER TABLE {qualified} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {qualified} DISABLE ROW LEVEL SECURITY",
    ]


def append_only(table: str, *, schema: str = "app", role: str = APP_ROLE) -> list[str]:
    """Make a table insert/read-only for the API role (audit log, ledgers)."""
    return [f"REVOKE UPDATE, DELETE, TRUNCATE ON {_qualified(table, schema)} FROM {role}"]


def read_only(table: str, *, schema: str = "app", role: str = APP_ROLE) -> list[str]:
    """Reference data the API may read but never change."""
    return [f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON {_qualified(table, schema)} FROM {role}"]
