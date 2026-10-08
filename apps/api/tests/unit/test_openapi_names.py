"""API contract hygiene: unique schema names (the web client needs them) and open response enums."""

from typing import Annotated

import pytest
from pydantic import BaseModel, ValidationError

from app.core.config import Environment, Settings
from app.core.schema import ExtensibleEnum
from app.main import create_app


def test_schema_names_are_unique_and_unqualified() -> None:
    """Two modules exporting the same model name make FastAPI fall back to module-qualified names
    (``app__modules__x__schemas__Name``), which breaks the generated client."""
    app = create_app(Settings(environment=Environment.TEST, metrics_enabled=False))
    names = app.openapi()["components"]["schemas"].keys()
    assert [n for n in names if "__" in n] == []


class _Out(BaseModel):
    status: Annotated[str, ExtensibleEnum("open", "paid")]


def test_extensible_enums_validate_and_publish_open_sets() -> None:
    assert _Out(status="paid").status == "paid"
    with pytest.raises(ValidationError):
        _Out(status="lost")
    schema = _Out.model_json_schema()["properties"]["status"]
    assert schema["type"] == "string"
    assert schema["x-extensible-enum"] == ["open", "paid"]
    assert "enum" not in schema
