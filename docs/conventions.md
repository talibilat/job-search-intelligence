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
- `EmailProvider` implementations expose metadata pages separately from retained body batches, reject body-derived metadata snippets, keep provider sync cursors opaque, require a cursor for incremental metadata sync, and do not expose attachment content in v1.
- Secret storage goes through the `SecretStore` protocol with `SecretRef` identifiers and `SecretStr` values; the default adapter is OS keyring, and adapters own encrypted-at-rest storage.
- Pipeline stages for `ingest -> filter -> classify -> aggregate`, each passing DTOs.
- Service layer holds business logic; FastAPI route handlers stay thin.
- FastAPI dependency injection supplies repositories, providers, and config.
- Typed errors at API boundaries; no bare exceptions leak to the client.
- Public API failures use the standard `{"error": {"code": "...", "message": "...", "details": []}}` response shape, and route-specific public failures should raise `ApiError` instead of exposing arbitrary `HTTPException.detail` text.
- Validation, HTTP, and internal exception handlers must sanitize raw request input, tracebacks, secrets, and private exception details.
- Frontend code imports API client types and helpers from `frontend/src/api`; `frontend/src/api/generated/` is reserved for OpenAPI-generated output and placeholder destination code.

## Determinism and the LLM

- Dashboard counts, rates, funnels, time math, and group-bys are deterministic SQL or typed Python.
- The same input database produces the same metrics every time.
- The LLM never produces authoritative counts and never emits raw SQL for execution.
- Quantitative answers reconcile with deterministic queries; content answers cite real emails or applications.

## Style and hygiene

- Format and lint with `ruff`; keep modules small and focused, since a growing file signals it is doing too much.
- Use conventional commit messages.
- Never log secrets, OAuth tokens, API keys, or private email content unnecessarily; route secrets through `SecretStore` and store them encrypted at rest.
- Use `app.security.redaction` before logging structured data that may contain secrets or retained email bodies.
- Do not add telemetry, shared credentials, auto-apply, or autonomous outbound email.

## Verification

- Backend changes: run `ruff`, `mypy`, and the relevant `pytest` tests.
- Frontend changes: run `npm run check` from `frontend/`; run relevant tests once those tools are scaffolded.
- Classification changes: run the golden-set eval; regressions block merges unless explicitly accepted.
- Aggregation changes: verify idempotency and no duplicate applications.
- Never claim work is complete without fresh verification evidence.
