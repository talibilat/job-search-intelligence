# Job-Search Intelligence

A local-first web app that connects to your email (Gmail first), mines your entire job-search history, and answers questions about it, from "how many jobs did I apply to?" to "why am I getting rejected and what should I fix?", through a dashboard and a conversational RAG agent.

## Core principle

All factual job-search answers come from one clean `applications` table and its event timeline (`application_events`).
Dashboard numbers are deterministic SQL or typed Python logic.
The LLM synthesizes narrative insight only after deterministic facts are prepared, and it never produces authoritative counts or emits raw SQL for execution.

## Status

Phase 0 (Groundwork).
The repository currently contains planning documents, root project metadata, the monorepo directory skeleton, an initial FastAPI app factory (`backend/app/main.py`) with an empty API router, backend mypy/pytest scaffolding, and `backend/.env.example` for v1 operational settings.
The rest of the backend, the frontend, and the CI scaffold fill in over subsequent Phase 0 tickets.

## Architecture at a glance

| Area | Decision |
|---|---|
| Backend | FastAPI, Python 3.12, async |
| Frontend | React, TypeScript, Vite |
| Database | SQLite (single local file) |
| Vector store | sqlite-vec (embeddings in the same SQLite file) |
| LLM providers | Pluggable: Azure OpenAI and Ollama first; OpenAI and Anthropic later |
| API style | REST with a generated TypeScript client from OpenAPI |
| Data contracts | Pydantic v2 DTOs at every boundary |
| Background sync | APScheduler in-process |
| RAG agent | LangGraph hybrid router (structured query + semantic retrieval) |
| Python tooling | uv, ruff, mypy, pre-commit |

See `docs/groundwork-spec.md` for the full locked architecture and repository layout.

## Repository layout

```text
backend/    FastAPI app, pipeline, providers, repositories, evals, tests
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

The backend has an initial FastAPI app factory, `backend/pyproject.toml` with strict mypy defaults, `backend/pytest.ini`, and `backend/.env.example` documenting expected v1 operational settings.
The backend settings loader, database, uv project metadata, and the frontend scaffold do not exist yet, so the commands referencing them below apply once those land.

- Backend type checking: `backend/pyproject.toml` defines strict mypy defaults for backend code.
- Current scaffold check: run `mypy --config-file pyproject.toml` from `backend/`.
- Current backend tests: run `python3 -m pytest` from `backend/`; `backend/pytest.ini` discovers `tests/` and sets `pythonpath = .` so tests import the local `app` package deterministically.
- Local backend overrides: copy `backend/.env.example` to `backend/.env` only when local settings are needed; `.env` files are ignored and must not contain secrets.
- Current backend health check: `GET /health` returns `{"status": "ok"}`.
- Once backend `uv` project metadata exists, run `uv run mypy` from `backend/`.
- Backend: `uv run` from `backend/`, with `ruff`, `mypy`, and `pytest` as the verification gate.
- Frontend: Vite dev server from `frontend/`, with TypeScript checks and lint as the verification gate.
- Classification changes: run the golden-set eval (`backend/evals/run_eval.py`); regressions block merges.

Never claim work is complete without fresh verification evidence.
