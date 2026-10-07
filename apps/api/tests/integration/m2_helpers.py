"""Shared helpers for M2 integration tests."""

import io
import uuid
from typing import Any

import httpx
from pypdf import PdfReader

from tests.support import Org

PDF_BYTES = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)
# 1x1 transparent PNG
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


async def start_upload(
    api: httpx.AsyncClient, org: Org, filename: str, size: int, **extra: Any
) -> dict[str, Any]:
    body = {
        "filename": filename,
        "size_bytes": size,
        "category": extra.pop("category", "kyc_id"),
        **extra,
    }
    response = await api.post("/api/v1/documents", json=body, headers=org.headers())
    assert response.status_code == 201, response.text
    return dict(response.json())


async def upload(
    api: httpx.AsyncClient, org: Org, filename: str, data: bytes, **extra: Any
) -> dict[str, Any]:
    started = await start_upload(api, org, filename, len(data), **extra)
    async with httpx.AsyncClient() as raw:
        put = await raw.put(
            started["upload"]["url"], content=data, headers=started["upload"]["headers"]
        )
        assert put.status_code == 200, put.text
    doc_id = started["document"]["id"]
    done = await api.post(
        f"/api/v1/documents/{doc_id}/versions/{started['version_no']}/complete",
        headers=org.headers(),
    )
    assert done.status_code == 200, done.text
    return dict(done.json())


def pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def entity() -> dict[str, str]:
    return {"entity_type": "client", "entity_id": str(uuid.uuid4())}
