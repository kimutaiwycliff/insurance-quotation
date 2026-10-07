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

    # HTTP
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    readiness_timeout_seconds: float = 2.0

    # Observability
    sentry_dsn: SecretStr | None = None
    metrics_enabled: bool = True

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept ``CORS_ALLOWED_ORIGINS`` as a comma-separated string."""
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
        return self

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
