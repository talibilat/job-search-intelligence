# Job-Search Intelligence

A local-first web app that connects to your email (Gmail first), mines your entire job-search history, and answers questions about it, from "how many jobs did I apply to?" to "why am I getting rejected and what should I fix?", through a dashboard and a conversational RAG agent.

## Core principle

All factual job-search answers come from one clean `applications` table and its event timeline (`application_events`).
Dashboard numbers are deterministic SQL or typed Python logic.
The LLM synthesizes narrative insight only after deterministic facts are prepared, and it never produces authoritative counts or emits raw SQL for execution.

## Status

Phase 1 (Gmail ingestion) has started on top of the Phase 0 scaffold.
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with health, setup, provider config, local wipe-data, and Gmail auth-start routes, typed settings and API errors, the keyring-backed `SecretStore` adapter, provider registry, backend `LLMProvider` and `EmailProvider` Strategy interfaces, the backend `EmailSyncService` coordinator for paginated metadata sync and expired-cursor reconciliation, a provider-neutral broad job-search candidate query DTO and static signal factory, a Gmail provider helper for building read-only OAuth authorization URLs, an async SQLite engine module with Phase 0 connection PRAGMAs, shared SQLite URL parsing, an Alembic migration environment, shared SQLite repository helpers, Phase 0 repository stubs with table-shaped Pydantic record DTOs, the synthetic fixture DTO contract, sample fixture, and SQLite fixture loader, the backend OpenAPI schema generator, root pre-commit configuration, backend and frontend CI workflows, and the frontend Vite React TypeScript shell with Orval API client generation, Recharts foundation, route-query helpers, shared accessible UI primitives, setup and sync-readiness shell copy, npm API contract, typecheck, lint, Vitest, build gate scripts, and a Chromium Playwright smoke harness for the current Phase 0 browser shell.
Gmail OAuth callback handling, token exchange, token persistence, message sync, product pages, the first application schema revision, sqlite-vec engine loading, and remaining backend pieces fill in over subsequent Phase 1 tickets.

## Architecture at a glance

| Area                | Decision                                                                                                                   |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Backend             | FastAPI, Python 3.12, async                                                                                                |
| Frontend            | React, TypeScript, Vite, shared accessible primitives                                                                      |
| Database            | SQLite (single local file) through async SQLAlchemy + aiosqlite                                                            |
| Migrations          | Alembic with SQLite batch mode; sqlite-vec and virtual tables are hand-written revisions                                   |
| Vector store        | sqlite-vec (embeddings in the same SQLite file)                                                                            |
| LLM providers       | Pluggable: Azure OpenAI and Ollama first; OpenAI and Anthropic later                                                       |
| Provider registry   | Backend `app.providers.provider_registry` metadata for supported providers, non-secret requirements, and secret references |
| LLM provider seam   | Backend `app.providers.llm.LLMProvider` protocol with typed Pydantic generation DTOs                                       |
| Email providers     | `EmailProvider` protocol with typed auth, metadata, cursor, candidate-query, and retained-body DTOs; Gmail can build read-only OAuth authorization URLs, while callback, token, and message access remain deferred |
| API style           | REST with an Orval-generated TypeScript client from OpenAPI, imported through `frontend/src/api`                           |
| Data contracts      | Pydantic v2 DTOs at every boundary                                                                                         |
| API errors          | Typed `{"error": ...}` responses with sanitized validation, HTTP, and internal error details                               |
| Secret storage seam | Backend `SecretStore` protocol with Pydantic `SecretRef` identifiers and `SecretStr` values                                |
| Frontend charting   | Recharts through small accessible wrapper components; currently empty-state only until deterministic metrics APIs exist    |
| Secret storage      | Backend `SecretStore` protocol with a default OS keyring adapter, Pydantic `SecretRef` identifiers, and `SecretStr` values |
| Background sync     | APScheduler in-process                                                                                                     |
| RAG agent           | LangGraph hybrid router (structured query + semantic retrieval)                                                            |
| Python tooling      | uv, ruff, mypy, pre-commit                                                                                                 |

See `docs/groundwork-spec.md` for the full locked architecture and repository layout.

## Repository layout

```text
backend/          FastAPI app, pipeline, providers, security interfaces, repositories, evals, tests
backend/scripts/  backend operational scripts, including OpenAPI schema generation
frontend/         React + TypeScript + Vite app
docs/             source-of-truth product, architecture, setup, and convention documents
tickets/          issue manifest and templates
scripts/          repository-level developer and operational scripts
.github/          CI workflows
.pre-commit-config.yaml  root hooks for backend and frontend checks
```

## Privacy

- Local-first: app state lives in a single local SQLite file, and nothing leaves the machine except LLM API calls the user explicitly configures.
- Bring-your-own-credentials: no shared or bundled credentials, ever.
- Fernet fallback storage is documented in `docs/secret-storage.md`; set `JOBTRACKER_SECRET_STORE_BACKEND=fernet` until the OS keyring adapter lands or when OS keyring is unavailable.
- Secrets are stored encrypted at rest through OS keyring by default and never logged; backend redaction helpers are exported from `app.security` for logging boundaries.
- Email backfill stores broad metadata first; retained body text is fetched separately only for selected candidate or reconciliation messages.
- If a provider reports an expired incremental cursor, the sync service restarts as full metadata reconciliation and returns the provider page token plus replacement sync cursor for resumable progress.
- Candidate selection uses provider-neutral static sender-domain, subject keyword, and excluded-label signals after metadata listing, so broad Gmail metadata queries do not expose snippets or body content.
- Broad email metadata excludes body-derived snippets, and v1 ignores attachment content.
- `backend/.env.example` documents operational settings only; keep API keys, OAuth tokens, passwords, client secrets, and Google OAuth client JSON out of the repo.
- Local wipe-data path: `POST /local-data/wipe` clears configured local app data and derived artifacts after the request body confirms `{"confirmation":"wipe-local-data"}`.
- The wipe deletes `JOBTRACKER_DATA_DIR` recursively, and when `JOBTRACKER_DATABASE_URL` points to a local SQLite file outside that directory, it also deletes the database file plus `-wal`, `-shm`, and `-journal` sidecars.
- With the default Fernet paths, the wipe deletes encrypted secret payloads and the Fernet key inside `JOBTRACKER_DATA_DIR`; a custom `JOBTRACKER_FERNET_KEY_FILE` outside that directory is not a wipe target.
- For recursive wipe safety, a custom `JOBTRACKER_DATA_DIR` must either be named `.jobtracker` or contain a `.jobtracker-data` marker file before `POST /local-data/wipe` will delete it.
- Wipe safety checks preflight every target before deleting anything; unsafe directories, escaping symlinks, or unsafe external SQLite targets return a typed `400` error instead of a partial wipe.
- A successful wipe returns `{"status":"wiped","deleted_paths":[],"missing_paths":[]}`; invalid confirmation bodies return the standard typed `422` validation error.
- No telemetry.
- Gmail access is read-only (`gmail.readonly`) in v1.
- Google OAuth setup is documented in `docs/google-oauth-setup.md` and assumes a user-created Desktop app client with no shared or bundled credentials.

## Repository guide

Read the source-of-truth documents in this order:

1. `docs/prd.md` - what is being built, for whom, and why (FR/NFR contract).
2. `docs/groundwork-spec.md` - the keystone architecture and phase roadmap.
3. `docs/questions.md` - the 54 questions the app must answer, tiered by capability.

Developer instructions:

- `AGENTS.md` - the canonical local agent guide with workflows and non-negotiable constraints.
- `docs/conventions.md` - baseline coding standards.
- `docs/google-oauth-setup.md` - Google OAuth setup guide for user-created Gmail credentials.
- `docs/synthetic-fixtures.md` - private-data-free backend fixture format and SQLite loader for deterministic backend, aggregation, and dashboard smoke work.
- `.editorconfig` - shared editor defaults.
- Project-local agent worktrees and scratch checkouts under `.worktrees/` are ignored; ticket source-of-truth files stay tracked under `tickets/`.

## Local Developer Quickstart

Use this path for a fresh local checkout in the current Phase 1 scaffold.
The backend SQLite engine loads sqlite-vec, applies Phase 0 connection setup, and the Alembic migration environment exists, but the first schema revision is later Phase 0 work.
Schema-specific upgrade behavior will apply once that revision lands.
The synthetic fixture loader can still populate caller-provided local SQLite connections for deterministic backend tests.

### 1. Clone the repository

```sh
git clone https://github.com/talibilat/job-search-intelligence.git
cd job-search-intelligence
```

Read the source-of-truth docs before implementing a ticket: `docs/prd.md`, `docs/groundwork-spec.md`, and `docs/questions.md`.

### 2. Install backend dependencies

The backend targets Python 3.12 and uses `uv` for dependency management.

```sh
cd backend
uv sync
```

Run backend commands from `backend/` with `uv run`.

### 3. Configure local backend environment

Copy the example only when you need local overrides.

```sh
cp .env.example .env
```

Do not put API keys, OAuth tokens, passwords, client secrets, or Google OAuth client JSON in `backend/.env`.
Keep Google OAuth client JSON outside the repository, for example at `~/.config/jobtracker/google-oauth-client.json`, and point `JOBTRACKER_GMAIL_CLIENT_CONFIG_FILE` at that path.
Keep `JOBTRACKER_GMAIL_SCOPES` set to `https://www.googleapis.com/auth/gmail.readonly` for v1 ingestion.
`GET /auth/gmail` reads the client JSON to build a Google authorization URL, returns the generated state and requested read-only scope, and never returns the Google client secret or tokens.
The default `JOBTRACKER_DATA_DIR=./.jobtracker` is local app storage and is ignored by git.

### 4. Run the backend

From `backend/`:

```sh
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Current backend endpoints include `GET /health`, `GET /setup/status`, `POST /setup`, `GET|PUT /config/providers`, `GET /auth/gmail`, and `POST /local-data/wipe`.
The health endpoint returns `{"status":"ok"}`.
The setup status endpoint returns typed first-run readiness fields without reading or returning secrets.
The Gmail auth-start endpoint returns a provider-built Google authorization URL for `gmail.readonly` and maps missing, unreadable, or invalid client config files to typed `400` errors.
The wipe-data endpoint requires the exact confirmation phrase `wipe-local-data` before deleting configured local app data.

### 5. Install frontend dependencies

Use Node `^20.19.0 || ^22.13.0 || >=24`.

```sh
cd ../frontend
npm install
```

### 6. Run the frontend

From `frontend/`:

```sh
npm run dev
```

Vite serves the Phase 0 frontend shell locally, usually at `http://127.0.0.1:5173/`, with the setup shell at `http://127.0.0.1:5173/setup`.
Keep the backend running separately on `127.0.0.1:8000` when testing API-backed flows.

### 7. Smoke-check the local setup

With the backend running, verify the health route:

```sh
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{ "status": "ok" }
```

Run the backend smoke test from `backend/`:

```sh
uv run pytest tests/test_health.py -q
```

Run the frontend toolchain gate from `frontend/` after backend dependencies have been synced:

```sh
npm run check
```

Install the Chromium browser for the frontend Playwright smoke suite once per machine:

```sh
npx playwright install chromium
```

Run the frontend Playwright smoke suite from `frontend/`:

```sh
npm run test:smoke
```

The smoke suite starts the Vite dev server on `127.0.0.1:4173` and asserts the currently rendered Phase 0 shell for setup copy, sync readiness, and dashboard empty-state coverage.

## Development Commands

The backend has an initial FastAPI app factory, typed API error DTOs in `backend/app/api/errors.py`, setup, auth-start, and provider config DTOs/routes/services, the `app.providers.provider_registry` metadata and validation seam, the `app.providers.llm.LLMProvider` strategy seam, typed settings in `backend/app/config.py`, the `SecretStore` protocol, keyring adapter, and redaction helpers in `backend/app/security/`, the `EmailProvider` contract in `backend/app/providers/email/`, the `EmailSyncService` metadata-page coordinator in `backend/app/services/sync_service.py`, provider-neutral candidate query DTOs, a Gmail provider helper that builds read-only OAuth authorization URLs from the user-owned Desktop client JSON, an async SQLite engine in `backend/app/db/engine.py`, shared SQLite URL parsing in `backend/app/db/sqlite_url.py`, an Alembic migration environment in `backend/app/db/migrations/`, shared SQLite repository helpers and repository stubs in `backend/app/db/repositories/`, table-shaped record DTOs in `backend/app/models/records.py`, synthetic fixture DTOs in `backend/app/models/synthetic_fixture.py`, the `SyntheticFixtureRepository` loader in `backend/app/db/repositories/synthetic_fixture.py`, a sample fixture in `backend/tests/fixtures/synthetic/basic_job_search.json`, `backend/scripts/generate_openapi.py` for deterministic OpenAPI schema generation, a `backend/pyproject.toml` with strict mypy defaults plus `uv` project metadata, `backend/pytest.ini`, and `backend/.env.example` documenting expected v1 operational settings.
The database engine creates the configured local database parent directory, accepts `sqlite:///` or `sqlite+aiosqlite:///` file-backed URLs, registers `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`, and a 5000 ms busy timeout, and exposes a transaction context manager for future repositories and services.
The backend has an initial FastAPI app factory, typed API error DTOs in `backend/app/api/errors.py`, setup and provider config DTOs/routes/services, the `app.providers.provider_registry` metadata and validation seam, the `app.providers.llm.LLMProvider` strategy seam, typed settings in `backend/app/config.py`, the `SecretStore` protocol, keyring adapter, and redaction helpers in `backend/app/security/`, the `EmailProvider` contract in `backend/app/providers/email/`, an async SQLite engine with sqlite-vec setup in `backend/app/db/engine.py`, shared SQLite URL parsing in `backend/app/db/sqlite_url.py`, an Alembic migration environment in `backend/app/db/migrations/`, shared SQLite repository helpers and repository stubs in `backend/app/db/repositories/`, table-shaped record DTOs in `backend/app/models/records.py`, synthetic fixture DTOs in `backend/app/models/synthetic_fixture.py`, the `SyntheticFixtureRepository` loader in `backend/app/db/repositories/synthetic_fixture.py`, a sample fixture in `backend/tests/fixtures/synthetic/basic_job_search.json`, `backend/scripts/generate_openapi.py` for deterministic OpenAPI schema generation, a `backend/pyproject.toml` with strict mypy defaults plus `uv` project metadata, `backend/pytest.ini`, and `backend/.env.example` documenting expected v1 operational settings.
The database engine creates the configured local database parent directory, accepts `sqlite:///` or `sqlite+aiosqlite:///` file-backed URLs, loads sqlite-vec from the bundled runtime dependency or `JOBTRACKER_SQLITE_VEC_EXTENSION_PATH`, verifies availability with `vec_version()`, registers `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`, and a 5000 ms busy timeout, and exposes a transaction context manager for future repositories and services.
The backend database schema does not exist yet; `uv run alembic ensure_version` can initialize the Alembic version table, and schema-specific upgrades will apply once the first revision lands.

- Backend: `uv sync` then `uv run <command>` from `backend/`. The project targets Python 3.12, declares `fastapi`/`uvicorn`, `keyring`, `cryptography`, `sqlalchemy[asyncio]`, `aiosqlite`, `sqlite-vec`, and `alembic` as runtime dependencies, and uses `ruff`, `mypy`, `pytest`, and `pre-commit` as dev-dependency verification tooling; `backend/pyproject.toml` also holds the strict mypy defaults.
- Backend tests: `uv run pytest` from `backend/`; `backend/pytest.ini` discovers `tests/` and sets `pythonpath = .` so tests import the local `app` package deterministically.
- Repository base contract: import `BaseRepository` and the shared `SqlParameters` type from `app.db.repositories`; `uv run pytest tests/test_repository_base.py -v` verifies typed row mapping, parameterized statements, transactions, and the package export contract.
- SQLite engine test: `uv run pytest tests/test_sqlite_engine.py -v` from `backend/` verifies async engine creation, sync-to-async SQLite URL normalization, sqlite-vec loading and `vec_version()` availability, connection PRAGMAs, transaction commit/rollback behavior, and local database parent directory creation.
- Alembic migration test: `uv run pytest tests/test_alembic_migrations.py -v` from `backend/` verifies the Alembic config, SQLite batch mode, sync migration URL normalization, virtual-table autogenerate exclusion, and SQLite version-table creation.
- Synthetic fixture format test: `uv run pytest tests/test_synthetic_fixture_format.py -v` from `backend/` verifies the versioned private-data-free fixture contract, duplicate ID rejection, cross-reference validation, unknown-field rejection, retained-body repr redaction, and the checked-in sample fixture.
- Synthetic fixture loader test: `uv run pytest tests/test_synthetic_fixture_loader.py -v` from `backend/` verifies JSON fixture loading into the four core SQLite tables, typed per-table load counts, repository reads, and idempotent reloads.
- Repository stubs: import `EmailRepository`, `ApplicationRepository`, `EventRepository`, `InsightRepository`, `CorrectionRepository`, and `ChatRepository` from `app.db.repositories`; `uv run pytest tests/test_repository_stubs.py -v` verifies package exports and row-to-record mapping for Phase 0 table-shaped DTOs.
- Backend smoke test: `uv run pytest tests/test_health.py -q` from `backend/`.
- Email provider contract test: `uv run pytest tests/test_email_provider_contract.py -v` from `backend/` verifies the provider boundary keeps OAuth token material behind `SecretRef`, separates metadata from retained body fetching, supports full and incremental cursor shapes, excludes body-derived metadata snippets, and excludes attachment content.
- Sync service test: `uv run pytest tests/test_sync_service.py -v` from `backend/` verifies metadata-page coordination, expired history cursor fallback to full reconciliation, continuation page-token forwarding, and ambiguity rejection when paginated sync includes a cursor without an explicit mode.
- Email candidate query test: `uv run pytest tests/test_email_candidate_query.py -v` from `backend/` verifies broad job-search candidate signals, label exclusions, no body or snippet fields in the query, and that candidate filters stay out of provider metadata listing requests.
- Gmail provider skeleton test: `uv run pytest tests/test_gmail_email_provider.py -v` from `backend/` verifies readonly scope enforcement, advertised read-only ingestion capabilities, attachment exclusion, and public-safe not-implemented runtime errors.
- Secret store test: `uv run pytest tests/test_keyring_secret_store.py -v` from `backend/` verifies the default keyring-backed `SecretStore` adapter, sanitized backend failures, idempotent deletion, and the JT-015 Fernet placeholder.
- Local backend overrides: copy `backend/.env.example` to `backend/.env` only when local settings are needed; `.env` files are ignored and must not contain secrets.
- Current backend health check: `GET /health` returns `{"status": "ok"}`.
- Current setup shell: `GET /setup/status` returns typed first-run setup readiness fields without reading or returning secrets, and `POST /setup` accepts non-secret first-run choices, validates selected provider metadata, and returns `{"status":"accepted",...}` without running provider auth flows or persisting secrets.
- Current Gmail auth-start endpoint: `GET /auth/gmail` returns a Google authorization URL, generated OAuth state, provider name, and the single `gmail.readonly` scope; callback handling, token exchange, token persistence, and message access remain later Phase 1 work.
- LLM provider setup guide: [`docs/llm-provider-setup.md`](docs/llm-provider-setup.md) documents the Azure OpenAI and Ollama values the first-run setup flow needs, including `classification_mode` choices and `SecretStore` boundaries.
- Current local wipe-data endpoint: `POST /local-data/wipe` removes configured local storage targets after the exact confirmation phrase `wipe-local-data`.
- Current provider registry: `app.providers.provider_registry` declares Gmail, Ollama, and Azure OpenAI metadata; validation checks selected non-secret LLM settings only and does not read secret values.
- Current OpenAPI schema generation: run `uv run python -m scripts.generate_openapi` from `backend/` to write sorted, indented JSON to `frontend/src/api/openapi.json`; pass `--output <path>` to write the schema elsewhere.
- Frontend OpenAPI generation script: `npm run generate:openapi` from `frontend/` shells into `backend/` and runs `uv run python -m scripts.generate_openapi`.
- Current provider config API shell: `GET /config/providers` returns the selected email provider, LLM provider, classification mode, visible non-secret provider settings, supported provider metadata, and `SecretRef` requirements without secret values.
- Current provider config update shell: `PUT /config/providers` validates and applies partial non-secret provider selection and setting changes to the running backend process only; durable setup persistence and secret writes are later work.
- Current Fernet fallback: `app.security.FernetSecretStore` stores encrypted secret payloads under `JOBTRACKER_DATA_DIR/secrets/` with a generated or configured `JOBTRACKER_FERNET_KEY_FILE`; `app.security.build_secret_store` returns it only when `JOBTRACKER_SECRET_STORE_BACKEND=fernet`.
- Current TypeScript API client generation: run `npm run generate:api` from `frontend/` to regenerate `src/api/openapi.json` through the backend script and then generate the Orval fetch client at `src/api/generated.ts`.
- Frontend API contract check: `npm run check` includes `check:api` so stale generated API artifacts fail before typecheck, lint, and build.
- Current backend type check: `uv run mypy` from `backend/`.
- Current frontend setup page shell: `frontend/src/pages/SetupPage.tsx` renders the `/setup` Phase 0 shell with disabled setup actions, setup checklist, provider, classification mode, Gmail read-only OAuth, privacy-boundary, and not-ready copy while real setup persistence, secrets, and OAuth flows remain later work.
- Current frontend setup copy: `frontend/src/setupWizardCopy.ts` defines the Phase 0 card copy that the setup page shell renders for LLM provider, classification mode, Gmail read-only OAuth, and privacy-boundary choices while the full wizard flow is still scaffolded.
- Setup copy smoke test: `uv run pytest tests/test_setup_wizard_copy.py -v` from `backend/` verifies the static copy keeps the required provider, mode, Gmail, `SecretStore`, and privacy terms visible.
- Backend linting and formatting: `backend/ruff.toml` defines ruff lint and format defaults.
- Current backend lint check: run `uv run ruff check .` from `backend/`.
- Current backend format check: run `uv run ruff format --check .` from `backend/`.
- Pre-commit setup: run `uv run --project backend pre-commit install` from the repository root after backend and frontend dependencies are installed.
- Current pre-commit gate: run `uv run --project backend pre-commit run --all-files` from the repository root to execute backend Ruff lint, backend Ruff format check, backend mypy, and the frontend `npm run check` gate.
- Backend: `uv run` from `backend/`, with `ruff`, `mypy`, and `pytest` as the verification gate.
- Backend CI: `.github/workflows/backend-ci.yml` runs on backend and workflow changes, installs the locked `uv` environment with Python 3.12, then runs `uv run ruff check app evals tests`, `uv run mypy`, and `uv run pytest` from `backend/`.
- Frontend setup: use Node `>=22.18.0`, then run `npm install` from `frontend/`.
- Frontend dev server: `npm run dev` from `frontend/`.
- Current insights page shell: open `/insights` in the frontend app to see the Phase 0 placeholder; it does not call backend APIs, generate insights, regenerate cached content, or trigger LLM calls.
- Frontend UI primitives: import shared buttons, text inputs, labelled form fields, alerts, tabs, and data tables from `frontend/src/components/ui`; these primitives carry the baseline accessibility behavior for later pages.
- Alert live regions: non-danger `info`, `success`, and `warning` alerts are static by default; `danger` alerts default to `role="alert"`, and callers can pass `role="status"` for dynamic non-danger status messages.
- Data table columns: scalar string, number, null, and undefined fields render directly; object-valued fields must provide a `render` callback and every table must include a caption.
- Frontend TypeScript check: `npm run typecheck` from `frontend/`.
- Frontend lint check: `npm run lint` from `frontend/`.
- Frontend unit tests: `npm run test` from `frontend/` runs Vitest with jsdom for component behavior such as UI primitive accessibility contracts.
- Current frontend route-query helper: `frontend/src/lib/routeQuery.ts` parses, serializes, and patches URL query strings for URL-backed filter state.
- Frontend Playwright browser install: run `npx playwright install chromium` from `frontend/` once per machine before the browser smoke suite.
- Frontend Playwright smoke tests: run `npm run test:smoke` from `frontend/`; the suite starts Vite on `127.0.0.1:4173` and covers the current Phase 0 setup copy, sync-readiness copy, and dashboard empty state.
- Frontend tooling gate: after backend dependencies are synced with `uv`, `npm run check` from `frontend/` runs API contract generation and staleness checks, typecheck, lint, Vitest, and build.
- Current frontend API boundary: import client types and helpers from `frontend/src/api`; `frontend/src/api/generated.ts` is the Orval-generated fetch client from `frontend/src/api/openapi.json`.
- Frontend CI: `.github/workflows/frontend-ci.yml` runs on pushes and pull requests to `main`, installs `uv`, sets up Python 3.12, syncs locked backend dependencies, sets up Node.js with npm caching keyed by `frontend/package-lock.json`, runs `npm ci` from `frontend/`, and runs `npm run check` from `frontend/`.
- Current frontend build check: `npm run build` from `frontend/`.
- Current frontend preview server: `npm run preview` from `frontend/` after a successful build.
- Classification changes: run the golden-set eval at `backend/evals/run_eval.py`; regressions block merges.

Never claim work is complete without fresh verification evidence.
