"""Print the OpenAPI document to stdout (``make openapi`` commits it as openapi.json)."""

import json
import sys

from app.core.config import Environment, Settings
from app.main import create_app


def main() -> int:
    app = create_app(Settings(environment=Environment.TEST, metrics_enabled=False))
    sys.stdout.write(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
