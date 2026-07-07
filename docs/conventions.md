# Coding conventions

Baseline coding standards for every agent and contributor.
`AGENTS.md` is the canonical guide; this file is the quick reference it points at.

## Types and boundaries

- Type everything; code is `mypy`-clean.
- Cross every boundary with a Pydantic v2 DTO, never a raw dict.
- Keep core storage DTOs in focused `app.models` domain modules, and preserve stable aggregate imports through `app.models` and `app.models.records` for shared repository and pipeline code.
- Validate structured LLM output with Pydantic and reject malformed output instead of storing it.
- Classification provider responses must be parsed through the classification generation parser before any storage or aggregation code can consume extracted fields.
- Malformed classification or extraction output must cross downstream boundaries as public-safe quarantine metadata only, without raw provider content or storage-ready classification records.

## Architecture patterns

- Repository pattern for all database access; no raw SQL scattered through services.
- Strategy pattern for `EmailProvider` and `LLMProvider`; provider-specific code stays behind the interface.
- Provider selection metadata belongs in `app.providers.provider_registry`; it declares supported providers, non-secret setting requirements, and `SecretRef` metadata without instantiating adapters or reading secrets.
- LLM calls go through the `app.providers.llm.LLMProvider` protocol using provider-neutral Pydantic generation DTOs; concrete provider adapters own vendor payloads and credential lookup.
- Ollama provider adapters must keep local mode local: reject non-local base URLs, do not use HTTP proxy routing for local calls, and map transport failures to public-safe LLM provider errors without prompt or completion content.
- Classification prompt requests go through `app.pipeline.classify.build_classification_prompt_request`, request `LLMResponseFormat.JSON_OBJECT`, embed `CLASSIFICATION_PROMPT_VERSION`, and send only retained email candidate fields needed for classification.
- Classification service orchestration belongs in `app.services.classification`: it calls the configured `LLMProvider`, validates responses before storage, returns accepted and malformed DTOs, aggregates token usage, and leaves persistence plus aggregation to later pipeline stages.
- Structured extraction batches go through `StructuredExtractionService`; services may store accepted `email_classifications` rows and `classification_runs` accounting, but malformed provider output must remain public-safe and aggregation writes stay in the later aggregate stage.
- Insight generation must build deterministic facts and cited evidence before calling the LLM, keep debugging retained bodies out of provider payloads, include the insight prompt version in cache hashes, and keep Q-46 `story` evidence chronological within the recent search window.
- `EmailProvider` implementations expose metadata pages separately from retained body batches, reject body-derived metadata snippets, normalize retained HTML bodies to plain text, reject raw HTML retention fields, keep provider sync cursors opaque, require a cursor for incremental metadata sync, and do not expose attachment content in v1.
- Gmail metadata listing must keep full backfill and incremental sync metadata-only: use message list pages for full backfill, `users.history.list` `messageAdded` records for incremental sync, withhold replacement history cursors until paginated listing is fully drained, and map Gmail history `404` responses to expired-cursor recovery.
- Sync services persist provider-owned cursors through `SyncStateRepository`, keyed by provider and account, without treating cursor values as OAuth token material or email content.
[JT-066 2026-07-05 v2] - Sync services persist full-backfill status, page tokens, counters, replacement cursors, and public-safe failure text through `BackfillStateRepository`, keyed by provider and account, without storing token material or email content in backfill state.
[JT-066 2026-07-05 v2] - Completed full backfills must clear the next page token, require a replacement provider cursor with issued timestamp, and promote that cursor to `SyncStateRepository` in the same local SQLite transaction that records the final page.
[JT-066 2026-07-05 v2] - Full-backfill callers must persist raw emails and retained candidate bodies before recording page progress; listing a page with `run_backfill_page` must not advance counters or resume tokens by itself, and retained-body failures must fail the page without advancing durable progress.
- Sync services persist provider-owned cursors and in-progress page tokens through `SyncStateRepository`, keyed by provider and account, without treating cursor values or page tokens as OAuth token material or email content.
- Sync services coordinate provider metadata pagination, persist page progress before continuing, and must recover from expired incremental cursors by restarting resumable full metadata reconciliation without passing stale cursors into full-backfill requests.
- Public sync status crosses the API boundary through the `EmailSyncStatus` DTO and must expose only run state, mode, deterministic counts, sanitized errors, and timestamps, never provider payloads, OAuth tokens, raw cursors, page tokens, or email content.
- Sync scheduling stays backend-process local: `SyncScheduler` owns APScheduler start and shutdown through the FastAPI lifespan, registers only injected async sync jobs, and remains stopped when `sync_on_open` is false.
- Broad job-search candidate selection belongs in provider-neutral DTOs over normalized metadata; provider metadata listing requests must not accept body content, snippets, or provider-specific candidate filters.
- Candidate decisions must be deterministic scored outcomes with public-safe signal tokens; excluded labels are hard rejections, and same-page thread promotion must expose only a static thread signal instead of raw provider thread IDs.
- Candidate-query keyword checks may also run over already-normalized retained body text when a caller already has it, but the query must store only static terms and never serialize private email content.
- Persisted broad job-search filter decisions must use the `email_filter_decisions` audit table, upsert by raw email ID and strategy, use the same batch candidate decision path as retained-body selection, and store only static public-safe reason tokens rather than raw subjects, snippets, bodies, provider thread IDs, or provider payloads.
- Gmail OAuth setup and auth work must follow `docs/google-oauth-setup.md`: user-created Desktop client, `gmail.readonly` only, provider-owned authorization URLs, callback codes as `SecretStr`, refresh-token reuse behind the provider seam, and token material routed through `SecretStore`.
- Raw email DTO boundaries track body retention with `metadata_only`, `retained`, or `debugging`; metadata-only rows omit `body_text`, retained and debugging rows include it, and retained body text stays out of repr output.
- Classification DTO boundaries use retained `EmailClassificationCandidate` inputs, provider-neutral `EmailClassificationResult` outputs, and stored `EmailClassificationRecord` rows; they reject unknown fields, keep retained body text out of repr output, and require timezone-aware candidate and classification timestamps.
- Classification reprocessing plans must be deterministic read-only service results over retained candidate rows and stored `model` plus `prompt_version` values; they must not call an LLM, expose email content, or classify stale rows before an explicit runner executes that work.
- Classification candidate queries must exclude empty or whitespace-only retained body text so the LLM provider only receives useful retained candidates.
- Raw email repository writes must be idempotent by provider message ID and must preserve existing `retained` or `debugging` body text when later metadata-only reconciliation pages replay the same message.
- Raw email retained and debugging body writes must insert a minimal `raw_emails` row when metadata is not present yet, then allow later metadata-only replays to fill metadata without downgrading the retained body state.
- Downstream pipeline code should use `RawEmailRecord.has_retained_body` to test body availability instead of re-checking retention enum values directly.
- [JT-020 2026-07-05 v1] Application event DTOs and schema constraints allow a null `email_id` only for `ghost_inferred` events; evidence-backed events must keep a source email reference.
- Manual event edit code must validate changed source-email references against `raw_emails`, reject no-op edits, recompute deterministic event IDs when identity fields change, clear stale `extracted_status` when changing event type, and protect edited event/source-email evidence from aggregation overwrite.
- Gmail OAuth connection records must persist non-secret metadata separately from `SecretStore` token material.
- Secret storage goes through the `SecretStore` protocol with `SecretRef` identifiers and `SecretStr` values; the default adapter is OS keyring, and adapters own encrypted-at-rest storage.
- Alembic migrations run in SQLite batch mode; sqlite-vec and other virtual or vector tables are excluded from autogenerate and must be managed by hand-written revisions.
- Pipeline stages for `ingest -> filter -> classify -> aggregate`, each passing DTOs.
- Classification pipeline code must parse provider-neutral `LLMGenerationResponse` values before storage side effects, accept only clean finish reasons and strict structured JSON, and keep rejected provider output out of `email_classifications`, `applications`, and `application_events`.
- Aggregation grouping-key assembly belongs in `app.pipeline.aggregate.build_application_grouping_key`: use normalized company and role values, trim provider thread IDs without case-folding them, prefer a present thread signal, and use the UTC date-window bucket only when the thread signal is missing.
- Aggregation status derivation belongs in the aggregate service: combine already-persisted `application_events` with the current batch, order them by event timestamp, raw email `sent_at`, and classification timestamp, then derive `applications.current_status` from status-bearing event types without overwriting manual-lock conflicts.
- Service layer holds business logic; FastAPI route handlers stay thin.
- FastAPI dependency injection supplies repositories, providers, and config.
- Typed errors at API boundaries; no bare exceptions leak to the client.
- Email-provider failures that can cross the API boundary must use stable `EmailProviderErrorCode` values and `EmailProviderUserAction` hints so clients can distinguish reconnect, scope, rate-limit, temporary outage, expired-cursor, invalid-provider-response, and generic provider-failure cases without inspecting provider payloads.
- LLM-provider failures that can cross the API boundary must use typed `LLMProviderError` subclasses so clients can distinguish unavailable providers, failed requests, invalid responses, and timeouts without inspecting provider payloads.
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
- Synthetic fixtures and golden-set fixtures must be private-data-free, must set `contains_private_data` to `false`, and must use synthetic domains and content instead of copied inbox data.
- Do not add telemetry, shared credentials, auto-apply, or autonomous outbound email.

## Verification

- Backend changes: run `ruff`, `mypy`, and the relevant `pytest` tests.
- Frontend changes: after backend dependencies are synced with `uv`, run `npm run check` from `frontend/`; it generates the OpenAPI schema through the backend, then runs type checking, linting, Vitest, and build verification.
- Frontend component behavior or frontend logic changes: run `npm run test` from `frontend/`.
- Frontend browser smoke changes: run `npm run test:smoke` from `frontend/` after installing Chromium with `npx playwright install chromium` once per machine.
- Pre-commit config changes: run `uv run --project backend pre-commit run --all-files` from the repository root.
- Heuristic filter changes: run `uv run python -m evals.run_eval --filter` from `backend/`; regressions below 90 percent precision or 85 percent recall block merges unless explicitly accepted.
- Classification changes to prompts, models, categories, extraction schemas, or parser behavior: run `uv run python -m evals.run_eval` from `backend/`; regressions below 90 percent precision or 85 percent recall block merges unless explicitly accepted.
- Golden-set fixture changes: run `uv run pytest tests/test_golden_set_fixture.py -v` from `backend/`.
- Aggregation changes: verify idempotency and no duplicate applications.
- Status-derivation aggregation changes: verify incremental out-of-order evidence, manual-lock preservation, event-type-only derivation, and missing-`event_at` idempotency.
- Grouping-key-only aggregation changes: run the focused grouping-key tests plus the company and role normalization tests that feed the key.
- Insight prompt, evidence-scope, or cache-hash changes: run the focused insight input and generation service tests, and verify grounding plus citation behavior.
- Never claim work is complete without fresh verification evidence.

## Ticket-specific conventions

- [JT-063 2026-07-05 v2] Email providers must retain body content as normalized plain text: HTML MIME bodies are converted through the email HTML normalizer before storage, raw HTML fields are forbidden on retained body DTOs, and plain-text bodies that still look like raw HTML are rejected instead of silently retained.
