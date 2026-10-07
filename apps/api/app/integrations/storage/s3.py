"""S3-compatible object storage adapter (RustFS in dev/CI, AWS S3 or Cloudflare R2 in production).

Only the plain S3 API is used so the backing store can be swapped by configuration (ADR-0005).
Presigned upload/download helpers arrive with the documents module in milestone M2.

The client is opened once per process (in the app lifespan) and reused: creating an aioboto3 client loads
botocore service models synchronously, which would block the event loop if done per request.
"""

from contextlib import AsyncExitStack
from typing import Any

import aioboto3
from botocore.config import Config

from app.core.config import Settings


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self._session = aioboto3.Session()
        self._stack = AsyncExitStack()
        self._client: Any = None
        self._client_kwargs: dict[str, Any] = {
            "endpoint_url": settings.s3_endpoint_url,
            "region_name": settings.s3_region,
            "aws_access_key_id": settings.s3_access_key_id.get_secret_value(),
            "aws_secret_access_key": settings.s3_secret_access_key.get_secret_value(),
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=2,
                read_timeout=10,
            ),
        }
        self.documents_bucket = settings.s3_bucket_documents

    async def open(self) -> None:
        self._client = await self._stack.enter_async_context(
            self._session.client("s3", **self._client_kwargs)
        )

    async def close(self) -> None:
        await self._stack.aclose()
        self._client = None

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError("S3Storage.open() has not been called")
        return self._client

    async def ping(self) -> None:
        await self.client.head_bucket(Bucket=self.documents_bucket)
