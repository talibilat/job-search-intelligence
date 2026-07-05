# Coding conventions

Baseline coding standards for every agent and contributor.
`AGENTS.md` is the canonical guide; this file is the quick reference it points at.

## Types and boundaries

- Type everything; code is `mypy`-clean.
- Cross every boundary with a Pydantic v2 DTO, never a raw dict.
- Validate structured LLM output with Pydantic and reject malformed output instead of storing it.

## Architecture patterns

- Repository pattern for all database access; no raw SQL scattered through services.
- Strategy pattern for `EmailProvider` and `LLMProvider`; provider-specific code stays behind the interface.
- Provider selection metadata belongs in `app.providers.provider_registry`; it declares supported providers, non-secret setting requirements, and `SecretRef` metadata without instantiating adapters or reading secrets.
- LLM calls go through the `app.providers.llm.LLMProvider` protocol using provider-neutral Pydantic generation DTOs; concrete provider adapters own vendor payloads and credential lookup.
- `EmailProvider` implementations expose metadata pages separately from retained body batches, reject body-derived metadata snippets, normalize retained HTML bodies to plain text, reject raw HTML retention fields, keep provider sync cursors opaque, require a cursor for incremental metadata sync, and do not expose attachment content in v1.
- Sync services persist provider-owned cursors through `SyncStateRepository`, keyed by provider and account, without treating cursor values as OAuth token material or email content.
- Sync services coordinate provider metadata pagination and must recover from expired incremental cursors by restarting resumable full metadata reconciliation without passing stale cursors into full-backfill requests.
- Broad job-search candidate selection belongs in provider-neutral DTOs over normalized metadata; provider metadata listing requests must not accept body content, snippets, or provider-specific candidate filters.
- Raw email DTO boundaries track body retention with `metadata_only`, `retained`, or `debugging`; metadata-only rows omit `body_text`, retained and debugging rows include it, and retained body text stays out of repr output.
[JT-065 2026-07-05 v4] Raw email DTO boundaries track body retention with `metadata_only`, `retained`, or `debugging`; metadata-only rows omit `body_text`, retained and debugging rows include it, and retained body text stays out of repr output.
- Gmail OAuth setup and future auth work must follow `docs/google-oauth-setup.md`: user-created Desktop client, `gmail.readonly` only, and token material routed through `SecretStore`.
- Secret storage goes through the `SecretStore` protocol with `SecretRef` identifiers and `SecretStr` values; the default adapter is OS keyring, and adapters own encrypted-at-rest storage.
- Alembic migrations run in SQLite batch mode; sqlite-vec and other virtual or vector tables are excluded from autogenerate and must be managed by hand-written revisions.
- Pipeline stages for `ingest -> filter -> classify -> aggregate`, each passing DTOs.
- Service layer holds business logic; FastAPI route handlers stay thin.
- FastAPI dependency injection supplies repositories, providers, and config.
- Typed errors at API boundaries; no bare exceptions leak to the client.
- Public API failures use the standard `{"error": {"code": "...", "message": "...", "details": []}}` response shape, and route-specific public failures should raise `ApiError` instead of exposing arbitrary `HTTPException.detail` text.
- Validation, HTTP, and internal exception handlers must sanitize raw request input, tracebacks, secrets, and private exception details.
- Frontend code imports API client types and helpers from `frontend/src/api`; `frontend/src/api/generated/` is reserved for OpenAPI-generated output and placeholder destination code.
- Frontend UI code uses shared primitives from `frontend/src/components/ui` for buttons, text inputs, labelled fields, alerts, tabs, and data tables so accessibility behavior stays centralized.

## Determinism and the LLM

- Dashboard counts, rates, funnels, time math, and group-bys are deterministic SQL or typed Python.
- The same input database produces the same metrics every time.
- The LLM never produces authoritative counts and never emits raw SQL for execution.
- Quantitative answers reconcile with deterministic queries; content answers cite real emails or applications.

## Style and hygiene

- Format and lint with `ruff`; keep modules small and focused, since a growing file signals it is doing too much.
- Use conventional commit messages.
- Never log secrets, OAuth tokens, API keys, or private email content unnecessarily; route secrets through `SecretStore` and store them encrypted at rest.
- Use the redaction helpers exported by `app.security` before logging structured data that may contain secrets or retained email bodies.
- Synthetic fixtures must be private-data-free, must set `contains_private_data` to `false`, and must use synthetic domains and content instead of copied inbox data.
- Do not add telemetry, shared credentials, auto-apply, or autonomous outbound email.

## Verification

- Backend changes: run `ruff`, `mypy`, and the relevant `pytest` tests.
- Frontend changes: after backend dependencies are synced with `uv`, run `npm run check` from `frontend/`; it generates the OpenAPI schema through the backend, then runs type checking, linting, Vitest, and build verification.
- Frontend component behavior or frontend logic changes: run `npm run test` from `frontend/`.
- Frontend browser smoke changes: run `npm run test:smoke` from `frontend/` after installing Chromium with `npx playwright install chromium` once per machine.
- Pre-commit config changes: run `uv run --project backend pre-commit run --all-files` from the repository root.
- Classification changes: run the golden-set eval; regressions block merges unless explicitly accepted.
- Aggregation changes: verify idempotency and no duplicate applications.
- Never claim work is complete without fresh verification evidence.

## Ticket-specific conventions

- [JT-063 2026-07-05 v2] Email providers must retain body content as normalized plain text: HTML MIME bodies are converted through the email HTML normalizer before storage, raw HTML fields are forbidden on retained body DTOs, and plain-text bodies that still look like raw HTML are rejected instead of silently retained.
