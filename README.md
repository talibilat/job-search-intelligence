# Job-Search Intelligence

A local-first web app that connects to your email (Gmail first), mines your entire job-search history, and answers questions about it, from "how many jobs did I apply to?" to "why am I getting rejected and what should I fix?", through a dashboard and a conversational RAG agent.

## Core principle

All factual job-search answers come from one clean `applications` table and its event timeline (`application_events`).
Dashboard numbers are deterministic SQL or typed Python logic.
The LLM synthesizes narrative insight only after deterministic facts are prepared, and it never produces authoritative counts or emits raw SQL for execution.

## Status

Phase 0 (Groundwork).
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with a health route, setup shell routes, local wipe-data route, and typed API error boundary, typed settings, the keyring-backed `SecretStore` adapter, the provider registry seam, the backend `LLMProvider` and `EmailProvider` Strategy interfaces, the shared SQLite repository base package, the backend OpenAPI schema generator, and the frontend Vite React TypeScript shell with npm typecheck, lint, Vitest, build gate scripts, and route-query helpers.
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
| API style | REST with a generated TypeScript client from OpenAPI |
| Data contracts | Pydantic v2 DTOs at every boundary |
| API errors | Typed `{"error": ...}` responses with sanitized validation, HTTP, and internal error details |
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
docs/             source-of-truth product and architecture documents
tickets/          issue manifest and templates
scripts/          repository-level developer and operational scripts
.github/          CI workflows
```

## Privacy

- Local-first: app state lives in a single local SQLite file, and nothing leaves the machine except LLM API calls the user explicitly configures.
- Bring-your-own-credentials: no shared or bundled credentials, ever.
- Secrets are stored encrypted at rest through OS keyring by default and never logged.
- Email backfill stores broad metadata first; retained body text is fetched separately only for selected candidate or reconciliation messages.
- Broad email metadata excludes body-derived snippets, and v1 ignores attachment content.
- `backend/.env.example` documents operational settings only; keep API keys, OAuth tokens, passwords, client secrets, and Google OAuth client JSON out of the repo.
- Local wipe-data path: `POST /local-data/wipe` clears configured local app data and derived artifacts after the request body confirms `{"confirmation":"wipe-local-data"}`.
- The wipe deletes `JOBTRACKER_DATA_DIR` recursively, and when `JOBTRACKER_DATABASE_URL` points to a local SQLite file outside that directory, it also deletes the database file plus `-wal`, `-shm`, and `-journal` sidecars.
- For recursive wipe safety, a custom `JOBTRACKER_DATA_DIR` must either be named `.jobtracker` or contain a `.jobtracker-data` marker file before `POST /local-data/wipe` will delete it.
- Wipe safety checks preflight every target before deleting anything; unsafe directories, escaping symlinks, or unsafe external SQLite targets return a typed `400` error instead of a partial wipe.
- A successful wipe returns `{"status":"wiped","deleted_paths":[],"missing_paths":[]}`; invalid confirmation bodies return the standard typed `422` validation error.
- No telemetry.
- Gmail access is read-only (`gmail.readonly`) in v1.

## Repository guide

Read the source-of-truth documents in this order:

1. `docs/prd.md` - what is being built, for whom, and why (FR/NFR contract).
2. `docs/groundwork-spec.md` - the keystone architecture and phase roadmap.
3. `docs/questions.md` - the 54 questions the app must answer, tiered by capability.

Developer instructions:

- `AGENTS.md` - the canonical local agent guide with workflows and non-negotiable constraints.
- `docs/conventions.md` - baseline coding standards.
- `.editorconfig` - shared editor defaults.
- Project-local agent worktrees and scratch checkouts under `.worktrees/` are ignored; ticket source-of-truth files stay tracked under `tickets/`.

## Development

The backend has an initial FastAPI app factory, typed API error DTOs in `backend/app/api/errors.py`, setup status and setup submission DTOs in `backend/app/models/setup.py`, the `app.providers.provider_registry` metadata and validation seam, the `app.providers.llm.LLMProvider` strategy seam, typed settings in `backend/app/config.py`, the `SecretStore` protocol and keyring adapter in `backend/app/security/`, the `EmailProvider` contract in `backend/app/providers/email/`, shared SQLite repository helpers in `backend/app/db/repositories/`, `backend/scripts/generate_openapi.py` for deterministic OpenAPI schema generation, a `backend/pyproject.toml` with strict mypy defaults plus `uv` project metadata, `backend/pytest.ini`, and `backend/.env.example` documenting expected v1 operational settings.
The backend database schema and engine do not exist yet; schema-specific commands will apply once they land.

- Backend: `uv sync` then `uv run <command>` from `backend/`. The project targets Python 3.12, declares `fastapi`, `uvicorn`, and `keyring` as runtime dependencies, and uses `ruff`, `mypy`, and `pytest` as the dev-dependency verification gate; `backend/pyproject.toml` also holds the strict mypy defaults.
- Backend tests: `uv run pytest` from `backend/`; `backend/pytest.ini` discovers `tests/` and sets `pythonpath = .` so tests import the local `app` package deterministically.
- Repository base contract: import `BaseRepository` and the shared `SqlParameters` type from `app.db.repositories`; `uv run pytest tests/test_repository_base.py -v` verifies typed row mapping, parameterized statements, transactions, and the package export contract.
- Email provider contract test: `uv run pytest tests/test_email_provider_contract.py -v` from `backend/` verifies the provider boundary keeps OAuth token material behind `SecretRef`, separates metadata from retained body fetching, supports full and incremental cursor shapes, excludes body-derived metadata snippets, and excludes attachment content.
- Secret store test: `uv run pytest tests/test_keyring_secret_store.py -v` from `backend/` verifies the default keyring-backed `SecretStore` adapter, sanitized backend failures, idempotent deletion, and the JT-015 Fernet placeholder.
- Local backend overrides: copy `backend/.env.example` to `backend/.env` only when local settings are needed; `.env` files are ignored and must not contain secrets.
- Current backend health check: `GET /health` returns `{"status": "ok"}`.
- Current setup shell: `GET /setup/status` returns typed first-run setup readiness fields without reading or returning secrets, and `POST /setup` accepts non-secret first-run choices, validates selected provider metadata, and returns `{"status":"accepted",...}` without running provider auth flows or persisting secrets.
- Current local wipe-data endpoint: `POST /local-data/wipe` removes configured local storage targets after the exact confirmation phrase `wipe-local-data`.
- Current provider registry: `app.providers.provider_registry` declares Gmail, Ollama, and Azure OpenAI metadata; validation checks selected non-secret LLM settings only and does not read secret values.
- Current OpenAPI schema generation: run `uv run python -m scripts.generate_openapi` from `backend/` to write sorted, indented JSON to `frontend/src/api/openapi.json`; pass `--output <path>` to write the schema elsewhere.
- Current backend type check: run `uv run mypy` from `backend/`.
- Backend linting and formatting: `backend/ruff.toml` defines ruff lint and format defaults.
- Current backend lint check: run `ruff check .` from `backend/`.
- Current backend format check: run `ruff format --check .` from `backend/`.
- Backend: `uv run` from `backend/`, with `ruff`, `mypy`, and `pytest` as the verification gate.
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
- Classification changes: run the golden-set eval (`backend/evals/run_eval.py`); regressions block merges.

Never claim work is complete without fresh verification evidence.
