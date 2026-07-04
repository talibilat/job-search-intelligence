# Job-Search Intelligence

A local-first web app that connects to your email (Gmail first), mines your entire job-search history, and answers questions about it, from "how many jobs did I apply to?" to "why am I getting rejected and what should I fix?", through a dashboard and a conversational RAG agent.

## Core principle

All factual job-search answers come from one clean `applications` table and its event timeline (`application_events`).
Dashboard numbers are deterministic SQL or typed Python logic.
The LLM synthesizes narrative insight only after deterministic facts are prepared, and it never produces authoritative counts or emits raw SQL for execution.

## Status

Phase 0 (Groundwork).
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, the backend `uv` project scaffold, an initial FastAPI app factory (`backend/app/main.py`) with an empty API router and typed API error boundary, and the frontend Vite React TypeScript shell with npm typecheck, lint, and build gate scripts.
The rest of the backend and the CI scaffold fill in over subsequent Phase 0 tickets.

## Architecture at a glance

| Area | Decision |
|---|---|
| Backend | FastAPI, Python 3.12, async |
| Frontend | React, TypeScript, Vite |
| Database | SQLite (single local file) |
| Vector store | sqlite-vec (embeddings in the same SQLite file) |
| LLM providers | Pluggable: Azure OpenAI and Ollama first; OpenAI and Anthropic later |
| LLM provider seam | Backend `app.providers.llm.LLMProvider` protocol with typed Pydantic generation DTOs |
| API style | REST with a generated TypeScript client from OpenAPI |
| Data contracts | Pydantic v2 DTOs at every boundary |
| API errors | Typed `{"error": ...}` responses with sanitized validation, HTTP, and internal error details |
| Secret storage seam | Backend `SecretStore` protocol with Pydantic `SecretRef` identifiers and `SecretStr` values |
| Background sync | APScheduler in-process |
| RAG agent | LangGraph hybrid router (structured query + semantic retrieval) |
| Python tooling | uv, ruff, mypy, pre-commit |

See `docs/groundwork-spec.md` for the full locked architecture and repository layout.

## Repository layout

```text
backend/    FastAPI app, pipeline, providers, security interfaces, repositories, evals, tests
frontend/   React + TypeScript + Vite app
docs/       source-of-truth product and architecture documents
tickets/    issue manifest and templates
scripts/    developer and operational scripts
.github/    CI workflows
```

## Privacy

- Local-first: app state lives in a single local SQLite file, and nothing leaves the machine except LLM API calls the user explicitly configures.
- Bring-your-own-credentials: no shared or bundled credentials, ever.
- Secrets are stored encrypted at rest and never logged.
- `backend/.env.example` documents operational settings only; keep API keys, OAuth tokens, passwords, client secrets, and Google OAuth client JSON out of the repo.
- Local wipe-data path: `POST /local-data/wipe` clears configured local app data and derived artifacts after the request body confirms `{"confirmation":"wipe-local-data"}`.
- For recursive wipe safety, a custom `JOBTRACKER_DATA_DIR` must either be named `.jobtracker` or contain a `.jobtracker-data` marker file before `POST /local-data/wipe` will delete it.
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

The backend has an initial FastAPI app factory, typed API error DTOs in `backend/app/api/errors.py`, the `app.providers.llm.LLMProvider` strategy seam, typed settings in `backend/app/config.py`, a `backend/pyproject.toml` with strict mypy defaults plus `uv` project metadata, `backend/pytest.ini`, and `backend/.env.example` documenting expected v1 operational settings.
The backend database does not exist yet; database-specific commands will apply once it lands.

- Backend: `uv sync` then `uv run <command>` from `backend/`. The project targets Python 3.12, declares `fastapi`/`uvicorn` as runtime dependencies, and uses `ruff`, `mypy`, and `pytest` as the dev-dependency verification gate; `backend/pyproject.toml` also holds the strict mypy defaults.
- Backend tests: `uv run pytest` from `backend/`; `backend/pytest.ini` discovers `tests/` and sets `pythonpath = .` so tests import the local `app` package deterministically.
- Local backend overrides: copy `backend/.env.example` to `backend/.env` only when local settings are needed; `.env` files are ignored and must not contain secrets.
- Current backend health check: `GET /health` returns `{"status": "ok"}`.
- Current setup shell: `GET /setup/status` returns typed first-run setup readiness fields without reading or returning secrets.
- Current backend type check: run `uv run mypy` from `backend/`.
- Backend linting and formatting: `backend/ruff.toml` defines ruff lint and format defaults.
- Current backend lint check: run `ruff check .` from `backend/`.
- Current backend format check: run `ruff format --check .` from `backend/`.
- Backend: `uv run` from `backend/`, with `ruff`, `mypy`, and `pytest` as the verification gate.
- Frontend setup: use Node `^20.19.0 || ^22.13.0 || >=24`, then run `npm install` from `frontend/`.
- Frontend dev server: `npm run dev` from `frontend/`.
- Frontend TypeScript check: `npm run typecheck` from `frontend/`.
- Frontend lint check: `npm run lint` from `frontend/`.
- Frontend tooling gate: `npm run check` from `frontend/` runs typecheck, lint, and build.
- Current frontend build check: `npm run build` from `frontend/`.
- Current frontend preview server: `npm run preview` from `frontend/` after a successful build.
- Frontend test scripts are not scaffolded yet; later frontend and Playwright tickets own those checks.
- Classification changes: run the golden-set eval (`backend/evals/run_eval.py`); regressions block merges.

Never claim work is complete without fresh verification evidence.
