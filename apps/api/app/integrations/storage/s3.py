"""S3-compatible object storage adapter (RustFS in dev/CI, AWS S3 or Cloudflare R2 in production).

Only the plain S3 API is used so the backing store can be swapped by configuration (ADR-0005).

The client is opened once per process (in the app lifespan) and reused: creating an aioboto3 client loads
botocore service models synchronously, which would block the event loop if done per request. Presigned URLs
are signed offline by a separate client configured with the *public* endpoint, because browsers cannot reach
the internal one.
"""

import hashlib
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import aioboto3
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings

_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    size: int
    content_type: str | None


@dataclass(frozen=True, slots=True)
class ObjectDigest:
    size: int
    sha256: str
    head: bytes  # first bytes, for content sniffing


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self._session = aioboto3.Session()
        self._stack = AsyncExitStack()
        self._client: Any = None
        config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=2,
            read_timeout=10,
        )
        credentials = {
            "region_name": settings.s3_region,
            "aws_access_key_id": settings.s3_access_key_id.get_secret_value(),
            "aws_secret_access_key": settings.s3_secret_access_key.get_secret_value(),
            "config": config,
        }
        self._client_kwargs: dict[str, Any] = {
            "endpoint_url": settings.s3_endpoint_url,
            **credentials,
        }
        # Signing is local (no network), so a plain botocore client is fine here.
        self._presigner: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_public_endpoint_url or settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            config=config,
        )
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

    def presign_put(self, key: str, *, content_type: str, content_length: int, ttl: int) -> str:
        """URL for one PUT of exactly ``content_length`` bytes of ``content_type`` (both signed)."""
        return str(
            self._presigner.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.documents_bucket,
                    "Key": key,
                    "ContentType": content_type,
                    "ContentLength": content_length,
                },
                ExpiresIn=ttl,
                HttpMethod="PUT",
            )
        )

    def presign_get(
        self, key: str, *, filename: str, content_type: str, ttl: int, inline: bool
    ) -> str:
        disposition = "inline" if inline else "attachment"
        safe_name = filename.replace('"', "").replace("\\", "")
        return str(
            self._presigner.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.documents_bucket,
                    "Key": key,
                    "ResponseContentDisposition": f'{disposition}; filename="{safe_name}"',
                    "ResponseContentType": content_type,
                },
                ExpiresIn=ttl,
            )
        )

    async def head(self, key: str) -> ObjectInfo | None:
        try:
            response = await self.client.head_object(Bucket=self.documents_bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return ObjectInfo(
            size=int(response["ContentLength"]), content_type=response.get("ContentType")
        )

    async def digest(self, key: str, *, head_bytes: int = 512) -> ObjectDigest:
        """Stream the object once: SHA-256, size and the first bytes."""
        response = await self.client.get_object(Bucket=self.documents_bucket, Key=key)
        sha = hashlib.sha256()
        size = 0
        head = b""
        body = response["Body"]
        # Iterate the StreamingBody wrapper itself: its __aenter__ returns the raw aiohttp response.
        async with body:
            async for chunk in body.iter_chunks(_CHUNK):
                if len(head) < head_bytes:
                    head += chunk[: head_bytes - len(head)]
                sha.update(chunk)
                size += len(chunk)
        return ObjectDigest(size=size, sha256=sha.hexdigest(), head=head)

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        await self.client.put_object(
            Bucket=self.documents_bucket, Key=key, Body=data, ContentType=content_type
        )

    async def get(self, key: str) -> bytes:
        response = await self.client.get_object(Bucket=self.documents_bucket, Key=key)
        body = response["Body"]
        async with body:
            data: bytes = await body.read()
        return data

    async def delete(self, key: str) -> None:
        await self.client.delete_object(Bucket=self.documents_bucket, Key=key)
