"""Access-token verification against the auth service's JWKS (ADR-0006).

* Keys are cached for ``AUTH_JWKS_CACHE_SECONDS``. An unknown ``kid`` triggers one refetch (key rotation), rate
  limited by ``AUTH_JWKS_MIN_REFETCH_SECONDS`` so garbage tokens cannot make us hammer the auth service.
* Only asymmetric algorithms from ``AUTH_ALGORITHMS`` are accepted (never ``none`` or HMAC).
* ``iss``, ``aud``, ``exp``, ``nbf`` and ``iat`` are checked; ``sub`` is required.
"""

import asyncio
import time
from collections.abc import Mapping
from typing import Any, Protocol

import httpx
import jwt
import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.core.errors import AuthenticationError

logger = structlog.get_logger(__name__)


class AccessClaims(BaseModel):
    """Claims the auth service puts in access tokens (``definePayload`` in apps/auth)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    sub: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(default="", max_length=255)
    # Active organization. Absent when the user has not created or chosen one yet.
    org_id: str | None = Field(default=None, min_length=1, max_length=255)
    org_role: str | None = Field(default=None, max_length=64)
    org_name: str | None = Field(default=None, max_length=255)
    org_slug: str | None = Field(default=None, max_length=255)
    mfa_enrolled: bool = False


class ServiceClaims(BaseModel):
    """Service-to-service token sent by the auth service to ``/internal/*``."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    sub: str


class KeySource(Protocol):
    async def get_key(self, kid: str) -> jwt.PyJWK: ...


class JwksCache:
    """Async JWKS fetcher with TTL caching and rate-limited refetch on unknown ``kid``."""

    def __init__(
        self,
        url: str,
        http: httpx.AsyncClient,
        *,
        cache_seconds: int,
        min_refetch_seconds: int,
    ) -> None:
        self._url = url
        self._http = http
        self._cache_seconds = cache_seconds
        self._min_refetch_seconds = min_refetch_seconds
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    def _age(self) -> float:
        return float("inf") if self._fetched_at is None else time.monotonic() - self._fetched_at

    async def _refresh(self) -> None:
        try:
            response = await self._http.get(self._url, timeout=5.0)
            response.raise_for_status()
            key_set = jwt.PyJWKSet.from_dict(response.json())
        except (httpx.HTTPError, ValueError, jwt.PyJWKSetError) as exc:
            logger.warning("jwks_fetch_failed", error=type(exc).__name__)
            # Keep serving the previous keys; back off before the next attempt.
            self._fetched_at = time.monotonic() - self._cache_seconds + self._min_refetch_seconds
            return
        self._keys = {key.key_id: key for key in key_set.keys if key.key_id}
        self._fetched_at = time.monotonic()
        logger.info("jwks_refreshed", keys=len(self._keys))

    async def get_key(self, kid: str) -> jwt.PyJWK:
        if kid in self._keys and self._age() < self._cache_seconds:
            return self._keys[kid]
        async with self._lock:
            age = self._age()
            stale = age >= self._cache_seconds
            unknown = kid not in self._keys
            if stale or (unknown and age >= self._min_refetch_seconds):
                await self._refresh()
        try:
            return self._keys[kid]
        except KeyError:
            raise AuthenticationError("Token signed with an unknown key") from None


class TokenVerifier:
    def __init__(self, settings: Settings, keys: KeySource) -> None:
        self._settings = settings
        self._keys = keys
        self._algorithms = list(settings.auth_algorithms)

    async def _decode(self, token: str, audience: str) -> Mapping[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError:
            raise AuthenticationError("Malformed token") from None
        if header.get("alg") not in self._algorithms:
            raise AuthenticationError("Token algorithm not allowed")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise AuthenticationError("Token has no key id")
        key = await self._keys.get_key(kid)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=self._algorithms,
                audience=audience,
                issuer=self._settings.auth_issuer,
                leeway=self._settings.auth_leeway_seconds,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired") from None
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError(f"Invalid token ({type(exc).__name__})") from None
        return claims

    async def verify_access_token(self, token: str) -> AccessClaims:
        claims = await self._decode(token, self._settings.auth_audience)
        try:
            return AccessClaims.model_validate(claims)
        except ValidationError:
            raise AuthenticationError("Token is missing required claims") from None

    async def verify_service_token(self, token: str) -> ServiceClaims:
        claims = await self._decode(token, self._settings.auth_internal_audience)
        service = ServiceClaims.model_validate(claims)
        if service.sub != "service:auth":
            raise AuthenticationError("Unknown service")
        return service


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("Missing bearer token")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Authorization header must be 'Bearer <token>'")
    return token.strip()
