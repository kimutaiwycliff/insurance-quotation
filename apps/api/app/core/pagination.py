"""Cursor pagination over time-ordered (uuidv7) ids.

Cursors are opaque to clients. Lists are newest first; ``next_cursor`` is ``null`` on the last page.
"""

import base64
import binascii
import uuid
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field

from app.core.errors import AppError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class InvalidCursorError(AppError):
    code = "invalid_cursor"
    title = "The pagination cursor is invalid"


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = Field(
        default=None, description="Pass as `cursor` to fetch the next page; null on the last page"
    )


class PageParams(BaseModel):
    cursor: uuid.UUID | None = None
    limit: int = DEFAULT_LIMIT


def encode_cursor(last_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(last_id.bytes).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> uuid.UUID:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        return uuid.UUID(bytes=raw)
    except binascii.Error, ValueError:
        raise InvalidCursorError() from None


def page_params(
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> PageParams:
    return PageParams(cursor=decode_cursor(cursor) if cursor else None, limit=limit)


def build_page[T](rows: list[T], ids: list[uuid.UUID], limit: int) -> Page[T]:
    """``rows``/``ids`` were fetched with ``LIMIT limit + 1``; the extra row only signals another page."""
    has_more = len(rows) > limit
    items = rows[:limit]
    return Page(items=items, next_cursor=encode_cursor(ids[limit - 1]) if has_more else None)
