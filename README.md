# Job-Search Intelligence

A local-first web app that connects to your email (Gmail first), mines your entire job-search history, and answers questions about it, from "how many jobs did I apply to?" to "why am I getting rejected and what should I fix?", through a dashboard and a conversational RAG agent.

## Core principle

All factual job-search answers come from one clean `applications` table and its event timeline (`application_events`).
Dashboard numbers are deterministic SQL or typed Python logic.
The LLM synthesizes narrative insight only after deterministic facts are prepared, and it never produces authoritative counts or emits raw SQL for execution.

## Status

Phase 0 (Groundwork).
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with a health route, setup shell routes, local wipe-data route, and typed API error boundary, typed settings, the keyring-backed `SecretStore` adapter, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the shared SQLite repository base package, the backend OpenAPI schema generator, the backend GitHub Actions workflow, and the frontend Vite React TypeScript shell with npm typecheck, lint, and build gate scripts.
Concrete Gmail provider behavior and remaining backend pieces fill in over subsequent Phase 0 and Phase 1 tickets.
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with a health route, setup shell routes, local wipe-data route, and typed API error boundary, typed settings, the keyring-backed `SecretStore` adapter, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the shared SQLite repository base package, the backend OpenAPI schema generator, and the frontend Vite React TypeScript shell with npm typecheck, lint, Vitest, build gate scripts, and route-query helpers.
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with a health route, setup shell routes, local wipe-data route, and typed API error boundary, typed settings, the keyring-backed `SecretStore` adapter, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the shared SQLite repository base package, the backend OpenAPI schema generator, and the frontend Vite React TypeScript shell with npm typecheck, lint, and build gate scripts.
The frontend also has a generated API client destination placeholder, a stable `frontend/src/api` import boundary, and a compile-time contract covered by the TypeScript check until OpenAPI generation is wired.
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with a health route, setup shell routes, provider config API shell, local wipe-data route, and typed API error boundary, typed settings and secret-store seams, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the shared SQLite repository base package, the backend OpenAPI schema generator, and the frontend Vite React TypeScript shell with npm typecheck, lint, and build gate scripts.
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with an empty API router and typed API error boundary, typed settings and secret-store seams, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the backend OpenAPI schema generator, the shared SQLite repository base package, and the frontend Vite React TypeScript shell with a Recharts chart wrapper foundation plus npm typecheck, lint, test, and build gate scripts.
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with a health route, setup shell routes, local wipe-data route, and typed API error boundary, typed settings and secret-store seams, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the shared SQLite repository base package, the backend OpenAPI schema generator, and the frontend Vite React TypeScript shell with npm typecheck, lint, and build gate scripts.
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with a health route, setup shell routes, local wipe-data route, and typed API error boundary, typed settings, the keyring-backed `SecretStore` adapter, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the shared SQLite repository base package, the backend OpenAPI schema generator, the frontend Vite React TypeScript shell with npm typecheck, lint, and build gate scripts, and a root pre-commit configuration for backend and frontend checks.
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with a health route, setup shell routes, local wipe-data route, and typed API error boundary, typed settings, the keyring-backed `SecretStore` adapter, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the shared SQLite repository base package, the backend OpenAPI schema generator, the frontend Vite React TypeScript shell with npm typecheck, lint, and build gate scripts, and a frontend GitHub Actions workflow that runs the combined frontend check.
Concrete Gmail provider behavior, remaining backend pieces, and remaining CI workflows fill in over subsequent Phase 0 and Phase 1 tickets.
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with a health route, setup shell routes, local wipe-data route, and typed API error boundary, typed settings, the keyring-backed `SecretStore` adapter, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the shared SQLite repository base package, the synthetic fixture DTO contract and sample fixture, the backend OpenAPI schema generator, and the frontend Vite React TypeScript shell with npm typecheck, lint, and build gate scripts.
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with a health route, setup shell routes, local wipe-data route, and typed API error boundary, typed settings, the keyring-backed `SecretStore` adapter, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the shared SQLite repository base package, Phase 0 repository stubs with table-shaped Pydantic record DTOs, the backend OpenAPI schema generator, and the frontend Vite React TypeScript shell with npm typecheck, lint, and build gate scripts.
Concrete Gmail provider behavior, remaining backend pieces, and the CI scaffold fill in over subsequent Phase 0 and Phase 1 tickets.

## Architecture at a glance

| Area | Decision |
|---|---|
| Backend | FastAPI, Python 3.12, async |
| Frontend | React, TypeScript, Vite |
| Database | SQLite (single local file) |
| Vector store | sqlite-vec (embeddings in the same SQLite file) |
| LLM providers | Pluggable: Azure OpenAI and Ollama first; OpenAI and Anthropic later |
| Provider registry | Backend `app.providers.provider_registry` metadata for supported providers, non-secret requirements, and secret references |
| LLM provider seam | Backend `app.providers.llm.LLMProvider` protocol with typed Pydantic generation DTOs |
| Email providers | `EmailProvider` protocol with typed auth, metadata, cursor, and retained-body DTOs; Gmail implementation deferred |
| API style | REST with a generated TypeScript client from OpenAPI, imported through `frontend/src/api` |
| Data contracts | Pydantic v2 DTOs at every boundary |
| API errors | Typed `{"error": ...}` responses with sanitized validation, HTTP, and internal error details |
| Secret storage seam | Backend `SecretStore` protocol with Pydantic `SecretRef` identifiers and `SecretStr` values |
| Frontend charting | Recharts through small accessible wrapper components; currently empty-state only until deterministic metrics APIs exist |
| Secret storage | Backend `SecretStore` protocol with a default OS keyring adapter, Pydantic `SecretRef` identifiers, and `SecretStr` values |
| Background sync | APScheduler in-process |
| RAG agent | LangGraph hybrid router (structured query + semantic retrieval) |
| Python tooling | uv, ruff, mypy, pre-commit |

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
- `docs/synthetic-fixtures.md` - private-data-free backend fixture format for future loader, aggregation, and dashboard smoke work.
- `.editorconfig` - shared editor defaults.
- Project-local agent worktrees and scratch checkouts under `.worktrees/` are ignored; ticket source-of-truth files stay tracked under `tickets/`.

## Local Developer Quickstart

Use this path for a fresh local checkout in Phase 0.
The backend database does not exist yet, so database-specific commands will apply once it lands.

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
The default `JOBTRACKER_DATA_DIR=./.jobtracker` is local app storage and is ignored by git.

### 4. Run the backend

From `backend/`:

```sh
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Current backend endpoints include `GET /health`, `GET /setup/status`, and `POST /local-data/wipe`.
The health endpoint returns `{"status":"ok"}`.
The setup status endpoint returns typed first-run readiness fields without reading or returning secrets.
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

Vite serves the Phase 0 frontend shell locally, usually at `http://127.0.0.1:5173/`.
Keep the backend running separately on `127.0.0.1:8000` when testing API-backed flows.

### 7. Smoke-check the local setup

With the backend running, verify the health route:

```sh
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Run the backend smoke test from `backend/`:

```sh
uv run pytest tests/test_health.py -q
```

Run the frontend toolchain gate from `frontend/`:

```sh
npm run check
```

## Development Commands

The backend has an initial FastAPI app factory, typed API error DTOs in `backend/app/api/errors.py`, setup status and setup submission DTOs in `backend/app/models/setup.py`, provider config DTOs/routes/services for `GET|PUT /config/providers`, the `app.providers.provider_registry` metadata and validation seam, the `app.providers.llm.LLMProvider` strategy seam, typed settings in `backend/app/config.py`, the `SecretStore` seam in `backend/app/security/`, the `EmailProvider` contract in `backend/app/providers/email/`, shared SQLite repository helpers in `backend/app/db/repositories/`, `backend/scripts/generate_openapi.py` for deterministic OpenAPI schema generation, a `backend/pyproject.toml` with strict mypy defaults plus `uv` project metadata, `backend/pytest.ini`, and `backend/.env.example` documenting expected v1 operational settings.
The backend has an initial FastAPI app factory, typed API error DTOs in `backend/app/api/errors.py`, setup status and setup submission DTOs in `backend/app/models/setup.py`, the `app.providers.provider_registry` metadata and validation seam, the `app.providers.llm.LLMProvider` strategy seam, typed settings in `backend/app/config.py`, the `SecretStore` protocol, keyring adapter, and redaction helpers in `backend/app/security/`, the `EmailProvider` contract in `backend/app/providers/email/`, shared SQLite repository helpers and repository stubs in `backend/app/db/repositories/`, table-shaped record DTOs in `backend/app/models/records.py`, `backend/scripts/generate_openapi.py` for deterministic OpenAPI schema generation, a `backend/pyproject.toml` with strict mypy defaults plus `uv` project metadata, `backend/pytest.ini`, and `backend/.env.example` documenting expected v1 operational settings.
The backend has an initial FastAPI app factory, typed API error DTOs in `backend/app/api/errors.py`, setup status and setup submission DTOs in `backend/app/models/setup.py`, the `app.providers.provider_registry` metadata and validation seam, the `app.providers.llm.LLMProvider` strategy seam, typed settings in `backend/app/config.py`, the `SecretStore` protocol and keyring adapter in `backend/app/security/`, the `EmailProvider` contract in `backend/app/providers/email/`, shared SQLite repository helpers in `backend/app/db/repositories/`, synthetic fixture DTOs in `backend/app/models/synthetic_fixture.py`, a sample fixture in `backend/tests/fixtures/synthetic/basic_job_search.json`, `backend/scripts/generate_openapi.py` for deterministic OpenAPI schema generation, a `backend/pyproject.toml` with strict mypy defaults plus `uv` project metadata, `backend/pytest.ini`, and `backend/.env.example` documenting expected v1 operational settings.
The backend has an initial FastAPI app factory, typed API error DTOs in `backend/app/api/errors.py`, setup status and setup submission DTOs in `backend/app/models/setup.py`, the `app.providers.provider_registry` metadata and validation seam, the `app.providers.llm.LLMProvider` strategy seam, typed settings in `backend/app/config.py`, the `SecretStore` protocol and keyring adapter in `backend/app/security/`, the `EmailProvider` contract in `backend/app/providers/email/`, shared SQLite repository helpers and repository stubs in `backend/app/db/repositories/`, table-shaped record DTOs in `backend/app/models/records.py`, `backend/scripts/generate_openapi.py` for deterministic OpenAPI schema generation, a `backend/pyproject.toml` with strict mypy defaults plus `uv` project metadata, `backend/pytest.ini`, and `backend/.env.example` documenting expected v1 operational settings.
The backend database schema and engine do not exist yet; schema-specific commands will apply once they land.

- Backend: `uv sync` then `uv run <command>` from `backend/`. The project targets Python 3.12, declares `fastapi`, `uvicorn`, and `keyring` as runtime dependencies, and uses `ruff`, `mypy`, `pytest`, and `pre-commit` as dev-dependency verification tooling; `backend/pyproject.toml` also holds the strict mypy defaults.
- Backend tests: `uv run pytest` from `backend/`; `backend/pytest.ini` discovers `tests/` and sets `pythonpath = .` so tests import the local `app` package deterministically.
- Repository base contract: import `BaseRepository` and the shared `SqlParameters` type from `app.db.repositories`; `uv run pytest tests/test_repository_base.py -v` verifies typed row mapping, parameterized statements, transactions, and the package export contract.
- Synthetic fixture format test: `uv run pytest tests/test_synthetic_fixture_format.py -v` from `backend/` verifies the versioned private-data-free fixture contract, duplicate ID rejection, cross-reference validation, unknown-field rejection, retained-body repr redaction, and the checked-in sample fixture.
- Repository base contract: import `BaseRepository` and the shared `SqlParameters` type from `app.db.repositories`; `uv run pytest tests/test_repository_base.py -v` verifies typed row mapping, parameterized statements, transactions, and the base package export contract.
- Repository stubs: import `EmailRepository`, `ApplicationRepository`, `EventRepository`, `InsightRepository`, `CorrectionRepository`, and `ChatRepository` from `app.db.repositories`; `uv run pytest tests/test_repository_stubs.py -v` verifies package exports and row-to-record mapping for Phase 0 table-shaped DTOs.
- Backend smoke test: `uv run pytest tests/test_health.py -q` from `backend/`.
- Email provider contract test: `uv run pytest tests/test_email_provider_contract.py -v` from `backend/` verifies the provider boundary keeps OAuth token material behind `SecretRef`, separates metadata from retained body fetching, supports full and incremental cursor shapes, excludes body-derived metadata snippets, and excludes attachment content.
- Secret store test: `uv run pytest tests/test_keyring_secret_store.py -v` from `backend/` verifies the default keyring-backed `SecretStore` adapter, sanitized backend failures, idempotent deletion, and the JT-015 Fernet placeholder.
- Local backend overrides: copy `backend/.env.example` to `backend/.env` only when local settings are needed; `.env` files are ignored and must not contain secrets.
- Current backend health check: `GET /health` returns `{"status": "ok"}`.
- Current setup shell: `GET /setup/status` returns typed first-run setup readiness fields without reading or returning secrets, and `POST /setup` accepts non-secret first-run choices, validates selected provider metadata, and returns `{"status":"accepted",...}` without running provider auth flows or persisting secrets.
- LLM provider setup guide: [`docs/llm-provider-setup.md`](docs/llm-provider-setup.md) documents the Azure OpenAI and Ollama values the first-run setup flow needs, including `classification_mode` choices and `SecretStore` boundaries.
- Current local wipe-data endpoint: `POST /local-data/wipe` removes configured local storage targets after the exact confirmation phrase `wipe-local-data`.
- Current provider registry: `app.providers.provider_registry` declares Gmail, Ollama, and Azure OpenAI metadata; validation checks selected non-secret LLM settings only and does not read secret values.
- Current OpenAPI schema generation: run `uv run python -m scripts.generate_openapi` from `backend/` to write sorted, indented JSON to `frontend/src/api/openapi.json`; pass `--output <path>` to write the schema elsewhere.
- Current provider config API shell: `GET /config/providers` returns the selected email provider, LLM provider, classification mode, visible non-secret provider settings, supported provider metadata, and `SecretRef` requirements without secret values.
- Current provider config update shell: `PUT /config/providers` validates and applies partial non-secret provider selection and setting changes to the running backend process only; durable setup persistence and secret writes are later work.
- Current Fernet fallback: `app.security.FernetSecretStore` stores encrypted secret payloads under `JOBTRACKER_DATA_DIR/secrets/` with a generated or configured `JOBTRACKER_FERNET_KEY_FILE`; `app.security.build_secret_store` returns it only when `JOBTRACKER_SECRET_STORE_BACKEND=fernet`.
- Current backend type check: `uv run mypy` from `backend/`.
- Backend linting and formatting: `backend/ruff.toml` defines ruff lint and format defaults.
- Current backend lint check: run `uv run ruff check .` from `backend/`.
- Current backend format check: run `uv run ruff format --check .` from `backend/`.
- Pre-commit setup: run `uv run --project backend pre-commit install` from the repository root after backend and frontend dependencies are installed.
- Current pre-commit gate: run `uv run --project backend pre-commit run --all-files` from the repository root to execute backend Ruff lint, backend Ruff format check, backend mypy, and the frontend `npm run check` gate.
- Backend: `uv run` from `backend/`, with `ruff`, `mypy`, and `pytest` as the verification gate.
- Backend CI: `.github/workflows/backend-ci.yml` runs on backend and workflow changes, installs the locked `uv` environment with Python 3.12, then runs `uv run ruff check app evals tests`, `uv run mypy`, and `uv run pytest` from `backend/`.
- Frontend setup: use Node `^20.19.0 || ^22.13.0 || >=24`, then run `npm install` from `frontend/`.
- Frontend dev server: `npm run dev` from `frontend/`.
- Frontend TypeScript check: `npm run typecheck` from `frontend/`.
- Frontend lint check: `npm run lint` from `frontend/`.
- Frontend unit tests: `npm run test` from `frontend/` runs Vitest.
- Frontend tooling gate: `npm run check` from `frontend/` runs typecheck, lint, Vitest, and build.
- Current frontend build check: `npm run build` from `frontend/`.
- Current frontend preview server: `npm run preview` from `frontend/` after a successful build.
- Current frontend route-query helper: `frontend/src/lib/routeQuery.ts` parses, serializes, and patches URL query strings for URL-backed filter state.
- Playwright smoke tests are not scaffolded yet; a later frontend ticket owns those checks.
- Frontend tooling gate: `npm run check` from `frontend/` runs typecheck, lint, Vitest, and build.
- Frontend unit test check: `npm run test` from `frontend/` runs Vitest in jsdom.
- Frontend tooling gate: `npm run check` from `frontend/` runs typecheck, lint, Vitest, and build.
- Current frontend API boundary: import client types and helpers from `frontend/src/api`; `frontend/src/api/generated/client.ts` is the OpenAPI-generated client destination placeholder until client generation is wired, and `frontend/src/api/client.contract.ts` is covered by `npm run typecheck`.
- Frontend CI: `.github/workflows/frontend-ci.yml` runs on pushes and pull requests to `main`, sets up Node.js with npm caching keyed by `frontend/package-lock.json`, runs `npm ci` from `frontend/`, and runs `npm run check` from `frontend/`.
- Current frontend build check: `npm run build` from `frontend/`.
- Current frontend preview server: `npm run preview` from `frontend/` after a successful build.
- Frontend unit test scripts are scaffolded; Playwright smoke scripts are not scaffolded yet.
- Classification changes: run the golden-set eval at `backend/evals/run_eval.py`; regressions block merges.
- Playwright smoke scripts are not scaffolded yet; later Playwright tickets own those checks.
- Classification changes: run the golden-set eval (`backend/evals/run_eval.py`); regressions block merges.

Never claim work is complete without fresh verification evidence.
