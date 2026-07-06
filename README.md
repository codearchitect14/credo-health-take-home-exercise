# Credo Health — FHIR Migration Take-Home

A working slice of a FHIR R4 patient/observation migration: fetch from the [HAPI FHIR sandbox](https://hapi.fhir.org/baseR4), transform into a simplified internal schema, persist via an async Celery pipeline to SQLite, and browse via a React frontend.

> **Synthetic data only.** This project uses the public HAPI sandbox. No real PHI is used or stored.

## Project Structure

```
credo-fhir-migration/
├── Plan.md                  # Part 1: production migration plan (50k patients)
├── README.md
├── docker-compose.yml       # Redis + API + Celery worker + frontend
├── backend/                 # Django + DRF
│   ├── credo/               # Project settings, Celery app
│   └── migration/           # FHIR client, transformers, tasks, API, tests
└── frontend/                # React + Vite
```

## Quick Start with Docker (recommended)

One command brings up Redis, the Django API, a Celery worker (true async mode), and the frontend:

```bash
docker compose up --build
```

Then open `http://localhost:5173`, click **Run Migration**, and the run is dispatched to the Celery worker; the UI polls until it completes. The API is at `http://localhost:8000/api/`. To trigger a migration from the CLI instead:

```bash
docker compose exec backend python manage.py migrate_fhir --limit 20
```

## Manual Setup (no Docker)

Prerequisites: Python 3.11+, Node.js 18+

### Backend

```bash
cd credo-fhir-migration
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
cd backend
python manage.py migrate
```

### Run migration (CLI)

Fetch up to 20 patients and their observations from the FHIR sandbox:

```bash
python manage.py migrate_fhir --limit 20
```

### Start API server

```bash
python manage.py runserver
```

API runs at `http://localhost:8000/api/`. Migrations run inline by default (eager mode, no broker needed); see [Async execution](#async-execution-with-celery--redis) to run them through Redis-backed workers instead.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Click **Run Migration** to pull data, then click a patient to view observations.

The frontend expects the backend at `http://localhost:8000/api` (configurable via `VITE_API_BASE`).

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/patients/` | GET | List migrated patients |
| `/api/patients/<id>/` | GET | Patient detail with observations |
| `/api/migrate/?limit=20` | POST | Trigger migration (201 if completed inline, 202 if dispatched to workers) |
| `/api/migrate/status/` | GET | Recent migration run history |

## Configuration (optional)

All FHIR settings have sensible defaults; no configuration is required to run the project. To override, either set environment variables or copy the sample env file:

```bash
cp backend/.env.example backend/.env   # then edit values
```

Real environment variables take precedence over `.env` entries.

| Variable | Default | Purpose |
|----------|---------|---------|
| `FHIR_BASE_URL` | `https://hapi.fhir.org/baseR4` | Source FHIR server |
| `FHIR_REQUEST_TIMEOUT` | `30` | Per-request timeout (seconds) |
| `FHIR_MAX_RETRIES` | `5` | Retry attempts for transient errors |
| `FHIR_PAGE_SIZE` | `50` | `_count` used when paginating bundles |
| `MIGRATION_DEFAULT_PATIENT_LIMIT` | `20` | Default patient cap when no `--limit`/`?limit=` given |
| `MIGRATION_BATCH_SIZE` | `5` | Patients per observation-fetch Celery task |
| `CELERY_TASK_ALWAYS_EAGER` | `true` | `true` = tasks run inline (no broker needed); `false` = real async via Redis |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker when eager mode is off |

## Async execution with Celery + Redis

The migration is structured as a Celery task pipeline: a discovery task upserts patients sequentially (FHIR pagination is serial), then fans out observation fetching to batch tasks. **Docker Compose runs this async mode out of the box.** For manual setup, `CELERY_TASK_ALWAYS_EAGER=true` (the default) runs the same pipeline inline so no Redis or worker is needed; to execute it truly asynchronously outside Docker:

```bash
redis-server                                   # terminal 1
cd backend
CELERY_TASK_ALWAYS_EAGER=false celery -A credo worker -c 4 -l info   # terminal 2
CELERY_TASK_ALWAYS_EAGER=false python manage.py runserver            # terminal 3
```

`POST /api/migrate/` then returns `202 Accepted` with a `running` run, batches process concurrently across workers, and the frontend polls `/api/migrate/status/` until the run resolves.

## Run Tests

```bash
cd backend
source ../venv/bin/activate
pytest -v
```

Tests run the Celery pipeline in eager mode with a mocked FHIR client — no network or broker needed. Coverage: FHIR transformers (including `component[]` and `valueCodeableConcept` values, official-name and MRN selection), the task pipeline (success, discovery failure, batch failure, fan-out batching), FHIR client retry behavior (transient errors retried, permanent errors not), and the REST API (list, detail, 404, invalid limit, 201/502 migration responses).

## Design Decisions

- **Django + DRF** — familiar, batteries-included ORM and REST framework.
- **Idempotent upserts** — `update_or_create` on `fhir_id` so re-running migration is safe.
- **Retry with backoff** — `tenacity` retries transient FHIR errors (429, 5xx, timeouts) up to 5 times with exponential jitter.
- **Celery task pipeline with eager default** — the migration mirrors the plan's architecture (sequential discovery, fan-out observation batches, out-of-order completion tracked by `pending_batches`), but defaults to eager mode so reviewers can run it with zero infrastructure; Redis + a worker turns on real async without code changes.
- **Simplified schema** — flat `Patient` and `Observation` models instead of storing raw FHIR bundles; easier to query and display.
- **FHIR `value[x]` handling** — observations store `valueQuantity`/`valueInteger` as numeric, and fall back through `valueString`, `valueBoolean`, `valueCodeableConcept`, and flattened `component[]` values (e.g. blood pressure panels) so multi-part observations still render meaningfully.
- **Default limit of 20** — keeps sandbox load reasonable for a demo (env-configurable via `MIGRATION_DEFAULT_PATIENT_LIMIT`); the plan in `Plan.md` describes the full 50k migration.

## AI Usage Disclosure

AI (Claude via Cursor) was used to:

- Scaffold the Django project structure and boilerplate (settings, URLs, admin)
- Draft the initial `Plan.md` structure and expand it with production-minded details
- Generate the React component layout and API client module
- Write the initial test cases and README
- Implement the Celery task pipeline refactor and the Docker Compose setup

All code was reviewed, run, and tested locally (both eager and Redis-backed async modes, natively and in Docker). Architectural decisions (idempotent upserts, retry strategy, simplified schema, Celery fan-out with eager default, batch completion tracked by `pending_batches`) were made deliberately and can be explained in an interview.

## What I'd Do Next

Given more time, in priority order:

1. **Pagination** — both for FHIR fetch (already paginates bundles) and internal API (`?page=` / cursor-based).
2. **Rate limiting** — shared token bucket across Celery workers (e.g. via Redis) with AIMD adjustment on 429s, as described in `Plan.md`.
3. **Incremental sync** — `_lastUpdated` filter for delta migrations instead of full re-fetch.
4. **Validation suite** — post-migration count reconciliation against FHIR `_summary=count`.
5. **Local HAPI FHIR container** — add a HAPI FHIR image to `docker-compose.yml` for deterministic integration tests against a source we control.
6. **Structured logging** — JSON logs with patient/observation counts per batch for observability.

## License

Submitted as a take-home exercise for Credo Health.
