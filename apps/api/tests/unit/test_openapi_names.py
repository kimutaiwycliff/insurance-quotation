"""The generated web client needs one schema per name: two modules exporting the same model name makes
FastAPI fall back to module-qualified names (``app__modules__x__schemas__Name``) and breaks the client."""

from app.core.config import Environment, Settings
from app.main import create_app


def test_schema_names_are_unique_and_unqualified() -> None:
    app = create_app(Settings(environment=Environment.TEST, metrics_enabled=False))
    names = app.openapi()["components"]["schemas"].keys()
    assert [n for n in names if "__" in n] == []
