"""Authentication, principal resolution, provisioning (hook and lazy), MFA policy and permissions."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from app.core.permissions import ROLE_PERMISSIONS, Perm, Role
from app.core.tenancy import tenant_id_for_org
from tests.support import Org, SigningKey, access_claims, new_id, service_claims


class TestAuthentication:
    async def test_missing_token(self, api: httpx.AsyncClient) -> None:
        response = await api.get("/api/v1/me")
        assert response.status_code == 401
        assert response.json()["code"] == "unauthenticated"
        assert response.headers["WWW-Authenticate"] == "Bearer"

    async def test_expired_token(self, api: httpx.AsyncClient, org: Org) -> None:
        token = org.key.sign(
            access_claims(user_id=org.owner_id, org_id=org.org_id) | {"exp": int(time.time()) - 60}
        )
        response = await api.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    async def test_token_from_unknown_key(self, api: httpx.AsyncClient, org: Org) -> None:
        forged = Org(key=SigningKey(), org_id=org.org_id)
        response = await api.get("/api/v1/me", headers=forged.headers())
        assert response.status_code == 401

    async def test_no_active_organization(self, api: httpx.AsyncClient, org: Org) -> None:
        token = org.key.sign(access_claims(user_id=new_id("usr"), org_id=None))
        response = await api.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403
        assert response.json()["code"] == "no_active_organization"


class TestLazyProvisioning:
    async def test_first_request_provisions_tenant_and_owner(
        self, api: httpx.AsyncClient, org: Org
    ) -> None:
        response = await api.get("/api/v1/me", headers=org.headers())
        assert response.status_code == 200, response.text
        me = response.json()
        assert me["tenant"]["id"] == str(tenant_id_for_org(org.org_id))
        assert me["tenant"]["name"] == "Test Agency"
        assert me["role"] == "owner"
        assert set(me["permissions"]) == {p.value for p in Perm}
        assert me["mfa_required"] is False

    async def test_concurrent_first_requests_provision_once(
        self, api: httpx.AsyncClient, org: Org
    ) -> None:
        responses = await asyncio.gather(
            *(api.get("/api/v1/me", headers=org.headers()) for _ in range(5))
        )
        assert [r.status_code for r in responses] == [200] * 5
        assert len({r.json()["tenant"]["id"] for r in responses}) == 1

    async def test_second_user_joins_with_token_role(
        self, api: httpx.AsyncClient, ready_org: Org
    ) -> None:
        response = await api.get("/api/v1/me", headers=ready_org.headers("agent"))
        assert response.json()["role"] == "agent"
        members = (await api.get("/api/v1/members", headers=ready_org.headers())).json()
        assert {m["role"] for m in members} == {"owner", "agent"}


class TestMfaPolicy:
    async def test_2fa_is_optional_by_default(self, api: httpx.AsyncClient, org: Org) -> None:
        headers = org.headers(mfa=False)
        me = await api.get("/api/v1/me", headers=headers)
        assert me.json()["mfa_required"] is False
        assert (await api.get("/api/v1/organization", headers=headers)).status_code == 200

    async def test_enforced_roles_are_blocked_except_me(
        self, make_api: Callable[..., AsyncIterator[httpx.AsyncClient]], org: Org
    ) -> None:
        headers = org.headers(mfa=False)
        async for api in make_api(rate_limit_enabled=False, mfa_enforced_roles=["owner"]):
            me = await api.get("/api/v1/me", headers=headers)
            assert me.status_code == 200
            assert me.json()["mfa_required"] is True
            response = await api.get("/api/v1/organization", headers=headers)
            assert response.status_code == 403
            assert response.json()["code"] == "mfa_required"
            enrolled = await api.get("/api/v1/organization", headers=org.headers(mfa=True))
            assert enrolled.status_code == 200

    async def test_agent_without_mfa_is_allowed(
        self, api: httpx.AsyncClient, ready_org: Org
    ) -> None:
        response = await api.get("/api/v1/branches", headers=ready_org.headers("agent", mfa=False))
        assert response.status_code == 200


ENDPOINTS: list[tuple[str, str, Perm]] = [
    ("GET", "/api/v1/organization", Perm.ORG_READ),
    ("GET", "/api/v1/branches", Perm.BRANCH_READ),
    ("GET", "/api/v1/members", Perm.MEMBER_READ),
    ("GET", "/api/v1/roles", Perm.MEMBER_READ),
    ("GET", "/api/v1/numbering-schemes", Perm.NUMBERING_READ),
    ("GET", "/api/v1/audit-events", Perm.AUDIT_READ),
    ("PATCH", "/api/v1/organization", Perm.ORG_UPDATE),
    ("POST", "/api/v1/branches", Perm.BRANCH_MANAGE),
    ("POST", "/api/v1/numbering-schemes", Perm.NUMBERING_MANAGE),
    ("GET", "/api/v1/documents", Perm.DOCUMENT_READ),
    ("POST", "/api/v1/documents", Perm.DOCUMENT_WRITE),
    ("PATCH", "/api/v1/branding", Perm.BRANDING_MANAGE),
    ("POST", "/api/v1/public-links", Perm.LINK_MANAGE),
    ("GET", "/api/v1/messages", Perm.MESSAGE_READ),
    ("POST", "/api/v1/messages/test-email", Perm.MESSAGE_TEMPLATE_MANAGE),
    ("POST", "/api/v1/clients", Perm.CLIENT_WRITE),
    ("POST", "/api/v1/leads", Perm.LEAD_WRITE),
    ("POST", "/api/v1/tasks", Perm.TASK_WRITE),
    ("POST", "/api/v1/policies", Perm.CLIENT_WRITE),
    ("POST", "/api/v1/invoices", Perm.INVOICE_WRITE),
    ("POST", "/api/v1/payments", Perm.PAYMENT_WRITE),
    ("POST", "/api/v1/items", Perm.CATALOG_MANAGE),
    ("PUT", "/api/v1/mpesa/connection", Perm.ORG_UPDATE),
    ("GET", "/api/v1/mpesa/transactions", Perm.PAYMENT_WRITE),
    ("GET", "/api/v1/commission-receipts", Perm.COMMISSION_READ_ALL),
    ("POST", "/api/v1/commission-receipts", Perm.COMMISSION_MANAGE),
    (
        "POST",
        "/api/v1/policies/00000000-0000-7000-8000-000000000000/payments",
        Perm.PREMIUM_WRITE,
    ),
]


@pytest.mark.parametrize("role", list(Role))
async def test_permission_matrix(api: httpx.AsyncClient, ready_org: Org, role: Role) -> None:
    """Role x endpoint: allowed → not 403, denied → 403 permission_denied (generated from the registry)."""
    headers = ready_org.headers(role.value)
    for method, path, perm in ENDPOINTS:
        response = await api.request(method, path, headers=headers, json={})
        allowed = perm in ROLE_PERMISSIONS[role]
        if allowed:
            assert response.status_code != 403, (role, path, response.text)
        else:
            assert response.status_code == 403, (role, path, response.text)
            assert response.json()["code"] == "permission_denied"


class TestInternalHooks:
    async def test_hook_provisions_tenant_and_owner(
        self, api: httpx.AsyncClient, org: Org, service_headers: dict[str, str]
    ) -> None:
        body = {
            "org_id": org.org_id,
            "name": "Wanjiku Insurance Agency",
            "slug": "wanjiku",
            "owner": {"user_id": org.owner_id, "email": "owner@wanjiku.co.ke", "name": "Wanjiku"},
        }
        first = await api.post("/internal/v1/tenants", json=body, headers=service_headers)
        again = await api.post("/internal/v1/tenants", json=body, headers=service_headers)
        assert first.json()["created"] is True
        assert again.json()["created"] is False  # idempotent

        me = (await api.get("/api/v1/me", headers=org.headers())).json()
        assert me["tenant"]["name"] == "Wanjiku Insurance Agency"
        assert me["email"] == "owner@wanjiku.co.ke"
        org_out = (await api.get("/api/v1/organization", headers=org.headers())).json()
        assert org_out["timezone"] == "Africa/Nairobi"
        assert org_out["default_currency"] == "KES"

    async def test_member_role_change_and_removal_take_effect_immediately(
        self, api: httpx.AsyncClient, ready_org: Org, service_headers: dict[str, str]
    ) -> None:
        user_id = new_id("usr")
        member = {
            "org_id": ready_org.org_id,
            "org_name": "Test Agency",
            "user": {"user_id": user_id, "email": "agent@example.com", "name": "Otieno"},
            "role": "viewer",
        }
        headers = ready_org.headers("agent", user_id=user_id)  # token still says "agent"
        assert (
            await api.put("/internal/v1/memberships", json=member, headers=service_headers)
        ).status_code == 204
        assert (await api.get("/api/v1/me", headers=headers)).json()[
            "role"
        ] == "viewer"  # mirror wins

        remove = {"org_id": ready_org.org_id, "user_id": user_id}
        response = await api.post(
            "/internal/v1/memberships/remove", json=remove, headers=service_headers
        )
        assert response.status_code == 204
        blocked = await api.get("/api/v1/me", headers=headers)
        assert blocked.status_code == 403
        assert blocked.json()["code"] == "membership_inactive"

        # Re-invited: active again.
        await api.put("/internal/v1/memberships", json=member, headers=service_headers)
        assert (await api.get("/api/v1/me", headers=headers)).status_code == 200

    @pytest.mark.parametrize("kind", ["none", "access", "other_service"])
    async def test_internal_routes_need_the_auth_service_token(
        self, api: httpx.AsyncClient, org: Org, kind: str
    ) -> None:
        headers = {
            "none": {},
            "access": org.headers(),
            "other_service": {
                "Authorization": f"Bearer {org.key.sign(service_claims('service:x'))}"
            },
        }[kind]
        body = {"org_id": org.org_id, "user_id": "u"}
        response = await api.post("/internal/v1/memberships/remove", json=body, headers=headers)
        assert response.status_code == 401
