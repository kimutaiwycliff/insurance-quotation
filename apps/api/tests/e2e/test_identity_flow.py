"""End-to-end identity flow through the real auth service, API and Mailpit (plan M1 acceptance).

sign up → verify email (Mailpit API) → create organization → tenant provisioned by the hook → JWT → /me →
optional 2FA enrolment → invite + accept → member mirrored → removal blocks access.

Runs with `make e2e`; skipped elsewhere.
"""

import asyncio
import base64
import hashlib
import hmac
import os
import re
import struct
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

AUTH = os.environ.get("E2E_AUTH_URL", "")
API = os.environ.get("E2E_API_URL", "")
MAILPIT = os.environ.get("E2E_MAILPIT_URL", "")
ORIGIN = os.environ.get("E2E_ORIGIN", "http://localhost:3000")

pytestmark = pytest.mark.skipif(not AUTH, reason="needs the live stack (make e2e)")
PASSWORD = "correct-horse-battery-9"


def totp(secret: str, at: float | None = None) -> str:
    """RFC 6238 TOTP (SHA-1, 6 digits, 30 s), enough to complete 2FA enrolment."""
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    counter = int((at or time.time()) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


@dataclass
class User:
    email: str
    session: str = ""

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.session}", "Origin": ORIGIN}


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        yield client


async def _mail_link(http: httpx.AsyncClient, to: str, contains: str) -> str:
    for _ in range(40):
        found = (await http.get(f"{MAILPIT}/api/v1/search", params={"query": f"to:{to}"})).json()
        for message in found.get("messages", []):
            body = (await http.get(f"{MAILPIT}/api/v1/message/{message['ID']}")).json()["Text"]
            match = re.search(rf"https?://\S*{re.escape(contains)}\S*", body)
            if match:
                return match.group(0)
        await asyncio.sleep(0.25)
    raise AssertionError(f"no email to {to} containing {contains}")


def _internal(url: str, base: str) -> str:
    """Links in emails use the public URL; reach the same path on the internal host."""
    parsed = urlparse(url)
    return f"{base}{parsed.path}?{parsed.query}" if parsed.query else f"{base}{parsed.path}"


async def sign_up_and_verify(http: httpx.AsyncClient, name: str) -> User:
    user = User(email=f"{name.lower()}-{uuid.uuid4().hex[:8]}@example.com")
    response = await http.post(
        f"{AUTH}/api/auth/sign-up/email",
        json={"email": user.email, "password": PASSWORD, "name": name},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200, response.text

    blocked = await http.post(
        f"{AUTH}/api/auth/sign-in/email",
        json={"email": user.email, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert blocked.status_code == 403  # email verification is required

    link = await _mail_link(http, user.email, "/api/auth/verify-email")
    token = parse_qs(urlparse(link).query)["token"][0]
    verified = await http.get(f"{AUTH}/api/auth/verify-email", params={"token": token})
    assert verified.status_code in (200, 302), verified.text

    signed_in = await http.post(
        f"{AUTH}/api/auth/sign-in/email",
        json={"email": user.email, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert signed_in.status_code == 200, signed_in.text
    user.session = signed_in.headers["set-auth-token"]
    return user


async def access_token(http: httpx.AsyncClient, user: User) -> str:
    response = await http.get(f"{AUTH}/api/auth/token", headers=user.auth_headers)
    assert response.status_code == 200, response.text
    return str(response.json()["token"])


async def api_get(http: httpx.AsyncClient, token: str, path: str) -> httpx.Response:
    return await http.get(f"{API}{path}", headers={"Authorization": f"Bearer {token}"})


async def auth_post(http: httpx.AsyncClient, user: User, path: str, body: dict[str, Any]) -> Any:
    response = await http.post(f"{AUTH}/api/auth{path}", json=body, headers=user.auth_headers)
    assert response.status_code == 200, (path, response.text)
    if rotated := response.headers.get("set-auth-token"):
        user.session = rotated  # e.g. enabling 2FA issues a new session
    return response.json()


async def test_agency_onboarding_end_to_end(http: httpx.AsyncClient) -> None:
    owner = await sign_up_and_verify(http, "Wanjiku")

    # No organization yet: the API asks the user to create one.
    no_org = await api_get(http, await access_token(http, owner), "/api/v1/me")
    assert no_org.status_code == 403
    assert no_org.json()["code"] == "no_active_organization"

    org = await auth_post(
        http,
        owner,
        "/organization/create",
        {"name": "Wanjiku Insurance Agency", "slug": f"wia-{uuid.uuid4().hex[:6]}"},
    )
    token = await access_token(http, owner)

    me = await api_get(http, token, "/api/v1/me")
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["tenant"]["name"] == "Wanjiku Insurance Agency"
    assert body["role"] == "owner"
    assert "branch:manage" in body["permissions"]
    assert body["mfa_required"] is False  # 2FA is optional (ADR-0007)
    assert body["mfa_enrolled"] is False

    # Optional TOTP enrolment: a fresh token then carries mfa_enrolled=true.
    enabled = await auth_post(http, owner, "/two-factor/enable", {"password": PASSWORD})
    secret = parse_qs(urlparse(enabled["totpURI"]).query)["secret"][0]
    await auth_post(http, owner, "/two-factor/verify-totp", {"code": totp(secret)})
    token = await access_token(http, owner)
    assert (await api_get(http, token, "/api/v1/me")).json()["mfa_enrolled"] is True
    organization = await api_get(http, token, "/api/v1/organization")
    assert organization.status_code == 200, organization.text
    assert organization.json()["default_currency"] == "KES"

    # Invite an agent; acceptance is mirrored into the API by the hook.
    agent = await sign_up_and_verify(http, "Otieno")
    invitation = await auth_post(
        http,
        owner,
        "/organization/invite-member",
        {"email": agent.email, "role": "agent", "organizationId": org["id"]},
    )
    await _mail_link(http, agent.email, "/accept-invitation/")
    await auth_post(
        http, agent, "/organization/accept-invitation", {"invitationId": invitation["id"]}
    )
    agent_token = await access_token(http, agent)
    agent_me = (await api_get(http, agent_token, "/api/v1/me")).json()
    assert agent_me["role"] == "agent"
    assert agent_me["tenant"]["id"] == body["tenant"]["id"]

    members = (await api_get(http, token, "/api/v1/members")).json()
    assert {m["email"]: m["role"] for m in members} == {owner.email: "owner", agent.email: "agent"}

    # Removing the agent blocks their still-valid token immediately.
    await auth_post(
        http,
        owner,
        "/organization/remove-member",
        {"memberIdOrEmail": agent.email, "organizationId": org["id"]},
    )
    removed = await api_get(http, agent_token, "/api/v1/me")
    assert removed.status_code == 403
    assert removed.json()["code"] == "membership_inactive"


async def test_api_rejects_tokens_not_issued_by_the_auth_service(http: httpx.AsyncClient) -> None:
    jwks = (await http.get(f"{AUTH}/api/auth/jwks")).json()
    assert jwks["keys"][0]["alg"] == "EdDSA"
    forged = await api_get(http, "eyJhbGciOiJFZERTQSIsImtpZCI6Im5vcGUifQ.e30.c2ln", "/api/v1/me")
    assert forged.status_code == 401
