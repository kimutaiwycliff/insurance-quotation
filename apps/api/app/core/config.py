"""Application settings.

All configuration comes from environment variables (12-factor). This is the only module that reads the
environment; everything else receives a ``Settings`` instance via ``get_settings()``.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEV_STORAGE_KEY = "devaccesskey"
# Asymmetric algorithms only: a symmetric algorithm here would let anyone holding the public key forge tokens.
_ALLOWED_JWT_ALGORITHMS = frozenset({"EdDSA", "ES256", "ES384", "RS256", "PS256"})


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    environment: Environment = Environment.LOCAL
    service_name: str = "api"
    release: str = "dev"

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    # Database: the API connects as the non-owner ``app_user`` role so Row-Level Security applies.
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+psycopg://app_user:app_user@localhost:5432/app"
    )
    # Migrations run as the schema owner ``app_owner``; never used by the running API.
    migrations_database_url: PostgresDsn | None = None
    database_pool_size: int = 10
    database_max_overflow: int = 5
    database_statement_timeout_ms: int = 15_000

    # Valkey (Redis protocol): cache and rate limiting.
    valkey_url: RedisDsn = RedisDsn("redis://localhost:6379/0")

    # S3-compatible object storage (RustFS locally, S3/R2 in production).
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr = SecretStr(_DEV_STORAGE_KEY)
    s3_secret_access_key: SecretStr = SecretStr("devsecretkey")
    s3_bucket_documents: str = "documents"
    s3_force_path_style: bool = True
    # Endpoint browsers use for presigned URLs (the internal one, e.g. http://storage:9000, is not reachable
    # from outside). Defaults to s3_endpoint_url.
    s3_public_endpoint_url: str | None = None

    # Documents (ADR-0023)
    upload_max_bytes: int = 25 * 1024 * 1024
    upload_url_ttl_seconds: int = 600  # presigned PUT, <= 10 min (spec 5.5)
    download_url_ttl_seconds: int = 300

    # PDF rendering (Gotenberg, internal network only)
    gotenberg_url: str = "http://localhost:3000"
    pdf_timeout_seconds: float = 30.0

    # Email (ADR-0024). "smtp" (Mailpit locally, SES SMTP in production) or "fake" (tests).
    email_provider: str = "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    # Shared sending identity; tenants appear as "<Agency> via <product>" with Reply-To set to the agency.
    email_from_address: str = "notifications@brokeros.local"
    email_from_name: str = "BrokerOS"
    # PII encryption (ADR-0018): "key_id:base64(32 bytes)" entries, comma-separated; the first encrypts,
    # all decrypt (rotation). The lookup key makes exact-match search possible without decrypting.
    pii_encryption_keys: SecretStr = SecretStr("dev1:ZGV2LW9ubHktcGlpLWtleS0wMTIzNDU2Nzg5YWJjZGU=")
    pii_lookup_key: SecretStr = SecretStr("dev-only-pii-lookup-key-0123456789abcdef")

    # HMAC key for unsubscribe tokens and for hashing visitor IPs on public links. Must be set in production.
    signing_secret: SecretStr = SecretStr("dev-only-signing-secret-0123456789abcdef")

    # Public links (ADR-0014)
    public_base_url: str = "http://localhost:3000"  # where /d/{token} pages are served (web app)
    public_api_base_url: str = "http://localhost:8000"  # API origin used in List-Unsubscribe URLs
    public_rate_limit_per_minute: int = 60  # per client IP
    public_link_default_ttl_days: int = 30

    # HTTP
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    readiness_timeout_seconds: float = 2.0

    # Observability
    sentry_dsn: SecretStr | None = None
    metrics_enabled: bool = True

    # Authentication (ADR-0006). Access tokens are issued by the Better Auth service (apps/auth) and verified
    # here against its JWKS. ``auth_issuer``/``auth_audience`` must match the auth service's jwt plugin config.
    auth_jwks_url: str = "http://localhost:3001/api/auth/jwks"
    auth_issuer: str = "http://localhost:3001"
    auth_audience: str = "brokeros-api"
    # Audience of service-to-service tokens the auth service sends to /internal/* (organization hooks).
    auth_internal_audience: str = "brokeros-internal"
    auth_algorithms: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["EdDSA"])
    auth_jwks_cache_seconds: int = 600
    # Minimum seconds between JWKS refetches triggered by an unknown ``kid`` (stops refetch storms).
    auth_jwks_min_refetch_seconds: int = 30
    auth_leeway_seconds: int = 30
    # Roles that must enrol two-factor authentication before using tenant endpoints (ADR-0007).
    # Empty by default: 2FA is optional for everyone. Set e.g. "owner,accounts" to enforce it.
    mfa_enforced_roles: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Rate limiting (Valkey fixed window). Requests per minute per principal for authenticated routes.
    rate_limit_enabled: bool = True
    rate_limit_read_per_minute: int = 600
    rate_limit_write_per_minute: int = 120

    # Idempotency keys are kept this long, then purged by a periodic job (ADR-0011).
    idempotency_ttl_hours: int = 24

    @field_validator("cors_allowed_origins", "auth_algorithms", "mfa_enforced_roles", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept list settings (e.g. ``CORS_ALLOWED_ORIGINS``) as comma-separated strings."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _reject_dev_defaults_in_production(self) -> Settings:
        if (
            self.environment is Environment.PRODUCTION
            and self.s3_access_key_id.get_secret_value() == _DEV_STORAGE_KEY
        ):
            raise ValueError("Development storage credentials must not be used in production")
        if (
            self.environment is Environment.PRODUCTION
            and self.signing_secret.get_secret_value().startswith("dev-only")
        ):
            raise ValueError("SIGNING_SECRET must be set in production")
        if self.environment is Environment.PRODUCTION and (
            self.pii_encryption_keys.get_secret_value().startswith("dev1:")
            or self.pii_lookup_key.get_secret_value().startswith("dev-only")
        ):
            raise ValueError("PII_ENCRYPTION_KEYS and PII_LOOKUP_KEY must be set in production")
        if not set(self.auth_algorithms) <= _ALLOWED_JWT_ALGORITHMS:
            raise ValueError(
                f"AUTH_ALGORITHMS must be a subset of {sorted(_ALLOWED_JWT_ALGORITHMS)}"
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
