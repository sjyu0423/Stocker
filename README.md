# MarketMind

MarketMind M0A is the product foundation for an evidence-first market intelligence platform. It
stores immutable source evidence, tracks provenance and processing state, exposes research APIs,
and provides a minimal dashboard. It intentionally performs **no external collection, AI
inference, forecasting, embedding, trading, or social-media integration**.

## Repository layout

| Path | Responsibility |
| --- | --- |
| `apps/backend/src/marketmind/domain` | Provider-neutral entities, enums, and ports |
| `apps/backend/src/marketmind/application` | Ingestion and query use cases |
| `apps/backend/src/marketmind/infrastructure` | SQLAlchemy persistence and fixture adapters |
| `apps/backend/src/marketmind/api` | FastAPI transport and contracts |
| `apps/backend/src/marketmind/worker` | Celery wiring; scheduling is deferred |
| `apps/backend/alembic` | Versioned database schema |
| `apps/frontend` | Next.js dashboard |
| `fixtures` | Offline, deterministic input |
| `tests` | Unit, migration, integration, and API contract tests |

See [docs/architecture.md](docs/architecture.md) for boundaries and design decisions.
See [docs/database-reliability.md](docs/database-reliability.md) for revision, concurrency, and
collector recovery semantics.

## Prerequisites

- Python 3.12+
- Node.js 22+
- Docker Compose (recommended for PostgreSQL and Redis)
- `uv` (recommended), or another PEP 517-compatible Python installer

## Setup

```bash
cp .env.example .env
uv sync --all-groups
cd apps/frontend
npm install
```

Start infrastructure, migrate, and seed deterministic fixtures:

```bash
docker compose up -d postgres redis
uv run alembic upgrade head
uv run python scripts/seed_fixtures.py
```

Run the API, worker, and UI in separate terminals:

```bash
uv run uvicorn marketmind.api.main:app --reload
uv run celery -A marketmind.worker.celery_app:celery_app worker --loglevel=INFO
cd apps/frontend && npm run dev
```

The API is at <http://localhost:8000>, OpenAPI at <http://localhost:8000/docs>, and dashboard at
<http://localhost:3000>. Without a reachable API, the dashboard clearly enters offline fixture
mode.

## Verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy apps/backend/src
uv run pytest --cov=marketmind
cd apps/frontend
npm run typecheck
npm run build
```

To include PostgreSQL-specific migration and concurrency tests:

```bash
TEST_POSTGRES_URL=postgresql+psycopg://marketmind:marketmind@localhost:5432/marketmind_test \
  uv run pytest -m postgresql
```

No paid API key or secret is required. Keep local values in `.env`, which is ignored by Git.

## API surface

- `GET /health` and `GET /api/v1/health`
- `GET /api/v1/data-sources`
- `GET /api/v1/companies`
- `GET /api/v1/collection-runs`
- `GET /api/v1/collection-runs/{id}`
- `GET /api/v1/source-records?page=1&page_size=25`
- `GET /api/v1/source-records/{data_source_id}/{external_id}/latest`
- `GET /api/v1/source-records/{data_source_id}/{external_id}/as-of?available_at=...`
- `GET /api/v1/events?page=1&page_size=25`

## Milestone boundary

This repository stops at M0A. Collector protocols exist, but only the offline fixture adapter is
implemented. Celery is configured, but no periodic schedule or external collection task exists.
The inference port and cost ledger are defined, but no AI provider is connected. M0A.1 adds
immutable source revisions, database-backed collector leases, resumable checkpoints, and
PostgreSQL concurrency verification without introducing any external provider.

