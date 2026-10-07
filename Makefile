# Developer entry points. CI and the definition of done use the same targets.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE      := docker compose
TEST_COMPOSE := docker compose -p brokeros-test -f compose.yaml -f compose.test.yaml
API_DIR      := apps/api
UV           := uv run --directory $(API_DIR)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- stack
.PHONY: up down logs ps migrate
up: ## Build and start the full stack
	$(COMPOSE) up -d --build --wait

down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down

logs: ## Tail logs
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps

migrate: ## Apply database migrations
	$(COMPOSE) run --rm migrate

# ---------------------------------------------------------------- quality
.PHONY: install fmt lint typecheck importlint audit check
install: ## Install Python dependencies locally (for IDEs and fast unit tests)
	cd $(API_DIR) && uv sync --frozen

fmt: ## Format code
	$(UV) ruff format . && $(UV) ruff check --fix .

lint: ## Lint (ruff) and check formatting
	$(UV) ruff check . && $(UV) ruff format --check .

typecheck: ## mypy --strict
	$(UV) mypy app tests scripts

importlint: ## Enforce module boundaries (import-linter)
	$(UV) lint-imports

audit: ## Dependency vulnerability audit
	cd $(API_DIR) && uv export --frozen --no-dev --format requirements-txt --no-hashes > /tmp/brokeros-reqs.txt && uv run pip-audit -r /tmp/brokeros-reqs.txt --strict

check: lint typecheck importlint unit ## Fast local checks (no Docker)

# ---------------------------------------------------------------- tests
.PHONY: unit test test-all openapi
unit: ## Unit tests only (no Docker)
	$(UV) pytest tests/unit -q

test: ## Full backend suite inside Compose (definition of done)
	$(TEST_COMPOSE) run --rm --build api-tests; status=$$?; $(TEST_COMPOSE) down -v --remove-orphans; exit $$status

test-all: test ## Everything (E2E suites are added from M1)

openapi: ## Regenerate the committed OpenAPI document
	$(UV) python -m scripts.export_openapi > $(API_DIR)/openapi.json
