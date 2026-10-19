"""Concurrency headers, cursors, permissions and the route-permission registry."""

import uuid

import pytest
from fastapi import Response
from fastapi.routing import APIRoute

from app.core.concurrency import check_version, etag, parse_if_match
from app.core.config import Settings
from app.core.errors import PreconditionFailedError, PreconditionRequiredError
from app.core.pagination import InvalidCursorError, build_page, decode_cursor, encode_cursor
from app.core.permissions import ROLE_PERMISSIONS, Perm, Role, normalise_role, permissions_for
from app.core.tenancy import tenant_id_for_org
from app.main import API_V1_PREFIX, create_app
from app.modules.numbering.references import generate_payment_reference
from app.platform.app_config import app_config


class TestConcurrency:
    def test_etag_round_trip(self) -> None:
        assert parse_if_match(etag(7)) == 7
        assert parse_if_match('"7"') == 7

    def test_missing_and_malformed(self) -> None:
        with pytest.raises(PreconditionRequiredError):
            parse_if_match(None)
        with pytest.raises(PreconditionFailedError):
            parse_if_match("*")

    def test_stale_version(self) -> None:
        check_version(etag(3), 3)
        with pytest.raises(PreconditionFailedError):
            check_version(etag(2), 3)


class TestPagination:
    def test_cursor_round_trip(self) -> None:
        value = uuid.uuid7()
        assert decode_cursor(encode_cursor(value)) == value

    @pytest.mark.parametrize("bad", ["!!!", "abc", "A" * 30])
    def test_invalid_cursor(self, bad: str) -> None:
        with pytest.raises(InvalidCursorError):
            decode_cursor(bad)

    def test_build_page(self) -> None:
        ids = [uuid.uuid7() for _ in range(3)]
        page = build_page(["a", "b", "c"], ids, limit=2)
        assert page.items == ["a", "b"]
        assert page.next_cursor == encode_cursor(ids[1])
        assert build_page(["a"], ids[:1], limit=2).next_cursor is None


class TestPermissions:
    def test_owner_and_admin_have_everything(self) -> None:
        assert ROLE_PERMISSIONS[Role.OWNER] == frozenset(Perm)
        assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(Perm)

    def test_every_role_is_mapped(self) -> None:
        assert set(ROLE_PERMISSIONS) == set(Role)

    def test_viewer_cannot_write(self) -> None:
        assert not {p for p in permissions_for("viewer") if p.endswith(("manage", "update"))}

    def test_unknown_role_grants_nothing(self) -> None:
        assert permissions_for("superuser") == frozenset()

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("owner", "owner"),
            ("agent,admin", "admin"),
            (" Accounts ", "accounts"),
            ("member", "agent"),
            ("", "viewer"),
            (None, "viewer"),
            ("hacker", "viewer"),
        ],
    )
    def test_normalise_role(self, raw: str | None, expected: str) -> None:
        assert normalise_role(raw) == expected


class TestTenancy:
    def test_tenant_id_is_deterministic(self) -> None:
        assert tenant_id_for_org("org_1") == tenant_id_for_org("org_1")
        assert tenant_id_for_org("org_1") != tenant_id_for_org("org_2")

    @pytest.mark.parametrize("bad", ["", "x" * 256])
    def test_rejects_bad_org_ids(self, bad: str) -> None:
        with pytest.raises(ValueError, match="organization id"):
            tenant_id_for_org(bad)


def test_payment_reference_is_random() -> None:
    assert len({generate_payment_reference() for _ in range(100)}) == 100


def test_every_api_route_declares_a_permission(unit_settings: object) -> None:
    """Every tenant endpoint goes through require_permission (spec §7.3, plan §3.1)."""
    app = create_app(unit_settings)  # type: ignore[arg-type]
    undeclared = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(API_V1_PREFIX):
            continue
        if route.path.startswith((f"{API_V1_PREFIX}/public/", f"{API_V1_PREFIX}/webhooks/")):
            continue  # anonymous, token-scoped routes and provider callbacks (secret paths)
        calls = [d.call for d in route.dependant.dependencies]
        if not any(hasattr(c, "required_permission") for c in calls):
            undeclared.append(f"{sorted(route.methods or ())} {route.path}")
    assert undeclared == []


async def test_app_config_reports_update_rules() -> None:
    settings = Settings(
        android_min_version_code=5,
        android_latest_version_code=3,  # never below the minimum
        android_store_url="https://play.google.com/store/apps/details?id=app.example",
        android_apk_url="https://app.example/downloads/app-5.apk",
        android_apk_sha256=" ABCDEF ",
        app_notice="",
        app_features="offline_notes, new_dashboard",  # type: ignore[arg-type]
    )
    response = Response()
    out = await app_config(response, settings)
    assert (out.android.min_version_code, out.android.latest_version_code) == (5, 5)
    assert (out.android.apk_url, out.android.apk_sha256) == (
        "https://app.example/downloads/app-5.apk",
        "abcdef",
    )
    assert out.notice is None
    assert out.features == ["offline_notes", "new_dashboard"]
    assert response.headers["Cache-Control"] == "public, max-age=300"
