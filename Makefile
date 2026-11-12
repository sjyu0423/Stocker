.PHONY: install test test-postgres lint typecheck verify migrate seed

install:
	uv sync --all-groups
	cd apps/frontend && npm install

test:
	uv run pytest --cov=marketmind

test-postgres:
	test -n "$$TEST_POSTGRES_URL"
	uv run pytest -m postgresql -vv

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy apps/backend/src
	cd apps/frontend && npm run typecheck

verify: lint typecheck test
	cd apps/frontend && npm run build

migrate:
	uv run alembic upgrade head

seed:
	uv run python scripts/seed_fixtures.py

