# Job-Search Intelligence - Groundwork & Architecture Spec

> **Status:** Draft for review · **Owner:** you (solo) · **Build style:** AI-agent-assisted ("vibe-coding")
> **This is the keystone document.** Every ticket, every scaffold file, and every coding agent reads from here.
> Nothing gets built until this is approved.

---

## 0. What this app is

A **local-first web app** that connects to your email (Gmail first), mines your entire job-search history, and answers 54 questions about it - from "how many jobs did I apply to" up to "why am I getting rejected and what should I fix" - through a **dashboard** and a **conversational RAG agent**.

**Core principle:** every question is a _read_ against one clean `applications` table. Get ingestion + classification right, and 40+ questions become nearly free. That's why Phases 0–2 are make-or-break.

---

## 1. Locked architecture decisions (ADR-lite)

| Area              | Decision                                                                                                            | Why                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Backend           | **FastAPI**, Python 3.12, async                                                                                     | Your stack; async fits I/O-bound email + LLM work                                                                |
| Frontend          | **React + TypeScript + Vite**                                                                                       | Your stack; fast dev loop                                                                                        |
| Database          | **SQLite** (single file)                                                                                            | Local-first, zero-ops, portable                                                                                  |
| Vector store      | **sqlite-vec**                                                                                                      | Embeddings live in the _same_ SQLite file → whole app is one file                                                |
| LLM               | **Pluggable provider** (Azure OpenAI / Ollama first, OpenAI / Anthropic later)                                      | Chosen in setup wizard; not locked to one vendor                                                                 |
| Deployment        | **Local-only** (localhost), coded hosting-ready                                                                     | Gmail Testing mode = no verification/CASA; remote/phone access is a later phase                                  |
| API style         | **REST**, resource-oriented, FastAPI auto-OpenAPI                                                                   | Simple, well-understood                                                                                          |
| Wire type-safety  | **Typed TS client generated from OpenAPI with Orval**                                                               | Frontend + backend contracts can't silently drift                                                                |
| Stage contracts   | **Pydantic v2** DTOs at every boundary                                                                              | One source of truth for shapes                                                                                   |
| Config/secrets    | **pydantic-settings** + `.env` + first-run wizard; keyring default with Fernet fallback; keys **encrypted at rest** | Safe defaults for eventual open-source                                                                           |
| Secret store seam | **`SecretStore` protocol** with default OS keyring adapter plus Pydantic `SecretRef` and `SecretStr` values         | OAuth tokens and LLM keys flow through one typed adapter boundary                                                |
| Migrations        | **Alembic** (batch mode; vec/virtual tables hand-written)                                                           | Schema will churn (aggregation, versioning, later phases); reversible revision graph supports idempotent re-runs |
| Background sync   | **APScheduler** in-process while backend is running                                                                 | "sync on open" / "sync now" without extra infra                                                                  |
| Python tooling    | **uv** + **ruff** + **mypy** + **pre-commit**                                                                       | Modern, fast, low-friction                                                                                       |
| RAG agent         | **LangGraph** hybrid (router → structured-query tool + semantic retrieval)                                          | Correct _counts_ and semantic recall                                                                             |
| Ticketing         | **GitHub Issues** via reviewed manifest and `gh` CLI                                                                | Free, trackable, agent-readable via `gh`, ties into future OSS repo                                              |
| Testing           | **Minimal smoke tests** + **golden-set filter and classification evals** + tiny Playwright smoke suite              | Speed, but don't trust unverified filtering, classification, or critical UI paths                                |

### Design-pattern set

- **Repository** - all DB access behind repository classes (no raw SQL scattered in services).
- **Strategy** - `EmailProvider` and `LLMProvider` protocols with swappable adapters.
- **Pipeline** - `ingest -> filter -> classify -> aggregate`, each stage a pure-ish function taking/returning Pydantic DTOs.
- **Service layer** - business logic in services; API routes stay thin.
- **Dependency Injection** - FastAPI `Depends` for repos, providers, config.
- **SecretStore adapter** - OAuth tokens and LLM API keys pass through a typed `SecretStore` protocol; the default adapter stores them in the host OS keyring and the configured Fernet fallback stores encrypted file-backed secrets.
- **DTOs** - Pydantic models cross every boundary (never pass raw dicts).
- **Typed errors** - explicit error types, no bare exceptions leaking to the API; API errors use a standard `{"error": {"code": "...", "message": "...", "details": []}}` response body.

---

## 2. Repository layout (monorepo)

```text
job-search-intelligence/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory, router registration
│   │   ├── config.py               # pydantic-settings, provider selection, env overrides
│   │   ├── db/
│   │   │   ├── engine.py           # SQLite engine, sqlite-vec loading, and connection PRAGMAs
│   │   │   ├── migrations/         # Alembic revisions (batch mode; vec tables hand-written)
│   │   │   └── repositories/       # EmailRepo, SyncStateRepo, ClassificationRunRepo, ApplicationRepo, EventRepo, InsightRepo, CorrectionRepo, ChatRepo
│   │   ├── models/                 # Focused Pydantic DTO modules plus stable aggregate exports
│   │   ├── providers/
│   │   │   ├── email/              # EmailProvider protocol + Gmail OAuth start/callback/metadata lister + retained-body text normalization + future outlook.py/imap.py
│   │   │   └── llm/                # LLMProvider protocol + generation/health DTOs + future azure_openai.py/ollama.py (+ future openai/anthropic)
│   │   ├── security/               # SecretStore protocol, secret refs, security adapters
│   │   ├── pipeline/
│   │   │   ├── filter.py           # heuristic pre-filter (ATS senders, keywords, labels, thread context)
│   │   │   ├── classify.py         # LLM classify + structured extract validation
│   │   │   └── aggregate.py        # emails → applications + event timeline (dedup)
│   │   ├── services/               # sync_service, metrics_service, insights_service, chat_service
│   │   ├── scripts/                # generate_openapi.py
│   │   ├── agent/                  # LangGraph graph, tools (structured_query, semantic_search)
│   │   ├── api/                    # routers, typed API errors, setup, auth, sync, applications, metrics, insights, chat
│   │   └── setup/                  # first-run wizard logic
│   ├── evals/
│   │   ├── golden_set.jsonl        # ~30 private-data-free labeled email cases
│   │   └── run_eval.py             # filter and classification accuracy reports
│   ├── tests/                      # minimal pytest (pipeline + metrics smoke)
│   │   └── fixtures/synthetic/      # private-data-free synthetic fixture JSON
│   ├── pyproject.toml              # uv, ruff, mypy config
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/                    # Orval-generated TS client (from OpenAPI)
│   │   ├── pages/                  # Dashboard, Insights, Chat, Setup, Feature Status
│   │   ├── featureStatus/          # Registry-backed developer inventory for implemented surfaces and QA entry points
│   │   ├── components/             # shared UI primitives, charts, filters, cards, chat UI
│   │   └── lib/
│   ├── package.json
│   └── vite.config.ts
├── tickets/
│   ├── manifest.yaml               # source of truth for all issues
│   └── issue_template.md
├── scripts/
│   └── create_github_issues.py     # gh CLI: labels + milestones + issues from manifest
├── docs/
│   ├── groundwork-spec.md          # this file
│   ├── questions.md                # the 54 questions, tiered
│   ├── backlog-decisions.md        # approved backlog and product decisions
│   ├── github-backlog-plan.md      # approved issue list before manifest generation
│   ├── google-oauth-setup.md       # user-created Google OAuth client setup guide
│   ├── conventions.md              # coding standards for agents
│   ├── llm-provider-setup.md       # Azure OpenAI and Ollama setup values and secret boundaries
│   └── synthetic-fixtures.md       # private-data-free fixture format and SQLite loader
├── .pre-commit-config.yaml
├── .github/workflows/backend-ci.yml # backend ruff + mypy + pytest
├── .github/workflows/frontend-ci.yml # frontend OpenAPI generation + typecheck + lint + test + build smoke check
└── README.md
```

[JT-069 2026-07-05 v2] `backend/app/db/repositories/` now includes `SyncStateRepository` for provider-owned sync anchors.
[JT-066 2026-07-05 v2] `backend/app/db/repositories/` now includes `BackfillStateRepository` for durable full-backfill page progress.
[JT-096 2026-07-05] `backend/app/db/repositories/` now includes `ClassificationRunRepository` for completed-run token and estimated-cost accounting.
[JT-094 2026-07-05] `backend/app/services/structured_extraction.py` now owns the Phase 2 structured extraction batch flow from retained candidates through LLM calls, accepted classification storage, public-safe malformed results, and classification-run accounting.

---

## 3. Data model (the crux)

### Tables

- **`raw_emails`** - `id` (provider msg id), `thread_id`, `from_addr`, `to_addr`, `subject`, `sent_at`, `body_text`, `body_retention_state`, `labels`, `provider`, `ingested_at`.
  `body_retention_state` is `metadata_only`, `retained`, or `debugging`; metadata-only rows must not carry `body_text`, while retained and debugging rows must carry it.
  Raw email writes are idempotent by provider message ID, and metadata-only reconciliation replays must not downgrade previously retained or debugging body text.
  Retained or debugging body writes may create a minimal row first when the body is fetched before metadata, and the later metadata-only replay fills in the metadata without dropping the body.
- **`email_sync_state`** - `provider`, `account_id`, `sync_cursor`, `cursor_issued_at`, `updated_at`; stores opaque provider-owned incremental sync anchors scoped to one connected account.
  [JT-066 2026-07-05 v2] **`email_backfill_state`** stores `provider`, `account_id`, `status`, `next_page_token`, page and message counters, replacement sync cursor fields, timestamps, and public-safe failure text for one connected account.
  [JT-066 2026-07-05 v2] `status` is `running`, `completed`, or `failed`; completed backfills clear `next_page_token`, require a replacement provider cursor with issued timestamp, promote that cursor to `email_sync_state`, and failures preserve page progress with `last_error` only when public-safe.
- **`email_sync_state`** - `provider`, `account_id`, `sync_cursor`, `cursor_issued_at`, `in_progress_mode`, `next_page_token`, `updated_at`; stores opaque provider-owned incremental sync anchors plus resumable page progress scoped to one connected account.
- **`email_connections`** - `provider`, `account_id`, `display_email`, credential `SecretRef` fields, granted scopes, `connected_at`, optional `credential_expires_at`, `reauth_required`, `updated_at`; stores only non-secret connection metadata for one Gmail account while token payloads live in the configured `SecretStore`.
- **`email_filter_decisions`** - `email_id` (FK), `strategy` (`broad_job_search`), `outcome` (`candidate | rejected`), `reason`, `decided_at`; stores one idempotent heuristic filter audit decision per raw email and strategy.
  Reasons are public-safe static signal tokens such as `sender_domain:greenhouse.io`, `subject_keyword:interview`, `excluded_label:spam`, `thread_signal:candidate_thread`, or `no_filter_signal`, not raw subjects, thread IDs, or body text.
- **`email_classifications`** - `email_id` (FK), `is_job_related`, `category` (`application_confirmation | rejection | interview_invite | recruiter_outreach | offer | assessment | follow_up | other`), `confidence`, `model`, `prompt_version`, `classified_at`.
- **`email_classifications`** - `email_id` (FK), `is_job_related`, `category` (`application_confirmation | rejection | interview_invite | recruiter_outreach | offer | assessment | follow_up | other`), `confidence`, `model`, `prompt_version`, timezone-aware `classified_at`.
- **`classification_runs`** - `id`, `provider`, `model`, `prompt_version`, `started_at`, `completed_at`, `candidate_count`, `classified_count`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost_usd`; stores one local accounting row per completed classification run.
  Counts, token totals, and estimated cost are non-negative; `classified_count` cannot exceed `candidate_count`, and `total_tokens` must cover prompt plus completion tokens.
- **`applications`** - `id`, `company`, `role_title`, `source` (`linkedin | company_site | indeed | referral | other`), `first_seen_at`, `current_status` (`applied | in_review | assessment | interview | offer | rejected | ghosted | withdrawn`), `salary_min`, `salary_max`, `currency`, `location`, `work_mode` (`remote | hybrid | onsite`), `seniority`, `sponsorship` (`offered | not_offered | unknown`), `tech_stack` (JSON list), `last_activity_at`, `manual_lock`, `created_at`, `updated_at`.
- **`application_events`** - `id`, `application_id` (FK), `email_id` (FK), `event_type` (`applied | response | assessment | interview_scheduled | feedback | rejection | offer | ghost_inferred`), `event_at`, `extract_note`.
  [JT-020 2026-07-05 v2] - **`application_events`** - `id`, `application_id` (FK), nullable `email_id` (FK; null for inferred events such as `ghost_inferred`), `event_type` (`applied | response | assessment | interview_scheduled | feedback | rejection | offer | ghost_inferred`), `event_at`, `extract_note`.
  [JT-107 2026-07-06] - **`application_events`** also stores nullable `extracted_status` using the same status enum as `applications.current_status` so status replay can preserve extraction-provided status on status-neutral event types.
- **`application_corrections`** - `id`, `application_id` (FK to `applications.id` with cascade delete), `correction_type` (`merge | split | status_edit | event_edit | reset_lock`), valid JSON `before_json`, valid JSON `after_json`, `reason`, `created_at`.
- **`insights`** - `id`, `type` (`why_rejected | recurring_feedback | skill_gaps | strongest_weakest_signals | role_fit | weekly_actions | story`), `content`, `inputs_hash`, `is_stale`, `model`, `generated_at`.
  [JT-195 2026-07-07] Insight cache `inputs_hash` includes the insight generation prompt version so prompt changes invalidate stale cached narratives without source-data changes.
- **`email_chunks`** (sqlite-vec) - `email_id`, `chunk_index`, `content`, `embedding`.
  [JT-020 2026-07-05 v2] - **`email_chunks`** (sqlite-vec) - `email_id`, `chunk_index`, `content`, 1536-dimensional `embedding`.
- **`chat_messages`** - `id`, `conversation_id`, `role`, `content`, `citations_json`, `tool_outputs_json`, `created_at`.

[JT-020 2026-07-05 v1] The initial core schema migration enforces enum, confidence, salary-range, and raw-email retention invariants with SQLite `CHECK` constraints, uses foreign keys for email/application relationships, and adds practical lookup indexes for the regular tables.
[JT-021 2026-07-05] The manual override schema migration creates `application_corrections` with constrained correction types, valid JSON before/after snapshots, application delete cascade, and an `(application_id, created_at)` lookup index for per-application audit history.
[JT-022 2026-07-05] The chat history schema migration creates `chat_messages`; `role` is constrained to `user | assistant | tool | system`, `citations_json` and `tool_outputs_json` must be valid JSON arrays, and `(conversation_id, created_at)` is indexed for history reads.
[JT-096 2026-07-05] The classification run accounting migration creates `classification_runs` with lookup indexes on `started_at` and `(provider, model)` so later classifier services can persist per-run token usage and estimated cost through `ClassificationRunRepository`.
[JT-084 2026-07-05] The filter decision schema migration creates `email_filter_decisions` with constrained strategy and outcome values, `raw_emails` cascade deletion, and lookup indexes for outcome and strategy.
[JT-192 2026-07-07] The insight type constraint now includes `strongest_weakest_signals` for Q-43 and preserves the shared insight staleness triggers across migration upgrade and downgrade.
[JT-190 2026-07-07] The recurring-feedback insight migration adds `recurring_feedback` to the constrained `insights.type` values for Q-41 while preserving insight staleness triggers across application, event, and source-email changes.

### Aggregation rule (the hard part)

An **application** is reconstructed from _many_ emails: a confirmation + later a rejection = **one** application whose `current_status` = `rejected`, with two `application_events`.
`ApplicationGroupingKey` is `(normalized_company, normalized_role, thread_id, time_window_start, time_window_days)`.
It always uses normalized company and role values, trims opaque provider thread IDs without case-folding them, prefers a present thread signal over date bucketing, and falls back to a UTC date-window bucket when the thread signal is missing.
When extraction omits `event_at`, aggregation uses raw email `sent_at` before the classification timestamp for event identity, event timeline ordering, and no-thread grouping-key date windows.
The default grouping window is 30 days.
`current_status` is derived by replaying already-persisted `application_events` plus the current aggregation batch in event-time order.
Status-bearing event types map to application statuses: `applied -> applied`, `response -> in_review`, `assessment -> assessment`, `interview_scheduled -> interview`, `rejection -> rejected`, `offer -> offer`, and `ghost_inferred -> ghosted`.
`feedback` keeps the prior status unless the event carries `extracted_status`.
`ghosted` is **inferred** when an application has an `applied` event but no response after your personal ghost-threshold (default 30 days, tunable).
Aggregation must be **idempotent** - re-runs never duplicate.
Manual corrections are audited, lock affected grouping/status from automatic overwrite by default, and surface conflicts when new evidence disagrees.
Manual event edits also protect the edited event identity and source email, so aggregation reruns must return a manual conflict instead of creating a competing timeline row for the same edited source evidence.

---

## 4. Pipeline

```text
EmailProvider -> metadata-only raw_emails
                 │
                 ├─ full backfill: paginated metadata pages, no body snippets
                 ├─ incremental sync: persisted provider-owned cursor required
                 ├─ expired cursor: restart resumable full metadata reconciliation
                 ├─ candidate query applied after listing
                 ├─ filter decision audit rows persisted for every evaluated metadata record
                 └─ retained bodies fetched only for selected candidate or debugging/reconciliation refs
                    and normalized to plain text before storage
                 │
                 ▼
   1. filter.py  heuristic pre-filter        (40k metadata rows -> retained candidates)
     - provider-neutral `EmailCandidateQuery` static signals and score threshold for broad job-search selection
     - known ATS/recruiter sender domains (greenhouse, lever, workday,
       ashby, icims, workable, smartrecruiters, myworkday, ...)
     - keyword signals across subjects and already-normalized retained body text
       when available ("application", "unfortunately", "interview",
       "next steps", "offer", "assessment", "regret to inform")
     - excluded labels are hard rejections, and same-page thread siblings can
       be promoted through the public-safe `thread_signal:candidate_thread`
       token without exposing raw provider thread IDs
                 │  candidates only
                 ▼
   2. classify.py  LLM classify + structured extract  (LLMProvider)
      - one provider-neutral JSON-object request per retained candidate -> Pydantic model
      - prompt version embedded in the system prompt for reproducible re-runs
      - retained `EmailClassificationCandidate` inputs and provider-neutral
        `EmailClassificationResult`/`EmailClassificationRecord` outputs reject unknown fields, keep retained
        body text out of repr output, and require timezone-aware timestamps
      - fields: company, role, status, dates, salary, location,
        work_mode, seniority, sponsorship, tech_stack, rejection_reason
      - malformed JSON, duplicate JSON keys, incomplete generations, extra fields,
        invalid enums, contradictory category/status pairs, inverted salary ranges,
        and extracted non-job data return public-safe quarantine results before storage
      - store model + prompt_version per row (reproducible re-runs)
      - `ClassificationService` builds one configured prompt per retained candidate,
        calls the configured `LLMProvider`, validates full provider generations,
        returns accepted and malformed DTOs, and aggregates token usage without
        writing classification, application, or event rows
      - `StructuredExtractionService` stores only accepted `email_classifications`
        rows, returns typed extraction facts for later aggregation, and records one
        `classification_runs` accounting row per attempted batch
                 │
                 ▼
    3. aggregate.py  emails -> applications + application_events (dedup)
       - `build_application_grouping_key()` returns a frozen `ApplicationGroupingKey`
         from normalized company, normalized role, trimmed opaque provider thread ID,
         and a UTC date-window fallback when no thread signal is available
       - `AggregationService` derives `applications.current_status` by replaying
         persisted plus current events in event-time order, using `raw_emails.sent_at`
         as the timestamp fallback when extraction omits `event_at`
                 │
                 ▼
         applications  (single source of truth)
            │            │             │
   deterministic     cached LLM     vector index
     metrics         insights       (sqlite-vec)
     (dashboard)     (insights)      (chat agent)
```

`EmailProvider` adapters own provider-specific auth, metadata normalization, pagination, opaque sync cursors, and retained-body fetching.
Gmail metadata normalization trims opaque message IDs, thread IDs, and history cursors without changing case, lowercases and deduplicates parsed email addresses, trims display names and selected headers, canonicalizes Gmail system labels while preserving custom label casing, and converts parsed message timestamps to timezone-aware UTC before DTOs cross the provider boundary.
The Gmail adapter lists full-backfill metadata through Gmail messages pages, anchors the eventual incremental cursor from the Gmail profile history ID, lists incremental metadata through `users.history.list` `messageAdded` records, and maps Gmail history `404` responses to expired-cursor recovery.
`SyncStateRepository` persists only the opaque cursor value and timestamps, keyed by provider and account, so incremental sync can resume without storing token material or email content in sync state.
`SyncService` exposes the persisted sync-state cursor snapshot for service-level status checks; public `POST /sync` and `GET /sync/status` route behavior is wired through the backend sync API and consumed by the overview page's manual sync action.
The sync service coordinates one metadata page at a time, carries provider page tokens forward, and turns expired incremental cursors into resumable full metadata reconciliation so callers can persist the next page token and replacement sync cursor.
[JT-066 2026-07-05 v2] Full-backfill page recording and final replacement-cursor promotion must share one local SQLite connection so a completed page and its promoted `email_sync_state` cursor commit atomically.
[JT-066 2026-07-05 v2] Full-backfill orchestration is two-step: `run_backfill_page` lists the next provider page from the stored resume token without advancing durable progress, then the caller persists raw emails and records the page with the expected token.
[JT-066 2026-07-05 v2] Recording the page advances counters, stores the next page token, and completes the run only when the final page carries a replacement provider cursor.
`SyncStateRepository` persists only opaque cursor values, page tokens, sync mode, and timestamps, keyed by provider and account, so incremental sync and failed page runs can resume without storing token material or email content in sync state.
The sync service coordinates one metadata page at a time, carries provider page tokens forward, persists in-progress page state between pages, and turns expired incremental cursors into resumable full metadata reconciliation so callers can persist the next page token and replacement sync cursor.
`SyncScheduler` owns the APScheduler lifecycle inside the FastAPI lifespan: when `sync_on_open` is true, it registers an immediate interval job for the injected async sync runner, and on shutdown it stops APScheduler without waiting.
The configured sync runtime resolves the latest non-reauth Gmail connection metadata from SQLite, runs full backfill until durable backfill state is completed and the replacement cursor is promoted, and then uses incremental sync on later manual runs.
Candidate selection is represented by provider-neutral DTOs and applied to normalized metadata outside provider listing, so adapters do not receive brittle Gmail-specific search filters.
Candidate decisions carry a deterministic score plus public-safe signal tokens; sender-domain, subject-keyword, and same-thread signals contribute to the threshold, while excluded labels reject regardless of positive signals.
The same static keyword terms may be applied to already-normalized retained body text when a caller has it, but broad provider metadata listing and body-retention selection remain metadata-only.
The sync runtime evaluates metadata pages as batches so same-page thread siblings use the same decision path for retained-body selection and persisted audit rows.
It persists the broad job-search filter outcome and public-safe reason for every evaluated normalized metadata record in `email_filter_decisions`, keyed by raw email ID and strategy so re-runs update the same audit row.
The provider seam keeps OAuth token material behind `SecretRef`, treats OAuth callback codes as `SecretStr`, excludes body-derived snippets from broad metadata backfill, converts HTML MIME bodies to normalized retained plain text, rejects retained-body DTOs with raw HTML fields, and ignores attachment content in v1.
The classification service validates provider-neutral `LLMGenerationResponse` content before storage: accepted results produce an `EmailClassificationRecord` and typed extraction fields, while malformed results include only public-safe quarantine metadata and must not write `email_classifications`, `applications`, or `application_events` rows.
Phase 1 reconciliation compares provider metadata pages against local `raw_emails` for the same provider using deterministic service-layer metrics: page count, total provider messages, unique provider messages, duplicate provider messages, local raw-email count, local-vs-provider delta, missing local messages, extra local messages, and a `reconciled` flag.
Classification prompt requests are built by `app.pipeline.classify.build_classification_prompt_request`, require retained email body text, request `LLMResponseFormat.JSON_OBJECT`, use temperature `0`, and embed `CLASSIFICATION_PROMPT_VERSION` in the system prompt.
Provider responses must pass `app.pipeline.classify.parse_classification_generation_response` before any downstream classification storage or aggregation.
`StructuredExtractionService` lists non-empty retained candidates stale for the configured model or prompt version, calls the configured `LLMProvider`, stores only accepted classification records through `EmailRepository`, writes completed-run accounting through `ClassificationRunRepository`, and returns accepted extraction facts plus public-safe malformed results without writing applications or events.
`InsightInputBuilder` builds cached narrative insight inputs from deterministic application/event facts plus cited source evidence, keeps debugging retained bodies out of LLM payloads, and hashes the insight prompt version with the source fingerprint so prompt changes invalidate the cache.
For the Q-46 `story` insight, evidence is narrowed to the recent 366-day window anchored to the newest event or email timestamp, then kept chronological so the LLM receives a grounded recent search arc.
The story prompt names Q-46 directly and asks for phases, turning points, repeated patterns, and changes over time with citation IDs for each narrative beat.
`InsightGenerationService` builds deterministic facts and cited evidence from local SQLite, calls the configured `LLMProvider` only when regeneration is needed or forced, rejects incomplete, blank, or uncited provider output before caching, and writes accepted narrative insights through `InsightRepository`.

**Split metrics from narrative:** dashboard numbers are **deterministic SQL/pandas** (accurate, free, instant). "Why / what to improve / role fit" is **LLM, cached, regenerate-on-demand**. Never let the LLM produce the counts.

**Cost control:** `classification_mode` config - `hybrid` (filter -> LLM), `llm` (LLM on everything), `local` (Ollama, offline/free).
Setup asks explicitly and recommends `hybrid` for Azure OpenAI, or `local` for Ollama, when the user has not explicitly selected a provider-valid mode.
Show a **pre-run cost estimate** and track tokens per run.

---

## 5. API surface (REST)

- **Health:** `GET /health` returns a liveness-only `{ "status": "ok" }` response for Phase 0 smoke checks.
- **Setup/auth:** `GET /setup/status` reports the Phase 0 first-run setup shell plus current and recommended classification modes without exposing secrets; `POST /setup` accepts non-secret first-run choices, applies the provider-based classification recommendation when `classification_mode` is omitted, validates selected provider metadata, and returns an accepted setup status without running provider auth flows or persisting secrets; `GET /config/providers` returns selected provider choices, recommended classification mode, visible non-secret provider settings, supported provider metadata, and secret-reference requirements without secret values; `PUT /config/providers` validates and applies partial non-secret provider config updates to the running backend process only, applying the provider-based classification recommendation only when `llm_provider` changes and `classification_mode` is omitted; `GET /auth/gmail` starts Gmail OAuth by returning a provider-built Google authorization URL, generated state value, and the read-only Gmail scope without returning client secrets or tokens; `GET /auth/gmail/callback` consumes the issued state, passes the authorization code as `SecretStr`, exchanges it through the Gmail provider, validates the returned read-only scope, stores token material through the configured `SecretStore`, persists only non-secret `email_connections` metadata, and returns an `EmailConnection` DTO without raw tokens.
  Gmail full and incremental metadata listing exists behind `SecretStore`; retained-body fetching exists behind the provider seam for caller-selected refs, expired stored Gmail credentials are refreshed before metadata or retained-body reads, default sync resolves the latest non-reauth Gmail connection metadata from SQLite, and manual sync stores retained bodies for broad candidate messages, including same-page thread-promoted candidates, after metadata persistence; the overview page can trigger and display manual sync state through backend APIs while deeper product pages remain later Phase 1 work.
- **Local data:** `POST /local-data/wipe` removes configured local app data and derived artifacts after the exact confirmation phrase `wipe-local-data`; unsafe configured filesystem targets return the standard typed `400` API error.
- **Sync:** `POST /sync` resolves the latest non-reauth Gmail connection metadata, runs full backfill until durable backfill state is completed and the replacement cursor is promoted, stores metadata-only `raw_emails` without overwriting retained bodies, persists `email_filter_decisions` audit rows for broad job-search filter outcomes using the same batch decision path as retained-body selection, stores retained bodies for broad job-search candidates when the provider supports body fetching, persists provider cursors and resumable page progress, returns a typed not-configured `400` when no Gmail connection is configured, returns typed `409` for concurrent manual runs, and maps email-provider failures to typed `401`, `403`, `409`, `429`, `502`, or `503` responses with email-specific error codes and a `user_action` detail; `GET /sync/status` reports current or last-run state, provider, account, mode, timestamps, page count, message count, raw-email count, expired-cursor recovery, and public error text.
  Raw-email retained and debugging body persistence is insert-or-update, so explicit body fetches are not dropped if they arrive before metadata.
- **Classification:** `GET /classification/estimate` returns retained candidate counts, estimated prompt and completion tokens, total estimated tokens, model and prompt version, token-estimate method, and cost availability before a bulk classification pass without calling an LLM or returning email content; `GET /classification/reprocessing-plan` returns read-only retained-candidate buckets for up-to-date, unclassified, stale-model, stale-prompt-version, and missing-target-model rows so prompt/model reruns are deterministic before a runner executes them; `POST /classification/run` executes one structured extraction batch for retained candidates through the configured provider, stores accepted classifications and run accounting, and returns accepted plus malformed counts without writing application or event rows.
- **Applications:** `GET /applications` (filters: status, source, sponsorship, date range, role, salary band, work_mode), `GET /applications/{id}`, `GET /applications/{id}/events`, correction endpoints for merge, split, status edit, and event edit.
  [JT-116 2026-07-06] The backend now implements the read-only detail slice, `GET /applications/{id}`, returning one `ApplicationRecord` from local SQLite and a typed `404` error when no application row matches.
  [JT-117 2026-07-06] The backend now implements the read-only event timeline slice, `GET /applications/{id}/events`, returning ordered `ApplicationEventRecord` rows from local SQLite, an empty list for applications without events, and a typed `404` error when no parent application row matches.
  [JT-113 2026-07-06] The backend now implements `PATCH /applications/{application_id}/status` and `PATCH /applications/{application_id}/events/{event_id}` for audited manual status and timeline-event corrections; event edits require at least one changed event field, validate source emails, replay application status from the edited timeline, and protect edited event/source-email evidence from conflicting aggregation reruns; list, split, and reset-lock routes remain later slices.
  [JT-112 2026-07-06] The backend now implements the manual split slice, `POST /applications/{application_id}/split`, moving selected events into a deterministic new manually locked application, locking the source application, recalculating source and target timeline dates, deriving target status from moved events, preserving an already locked source status, preserving corrected segmentation fields for deterministic dashboard breakdowns, writing one audited `split` correction row, and returning typed `404` or `409` errors for missing source applications and split conflicts.
  [2026-07-06] The backend now implements the manual merge slice, `POST /applications/{application_id}/merge`, moving source events into the target application, recalculating the merged summary, deleting the source application, writing one audited `merge` correction row, and returning typed errors for missing applications, self-merge requests, and duplicate evidence conflicts.
- **Metrics (deterministic):** `GET /metrics/summary`, `/metrics/rates`, `/metrics/funnel`, `/metrics/timeseries`, `/metrics/breakdown?dimension=role|source|salary|tech|sponsorship|seniority|work_mode`, `/metrics/diagnostics`
  [JT-127 2026-07-07] The backend now implements `GET /metrics/timeseries`, returning a typed `MetricsTimeseriesResponse` of daily application-volume points derived deterministically from `applications.first_seen_at` through `MetricsRepository` without any LLM path.
- **Insights (cached LLM):** `GET /insights` returns latest cached `InsightRecord` rows from local SQLite, including stale records so clients can show regeneration state; `POST /insights/regenerate` accepts `InsightRegenerateRequest` with an insight `type` and optional `max_evidence_items` defaulting to `100`, forces regeneration through deterministic cited inputs and the configured LLM provider, stores the accepted row in the insights cache, returns the saved insight plus evidence citation IDs, and maps validation or provider failures to typed public-safe API errors.
  [JT-190 2026-07-07] `recurring_feedback` answers Q-41 from `feedback` timeline events only; if fewer than two cited feedback items exist, the service saves an insufficient-evidence explanation instead of asking the LLM to infer a recurring theme.
- **Chat (agent):** `POST /chat` (SSE streaming), `GET /chat/history`

OpenAPI schema -> `backend/scripts/generate_openapi.py` -> `frontend/src/api/openapi.json` -> Orval fetch client in `frontend/src/api/generated.ts`.
Frontend application code imports through the stable `frontend/src/api` boundary instead of reaching into generated files directly.
`frontend/package.json` runs API generation and staleness checks before the frontend typecheck, lint, Vitest, and build gate so backend and frontend contracts cannot silently drift.

Standard error responses use a typed Pydantic shape: `{"error": {"code": "...", "message": "...", "details": []}}`.
Routes and services raise explicit `ApiError` values for public API-boundary failures.
Email-provider boundary errors map to stable email-specific API error codes such as `email_authorization_required`, `email_insufficient_scope`, `email_rate_limited`, `email_temporarily_unavailable`, `email_invalid_provider_response`, `email_provider_request_failed`, and `email_sync_cursor_expired`.
Those responses include a `details` item with `type: "user_action"`, `field: "email_provider"`, and an action value such as `reconnect_email`, `restart_full_sync`, `try_again_later`, or `check_configuration`.
LLM-provider boundary errors map to stable public API error codes such as `llm_provider_unavailable`, `llm_provider_request_failed`, `llm_provider_invalid_response`, and `llm_provider_timeout`, with public-safe messages only.
Request validation errors, Starlette HTTP errors, and unhandled exceptions are mapped by the FastAPI app factory and must not expose raw request input, tracebacks, secrets, or arbitrary exception details.

---

## 6. RAG agent (LangGraph)

```text
question -> router -> quantitative -> structured_query tool -> synthesize -> answer (+ citations)
question -> router -> content -> semantic_search tool -> synthesize -> answer (+ citations)
question -> router -> mixed -> both tools -> synthesize -> answer (+ citations)
```

- **`structured_query`** - answers counts/rates/breakdowns. **Security: the LLM never emits raw SQL.** It fills parameters on a **constrained query builder / whitelisted templates** over `applications`/`metrics`. Guarantees dashboard-consistent numbers.
- **`semantic_search`** - sqlite-vec retrieval over `email_chunks` for "what did the recruiter say" style questions; returns citations to real emails/applications.
- **synthesize** - composes the final answer, always grounded in tool output (no free-floating claims).

This is why counts are right (vectors can't count) _and_ content recall works.

---

## 7. The 54 questions -> phases (acceptance criteria)

Full list in `docs/questions.md`. Mapping:

| Tier                       | Questions | Capability                                 | Phase               |
| -------------------------- | --------- | ------------------------------------------ | ------------------- |
| 1 - Foundational counts    | 1-10      | `COUNT` on classified emails               | **3** Dashboard     |
| 2 - Rates, funnels, time   | 11-21     | ratios + date math                         | **3** Dashboard     |
| 3 - Segmentation           | 22-31     | `GROUP BY`                                 | **3** Dashboard     |
| 4 - Diagnostic/comparative | 32-39     | deterministic/light-statistics diagnostics | **3.5** Diagnostics |
| 5 - Narrative "why"        | 40-46     | LLM synthesis, cached                      | **4** Insights      |
| 6 - Conversational recall  | 47-50     | hybrid RAG                                 | **5** Chat          |
| 7 - Predictive/external    | 51-54     | external data / APIs                       | **Future**          |

**Each question becomes a ticket** whose acceptance criterion is: _"the app answers this question on screen (or in chat), and the answer reconciles with the underlying data."_

---

## 8. Phase roadmap (with Definition of Done)

**Phase 0 - Groundwork / scaffold**
Monorepo, uv/ruff/mypy/pre-commit, FastAPI skeleton + health route, React+Vite skeleton, frontend generated-client destination and import boundary, Recharts chart wrapper foundation with empty states, empty dashboard route shell without metrics, registry-backed `/features` developer inventory for implemented surfaces and QA entry points, empty `/chat` route shell with chat behavior deferred to Phase 5, shared accessible frontend primitives, SQLite engine + sqlite-vec + migrations, config + setup-wizard shell, `EmailProvider`/`LLMProvider` protocol seams, `SecretStore` protocol plus default keyring adapter, OpenAPI generation via `backend/scripts/generate_openapi.py`, backend and frontend CI, `.env.example`, synthetic fixtures, and tiny Playwright smoke harness.
**DoD:** API boots via `uv run`, React dev server runs, `/health` green, pre-commit + CI pass.

**Phase 1 - Gmail ingestion**
Gmail OAuth desktop flow (Testing mode), broad metadata backfill for roughly 40k emails, normalized retained body text for candidate, debugging, or reconciliation messages, incremental sync via `historyId`, and `raw_emails` populated without raw HTML by default.
Phase 1 raw email population tracks `metadata_only`, `retained`, and `debugging` body retention states; debugging and reconciliation bodies are retained only when explicitly needed.
**DoD:** your inbox backfilled; incremental pulls only new messages; local `raw_emails` reconcile with Gmail provider metadata pages, including duplicate provider page entries and missing or extra local message IDs.

Historical retention note: before JT-065, Phase 1 wording described retained bodies for candidate messages without the explicit debugging retention state.

**Phase 2 - Classify + extract + aggregate** _(make-or-break)_
Heuristic scored filter, provider-neutral classification prompt contract, Azure OpenAI and Ollama adapters, deterministic reprocessing version plan, structured extraction (Pydantic), `applications` + `application_events` with dedup + ghost inference, manual correction/audit path, **golden-set eval**.
**DoD:** `applications` populated; golden-set filter and classification evals each reach ≥90% precision AND ≥85% recall on job-vs-not; re-runs idempotent.

**Phase 3 - Dashboard (deterministic)** -> Tiers 1-3 (+ 3.5 diagnostics -> Tier 4)
Metrics endpoints + React dashboard (Recharts + small accessible component layer) + URL-backed filters (incl. sponsorship).
**DoD:** every Tier 1–3 question is answered on screen; numbers reconcile with the DB.

**Phase 4 - Insights (cached LLM narrative)** -> Tier 5
Insights service + page (why-rejected, skill-gaps, strongest/weakest signals, role-fit, weekly actions, story); cached with prompt-versioned input hashes, `regenerate`, stale detection, and user-triggered regeneration.
The Q-40 `why_rejected` insight uses rejection-event evidence only and prompts for recurring themes across rejection emails; feedback-specific summaries belong to Q-41.
`weekly_actions` answers Q-45 as exactly three numbered, cited actions that are executable during the next week, and invalid provider output is rejected before caching.
The Q-46 story insight uses recent chronological evidence from the last 6 to 12 months of search history, anchored to the newest cited event or email timestamp.
**DoD:** insights render and cite the applications/emails they're drawn from.

**Phase 5 - RAG chat (LangGraph)** -> Tier 6
Hybrid router + tools, sqlite-vec embeddings for retained job-related bodies, chat history API/UI behavior backed by persisted storage, and streaming chat UI in the web app.
**DoD:** quantitative questions return numbers matching the dashboard; content questions cite real emails.

**Later phases:** more providers (Outlook/Graph, IMAP for Yahoo/iCloud) · draft-writing (review-then-send, never autonomous) · hosting + phone/voice access · auto-apply · benchmarking (Tier 7) · open-source hardening (ship-no-data, bring-your-own-credentials).

---

## 9. Testing (minimal + one carve-out)

- **Minimal:** no broad e2e suites, no coverage targets. A few pytest smoke tests on the pipeline and metrics math. Focused Vitest checks cover frontend behavior that protects accessibility or component contracts.
- **Tiny Playwright smoke suite:** starts with the Phase 0 shell for setup copy, overview sync affordance, and dashboard empty-state coverage; later critical paths add dashboard fixture load and chat citation smoke checks as those pages exist.
- **Carve-out - the golden set:** ~30 private-data-free labeled email cases in `backend/evals/golden_set.jsonl`; `uv run python -m evals.run_eval --filter` from `backend/` validates metadata-only heuristic filter retention against each row's `expected_to_pass_filter` label, and `uv run python -m evals.run_eval` validates records through the classification contract. Both reports include precision/recall and fail below 90 percent precision or 85 percent recall. Run the filter eval whenever heuristic filter signals change, and run the classification eval whenever the classify prompt, model, categories, extraction schema, or parser behavior changes. _This is the one thing that keeps the dashboard honest._

---

## 10. Ticketing plan (GitHub Issues)

- **Repository:** create a new private personal repository named `job-search-intelligence`.
- **Milestones:** Phase 0-5, `Phase 3.5 - Diagnostics`, and `Future`.
- **Labels:** `phase:*`, `type:*`, `tier:*`, `area:*`, `priority:*`, `size:*`, and `status:blocked`.
- **Issues:** one per atomic task plus one per question, labeled with its tier/phase.
- **Source of truth:** `tickets/manifest.yaml` plus generated issue-body files.
- **Creation path:** use the local `gh` CLI to create the repository, labels, milestones, and issues idempotently from the manifest.
- **Issue template:** every issue contains `Title`, `Mini-PRD / Context`, `Linked requirements`, `Scope - in`, `Scope - out`, `Technical approach`, `Acceptance criteria`, `Dependencies`, `Definition of Done`, and `Estimate`.
- **GitHub Projects:** skipped for this pass.

---

## 11. Coding standards for agents (`docs/conventions.md`)

Typed everywhere (mypy) · Pydantic at every boundary · Repository pattern for all DB access · **LLM never emits raw SQL** · small focused modules (a growing file signals it's doing too much) · providers behind interfaces · `SecretStore` for OAuth tokens and LLM keys · ruff-formatted · conventional commits · secrets never logged, encrypted at rest.

---

## 12. Open questions before scaffolding

**Resolved:** the golden-set eval is a hard, mandatory gate, not optional.
Eval regressions block merges unless the user explicitly accepts the tradeoff.
See `AGENTS.md`.

**Also resolved:** Phase 2 DoD gate is ≥90% precision AND ≥85% recall on job-vs-not (floor-then-ratchet).

**Also resolved:** migrations use **Alembic** with batch mode enabled for SQLite's limited `ALTER TABLE`.
sqlite-vec and other virtual/vector tables are managed by hand-written revisions, not autogenerate.

**Resolved:** approved backlog decisions are recorded in `docs/backlog-decisions.md`.
The approved ticket plan is recorded in `docs/github-backlog-plan.md`.

[JT-103 2026-07-05 v1] Services layout now includes `backend/app/services/normalization.py` for deterministic role-title grouping logic.
[JT-103 2026-07-05 v1] Aggregation `normalized_role` uses `normalize_role_title()` to fold casing, punctuation, seniority labels, title levels, role abbreviations, common location tokens, and work-arrangement notes while preserving meaningful descriptors such as `back end`, `front end`, `growth`, and `machine learning`.
[JT-104 2026-07-06] Aggregation grouping-key assembly now lives in `backend/app/pipeline/aggregate.py` as a frozen `ApplicationGroupingKey` built by `build_application_grouping_key()`.
[JT-104 2026-07-06] The key combines `normalize_company_name()`, `normalize_role_title()`, a trimmed opaque provider thread ID when present, and a 30-day UTC time-window fallback when the thread signal is missing, without adding database writes or API behavior.
[JT-107 2026-07-06] Aggregation now stores `application_events.extracted_status`, combines persisted and current events for status replay, and derives `applications.current_status` chronologically instead of from an unordered priority set.
