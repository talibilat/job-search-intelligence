# JobTracker Agent Instructions

These instructions are project-local and apply to every agent working in this repository.
They are intentionally stricter than generic coding preferences because this project is built from product specs first.

## Read First

Before brainstorming, planning, ticket writing, scaffolding, or implementation, read these files in order:

1. `docs/prd.md`
2. `docs/groundwork-spec.md`
3. `docs/questions.md`

Treat those documents as the source of truth.
If a ticket, prompt, or implementation idea conflicts with those docs, pause and call out the conflict instead of guessing.

## Product North Star

JobTracker is a local-first job-search intelligence app.
It connects to Gmail first, mines historical job-search email, reconstructs applications and events, and answers analytics questions through dashboards, cached insights, and a RAG chat agent.

The core product invariant is this:

All factual job-search answers come from one clean `applications` table and its event timeline.

Protect that invariant in every design and implementation decision.

## Non-Negotiable Constraints

- Keep the app local-first.
- Store app state in a single local SQLite database when feasible.
- Keep embeddings in SQLite through `sqlite-vec`.
- Do not introduce telemetry.
- Do not ship shared or bundled credentials.
- Do not log secrets, OAuth tokens, raw API keys, or private email content unnecessarily.
- Store secrets encrypted at rest.
- Do not build auto-apply behavior in v1.
- Do not build autonomous outbound email in v1.
- Keep outbound writing draft-only for later phases.
- Keep v1 single-user and local.
- Never let an LLM produce authoritative dashboard counts.
- Never let an LLM emit raw SQL for execution.
- Quantitative answers must reconcile with deterministic database queries.
- Content answers must cite real source emails or applications.

## Project Architecture Contract

Use the architecture in `docs/groundwork-spec.md` unless the user explicitly approves a change.

- Backend: FastAPI, Python 3.12, async.
- Frontend: React, TypeScript, Vite.
- Database: SQLite.
- Vector store: `sqlite-vec`.
- LLM providers: Azure OpenAI and Ollama first, with OpenAI and Anthropic later behind interfaces.
- API style: REST with generated OpenAPI client for TypeScript.
- Data contracts: Pydantic v2 DTOs at boundaries.
- Background sync: APScheduler in-process.
- RAG agent: LangGraph hybrid router.
- Python tooling: `uv`, `ruff`, `mypy`, `pre-commit`.
- Testing: minimal smoke tests plus golden-set classification eval plus a tiny Playwright smoke suite for critical user paths.

Use these design patterns:

- Repository pattern for database access.
- Strategy pattern for `EmailProvider` and `LLMProvider` adapters.
- Pipeline stages for `ingest -> filter -> classify -> aggregate`.
- Service layer for business logic.
- FastAPI dependency injection for repos, providers, and config.
- Typed errors at API boundaries.
- Pydantic DTOs instead of raw dictionaries across boundaries.

## Brainstorming Workflow

Use this workflow before creating features, modifying behavior, changing architecture, or generating implementation tickets.

1. Read the three source-of-truth docs listed above.
2. Restate the relevant product goal and phase.
3. Identify which functional requirements, non-functional requirements, and question IDs are affected.
4. Ask one clarifying question at a time when the requirement is ambiguous.
5. Offer two or three approaches when there is a meaningful design choice.
6. Recommend the simplest robust approach, not the cheapest short-term implementation.
7. Preserve the phase boundaries from the roadmap.
8. Explicitly call out any scope creep into later phases.
9. Do not proceed from brainstorming to implementation until the user approves the design or ticket scope.

Good brainstorming output should include:

- The target phase.
- Relevant FR/NFR IDs.
- Relevant question IDs from `docs/questions.md`.
- Data model impact.
- API impact.
- Frontend impact.
- Privacy and security impact.
- Verification plan.
- Open questions.

Avoid brainstorming that produces vague action items.
Every output should be concrete enough to become a ticket or implementation plan.

## Implementation Workflow

Use this workflow when writing code or scaffolding the repo.

1. Confirm the task maps to a PRD requirement, groundwork phase, or question ID.
2. Inspect the existing files before proposing changes.
3. Choose the smallest correct change that preserves the architecture contract.
4. Keep API routes thin.
5. Put business logic in services.
6. Put database access in repositories.
7. Put provider-specific behavior behind provider adapters.
8. Put pipeline logic in explicit pipeline modules.
9. Add or update DTOs at every boundary.
10. Add deterministic tests or evals for logic that affects metrics, classification, aggregation, or agent correctness.
11. Run the relevant verification commands before claiming completion.
12. Report exactly what changed and what verification passed.

Do not implement broad speculative abstractions.
Do not add compatibility code unless there is persisted data, external consumers, shipped behavior, or an explicit user request.

## Phase Discipline

Follow the roadmap from `docs/groundwork-spec.md`.

- Phase 0: scaffold, tooling, health route, config shell, provider stubs, database engine, CI.
- Phase 1: Gmail ingestion, full backfill, incremental sync, `raw_emails`.
- Phase 2: heuristic filter, LLM classification, extraction, aggregation, dedupe, ghost inference, golden-set eval.
- Phase 3: deterministic dashboard metrics and filters for Tiers 1-3.
- Phase 3.5: diagnostics for Tier 4.
- Phase 4: cached LLM insights for Tier 5.
- Phase 5: hybrid RAG chat for Tier 6.
- Later: more providers, draft writing, hosting, phone or voice access, auto-apply, external enrichment, open-source hardening.

If a task crosses phases, split it or ask for explicit approval.

## Data Model Rules

Preserve these core tables unless a documented migration changes them:

- `raw_emails`
- `email_classifications`
- `applications`
- `application_events`
- `insights`
- `email_chunks`

Approved migrations may add supporting tables for manual corrections, pipeline overrides, and persisted chat history.

Aggregation is the hard part.
One application can have many emails.
A confirmation followed by a rejection must become one application with multiple events, not duplicate applications.
Re-runs must be idempotent.
Ghosting is inferred from event history and a configurable threshold.
Manual corrections must be audited.
User-corrected grouping and status are locked from automatic overwrite by default.
When new email evidence conflicts with a user correction, surface the conflict instead of silently changing the corrected record.

When modifying aggregation, always consider:

- Normalized company matching.
- Normalized role matching.
- Thread and time-window grouping.
- Event ordering.
- Duplicate prevention.
- Prompt and model versioning.
- Reprocessing behavior.
- Manual correction locks and conflict handling.

## Metrics Rules

Dashboard metrics are deterministic.
Use SQL or typed Python logic for counts, rates, funnels, date math, and group-bys.
The same input database must produce the same metrics every time.

Never use the LLM for:

- Total counts.
- Rates.
- Funnel numbers.
- Time-to-response calculations.
- Group-by breakdowns.
- Dashboard truth.

The LLM may synthesize narrative insights only after deterministic facts and cited source data are prepared.

## RAG Agent Rules

The chat agent must use hybrid routing.

- Quantitative questions go through constrained structured-query tools.
- Content questions go through semantic retrieval over cited email chunks.
- Mixed questions use both.
- Synthesis must be grounded in tool output.
- Answers must cite real emails, applications, or deterministic metric outputs.

The LLM must never emit raw SQL for execution.
Use whitelisted templates or constrained query builders.

## Classification Rules

Classification is make-or-break for the whole product.

- Use heuristic pre-filtering before LLM calls in hybrid mode.
- Store model and prompt version on classification rows.
- Validate structured extraction with Pydantic.
- Catch malformed LLM output instead of silently storing it.
- Run the golden-set eval when classification prompts, models, categories, or extraction schemas change.
- Treat eval regressions as blockers unless the user explicitly accepts the tradeoff.

## Privacy and Security Rules

- Do not read `.env` unless the user explicitly asks or the task requires it.
- Do not print secrets or tokens.
- Do not commit secrets.
- Do not add telemetry.
- Do not send email content to an LLM except through the configured provider path.
- Preserve local mode through Ollama where possible.
- Keep OAuth scopes minimal.
- Use Gmail `gmail.readonly` for v1 ingestion.
- Assume the user creates their own Google Cloud OAuth client.
- Store metadata for all ingested Gmail messages, but retain body text only for broad job-search candidates or reconciliation/debugging.
- Do not retain raw HTML by default.
- Ignore Gmail attachments in v1.
- Embed only retained job-related email bodies.
- Keep personal data deletion in mind for any storage feature.
- Include local wipe-data behavior in v1 work that stores email-derived data.

## Frontend Rules

- Preserve a clear dashboard hierarchy.
- Make every number traceable to a deterministic endpoint.
- Filters must compose consistently across metrics.
- Dashboard filter state should live in route query strings.
- Prefer accessible components and readable charts.
- Use Recharts for charts and a small accessible component layer.
- Avoid generic dashboards that hide the important story.
- Show citations for narrative and chat answers.
- Do not let the UI imply precision that the underlying data does not support.

## Backend Rules

- Keep FastAPI route handlers thin.
- Keep service methods focused and testable.
- Keep repositories responsible for database access.
- Keep provider adapters swappable.
- Use Pydantic DTOs for request, response, extraction, and pipeline objects.
- Use typed exceptions and map them to clear API errors.
- Keep database writes idempotent for ingestion, classification, and aggregation.
- Make sync resumable.

## Ticket and Documentation Rules

Every ticket should map to at least one of these:

- A functional requirement from `docs/prd.md`.
- A non-functional requirement from `docs/prd.md`.
- A phase deliverable from `docs/groundwork-spec.md`.
- A question ID from `docs/questions.md`.

Ticket acceptance criteria should be concrete and verifiable.
If a ticket changes behavior, include the relevant FR/NFR/Q IDs in the ticket body.
If a ticket implements one of the questions, the acceptance criterion is that the app answers the question and the answer reconciles with the underlying data.
Backlog issue IDs use one global `JT-NNN` sequence.
Question tickets also include their `Q-XX` ID.
Use stable `JT-NNN` references for dependencies instead of relying on GitHub issue numbers.
The source of truth for issue creation is `tickets/manifest.yaml` plus generated issue-body files.
GitHub issue creation uses the local `gh` CLI after the manifest is reviewed.

## Testing and Verification Rules

Testing is intentionally minimal, but verification is not optional.

Required checks depend on the work:

- Backend Python changes: run ruff, mypy, and relevant pytest tests once scaffolded.
- Frontend changes: run TypeScript checks, lint, and relevant tests once scaffolded.
- Critical frontend flows: run the tiny Playwright smoke suite once scaffolded.
- API contract changes: regenerate or validate the TypeScript client.
- Metric changes: verify against sample data or fixtures.
- Classification changes: run the golden-set eval.
- Aggregation changes: verify idempotency and no duplicate applications.
- Chat or insight changes: verify grounding and citations.
- Config changes: verify the tool can load the config.

Never claim that work is complete without fresh verification evidence.

## Communication Rules

- Be direct and factual.
- Keep progress updates brief.
- Lead final summaries with what changed and how it was verified.
- Call out blockers clearly.
- Do not hide uncertainty.
- Do not claim tests passed unless they were run and passed.
- Do not use the em dash character.

## Current Repository State

At the time this file was written, the repository contains planning docs but not the full scaffold.
Do not assume backend, frontend, tickets, scripts, or CI exist until you inspect the filesystem.

When scaffolding begins, follow the layout in `docs/groundwork-spec.md` unless the user approves a change.
