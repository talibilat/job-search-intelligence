# Product Requirements Document (PRD)

## Job-Search Intelligence - a personal AI job-application analytics platform

> **Document type:** PRD (the *what / why / for whom*) · Companion to `groundwork-spec.md` (the *how*)
> **Status:** Draft for review · **Version:** 0.2 · **Author:** you (solo builder)
> **Reading order:** PRD (this) -> groundwork spec -> `docs/questions.md` -> tickets
> **Rule:** every functional requirement below carries an ID (e.g. `FR-3.2`) and maps to one or more GitHub tickets. Acceptance criteria here are the contract; the ticket's Definition of Done points back to them.

---

## 1. Overview

### 1.1 One-line summary

A **local-first web app** that connects to your email, mines your entire job-search history, and answers 54 questions about it - from *"how many jobs did I apply to?"* to *"why am I getting rejected and what should I fix?"* - through a **dashboard** and a **conversational RAG agent**.

### 1.2 The problem

Job seekers fire off dozens or hundreds of applications and lose the thread.
The evidence of what's working - every confirmation, rejection, interview invite, and scrap of recruiter feedback - is already sitting in their inbox, but it's **unstructured, scattered across years, and never analyzed**.
Existing tools (Huntr, Teal, Simplify) focus on *tracking new applications going forward* and require manual logging or browser extensions.
**None mine your lifetime email history to produce diagnostic, prescriptive insight** ("why am I getting rejected", "which skills actually convert", "which roles suit me").
That gap is the reason this exists.

### 1.3 The solution

Ingest email -> isolate job-related messages -> reconstruct them into a clean `applications` table with a status timeline -> expose that one source of truth three ways: **deterministic dashboards** (accurate counts/rates), **cached LLM insights** (the narrative "why"), and a **hybrid RAG agent** (ask anything, correct numbers + real citations).

### 1.4 What this is *not* (non-goals for v1)

- **Not** an auto-apply bot. No applying on your behalf in v1.
- **Not** an autonomous emailer.
  Outbound is **draft-only, review-then-send** and only in a later phase.
- **Not** a multi-tenant SaaS. Single-user, local, on your laptop. Open-source and hosting come later.
- **Not** a job board or recruiter marketplace (Mercor / Jack & Jill territory).
  That's a different product.
- **Not** a CRM for recruiters. It's *your* personal analytics layer.

---

## 2. Goals & success metrics

### 2.1 Product goals

1. Turn a messy inbox into a **trustworthy, structured record** of your job search.
2. Answer the **Tier 1–3 factual questions** at a glance (dashboard).
3. Surface **diagnostic + prescriptive insight** (Tiers 4–5) you couldn't get by scrolling your inbox.
4. Let you **interrogate your history in natural language** (Tier 6), eventually from your phone.
5. Stay **private by construction** (local-first, your own credentials) so open-sourcing later is low-risk.

### 2.2 Success metrics (for you, the first and only user)

| Metric | Target |
|---|---|
| Inbox backfilled + classified end-to-end | 100% of Gmail history processed without manual logging |
| Classification accuracy (golden set) | ≥ 90% precision AND ≥ 85% recall on job-vs-not (floor-then-ratchet) |
| Dashboard trust | Every displayed number reconciles with the underlying DB |
| Coverage of the 50 questions | Tiers 1–3 by end of Phase 3; Tier 5 by Phase 4; Tier 6 by Phase 5 |
| Agent correctness | Quantitative chat answers **match** the dashboard; content answers cite real emails |
| Time-to-first-insight | From `git clone` to a populated dashboard in one sitting |

### 2.3 Explicit anti-metrics

- Not optimizing for number of users, engagement time, or retention.
  It's a personal tool.
- Not optimizing test coverage %.
  Minimal testing is a deliberate choice, with the golden-set eval as the exception.

---

## 3. Users & personas

### 3.1 Primary persona - "The Analyst Job-Seeker" (you)

Technical, comfortable running a local app with their own API keys, mid-search or perpetually opportunistic, frustrated by not knowing *what's actually working*. Wants data, not vibes. Values privacy. Will happily connect Gmail if nothing leaves their machine.

### 3.2 Secondary persona (future, post-open-source) - "The Self-Hoster"

Another technical job-seeker who clones the repo, brings their own credentials, and self-hosts.
Drives requirements around **bring-your-own-credentials**, **ship-no-data**, and clear setup docs, but is **out of scope for v1** beyond keeping the architecture clean.

### 3.3 Non-users (v1)

Recruiters, employers, non-technical job seekers needing a hosted zero-setup product. Deliberately unserved for now.

---

## 4. Scope by release

### 4.1 v1 (this build) - "See and understand my search"

Gmail ingestion · classification + extraction + aggregation · deterministic dashboard (Tiers 1-4) · cached LLM insights (Tier 5) · RAG chat (Tier 6) · pluggable LLM providers · local-only.

### 4.2 vNext (later, prioritized order)

1. **More email providers** - Outlook/Graph, then IMAP (Yahoo, iCloud).
2. **Draft-writing** - follow-up + recruiter-reply drafts, review-then-send, never autonomous.
3. **Hosting + phone/voice access** - always-on box + secure tunnel; conversational access on mobile.
4. **Auto-apply** - opt-in, guarded, with the known ToS/backlash caveats.
5. **External enrichment (Tier 7)** - benchmarking, recruiter/role cross-checks via APIs.
6. **Open-source hardening** - packaging, docs, per-user credential flows.

---

## 5. Functional requirements

> IDs group by area. Each has **Priority** (P0 = v1 must-have, P1 = v1 nice-to-have, P2 = later) and **Acceptance criteria**.

### FR-0 - Setup & configuration

- **FR-0.1 First-run setup wizard** *(P0)* - On first launch, guide the user through: choosing an LLM provider (Azure OpenAI or Ollama first, with OpenAI and Anthropic later behind the same interface) + entering credentials, choosing `classification_mode` (`hybrid` / `llm` / `local`), and connecting Gmail.
  *Accept:* fresh clone reaches a "ready" state through the wizard with no manual file editing required.
- **FR-0.2 Encrypted secrets at rest** *(P0)* - API keys and OAuth tokens stored encrypted with OS keyring by default and a documented Fernet fallback, never in plaintext, never logged.
  *Accept:* inspecting the config store shows no plaintext secrets; logs are clean.
- **FR-0.3 Provider switch** *(P1)* - Change LLM provider/model after setup via `GET|PUT /config/providers`.
  *Accept:* switching provider and re-running classification works without code changes.
- **FR-0.4 Cost estimate before bulk runs** *(P1)* - Before a full classification pass, show an estimated token/cost figure.
  *Accept:* estimate is shown and within a reasonable band of actual usage; per-run tokens are tracked.
- **FR-0.5 Environment-variable coverage** *(P0)* - Every user-changeable operational setting has a typed config field and `.env` override.
  *Accept:* `.env.example` documents every user-changeable setting without secrets.

### FR-1 - Email ingestion

- **FR-1.1 Gmail OAuth (Testing mode)** *(P0)* - Desktop OAuth flow; `gmail.readonly` scope; runs under Google Testing mode (no verification/CASA needed for personal use).
  *Accept:* user authorizes once; tokens persist and refresh.
- **FR-1.2 Full historical backfill** *(P0)* - Pull Gmail metadata broadly and retain body text only for messages that pass the broad job-search candidate filter or are needed for reconciliation/debugging.
  *Accept:* local raw-email metadata count reconciles with Gmail; large mailboxes around 40k messages complete without data loss (paginated, resumable); body retention state is tracked.
- **FR-1.3 Incremental sync** *(P0)* - Use `historyId` to fetch only new messages on subsequent syncs, and recover from expired history IDs by falling back to resumable full metadata reconciliation.
  *Accept:* a second sync pulls only new mail when the cursor is valid; an expired cursor restarts metadata reconciliation without losing pagination or next-cursor progress.
- **FR-1.4 Provider abstraction** *(P0)* - All ingestion behind an `EmailProvider` interface so Outlook/IMAP drop in later without touching the pipeline.
  *Accept:* Gmail is one implementation of a documented interface; adding a provider requires no pipeline changes.
- **FR-1.5 Sync triggers** *(P0)* - Manual "Sync now" + "sync on open"; background scheduler (APScheduler) while the local backend process is running.
  *Accept:* `POST /sync` runs a sync; `GET /sync/status` reports progress/last-run.
- **FR-1.6 Attachment exclusion** *(P0)* - Ignore Gmail attachments in v1.
  *Accept:* ingestion does not fetch, parse, store, or embed attachment content.

### FR-2 - Classification, extraction & aggregation *(make-or-break)*

- **FR-2.1 Heuristic pre-filter** *(P0)* - Cheaply narrow the inbox using known ATS/recruiter sender domains, keyword signals, excluded-label hard rejections, and same-page thread context before any LLM call.
  *Accept:* filter reduces the candidate set by orders of magnitude while retaining known job emails, `uv run python -m evals.run_eval --filter` from `backend/` validates that retention against the golden set, and each evaluated metadata record has an auditable local outcome, score, and public-safe static signal reason.
- **FR-2.2 LLM classification** *(P0)* - Classify each candidate into `application_confirmation | rejection | interview_invite | recruiter_outreach | offer | assessment | follow_up | other`, with a confidence score.
  *Accept:* categories populate `email_classifications`; model + prompt version stored per row.
- **FR-2.3 Structured extraction** *(P0)* - Extract company, role, status, dates, salary, location, work mode, seniority, sponsorship, tech stack, rejection reason, validated by Pydantic.
  *Accept:* extraction returns typed objects; malformed extractions are caught, not silently stored.
- **FR-2.4 Application aggregation** *(P0)* - Reconstruct one `application` from many emails, with an `application_events` timeline; dedupe idempotently.
  *Accept:* a confirmation + later rejection = one application (`rejected`) with two events; re-running never duplicates.
- **FR-2.5 Ghost inference** *(P0)* - Mark applications `ghosted` when no response arrives after a tunable threshold (default 30 days).
  *Accept:* ghost status appears correctly; threshold is configurable.
- **FR-2.6 Reproducible re-runs** *(P0)* - Re-processing is deterministic and incremental; stored prompt/model versions allow controlled re-classification.
  *Accept:* re-run on unchanged mail produces no changes; changing the prompt version re-classifies cleanly.
- **FR-2.7 Golden-set eval** *(P0, mandatory gate)* - ~30 private-data-free labeled emails + an accuracy report run whenever the classify prompt, model, category set, extraction schema, or parser behavior changes.
  *Accept:* `uv run python -m evals.run_eval` from `backend/` prints precision/recall; Phase 2 gate is ≥90% precision AND ≥85% recall on job-vs-not; regressions block merges unless explicitly accepted.
- **FR-2.8 Manual correction path** *(P0)* - Support audited merge, split, status edit, and event edit operations for aggregation mistakes.
  *Accept:* user-corrected grouping and status are locked from automatic overwrite by default, conflicts are surfaced when new evidence disagrees, and corrections can be explicitly reset.

### FR-3 - Dashboard (deterministic analytics) - Tiers 1-4

- **FR-3.1 Foundational counts (Tier 1)** *(P0)* - Total applications, by window, distinct companies, responses vs silence, rejections, ghosts, interviews, offers, per-application status, live applications.
  *Accept:* Questions 1–10 answered on screen; numbers reconcile with DB.
- **FR-3.2 Rates, funnels, time (Tier 2)** *(P0)* - Response/rejection/ghost rates, application-to-interview and interview-to-offer conversion, full funnel, time-to-first-response, time-to-rejection, personal ghost threshold, volume trend, improvement-over-time.
  *Accept:* Questions 11–21 answered; funnel and time math verified on sample data.
- **FR-3.3 Segmentation (Tier 3)** *(P0)* - Breakdowns by role, best-converting titles, company type, source, salary band, work mode, sponsorship vs not, tech stack, seniority.
  *Accept:* Questions 22–31 answered; `GROUP BY` breakdowns render as charts/tables.
- **FR-3.4 Diagnostics (Tier 4)** *(P1)* - What winners share, what losers share, strongest single correlate of a response, wasted-effort segments, best-ROI source, sponsorship-cost quantification, which listed skills actually convert, adjacent-role suggestions.
  *Accept:* Questions 32-39 answered with deterministic or light-statistics comparisons; optional narrative summaries only appear after deterministic facts are prepared and cited.
- **FR-3.5 Filtering** *(P0)* - Filter all views by status, source, sponsorship, date range, role, salary band, work mode.
  *Accept:* filters compose and update every metric consistently; dashboard filter state is represented in route query strings.
- **FR-3.6 Metric integrity** *(P0)* - All dashboard numbers are deterministic SQL/pandas; the LLM never produces counts.
  *Accept:* the same query always returns the same number; spot-checks match manual counts.

### FR-4 - Insights (cached LLM narrative) - Tier 5

- **FR-4.1 Narrative insights** *(P0)* - Generate: why rejections happen (themes), recurring feedback, real skill gaps, strongest/weakest signals, best-fit roles, next-week actions, the search "story".
  *Accept:* Questions 40–46 answered; each insight cites the applications/emails it's drawn from.
- **FR-4.2 Caching + regenerate** *(P0)* - Insights are cached with an inputs hash; `POST /insights/regenerate` recomputes on demand.
  *Accept:* insights load instantly from cache; source changes mark insights stale; regeneration remains user-triggered for cost control.
- **FR-4.3 Grounding** *(P0)* - No free-floating claims; insights are traceable to source data.
  *Accept:* every insight links back to evidence.

### FR-5 - RAG chat agent - Tier 6

- **FR-5.1 Hybrid routing (LangGraph)** *(P0)* - Route each question to a structured-query tool (quantitative), semantic retrieval (content), or both (mixed).
  *Accept:* Questions 47–50 answered; routing is correct on a handful of sample questions.
- **FR-5.2 Structured-query tool** *(P0)* - Answers counts/rates via a **constrained query builder / whitelisted templates**; the LLM never emits raw SQL.
  *Accept:* quantitative answers **match** the dashboard exactly; no arbitrary SQL is executed.
- **FR-5.3 Semantic retrieval tool** *(P0)* - sqlite-vec search over chunks from job-related retained email bodies; returns citations to real emails.
  *Accept:* "what did the recruiter at X say?" returns the right email with a citation; unrelated metadata-only messages are not embedded by default.
- **FR-5.4 Streaming chat UI** *(P0)* - In-app chat with streamed responses.
  *Accept:* responses stream; history is viewable.
- **FR-5.5 Grounded answers** *(P0)* - Every answer is grounded in tool output.
  *Accept:* no unsupported claims; answers reference data/emails.
- **FR-5.6 Persisted chat history** *(P0)* - Store chat history in SQLite with compact citations and tool outputs.
  *Accept:* `GET /chat/history` returns prior local conversations, and wipe-data removes chat history.

### FR-6 - Data & privacy

- **FR-6.1 Local-first storage** *(P0)* - All data in a single local SQLite file (incl. sqlite-vec embeddings). Nothing leaves the machine except LLM API calls the user configures.
  *Accept:* the whole app state is one portable file; no telemetry.
- **FR-6.2 Bring-your-own-credentials** *(P0 for architecture)* - The app uses the user's own Google Cloud OAuth client and LLM credentials.
  *Accept:* no shared/bundled credentials anywhere in the repo.
- **FR-6.3 Data deletion** *(P0)* - A clear way to wipe local data.
  *Accept:* a documented command/endpoint removes stored emails/derived data.

---

## 6. Non-functional requirements

- **NFR-1 Privacy** - Local-first; content sent to an LLM only per the user's provider choice; `local` mode (Ollama) keeps everything offline.
- **NFR-2 Cost transparency** - Pre-run estimates + per-run token tracking; hybrid mode default to minimize spend.
- **NFR-3 Portability / hosting-ready** - No hardcoded `localhost`; clean bind config; containerizable later so a flip to an always-on box is config, not a rewrite.
- **NFR-4 Reliability of the pipeline** - Backfill is resumable; sync + aggregation are idempotent.
- **NFR-5 Maintainability** - Typed everywhere (mypy), Pydantic at boundaries, repository pattern, providers behind interfaces, small focused modules, ruff-formatted, conventional commits.
- **NFR-6 Extensibility** - New email providers and LLM providers require no pipeline changes.
- **NFR-7 Performance** - Dashboard reads are instant (precomputed/deterministic); classification is batched and cost-bounded.
- **NFR-8 Security** - Secrets encrypted at rest; the agent cannot execute arbitrary SQL.

---

## 7. Assumptions & dependencies

- **Google Testing mode** suffices for personal `gmail.readonly` use (no verification/CASA for a single user).
- The user has (or will create) their own **Google Cloud OAuth client** and **LLM provider account**.
- Inbox scale assumed at roughly **40k lifetime emails** for cost and performance defaults.
- LLM extraction is **good but imperfect**; the golden set exists to keep it honest.
- GitHub issues are created via the local `gh` CLI after a reviewed `tickets/manifest.yaml` and issue-body files are generated.

---

## 8. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Classification silently wrong | Every downstream number lies | Golden-set eval as Phase 2 gate; store prompt/model versions |
| Aggregation duplicates/misgroups applications | Inflated counts, broken timelines | Idempotent dedupe; normalized grouping key; spot-check against inbox |
| LLM cost on full backfill | Unexpected spend | Heuristic pre-filter; hybrid mode default; pre-run estimate + token tracking; `local` (Ollama) option |
| Agent returns wrong numbers | Loss of trust | Structured-query tool (no raw SQL); numbers must match dashboard |
| Multi-provider complexity later | Scope creep | Provider interface now, implementations later; v1 is Gmail-only |
| Scope creep toward auto-apply/SaaS | Never shipping v1 | Non-goals fixed; vNext explicitly deferred |
| Google verification burden if going multi-user | Cost + process | Stay local/self-host + BYO-credentials; defer public hosting |

---

## 9. Release plan (phases -> this PRD)

| Phase | Delivers | Satisfies |
|---|---|---|
| **0 Groundwork** | Scaffold, tooling, skeletons, CI | FR-0 (partial), NFR-5 |
| **1 Ingestion** | Gmail backfill + incremental | FR-1 |
| **2 Classify/aggregate** | Clean `applications` + eval | FR-2, risk gate |
| **3 Dashboard** | Tiers 1–4 on screen | FR-3 |
| **4 Insights** | Tier 5 narrative | FR-4 |
| **5 Chat** | Tier 6 RAG agent | FR-5 |
| **Later** | Providers, drafts, hosting/voice, auto-apply, enrichment, OSS | §4.2 |

---

## 10. Open questions (carried from groundwork spec)

**Resolved:** the golden-set eval is a hard, mandatory gate, not optional.
Eval regressions block merges unless the user explicitly accepts the tradeoff.
See `AGENTS.md`.

**Resolved:** Phase 2 gate is ≥90% precision AND ≥85% recall on job-vs-not (floor-then-ratchet).
Recall is gated explicitly so silent false negatives (missed applications) cannot shrink the dataset undetected.

**Resolved:** migrations use **Alembic** with batch mode enabled.
sqlite-vec and other virtual/vector tables are managed by hand-written revisions, not autogenerate.

**Resolved:** inbox scale is roughly 40k lifetime emails.
Use this for cost-estimation and performance defaults.

---

*Next step after PRD sign-off:* generate `tickets/manifest.yaml` and issue-body files, then create the GitHub repo, labels, milestones, and issues with `gh`.
