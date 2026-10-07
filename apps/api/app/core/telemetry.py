"""Error reporting (Sentry). OpenTelemetry tracing is added in milestone M1."""

import sentry_sdk

from app.core.config import Settings


def configure_sentry(settings: Settings) -> None:
    if settings.sentry_dsn is None:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment.value,
        release=settings.release,
        send_default_pii=False,  # never ship request bodies, cookies or user data
        traces_sample_rate=0.0,
    )
