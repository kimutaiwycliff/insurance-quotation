"""Optimistic concurrency with ``ETag`` / ``If-Match`` (ADR-0011).

Reads return ``ETag: W/"<version>"``. Updates must send ``If-Match`` with that value: missing → 428,
stale → 412 ``version_conflict``. The ORM's ``version_id_col`` closes the remaining race inside the UPDATE.
"""

import re

from app.core.errors import PreconditionFailedError, PreconditionRequiredError

_ETAG = re.compile(r'^\s*(?:W/)?"(\d{1,18})"\s*$')


def etag(version: int) -> str:
    return f'W/"{version}"'


def parse_if_match(header: str | None) -> int:
    if header is None or not header.strip():
        raise PreconditionRequiredError()
    match = _ETAG.match(header)
    if match is None:
        raise PreconditionFailedError("If-Match must be an ETag returned by this API")
    return int(match.group(1))


def check_version(if_match: str | None, current: int) -> None:
    if parse_if_match(if_match) != current:
        raise PreconditionFailedError(
            "Reload the record and apply your change again (it changed since you read it)"
        )
