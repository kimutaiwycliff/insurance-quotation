"""Test helpers: an in-memory signing key, token minting and org/user factories (spec §7.4)."""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.errors import AuthenticationError
from app.core.permissions import Role

ISSUER = "http://localhost:3001"
AUDIENCE = "brokeros-api"
INTERNAL_AUDIENCE = "brokeros-internal"


@dataclass
class SigningKey:
    kid: str = field(default_factory=lambda: f"test-{uuid.uuid4().hex[:8]}")
    private: Ed25519PrivateKey = field(default_factory=Ed25519PrivateKey.generate)

    def jwk(self) -> dict[str, Any]:
        public = json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(self.private.public_key()))
        return {**public, "kid": self.kid, "alg": "EdDSA", "use": "sig"}

    def jwks(self) -> dict[str, Any]:
        return {"keys": [self.jwk()]}

    def sign(self, claims: dict[str, Any], *, headers: dict[str, Any] | None = None) -> str:
        return jwt.encode(
            claims, self.private, algorithm="EdDSA", headers={"kid": self.kid, **(headers or {})}
        )


class StaticKeys:
    """``KeySource`` serving fixed keys (replaces the JWKS fetcher in tests)."""

    def __init__(self, *keys: SigningKey) -> None:
        self._keys = {k.kid: jwt.PyJWK(k.jwk()) for k in keys}

    async def get_key(self, kid: str) -> jwt.PyJWK:
        try:
            return self._keys[kid]
        except KeyError:
            raise AuthenticationError("Token signed with an unknown key") from None


def access_claims(
    *,
    user_id: str,
    org_id: str | None,
    role: str = Role.OWNER.value,
    email: str | None = None,
    mfa: bool = True,
    org_name: str | None = "Test Agency",
    ttl: int = 900,
    **extra: Any,
) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": user_id,
        "iat": now,
        "nbf": now,
        "exp": now + ttl,
        "email": email or f"{user_id}@example.com",
        "name": f"User {user_id[-4:]}",
        "mfa_enrolled": mfa,
        **extra,
    }
    if org_id is not None:
        claims |= {"org_id": org_id, "org_role": role, "org_name": org_name}
    return claims


def service_claims(sub: str = "service:auth", ttl: int = 60) -> dict[str, Any]:
    now = int(time.time())
    return {"iss": ISSUER, "aud": INTERNAL_AUDIENCE, "sub": sub, "iat": now, "exp": now + ttl}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass
class Org:
    """A test organization with a token factory per role."""

    key: SigningKey
    org_id: str = field(default_factory=lambda: new_id("org"))
    owner_id: str = field(default_factory=lambda: new_id("usr"))

    def token(self, role: str = "owner", *, user_id: str | None = None, **kw: Any) -> str:
        uid = user_id or (self.owner_id if role == "owner" else f"{self.org_id}-{role}")
        return self.key.sign(access_claims(user_id=uid, org_id=self.org_id, role=role, **kw))

    def headers(self, role: str = "owner", **kw: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(role, **kw)}"}
