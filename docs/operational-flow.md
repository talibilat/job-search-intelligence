# Operational Flow

JobTracker's supported release flow runs through the current redesign at `/`.
Routes under `/legacy`, `/dashboard`, `/features`, `/setup`, and `/legacy/insights` remain diagnostic compatibility surfaces and are visibly marked as legacy.

## Start Locally

1. Follow `docs/google-oauth-setup.md` to create your own Gmail desktop OAuth client with the read-only scope.
2. Follow `docs/llm-provider-setup.md` to configure Azure OpenAI or local Ollama credentials and models.
3. Start the FastAPI backend from `backend/` with `uv run uvicorn app.main:app --reload`.
4. Start the frontend from `frontend/` with `npm run dev`.
5. Open the frontend URL and use Settings to confirm Gmail, classification, embedding, and chat readiness.

## Process A Search

1. Open Settings, select the LLM provider, and connect Gmail through the read-only OAuth flow.
2. Return to Overview and use Sync to fetch new mail, a date range, or a bounded recent-message set.
3. Review the sync estimate before starting the run.
4. Run processing when retained candidates are waiting.
5. Confirm Overview counts and rates after processing completes.
6. Open Applications to inspect the reconstructed application and its cited event timeline.
7. Open Insights to review cached narratives and explicitly regenerate stale cards when desired.

## Ask Grounded Questions

Open Ask AI from any current workspace page or navigate directly to `/chat`.
The drawer restores persisted local history from `GET /chat/history`.
Each new question is sent to `POST /chat` with an idempotent turn ID.
The configured LLM creates a typed plan and chooses ordinary conversation, deterministic local data, retained email evidence, Tavily web search, or a mixed route.
Ordinary conversation does not invoke tools.
Constrained tools gather deterministic facts or cited evidence only when they add value.

Quantitative answers use constrained deterministic tools and must match Overview metrics.
Content answers cite retained job-search evidence.
Mixed answers combine immutable deterministic metrics with LLM synthesis over retrieved evidence.
Invalid tool plans, unknown citation IDs, irrelevant retrieval results, and uncited content answers are rejected rather than displayed as grounded facts.
Application citations render as cards with company, role, status, and date.
Web citations render as Tavily source cards with safe external links.
Follow-up prompts can request the specific applications behind a count or continue a grouped analysis.
Application citations navigate to the application detail page.
Email citations open the existing public-safe email reader by opaque public ID, never by a raw provider message ID.

An answer with no supporting citation is displayed as a grounded refusal rather than an unsupported claim.
If the configured model is unavailable, use Retry answer after starting or correcting the provider, or open Settings from the error state.

## Privacy And Deletion

All application data, chat history, compact citations, tool outputs, and embeddings remain in the local SQLite data store.
Only the configured LLM provider receives evidence required for a model-backed operation.
Tavily receives only the public search query and bounded result count, never local email or application content.
No outbound writing, voice access, hosting, telemetry, or multi-user behavior is part of this release.

To remove local data, open Settings, choose Delete all local data, and confirm with the second click.
The wipe removes synced mail, derived applications, insights, chat history, embeddings, and configured secret references while leaving Gmail itself untouched.
