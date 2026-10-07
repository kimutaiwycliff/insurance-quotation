"""Access-token verification and the JWKS cache."""

import time
from collections.abc import AsyncIterator

import httpx
import jwt
import pytest
import respx

from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.core.security import JwksCache, TokenVerifier, bearer_token
from tests.support import (
    INTERNAL_AUDIENCE,
    SigningKey,
    StaticKeys,
    access_claims,
    service_claims,
)

JWKS_URL = "http://auth.test/api/auth/jwks"


@pytest.fixture
def key() -> SigningKey:
    return SigningKey()


@pytest.fixture
def verifier(unit_settings: Settings, key: SigningKey) -> TokenVerifier:
    return TokenVerifier(unit_settings, StaticKeys(key))


class TestAccessTokens:
    async def test_valid_token(self, verifier: TokenVerifier, key: SigningKey) -> None:
        claims = await verifier.verify_access_token(
            key.sign(access_claims(user_id="u1", org_id="o1", role="agent"))
        )
        assert (claims.sub, claims.org_id, claims.org_role) == ("u1", "o1", "agent")

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"exp": int(time.time()) - 120}, "expired"),
            ({"aud": "someone-else"}, "InvalidAudience"),
            ({"iss": "http://evil.test"}, "InvalidIssuer"),
            ({"nbf": int(time.time()) + 600}, "ImmatureSignature"),
            ({"email": None}, "missing required claims"),
        ],
    )
    async def test_rejects_bad_claims(
        self, verifier: TokenVerifier, key: SigningKey, overrides: dict[str, object], message: str
    ) -> None:
        claims = access_claims(user_id="u1", org_id="o1") | overrides
        with pytest.raises(AuthenticationError, match=message):
            await verifier.verify_access_token(key.sign(claims))

    async def test_rejects_unknown_key(self, verifier: TokenVerifier) -> None:
        with pytest.raises(AuthenticationError, match="unknown key"):
            await verifier.verify_access_token(
                SigningKey().sign(access_claims(user_id="u1", org_id="o1"))
            )

    async def test_rejects_hmac_and_none_algorithms(self, verifier: TokenVerifier) -> None:
        claims = access_claims(user_id="u1", org_id="o1")
        hmac_token = jwt.encode(claims, "x" * 32, algorithm="HS256", headers={"kid": "k"})
        with pytest.raises(AuthenticationError, match="algorithm"):
            await verifier.verify_access_token(hmac_token)
        none_token = jwt.encode(claims, None, algorithm="none")  # type: ignore[arg-type]
        with pytest.raises(AuthenticationError, match="algorithm"):
            await verifier.verify_access_token(none_token)

    async def test_rejects_missing_kid_and_garbage(
        self, verifier: TokenVerifier, key: SigningKey
    ) -> None:
        no_kid = jwt.encode(access_claims(user_id="u", org_id="o"), key.private, algorithm="EdDSA")
        with pytest.raises(AuthenticationError, match="key id"):
            await verifier.verify_access_token(no_kid)
        with pytest.raises(AuthenticationError, match="Malformed"):
            await verifier.verify_access_token("not-a-jwt")

    async def test_access_token_is_not_a_service_token(
        self, verifier: TokenVerifier, key: SigningKey
    ) -> None:
        with pytest.raises(AuthenticationError):
            await verifier.verify_service_token(key.sign(access_claims(user_id="u", org_id="o")))


class TestServiceTokens:
    async def test_valid(self, verifier: TokenVerifier, key: SigningKey) -> None:
        assert (
            await verifier.verify_service_token(key.sign(service_claims()))
        ).sub == "service:auth"

    async def test_unknown_service(self, verifier: TokenVerifier, key: SigningKey) -> None:
        with pytest.raises(AuthenticationError, match="Unknown service"):
            await verifier.verify_service_token(key.sign(service_claims(sub="service:other")))

    async def test_service_token_is_not_an_access_token(
        self, verifier: TokenVerifier, key: SigningKey
    ) -> None:
        assert service_claims()["aud"] == INTERNAL_AUDIENCE
        with pytest.raises(AuthenticationError, match="InvalidAudience"):
            await verifier.verify_access_token(key.sign(service_claims()))


@pytest.mark.parametrize(
    ("header", "ok"),
    [
        ("Bearer abc", True),
        ("bearer abc", True),
        (None, False),
        ("Basic abc", False),
        ("Bearer ", False),
    ],
)
def test_bearer_token_parsing(header: str | None, ok: bool) -> None:
    if ok:
        assert bearer_token(header) == "abc"
    else:
        with pytest.raises(AuthenticationError):
            bearer_token(header)


class TestJwksCache:
    @pytest.fixture
    async def http(self) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient() as client:
            yield client

    @respx.mock
    async def test_fetches_caches_and_refetches_on_rotation(self, http: httpx.AsyncClient) -> None:
        old, new = SigningKey(), SigningKey()
        route = respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=old.jwks()))
        cache = JwksCache(JWKS_URL, http, cache_seconds=600, min_refetch_seconds=0)

        assert (await cache.get_key(old.kid)).key_id == old.kid
        await cache.get_key(old.kid)
        assert route.call_count == 1  # cached

        route.mock(return_value=httpx.Response(200, json=new.jwks()))
        assert (await cache.get_key(new.kid)).key_id == new.kid  # unknown kid → refetch
        assert route.call_count == 2

    @respx.mock
    async def test_unknown_kid_refetch_is_rate_limited(self, http: httpx.AsyncClient) -> None:
        key = SigningKey()
        route = respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=key.jwks()))
        cache = JwksCache(JWKS_URL, http, cache_seconds=600, min_refetch_seconds=60)
        await cache.get_key(key.kid)
        for _ in range(5):
            with pytest.raises(AuthenticationError):
                await cache.get_key("forged")
        assert route.call_count == 1

    @respx.mock
    async def test_fetch_failure_keeps_previous_keys(self, http: httpx.AsyncClient) -> None:
        key = SigningKey()
        route = respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=key.jwks()))
        cache = JwksCache(JWKS_URL, http, cache_seconds=0, min_refetch_seconds=0)
        await cache.get_key(key.kid)
        route.mock(return_value=httpx.Response(503))
        assert (await cache.get_key(key.kid)).key_id == key.kid

    @respx.mock
    async def test_unreachable_auth_service(self, http: httpx.AsyncClient) -> None:
        respx.get(JWKS_URL).mock(side_effect=httpx.ConnectError("down"))
        cache = JwksCache(JWKS_URL, http, cache_seconds=600, min_refetch_seconds=0)
        with pytest.raises(AuthenticationError):
            await cache.get_key("any")
