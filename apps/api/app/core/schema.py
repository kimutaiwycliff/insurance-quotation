"""Schema helpers for the public API contract (ADR-0022)."""

from dataclasses import dataclass
from typing import Any

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_core import core_schema


@dataclass(frozen=True, slots=True, init=False)
class ExtensibleEnum:
    """``Annotated[str, ExtensibleEnum("a", "b")]``: a string limited to these values today, published as
    ``x-extensible-enum``.

    Use it for response fields whose set of values grows as the product does (document kinds, statuses,
    permissions). Clients must treat an unknown value gracefully, so adding one is not a breaking change.
    Request fields keep closed ``Literal`` enums: the server decides what it accepts.
    """

    values: tuple[str, ...]

    def __init__(self, *values: str) -> None:
        object.__setattr__(self, "values", values)

    def __get_pydantic_core_schema__(
        self, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        allowed = frozenset(self.values)

        def check(value: str) -> str:
            if value not in allowed:
                raise ValueError(f"{value!r} is not one of {sorted(allowed)}")
            return value

        return core_schema.no_info_after_validator_function(check, handler(source))

    def __get_pydantic_json_schema__(
        self, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> dict[str, Any]:
        return {"type": "string", "x-extensible-enum": list(self.values)}
