.PHONY: install infra run migrate seed dev-setup test lint format typecheck check clean

# Docker Compose reads `.env` on its own, but a plain shell does not, so every
# host-side command below passes `--env-file .env`. Without it Alembic and the
# seed scripts see empty DATABASE_URLs and fail.
ENV_FILE := .env

install:
	uv sync

# Backing services only. The backend itself runs on the host with --reload so
# editing src/ does not require a docker build.
infra:
	docker compose up -d postgres minio pgadmin

migrate:
	@for cfg in auth document products agent locations; do \
		echo "--- alembic $$cfg ---"; \
		uv run --env-file $(ENV_FILE) python -m alembic -c alembic-$$cfg.ini upgrade head || exit 1; \
	done

seed:
	uv run --env-file $(ENV_FILE) python scripts/seed_auth_users.py
	uv run --env-file $(ENV_FILE) python scripts/seed_catalog_data.py
	uv run --env-file $(ENV_FILE) python scripts/seed_locations_data.py

dev-setup: infra migrate seed

run:
	uv run --env-file $(ENV_FILE) uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run --env-file $(ENV_FILE) pytest tests/ -v

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/

check: lint format test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
