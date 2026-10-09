"""Unit tests for configuration and log scrubbing."""

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Environment, Settings
from app.core.logging import REDACTED, scrub_sensitive


class TestSettings:
    def test_cors_origins_accept_comma_separated_string(self) -> None:
        settings = Settings(cors_allowed_origins="https://a.example, https://b.example,")  # type: ignore[arg-type]
        assert settings.cors_allowed_origins == ["https://a.example", "https://b.example"]

    def test_production_rejects_development_storage_credentials(self) -> None:
        with pytest.raises(ValidationError, match="Development storage credentials"):
            Settings(environment=Environment.PRODUCTION)

    def test_production_accepts_real_credentials(self) -> None:
        settings = Settings(
            environment=Environment.PRODUCTION,
            s3_access_key_id=SecretStr("AKIAREALKEY"),
            s3_secret_access_key=SecretStr("real-secret"),
            signing_secret=SecretStr("a-real-production-signing-secret"),
            pii_encryption_keys=SecretStr("k2026:" + "A" * 43 + "="),
            pii_lookup_key=SecretStr("x" * 40),
            platform_mpesa_environment="production",
            platform_mpesa_callback_secret=SecretStr("a-long-random-callback-path-secret"),
        )
        assert settings.is_production

    def test_production_refuses_the_billing_simulator(self) -> None:
        with pytest.raises(ValidationError, match="PLATFORM_MPESA"):
            Settings(
                environment=Environment.PRODUCTION,
                s3_access_key_id=SecretStr("AKIAREALKEY"),
                s3_secret_access_key=SecretStr("real-secret"),
                signing_secret=SecretStr("a-real-production-signing-secret"),
                pii_encryption_keys=SecretStr("k2026:" + "A" * 43 + "="),
                pii_lookup_key=SecretStr("x" * 40),
            )

    def test_production_rejects_development_signing_secret(self) -> None:
        with pytest.raises(ValidationError, match="SIGNING_SECRET"):
            Settings(
                environment=Environment.PRODUCTION,
                s3_access_key_id=SecretStr("AKIAREALKEY"),
                s3_secret_access_key=SecretStr("real-secret"),
            )

    def test_secrets_are_not_rendered(self) -> None:
        settings = Settings(s3_secret_access_key=SecretStr("super-secret-value"))
        assert "super-secret-value" not in repr(settings)


class TestLogScrubbing:
    def test_redacts_sensitive_top_level_keys(self) -> None:
        event = scrub_sensitive(
            None, "info", {"event": "x", "password": "p", "Authorization": "Bearer t"}
        )
        assert event["password"] == REDACTED
        assert event["Authorization"] == REDACTED
        assert event["event"] == "x"

    def test_redacts_nested_keys_and_lists(self) -> None:
        event = scrub_sensitive(
            None,
            "info",
            {
                "event": "x",
                "client": {"name": "Wanjiku", "id_number": "12345678"},
                "items": [{"api_key": "k"}, {"amount": "100.00"}],
            },
        )
        assert event["client"] == {"name": "Wanjiku", "id_number": REDACTED}
        assert event["items"] == [{"api_key": REDACTED}, {"amount": "100.00"}]

    def test_leaves_ordinary_values_untouched(self) -> None:
        event = scrub_sensitive(None, "info", {"event": "x", "tenant_id": "t1", "status": 200})
        assert event == {"event": "x", "tenant_id": "t1", "status": 200}


class TestAuthSettings:
    def test_list_settings_accept_csv(self) -> None:
        settings = Settings(mfa_enforced_roles="owner, admin", auth_algorithms="EdDSA,ES256")  # type: ignore[arg-type]
        assert settings.mfa_enforced_roles == ["owner", "admin"]
        assert settings.auth_algorithms == ["EdDSA", "ES256"]

    def test_symmetric_algorithms_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="AUTH_ALGORITHMS"):
            Settings(auth_algorithms=["HS256"])
