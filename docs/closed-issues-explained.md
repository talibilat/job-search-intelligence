# Closed GitHub Issues Explained

This file explains every GitHub issue that was closed in `talibilat/job-search-intelligence` when this report was created on 2026-07-04.
It is written for someone new to this repository and to the tech stack.

The closed issues inspected were: `#1`, `#2`, `#3`, `#4`, `#5`, `#6`, `#7`, `#8`, `#9`, `#10`, `#11`, `#12`, `#13`, `#26`, `#27`, `#29`, `#32`, `#33`, and `#34`.
These are all Phase 0 groundwork tickets.
That means they mostly set up the repository, backend foundation, frontend foundation, typed interfaces, configuration, and safety rails.

Issue `#28` has a merged provider-registry PR on `main`, but the GitHub issue itself was not closed at inspection time.
Because the request was for closed issues only, this report does not summarize `#28` as a closed ticket.

## How This Was Checked

I checked the GitHub issue tracker for closed issues.
I checked the merged pull requests connected to those issues.
I inspected the merged code from `origin/main` at commit `45cbd98`.
I also checked the local ticket files where they existed.

The main thing to know is that the local working tree may not be on the latest `main` branch.
If you want to test exactly what this report describes, use a checkout of `origin/main` that includes commit `45cbd98` or newer.

## Beginner Setup For Testing

Most backend checks start in the backend folder:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv sync
```

Most frontend checks start in the frontend folder:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/frontend
npm install
```

If a command fails because your local branch is old, switch to an up-to-date `main` checkout first.
Do not switch branches if you have local work you have not saved or committed.

## Current Overall State

The repository now has the start of a local-first job-search intelligence app.
The backend exists as a Python FastAPI project.
The frontend exists as a Vite React TypeScript project.
The frontend also has a Recharts chart wrapper foundation with an empty state for future deterministic dashboard metrics.
The frontend also has a primary navigation shell with a `/setup` Phase 0 setup page for provider, mode, Gmail read-only, privacy, checklist, disabled action, and not-ready copy.
The frontend also has an empty `/dashboard` page shell with placeholder filter and metrics regions.
The frontend also has static Phase 0 setup-copy cards for provider, mode, Gmail, and privacy choices.
The frontend also has an empty `/chat` route shell with a disabled composer for the later Phase 5 RAG chat work.
There are backend endpoints for health, setup status, setup submission, provider config, Gmail auth start and callback, manual sync, sync status, and wiping local data.
There are typed provider interfaces for Gmail and future LLM implementations, plus an exported Gmail provider adapter with read-only OAuth URL construction, callback token exchange and persistence, non-secret connection metadata persistence, provider-level token refresh, safe metadata-only full-backfill and incremental history listing, and retained-body fetching when a `SecretStore` is configured.
There is configuration infrastructure, a keyring-backed secret-store path, Alembic migration infrastructure, raw-email metadata and retained-body persistence, sync-state persistence, and lint/type/test tooling.

What does not exist yet is the full product.
There is no full Gmail ingestion pipeline yet because classification and aggregation remain pending.
There is no populated metrics dashboard yet.
There is no backend chat agent, retrieval, streaming, or persisted chat history yet.
There is no concrete Azure OpenAI or Ollama adapter yet.

## #1 JT-001 - Create Private GitHub Repository

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/1>

What was done:
The private GitHub repository `talibilat/job-search-intelligence` was created.
The default branch is `main`.
The repository was seeded with core project files such as `AGENTS.md`, `CLAUDE.md`, `README.md`, and `docs/`.

Why it was done:
This app will eventually handle private email-derived job-search data.
Starting in a private repository keeps early planning, credentials guidance, and implementation work away from public view.

Area:
Repo setup.
No backend or frontend application behavior was added by this ticket.

Important things to inspect:
`AGENTS.md` explains how agents should work in this repo.
`README.md` explains the app goal and current status.
`docs/prd.md` and `docs/groundwork-spec.md` explain what the app is meant to become.

How to test it:

```bash
gh repo view talibilat/job-search-intelligence --json name,visibility,isPrivate,defaultBranchRef
```

Expected result:
The output should show `isPrivate: true`, `visibility: PRIVATE`, and default branch `main`.

Caveat:
This ticket is verified through GitHub repository state, not through code tests.

## #2 JT-002 - Initialize Monorepo Structure

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/2>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/224>

What was done:
The repository was organized as a monorepo.
A monorepo means the backend, frontend, scripts, docs, tickets, and GitHub workflow files live in one repository.
Placeholder `.gitkeep` files were added so empty folders could be tracked by Git.

Why it was done:
The project needs both a backend API and a frontend web app.
Creating the folder structure first makes later tickets predictable because every part of the app has a clear home.

Area:
Repo infrastructure.
It created backend and frontend folder skeletons, but no real backend or frontend behavior yet.

Important files and folders to inspect:
`backend/` is where the FastAPI backend lives.
`frontend/` is where the React app lives.
`docs/` is where the product and architecture docs live.
`tickets/` is where local ticket artifacts live.
`scripts/` is for project scripts.
`.github/workflows/` is for GitHub Actions workflows.
`.github/workflows/` is for GitHub Actions workflows as Phase 0 CI lands.

How to test it:

```bash
git ls-tree --name-only HEAD
```

Expected result:
You should see top-level folders such as `backend`, `frontend`, `docs`, `tickets`, `scripts`, and `.github`.

Caveat:
This ticket only created structure.
It did not make the app runnable yet.

## #3 JT-003 - Add Root Project Metadata

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/3>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/225>

What was done:
Root-level project metadata was added.
This includes the main `README.md`, `.gitignore`, `.editorconfig`, and `docs/conventions.md`.

Why it was done:
New contributors and agents need to know what the app is, how files should be formatted, and which generated or private files should not be committed.
The `.gitignore` is especially important because this app must not accidentally commit local databases, virtual environments, secrets, build outputs, or caches.

Area:
Documentation and repository infrastructure.

Important files to inspect:
`README.md` explains the app in plain language.
`.gitignore` lists files Git should ignore.
`.editorconfig` sets editor defaults such as indentation and line endings.
`docs/conventions.md` records coding conventions.

How to test it:

```bash
git show --name-only --oneline HEAD -- README.md .gitignore .editorconfig docs/conventions.md
```

Expected result:
The files should exist in the repository.
You can also open `README.md` and confirm it describes Job-Search Intelligence as a local-first app.

Caveat:
This was not feature work.
It set rules and documentation for future work.

## #4 JT-004 - Scaffold Backend Python Project

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/4>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/235>

What was done:
The backend was turned into a Python project managed by `uv`.
`uv` is a modern Python tool that installs dependencies and runs commands in the project environment.
The ticket added `backend/pyproject.toml` and `backend/uv.lock`.

Why it was done:
The backend needs a reproducible Python environment before FastAPI endpoints, tests, linting, and type checking can work reliably.
The lockfile helps make dependency installs consistent across machines.

Area:
Backend infrastructure.

Important files to inspect:
`backend/pyproject.toml` defines backend dependencies and tools.
`backend/uv.lock` records exact dependency versions.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv sync --locked
uv run python --version
```

Expected result:
`uv sync --locked` should install dependencies from the lockfile.
The Python version should be compatible with the backend project.

Caveat:
This ticket created the backend project shell.
It did not by itself add API behavior.

## #5 JT-005 - Configure Backend Linting And Formatting

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/5>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/234>

What was done:
Ruff was configured for the backend.
Ruff is a fast Python linter and formatter.
It catches common mistakes and keeps formatting consistent.

Why it was done:
As the backend grows, consistent formatting and automated lint checks reduce accidental bugs and style drift.
This matters because many later tickets will touch the same backend modules.

Area:
Backend tooling.

Important files to inspect:
`backend/ruff.toml` contains the Ruff settings.
`backend/pyproject.toml` includes the project dependencies needed to run Ruff.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run ruff check .
uv run ruff format --check .
```

Expected result:
Both commands should finish without errors.

Caveat:
This ticket does not change product behavior.
It gives contributors a quality gate for Python code.

## #6 JT-006 - Configure Backend Type Checking

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/6>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/228>

What was done:
Strict `mypy` type checking was configured for the backend.
`mypy` checks Python type hints before runtime.
The backend is expected to use typed DTOs, services, provider interfaces, and API boundaries.

Why it was done:
This app will move sensitive data through many layers.
Type checking helps catch broken assumptions early, such as a service returning the wrong shape or a provider interface being used incorrectly.

Area:
Backend tooling.

Important files to inspect:
`backend/pyproject.toml` contains the mypy settings.
`backend/tests/__init__.py` and `backend/evals/__init__.py` make those folders importable packages.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run mypy
```

Expected result:
`mypy` should finish without type errors.

Caveat:
This ticket does not add user-visible behavior.
It adds a backend correctness check.

## #7 JT-007 - Add Backend Test Harness

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/7>
Merged PRs: <https://github.com/talibilat/job-search-intelligence/pull/227> and <https://github.com/talibilat/job-search-intelligence/pull/229>

What was done:
Pytest was configured for backend tests.
Pytest is the Python test runner used by this project.
A smoke test was added, and the import path was stabilized so tests can import the local `app` package reliably.

Why it was done:
Before adding real backend behavior, the repository needed a repeatable way to run tests.
The import-path setup matters because otherwise tests might fail on one machine and pass on another depending on how Python resolves packages.

Area:
Backend testing infrastructure.

Important files to inspect:
`backend/pytest.ini` configures pytest.
`backend/tests/test_smoke.py` is the basic smoke test.
`backend/tests/` contains later backend tests as more features landed.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest -m smoke
uv run pytest
```

Expected result:
The smoke tests and the full backend test suite should pass.

Caveat:
Issue `#7` was closed before a follow-up import-path PR merged.
The follow-up PR is still relevant because it improved the test harness.

## #8 JT-008 - Create FastAPI App Factory

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/8>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/226>

What was done:
The backend got a FastAPI app factory.
FastAPI is the Python web framework used for the API.
An app factory is a function that creates the app object, which makes testing and server startup cleaner.

Why it was done:
All future API routes need one central app entrypoint.
The app factory lets tests create an app instance and lets an ASGI server such as `uvicorn` run the backend.

Area:
Backend.

Important files to inspect:
`backend/app/main.py` contains `create_app()` and the module-level `app`.
`backend/app/api/router.py` contains the API router registration point.
`backend/tests/test_app_factory.py` checks the factory behavior.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest tests/test_app_factory.py -v
uv run python -c "from app.main import create_app; app = create_app(); print(app.title)"
```

Expected result:
The tests should pass.
The import command should print the FastAPI application title.

Manual server check:

```bash
uv run uvicorn app.main:app --port 8000
```

Then open `http://127.0.0.1:8000/docs` in a browser.
You should see the FastAPI OpenAPI documentation page.

Caveat:
Later tickets added real routes into the router, so the app is no longer just an empty shell on `main`.

## #9 JT-009 - Add Health Endpoint

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/9>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/230>

What was done:
The backend got a `GET /health` endpoint.
It returns a small response showing the API process is alive.

Why it was done:
A health endpoint is the simplest way for a human, frontend, script, or future deployment check to confirm that the backend server is running.

Area:
Backend API.

Important files to inspect:
`backend/app/api/health.py` defines the route.
`backend/app/models/health.py` defines the typed response model.
`backend/app/api/router.py` registers the route.
`backend/tests/test_health.py` tests it.

How to test it with pytest:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest tests/test_health.py -v
```

How to test it manually:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Then in another terminal:

```bash
curl -s http://127.0.0.1:8765/health
```

Expected result:

```json
{ "status": "ok" }
```

Caveat:
This only proves the API process is alive.
It does not prove that the database, Gmail, or LLM providers are configured.

## #10 JT-010 - Add Typed API Error Model

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/10>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/232>

What was done:
The backend got a standard error response shape.
It added an `ApiError` exception and handlers for app errors, validation errors, HTTP errors, and unexpected errors.

Why it was done:
Frontend code needs predictable error responses.
The app also needs to avoid leaking raw exceptions, request data, tokens, or private email content in API errors.

Area:
Backend API and security.

Important files to inspect:
`backend/app/api/errors.py` contains the error model and handlers.
`backend/app/main.py` registers the error handlers.
`backend/tests/test_api_errors.py` tests the behavior.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest tests/test_api_errors.py -v
```

Expected result:
The tests should pass.
A typical error body should look like this:

```json
{
  "error": {
    "code": "not_found",
    "message": "Resource not found",
    "details": []
  }
}
```

Manual check:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Then in another terminal:

```bash
curl -s http://127.0.0.1:8765/missing-route
```

Expected result:
You should get a typed error response instead of an unstructured traceback.

Caveat:
Route authors still need to use `ApiError` for route-specific public errors.

## #11 JT-011 - Add Pydantic Settings Shell

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/11>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/236>

What was done:
The backend got typed application settings using `pydantic-settings`.
Pydantic settings reads environment variables and validates them into a Python object.

Why it was done:
The app needs one safe, typed place for configuration such as the API host, database URL, email provider, LLM provider, classification mode, and thresholds.
Without this, different modules might read raw environment variables inconsistently.

Area:
Backend configuration.

Important files to inspect:
`backend/app/config.py` defines `AppSettings`.
`backend/tests/test_config.py` tests defaults and validation.
`backend/.env.example` documents example environment variables.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest tests/test_config.py -v
uv run python -c "from app.config import AppSettings; print(AppSettings(_env_file=None).llm_provider)"
```

Expected result:
The tests should pass.
The import command should print the default LLM provider, currently `ollama`.

Caveat:
This is not the first-run setup wizard yet.
It validates settings, but it does not connect Gmail or store real secrets.

## #12 JT-012 - Add Env Example

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/12>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/233>

What was done:
The backend got `backend/.env.example`.
This file shows which environment variables can be configured without containing real secrets.

Why it was done:
Beginners need to know what settings exist.
At the same time, the project must not commit API keys, OAuth tokens, passwords, or Google OAuth client JSON.

Area:
Configuration documentation.

Important files to inspect:
`backend/.env.example` lists safe example settings.
`backend/tests/test_env_example.py` checks that the example stays safe and aligned.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest tests/test_env_example.py -v
```

Expected result:
The tests should pass.

Manual check:
Open `backend/.env.example` and confirm it uses `JOBTRACKER_` variables.
It should not contain real tokens or passwords.

Caveat:
Later tickets added more environment variables to the same file, so the current file contains more than the original JT-012 change.

## #13 JT-013 - Add Secret-Store Interface

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/13>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/231>

What was done:
A secret-store interface was added.
It defines how the app will refer to secrets such as OAuth tokens and LLM API keys without passing raw secret values around everywhere.

Why it was done:
This app must store secrets encrypted at rest.
Adding the interface first let later code depend on a clean contract before concrete backends such as OS keyring or Fernet were implemented.

Area:
Backend security infrastructure.

Important files to inspect:
`backend/app/security/secret_store.py` defines the protocol, secret reference model, secret kinds, and errors.
`backend/app/security/__init__.py` exports the public security types.
`backend/tests/test_secret_store_contract.py` tests the contract.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest tests/test_secret_store_contract.py -v
uv run python -c "from app.security import SecretKind, SecretRef; print(SecretRef(kind=SecretKind.OAUTH_TOKEN, provider='gmail', name='refresh_token'))"
```

Expected result:
The tests should pass.
The import command should print a typed secret reference.

Caveat:
This ticket did not save secrets by itself.
JT-014 later added the default OS keyring implementation, while the Fernet fallback remains separate.

## #26 JT-026 - Define EmailProvider Interface

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/26>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/244>

What was done:
The backend got an `EmailProvider` interface.
It defines the common shape for future email integrations, starting with Gmail and later allowing Outlook or IMAP.
The ticket also added typed DTOs for auth flow, connection status, sync cursors, metadata pages, retained body fetching, capabilities, and provider errors.

Why it was done:
The app should not hard-code Gmail everywhere.
The ingestion pipeline should talk to an abstract email provider so future providers can be swapped in without rewriting the pipeline.
This also keeps OAuth tokens behind secret references instead of raw strings.

Area:
Backend provider interface and security.

Important files to inspect:
`backend/app/providers/email/provider.py` defines the interface and DTOs.
`backend/app/providers/email/__init__.py` exports them.
`backend/tests/test_email_provider_contract.py` tests the contract.
`backend/app/security/secret_store.py` is used for secret references.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest tests/test_email_provider_contract.py -v
uv run python -c "from app.providers.email import EmailSyncMode; print(EmailSyncMode.FULL_BACKFILL)"
```

Expected result:
The tests should pass.
The import command should print `full_backfill`.

Caveat:
This does not implement Gmail yet.
It only defines the interface that the Gmail adapter must implement; JT-058 later added the Gmail provider skeleton.

## #27 JT-027 - Define LLMProvider Interface

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/27>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/239>

What was done:
The backend got an `LLMProvider` interface.
It defines request and response types for future LLM calls, including messages, roles, generation options, token usage, finish reasons, and provider errors.

Why it was done:
The app will eventually use LLMs for classification, extraction, cached insights, and chat.
Application code should not depend directly on one vendor SDK such as Azure OpenAI or Ollama.
A provider interface keeps those integrations swappable.

Area:
Backend provider interface and security.

Important files to inspect:
`backend/app/providers/llm/provider.py` defines the provider protocol.
`backend/app/providers/llm/types.py` defines typed request and response models.
`backend/app/providers/llm/errors.py` defines safe provider errors.
`backend/tests/test_llm_provider_contract.py` tests the contract.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest tests/test_llm_provider_contract.py -v
uv run python -c "from app.providers.llm import LLMMessage, LLMMessageRole; print(LLMMessage(role=LLMMessageRole.USER, content='hello'))"
```

Expected result:
The tests should pass.
The import command should print a typed LLM message.

Caveat:
This does not implement Azure OpenAI, Ollama, OpenAI, or Anthropic.
Embeddings were also deferred to a later ticket.

## #29 JT-029 - Add Setup Status API Shell

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/29>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/241>

What was done:
The backend got a `GET /setup/status` endpoint.
It returns whether first-run setup is complete, whether Gmail is connected, whether an LLM is configured, and which non-secret provider choices are selected.

Why it was done:
The frontend setup flow needs a safe way to ask the backend what still needs to be configured.
This endpoint gives that status without exposing secrets.

Area:
Backend API and configuration.

Important files to inspect:
`backend/app/api/setup.py` defines the route.
`backend/app/models/setup.py` defines the response model.
`backend/app/services/setup_status.py` contains the status logic.
`backend/tests/test_setup_status.py` tests it.

How to test it with pytest:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest tests/test_setup_status.py -v
```

How to test it manually:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Then in another terminal:

```bash
curl -s http://127.0.0.1:8765/setup/status
```

Expected result:

```json
{
  "setup_complete": false,
  "gmail_connected": false,
  "llm_configured": false,
  "email_provider": "gmail",
  "llm_provider": "ollama",
  "classification_mode": "local"
}
```

Caveat:
This is only a shell.
The boolean values are still always `false` because OAuth connection checks, credential checks, and setup completion logic are later work.

## #32 JT-032 - Add Local Wipe-Data Command Or Endpoint

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/32>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/243>

What was done:
The backend got a `POST /local-data/wipe` endpoint.
It can delete configured local app data after a strict confirmation.
It returns which paths were deleted and which were already missing.

Why it was done:
The app will store sensitive local job-search and email-derived data.
A local-first app needs an explicit way for the user to wipe local data safely.

Area:
Backend API, privacy, and security.

Important files to inspect:
`backend/app/api/wipe_data.py` defines the API route.
`backend/app/models/wipe_data.py` defines request and response DTOs.
`backend/app/services/wipe_data.py` contains the deletion safety logic.
`backend/tests/test_wipe_data_api.py` tests the endpoint.
`backend/tests/test_wipe_data_service.py` tests the wipe service.
`backend/.env.example` documents wipe-data related configuration.

How to test it with pytest:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run pytest tests/test_wipe_data_api.py tests/test_wipe_data_service.py -v
```

How to test a safe validation failure manually:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Then in another terminal:

```bash
curl -s -X POST http://127.0.0.1:8765/local-data/wipe -H 'Content-Type: application/json' -d '{"confirmation":"delete"}'
```

Expected result:
You should get a typed validation error because the confirmation is intentionally wrong.
This is a safe check because it should not delete anything.

Successful response shape:

```json
{ "status": "wiped", "deleted_paths": ["..."], "missing_paths": ["..."] }
```

Caveat:
Do not call the successful wipe path against real data unless you really intend to delete it.
This endpoint does not delete OS keyring secrets or external OAuth client JSON files.

## #33 JT-033 - Scaffold Frontend Vite React TypeScript App

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/33>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/238>

What was done:
The frontend app was created using Vite, React, TypeScript, npm, and plain CSS.
It includes a browser entrypoint, React root renderer, TypeScript config, Vite config, package files, and a static responsive Phase 0 UI.

Why it was done:
The project needs a browser app before it can show setup screens, dashboards, insights, or chat.
This ticket created the frontend foundation without connecting to real backend data yet.

Area:
Frontend and repo infrastructure.

Important files to inspect:
`frontend/package.json` defines frontend scripts and dependencies.
`frontend/index.html` is the browser HTML entrypoint.
`frontend/src/main.tsx` starts React in the browser.
`frontend/src/App.tsx` contains the initial app shell.
`frontend/src/index.css` styles the shell.
`frontend/vite.config.ts` configures Vite.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/frontend
node --version
npm install
npm run build
npm run dev -- --host 127.0.0.1 --port 5173
```

Expected result:
`npm run build` should finish successfully and create ignored build output under `frontend/dist/`.
`npm run dev` should print a local URL such as `http://127.0.0.1:5173/`.
Opening that URL should show the static JobTracker shell.

Caveat:
At the time this shell landed, dashboard routing, generated API client work, Playwright smoke suite, and backend integration were reserved for later tickets.

## #34 JT-034 - Configure Frontend Lint And Type Checks

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/34>
Merged PR: <https://github.com/talibilat/job-search-intelligence/pull/240>

What was done:
The frontend got verification scripts for type checking, linting, and a combined check.
Later API-client work extended the combined check with generated API contract validation before those original steps.
An ESLint config was added for TypeScript and React Hooks rules.
The frontend package now declares supported Node versions.

Why it was done:
Future frontend work needs a reliable quality gate.
This catches generated API contract drift, TypeScript mistakes, lint problems, React Hooks problems, and build failures before changes are merged.

Area:
Frontend tooling and documentation.

Important files to inspect:
`frontend/package.json` contains API generation, API contract check, `typecheck`, `lint`, and `check` scripts.
`frontend/eslint.config.js` contains the ESLint setup.
`frontend/tsconfig.json`, `frontend/tsconfig.app.json`, and `frontend/tsconfig.node.json` configure TypeScript.
`README.md`, `AGENTS.md`, and `docs/conventions.md` document the frontend checks.

How to test it:

```bash
cd /Users/talibilat/Documents/Projects/job-search-intelligence/frontend
node --version
npm install
npm run typecheck
npm run lint
npm run check
```

Expected result:
`npm run typecheck` should finish without TypeScript errors.
`npm run lint` should finish without ESLint errors or warnings.
`npm run check` should run API contract generation/staleness checks, typecheck, lint, and Vite build.

Caveat:
This ticket does not add frontend tests.
It originally added lint, type checking, and build verification only; later API-client work added the generated API contract gate.

## #48 JT-048 - Add Frontend CI Workflow

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/48>

What was done:
A frontend GitHub Actions workflow was added at `.github/workflows/frontend-ci.yml`.
It checks out the repository, installs `uv`, sets up Python 3.12, syncs locked backend dependencies, sets up Node.js 22 with npm caching keyed by `frontend/package-lock.json`, runs `npm ci` with `working-directory: frontend`, and runs `npm run check` with `working-directory: frontend`.

Why it was done:
The frontend OpenAPI schema generation, typecheck, ESLint gate, Vitest unit tests, and Vite build smoke check now run automatically on pushes and pull requests targeting `main`.
This keeps the existing frontend package scripts as the source of truth while making OpenAPI generation, type checking, linting, unit tests, and build verification part of the Phase 0 CI gate.
This keeps the OpenAPI-backed frontend package scripts as the source of truth for the Phase 0 CI gate.

Area:
Frontend CI and repository infrastructure.

Important files to inspect:
`.github/workflows/frontend-ci.yml` contains the GitHub Actions workflow.
`frontend/package.json` contains the `generate:openapi` script and the `check` script that CI invokes.
`frontend/package-lock.json` is the nested npm lockfile used by `npm ci` and the GitHub Actions npm cache.
`backend/tests/test_frontend_ci_workflow.py` verifies the lockfile is valid JSON, `npm run check` starts with OpenAPI generation through backend `uv`, and the workflow installs backend tooling before using the nested lockfile plus `frontend/` working directory for install and check steps.

How to test it locally:

```bash
cd frontend
npm ci
npm run check
```

`npm run check` requires the backend `uv` environment because it shells into `backend/` to generate `frontend/src/api/openapi.json` before running frontend checks.

To verify the workflow contract from the backend test suite:

```bash
cd backend
uv run pytest tests/test_frontend_ci_workflow.py -q
```

Expected result:
`npm run check` should run OpenAPI schema generation, TypeScript checking, ESLint, Vitest, and the Vite build without errors.

Caveat:
This ticket adds frontend CI only.
It does not add frontend tests, backend CI, application behavior, data model changes, secrets, telemetry, or backend API surfaces.

## #58 JT-058 - Add Gmail Provider Skeleton

GitHub issue: <https://github.com/talibilat/job-search-intelligence/issues/58>

What was done:
At the time of JT-058, the backend got an exported `GmailEmailProvider` skeleton in `backend/app/providers/email/gmail.py`.
That initial ticket implemented the existing `EmailProvider` protocol shape without calling live Google APIs.
That initial adapter enforced the v1 `gmail.readonly` scope, advertised read-only ingestion capabilities, ignored attachments, and returned public-safe `EmailProviderError` values for runtime methods deferred to later Gmail tickets.

Why it was done:
The ingestion pipeline needs a concrete Gmail adapter boundary before later OAuth, refresh, metadata listing, retained body fetching, and sync orchestration tickets fill in runtime behavior.
This keeps Gmail-specific behavior behind the provider seam while preserving local-first storage, bring-your-own credentials, and no outbound email behavior.

Area:
Backend email provider skeleton and privacy boundary.

Important files to inspect:
`backend/app/providers/email/gmail.py` defined the Gmail provider skeleton for this ticket and now also contains later safe full-backfill and incremental metadata-listing and retained-body fetching behavior.
`backend/app/providers/email/__init__.py` exports it.
`backend/tests/test_gmail_email_provider.py` verifies protocol conformance, readonly scopes, capabilities, attachment exclusion, provider-level callback token exchange and persistence, provider-level metadata-listing delegation, retained-body fetching, and public-safe errors for remaining deferred behavior.
`backend/tests/test_gmail_message_listing.py` verifies later safe full-backfill and incremental metadata-listing behavior.

How to test it:

```bash
cd backend
uv run pytest tests/test_gmail_email_provider.py -v
```

Expected result:
The Gmail provider tests should pass.

Caveat:
This ticket did not implement live Gmail OAuth, token refresh, metadata listing, retained body fetching, sync orchestration, database writes, or API routes; later work added safe metadata-only full-backfill and incremental history listing, retained-body fetching behind `SecretStore`, and Gmail token refresh.

## Quick Testing Checklist

Run these backend checks from `backend/`:

```bash
uv sync
uv run pytest
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

Run the root pre-commit gate after backend and frontend dependencies are installed:

```bash
uv run --project backend pre-commit run --all-files
```

Run these frontend checks from `frontend/`:

```bash
npm ci
npm run check
```

`npm run check` runs OpenAPI schema generation, type checking, linting, Vitest, and the Vite build.

Run the backend manually from `backend/`:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Then test endpoints in another terminal:

```bash
curl -s http://127.0.0.1:8765/health
curl -s http://127.0.0.1:8765/setup/status
curl -s -X POST http://127.0.0.1:8765/setup \
  -H 'content-type: application/json' \
  -d '{"email_provider":"gmail","llm_provider":"ollama","classification_mode":"local"}'
```

Run the frontend manually from `frontend/`:

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

Then open `http://127.0.0.1:5173/` and `http://127.0.0.1:5173/setup` in a browser.

## What To Look For In The App Right Now

Backend:
You can see a FastAPI app, generated API docs, a health endpoint, typed errors, setup status, setup submission, Gmail auth-start, manual sync, sync status, local wipe-data infrastructure, async SQLite engine infrastructure, Alembic migration infrastructure, and local sync/raw-email persistence.

Frontend:
You can see a static React shell for JobTracker, including an empty Recharts foundation panel for future deterministic dashboard metrics, a `/setup` page shell for provider, mode, Gmail, privacy, checklist, disabled action, and not-ready copy, a disabled `/chat` shell for later RAG work, and shared accessible UI primitives for later pages.
It is not connected to backend data yet.

Configuration:
You can see typed settings and a safe `.env.example`.
Real secrets should not be committed.

Providers:
You can see abstract provider contracts for email and LLM systems.
Gmail can start read-only OAuth authorization, complete the callback with encrypted token persistence, refresh expired stored credentials, store non-secret connection metadata, resolve the default connected account for sync, list safe metadata-only full-backfill and incremental history pages, fetch retained bodies for selected refs when constructed with a `SecretStore`, run resumable full backfill until the replacement cursor is promoted, and store broad candidate retained bodies during manual sync, but product pages and concrete LLM implementations are not done yet.

Privacy and safety:
You can see early safety work for typed errors, secret references, safe configuration examples, and local data wiping.

## Summary In Plain English

The closed tickets have built the foundation, not the finished product.
The backend can start, expose a few basic endpoints, prepare Alembic's version table, run tests, lint, and type checks.
The frontend can start, run unit tests, and build, but it is still a static shell with an empty chart foundation, disabled chat route shell, and shared primitive layer.
Frontend CI now runs backend OpenAPI generation plus the existing frontend typecheck, lint, unit test, and build gate on pushes and pull requests to `main`.
The backend can start, expose a few basic endpoints, create a configured async SQLite engine, run tests, lint, and type checks.
Frontend CI now runs the existing frontend typecheck, lint, unit test, and build gate on pushes and pull requests to `main`.
The backend can start, expose a few basic endpoints, create a configured async SQLite engine, initialize Alembic's version table, run tests, lint, and type checks.
The frontend can start, test, and build, but it is still a static shell with an empty chart foundation, a non-persistent `/setup` page shell, and a disabled chat route shell.
Frontend CI now runs backend OpenAPI generation plus the existing frontend typecheck, lint, Vitest, and build gate on pushes and pull requests to `main`.
The provider interfaces prepare the app for Gmail and LLM integrations; Gmail auth-start, Gmail callback token persistence, provider-level token refresh, non-secret connection metadata persistence, default connected-account lookup, `SecretStore`-backed full and incremental metadata listing, selected-ref retained-body fetching, resumable full-backfill orchestration, and manual-sync retained-body repository writes exist, while product pages and concrete LLM adapters remain later work.
The privacy-related groundwork is already visible through secret references, typed errors, safe env examples, the SQLite engine, Alembic migrations, and the wipe-data endpoint.
