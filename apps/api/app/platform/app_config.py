"""What the mobile app needs before sign-in: whether it must update, the store link, a notice, feature switches.

Public and cacheable: it holds no secrets and is the same for everyone (ADR-0026).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings

router = APIRouter(prefix="/public/app-config", tags=["public"])


class AndroidConfig(BaseModel):
    min_version_code: int = Field(description="Older versions must update before use")
    latest_version_code: int = Field(description="Newer than the installed one: offer an update")
    store_url: str = Field(description="Google Play listing; empty until the app is published")
    apk_url: str = Field(
        description="The latest signed APK for direct installs; empty when not offered"
    )
    apk_sha256: str = Field(
        description="SHA-256 of that APK (hex); the app refuses a download that differs"
    )


class AppConfigOut(BaseModel):
    android: AndroidConfig
    notice: str | None = Field(description="A short message for everyone, or null")
    features: list[str] = Field(description="Remote switches that are on")


@router.get("", operation_id="app_config_get")
async def app_config(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> AppConfigOut:
    response.headers["Cache-Control"] = "public, max-age=300"
    return AppConfigOut(
        android=AndroidConfig(
            min_version_code=settings.android_min_version_code,
            latest_version_code=max(
                settings.android_latest_version_code, settings.android_min_version_code
            ),
            store_url=settings.android_store_url,
            apk_url=settings.android_apk_url,
            apk_sha256=settings.android_apk_sha256.strip().lower(),
        ),
        notice=settings.app_notice or None,
        features=settings.app_features,
    )
