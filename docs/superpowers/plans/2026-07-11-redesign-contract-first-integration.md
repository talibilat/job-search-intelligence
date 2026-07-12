# Redesign Contract-First Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every supported interaction in the new frontend work against the existing backend while preserving the redesign's appearance and honestly disabling Phase 5 chat.

**Architecture:** Keep FastAPI routes thin and use the existing service, repository, provider, Pydantic DTO, OpenAPI, and stable frontend API boundaries. Complete only the Azure provider-resolution and live scheduler seams required by current Settings controls; all other work adapts the redesign to existing APIs and deterministic backend data.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, APScheduler, pytest, React 19, TypeScript 6, Vite, Vitest, Testing Library, Orval, and Playwright.

## Global Constraints

- Preserve the redesign's layout, typography, spacing, color system, visual hierarchy, and responsive structure.
- Do not modify `frontend/src/redesign/redesign.css` or redesign theme values unless a verified accessibility defect requires it.
- Do not add `POST /chat`, LangGraph execution, vector retrieval, streaming chat, source-email body APIs, or database migrations except the user-approved existing migration for persisted insight citations.
- The migration exception applies only to persisted insight citations and must follow the repository's SQLite Alembic batch-mode convention.
- Dashboard values remain deterministic backend values; the frontend formats but does not redefine metric semantics.
- Preserve all pre-existing uncommitted work and do not revert or reformat unrelated changes.
- Import frontend API functions and DTOs through `frontend/src/api`, never `frontend/src/api/generated.ts`.
- Do not expose or log OAuth tokens, API keys, raw email bodies, provider payloads, or arbitrary exception text.
- Do not commit unless the user explicitly requests a commit.
- Use test-first development for every behavioral change.

## File Structure

### Backend

- Modify `backend/app/api/dependencies.py`: canonical `LLMProvider` resolution for Ollama and Azure OpenAI through `SecretStore`.
- Modify `backend/app/api/provider_config.py`: reuse canonical provider resolution and apply provider-config scheduler changes to the active app scheduler.
- Modify `backend/app/services/provider_config.py`: validate scheduler-affecting updates before mutating live settings.
- Modify `backend/app/services/sync_service.py`: keep APScheduler alive and add atomic runtime enable, disable, and interval replacement.
- Modify `backend/app/api/sync.py`: expose a configured scheduled-sync job factory around the existing sync runtime.
- Modify `backend/app/main.py`: use the configured sync job by default while preserving test injection.
- Modify focused backend tests for provider resolution, scheduler behavior, app composition, and provider config.

### Frontend

- Create `frontend/src/redesign/apiError.ts`: public-safe extraction of the standard typed API error.
- Create `frontend/src/redesign/apiError.test.ts`: utility contract tests.
- Modify all `frontend/src/redesign/**/*.tsx` and `theme.ts`: import through the stable API boundary.
- Modify `frontend/src/redesign/RedesignApp.tsx`: URL-backed route/filter state, sync request state, and honest sync errors.
- Modify `frontend/src/redesign/pages/OverviewPage.tsx`: authoritative funnel data and distinct loading/error/empty states.
- Modify `frontend/src/redesign/pages/ApplicationsPage.tsx`: backend filters, consistent views, and timeline errors.
- Modify `frontend/src/redesign/pages/DetailPage.tsx`: status errors and audited event correction.
- Modify `frontend/src/redesign/pages/InsightsPage.tsx`: correct question mapping, complete order, regeneration errors, and citations.
- Modify `frontend/src/redesign/pages/SettingsPage.tsx`: Gmail redirect, provider health, atomic Settings state, and accurate inbox wording.
- Modify `frontend/src/redesign/ChatDrawer.tsx`: honest disabled Phase 5 state.
- Modify `frontend/src/redesign/pages/DeveloperPage.tsx`: registry-backed implementation status.
- Add focused redesign tests beside the relevant components or in `frontend/src/App.test.tsx` where the existing app-level fetch harness is required.
- Modify `frontend/tests/smoke/phase0-shell.pw.ts`: private-data-free critical redesign smoke path.

### Documentation

- Rewrite `docs/design/redesign-backend-coverage.md`: verified unexposed capabilities, incomplete integrations, and later-phase work with route, requirement, evidence, and rationale columns.

---

### Task 1: Resolve Configured LLM Providers

**Files:**
- Modify: `backend/app/api/dependencies.py:9-78`
- Modify: `backend/app/api/provider_config.py:15-44`
- Test: `backend/tests/test_azure_openai_provider.py`
- Test: `backend/tests/test_llm_provider_health.py`
- Test: `backend/tests/test_ollama_llm_provider.py`

**Interfaces:**
- Produces: `get_llm_secret_store(settings: AppSettings) -> SecretStore`.
- Produces: `get_llm_provider(settings: AppSettings, secret_store: SecretStore) -> LLMProvider` resolving `ollama` and `azure_openai`.
- Produces: `get_configured_llm_provider(...) -> LLMProvider` that validates registry settings and returns the canonical resolved provider.

- [ ] **Step 1: Write failing Azure dependency and health tests**

Add tests that override settings and `get_llm_secret_store`, but do not override `get_configured_llm_provider`:

```python
def test_llm_provider_dependency_resolves_selected_azure_provider() -> None:
    provider = get_llm_provider(azure_settings(), FakeSecretStore())

    assert isinstance(provider, AzureOpenAIProvider)
    assert provider.provider_name == "azure_openai"
    assert "api-key" not in repr(provider)


def test_health_endpoint_resolves_real_azure_adapter_through_normal_di(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(settings=azure_settings())
    app.dependency_overrides[get_llm_secret_store] = lambda: FakeSecretStore()
    monkeypatch.setattr(AzureOpenAIProvider, "health_check", healthy_azure_check)

    with TestClient(app) as client:
        response = client.post("/config/providers/llm/health")

    assert response.status_code == 200
    assert response.json()["provider"] == "azure_openai"
    assert "api-key" not in response.text
```

- [ ] **Step 2: Run focused tests and verify the current 503 failures**

Run: `uv run pytest tests/test_azure_openai_provider.py tests/test_llm_provider_health.py tests/test_ollama_llm_provider.py -q`

Expected: the new Azure resolution tests fail because normal DI only constructs Ollama and the health resolver always raises unavailable.

- [ ] **Step 3: Implement canonical SecretStore-backed provider resolution**

Add the dependency and Azure branch without duplicating adapter construction in the health route:

```python
def get_llm_secret_store(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> SecretStore:
    return create_secret_store(settings)


def get_llm_provider(
    settings: Annotated[AppSettings, Depends(get_settings)],
    secret_store: Annotated[SecretStore, Depends(get_llm_secret_store)],
) -> LLMProvider:
    if settings.llm_provider is LLMProviderName.AZURE_OPENAI:
        return AzureOpenAIProvider(settings=settings, secret_store=secret_store)
    if settings.llm_provider is LLMProviderName.OLLAMA:
        return OllamaLLMProvider.from_settings(settings)
    raise ApiError(status_code=503, code="llm_provider_unavailable", message="The selected LLM provider is unavailable.")
```

Make `get_configured_llm_provider` validate through `ProviderRegistry` and return the injected `get_llm_provider` result.

- [ ] **Step 4: Run provider tests**

Run: `uv run pytest tests/test_azure_openai_provider.py tests/test_llm_provider_health.py tests/test_ollama_llm_provider.py tests/test_classification_run_api.py tests/test_insights_api.py -q`

Expected: all selected-provider, health, classification, and insight provider tests pass without network access or secret exposure.

### Task 2: Reconfigure The Live Sync Scheduler

**Files:**
- Modify: `backend/app/services/sync_service.py:55-133`
- Modify: `backend/app/services/provider_config.py:61-79`
- Modify: `backend/app/api/provider_config.py:91-149`
- Test: `backend/tests/test_sync_service.py:161-357`
- Test: `backend/tests/test_provider_config_api.py`

**Interfaces:**
- Produces: `SyncScheduler.reconfigure(*, sync_on_open: bool, interval_seconds: int) -> None`.
- Produces: `get_active_sync_scheduler(request: Request) -> SyncScheduler`.
- Changes: `apply_provider_config_update(..., *, sync_scheduler: SyncScheduler) -> ProviderConfigResponse`.

- [ ] **Step 1: Extend the recording scheduler and write failing lifecycle tests**

Add `remove_job(job_id: str) -> None` to the scheduler protocol and test double, then add tests for disabled startup, live enable, interval replacement, disable, and failed replacement:

```python
def test_sync_scheduler_reconfigure_enables_live_interval_job() -> None:
    backend = RecordingScheduler()
    scheduler = SyncScheduler(
        sync_on_open=False,
        interval_seconds=3600,
        sync_job=recording_sync_job,
        scheduler=backend,
    )
    scheduler.start()

    scheduler.reconfigure(sync_on_open=True, interval_seconds=1800)

    assert backend.started is True
    assert backend.jobs[-1]["id"] == SYNC_ON_OPEN_JOB_ID
    assert backend.jobs[-1]["seconds"] == 1800
    assert backend.jobs[-1]["replace_existing"] is True
```

- [ ] **Step 2: Run scheduler tests and verify failures**

Run: `uv run pytest tests/test_sync_service.py -q`

Expected: failures show that disabled startup does not start APScheduler and no runtime reconfiguration API exists.

- [ ] **Step 3: Implement stable scheduler lifecycle and atomic reconfiguration**

Keep the APScheduler backend started for the FastAPI lifespan, register the startup job only when enabled, and apply runtime changes with one stable ID:

```python
def reconfigure(self, *, sync_on_open: bool, interval_seconds: int) -> None:
    if interval_seconds < 1:
        raise ValueError("interval_seconds must be at least 1")
    if sync_on_open:
        self._scheduler.add_job(
            self._sync_job,
            "interval",
            seconds=interval_seconds,
            id=SYNC_ON_OPEN_JOB_ID,
            replace_existing=True,
        )
        self._job_registered = True
    elif self._job_registered:
        self._scheduler.remove_job(SYNC_ON_OPEN_JOB_ID)
        self._job_registered = False
    self._sync_on_open = sync_on_open
    self._interval_seconds = interval_seconds
```

Do not schedule an immediate run during a Settings update; retain immediate startup behavior only for the initial configured startup job.

- [ ] **Step 4: Write failing provider-config integration tests**

Test that `PUT /config/providers` updates the active scheduler before mutating settings and returns a public-safe 503 if scheduler application fails:

```python
def test_provider_config_update_does_not_mutate_settings_when_scheduler_fails() -> None:
    settings = settings_with_sync(sync_on_open=False, interval=3600)
    app = create_app(settings=settings, scheduler=FailingScheduler())

    with TestClient(app) as client:
        response = client.put(
            "/config/providers",
            json={"sync_on_open": True, "sync_interval_seconds": 1800},
        )

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Sync scheduler settings could not be applied."
    assert settings.sync_on_open is False
    assert settings.sync_interval_seconds == 3600
    assert "scheduler exploded" not in response.text
```

- [ ] **Step 5: Wire the active scheduler into provider configuration**

Read `request.app.state.sync_scheduler`, add a documented typed 503 response, call `reconfigure` after validating the copied settings and before mutating the live settings object.

- [ ] **Step 6: Run scheduler and provider-config tests**

Run: `uv run pytest tests/test_sync_service.py tests/test_provider_config_api.py tests/test_app_factory.py -q`

Expected: enable, replace, disable, failure atomicity, and lifespan shutdown tests all pass.

### Task 3: Replace The Production No-Op Sync Job

**Files:**
- Modify: `backend/app/api/sync.py:67-194`
- Modify: `backend/app/main.py:45-59`
- Test: `backend/tests/test_sync_api.py`
- Test: `backend/tests/test_app_factory.py`

**Interfaces:**
- Produces: `create_configured_sync_job(settings: AppSettings) -> SyncJob`.
- Preserves: `create_app(sync_job=...)` injection for deterministic tests.

- [ ] **Step 1: Write failing composition tests**

```python
def test_create_app_uses_configured_sync_job_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_job = AsyncMock()
    monkeypatch.setattr(main, "create_configured_sync_job", lambda settings: configured_job)

    app = create_app(settings=test_settings())

    with TestClient(app):
        scheduler = app.state.sync_scheduler
        assert scheduler.sync_job is configured_job
```

Add a runner test proving that no configured Gmail connection is a safe skipped run rather than a false success or uncaught exception.

- [ ] **Step 2: Run app and sync tests and verify the default remains `noop_sync_job`**

Run: `uv run pytest tests/test_app_factory.py tests/test_sync_api.py -q`

Expected: the new default-composition assertion fails.

- [ ] **Step 3: Extract the existing configured runtime construction into a scheduled job factory**

Reuse the same `SecretStore`, Gmail provider, connection resolver, status store, repositories, and `ConfiguredEmailSyncRuntime.run_manual_sync()` path used by `POST /sync`:

```python
def create_configured_sync_job(settings: AppSettings) -> SyncJob:
    async def run_configured_sync() -> None:
        try:
            runtime = build_configured_email_sync_runtime(settings)
        except ApiError as error:
            if error.code == "email_not_configured":
                return
            raise
        await runtime.run_manual_sync()

    return run_configured_sync
```

Use the repository's actual not-configured error code and preserve the existing concurrent-run behavior.

- [ ] **Step 4: Make `create_app()` use the configured factory by default**

```python
resolved_sync_job = sync_job or create_configured_sync_job(resolved_settings)
```

Keep explicit test injection higher priority.

- [ ] **Step 5: Run the backend integration slice**

Run: `uv run pytest tests/test_app_factory.py tests/test_sync_api.py tests/test_sync_service.py tests/test_provider_config_api.py -q`

Expected: all tests pass, including safe no-connection startup and explicit injected-job behavior.

### Task 4: Establish Frontend API And Error Boundaries

**Files:**
- Create: `frontend/src/redesign/apiError.ts`
- Create: `frontend/src/redesign/apiError.test.ts`
- Modify: every import of `api/generated` under `frontend/src/redesign/`

**Interfaces:**
- Produces: `publicApiError(error: unknown, fallback: string) -> string`.
- Produces: redesign source files that import only from `../api` or `../../api`.

- [ ] **Step 1: Write failing public-safe error tests**

```ts
it("returns only the standard public API message", () => {
  expect(
    publicApiError(
      { response: { data: { error: { code: "busy", message: "Sync is already running.", details: [] } } } },
      "Sync failed.",
    ),
  ).toBe("Sync is already running.");
});

it("does not expose arbitrary exception text", () => {
  expect(publicApiError(new Error("token=secret"), "Request failed.")).toBe("Request failed.");
});
```

- [ ] **Step 2: Run the utility test and verify the missing module failure**

Run: `npm run test -- src/redesign/apiError.test.ts`

Expected: FAIL because `apiError.ts` does not exist.

- [ ] **Step 3: Implement strict structural extraction**

```ts
export function publicApiError(error: unknown, fallback: string): string {
  if (typeof error !== "object" || error === null || !("response" in error)) return fallback;
  const response = (error as { response?: unknown }).response;
  if (typeof response !== "object" || response === null || !("data" in response)) return fallback;
  const data = (response as { data?: unknown }).data;
  if (typeof data !== "object" || data === null || !("error" in data)) return fallback;
  const body = (data as { error?: unknown }).error;
  if (typeof body !== "object" || body === null || !("message" in body)) return fallback;
  return typeof (body as { message?: unknown }).message === "string"
    ? (body as { message: string }).message
    : fallback;
}
```

- [ ] **Step 4: Route all redesign API imports through `frontend/src/api`**

Change `../api/generated` to `../api` and `../../api/generated` to `../../api` without changing generated artifacts.

- [ ] **Step 5: Verify the boundary**

Run: `npm run test -- src/redesign/apiError.test.ts && npm run typecheck && npm run lint`

Expected: all commands pass and `grep` finds no `api/generated` import under `frontend/src/redesign`.

### Task 5: Fix Gmail Authorization And Sync Behavior

**Files:**
- Modify: `frontend/src/redesign/pages/SettingsPage.tsx:53-144`
- Modify: `frontend/src/redesign/RedesignApp.tsx:93-262`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `gmailAuthUrlAuthGmailGet()` and `publicApiError()`.
- Preserves: existing Settings and sync-menu markup, dimensions, colors, and layout.

- [ ] **Step 1: Write failing Gmail authorization tests**

Render `/settings`, trigger Gmail, and assert one request to `/auth/gmail`, redirect to the returned Google URL, pending disablement, and typed failure rendering.

```ts
expect(fetchMock.requestsFor("/auth/gmail")).toHaveLength(1);
expect(assignSpy).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/v2/auth?...safe...");
expect(assignSpy).not.toHaveBeenCalledWith("/auth/gmail");
```

- [ ] **Step 2: Run the focused app tests and verify direct JSON-route navigation**

Run: `npm run test -- src/App.test.tsx -t "redesign Gmail"`

Expected: the redirect assertion fails because Settings currently uses `getGmailAuthUrlAuthGmailGetUrl()`.

- [ ] **Step 3: Implement the typed Gmail authorization flow**

Call `gmailAuthUrlAuthGmailGet()`, require a successful response, then call `window.location.assign(response.data.authorization_url)`. Disable duplicate submission and render only `publicApiError(...)` on failure.

- [ ] **Step 4: Write failing sync scope and error tests**

Assert the existing scope bodies, initially empty custom dates, disabled sync controls while pending, and visible typed 401, 409, 429, 502, and 503 failures.

- [ ] **Step 5: Implement honest sync state**

Initialize custom dates as empty strings, block invalid custom submission, use returned sync state instead of assuming success, and preserve errors through status refreshes.

- [ ] **Step 6: Run the focused Settings and sync tests**

Run: `npm run test -- src/App.test.tsx -t "redesign (Gmail|sync)"`

Expected: Gmail redirect, every sync scope, duplicate prevention, and typed errors pass.

### Task 6: Use Deterministic Overview Data And URL-Backed Filters

**Files:**
- Modify: `frontend/src/redesign/RedesignApp.tsx:25-185`
- Modify: `frontend/src/redesign/pages/OverviewPage.tsx`
- Modify: `frontend/src/redesign/pages/ApplicationsPage.tsx`
- Modify: `frontend/src/lib/routeQuery.test.ts`
- Test: `frontend/src/App.test.tsx` or focused redesign page tests

**Interfaces:**
- Produces: route query `status=all|applied|screening|interview|offer|closed`, with `all` omitted as the default.
- Consumes: `getMetricsFunnelMetricsFunnelGet()` and canonical `GET /applications?status=` requests.

- [ ] **Step 1: Write failing authoritative-funnel tests**

Return inconsistent summary, rates, and funnel fixtures and assert the exact five backend stages `applied`, `screen`, `interview`, `final`, and `offer` render from `/metrics/funnel`.

- [ ] **Step 2: Implement funnel loading and error separation**

Add `getMetricsFunnelMetricsFunnelGet()` to the page request set, preserve the existing funnel card appearance, and show loading, successful empty, and typed failure states distinctly.

- [ ] **Step 3: Write failing route-query tests**

```ts
expect(redesignRouteFromLocation("/applications", "?status=interview").statusFilter).toBe("interview");
expect(pathForRoute({ page: "applications", statusFilter: "offer" })).toBe("/applications?status=offer");
expect(pathForRoute({ page: "applications", statusFilter: "all" })).toBe("/applications");
```

Also test invalid fallback, back/forward restoration, reload, and unrelated query preservation.

- [ ] **Step 4: Implement URL-backed filter routing**

Use the existing `enumQueryParam`, `parseRouteQuery`, and `updateRouteQuery` helpers. Parse `window.location.search` on initial load and `popstate`; update the query when Overview or Applications changes a filter.

- [ ] **Step 5: Write failing backend-filter and view-consistency tests**

Assert canonical chips request one status, `screening` requests `in_review` plus `assessment`, and `closed` requests `rejected`, `ghosted`, plus `withdrawn`. Merge composite results by application ID. Assert table, board, and timeline show the same population.

- [ ] **Step 6: Implement filtered backend requests and timeline states**

Request only the active canonical statuses, apply the merged filtered result to all views, request event timelines only when timeline view is active, and distinguish timeline loading, empty, and error states.

- [ ] **Step 7: Remove misleading metric drill-down claims**

Keep exact interview and offer filters. For response, screen, and final populations that cannot be expressed by the current list contract, retain the existing control position but use honest non-exact wording rather than claiming that every backing application will be shown.

- [ ] **Step 8: Run overview, filter, and route tests**

Run: `npm run test -- src/lib/routeQuery.test.ts src/App.test.tsx`

Expected: deterministic funnel, query persistence, backend status requests, consistent views, and honest errors pass.

### Task 7: Complete Corrections And Insights

**Files:**
- Modify: `frontend/src/redesign/pages/DetailPage.tsx`
- Modify: `frontend/src/redesign/pages/InsightsPage.tsx`
- Test: `frontend/src/App.test.tsx` or focused redesign page tests

**Interfaces:**
- Consumes: `editApplicationEventApplicationsApplicationIdEventsEventIdPatch(...)`.
- Consumes: all seven `InsightType` values and real `InsightCitation[]` records.

- [ ] **Step 1: Write failing correction tests**

Assert status updates only from a successful response, preserve old state on failure, disable pending controls, and surface typed errors. Assert `Fix a mistake` opens an in-card editor and submits at least one changed event field plus the correction reason to the existing event-edit endpoint.

- [ ] **Step 2: Implement status and event correction state**

Reuse the legacy correction request shapes from `frontend/src/pages/ApplicationCorrectionForms.tsx`, but preserve the redesign card structure and styling. Replace the event and application only from `response.data`; do not optimistically mutate.

- [ ] **Step 3: Correct source and correction copy**

Keep email subjects as noninteractive metadata pills. Remove claims that each source is a clickable email destination. Keep the `Fix a mistake` control accurate by connecting it to the editor.

- [ ] **Step 4: Write failing seven-type insight tests**

Assert order `why_rejected`, `recurring_feedback`, `skill_gaps`, `strongest_weakest_signals`, `role_fit`, `weekly_actions`, `story`; distinguish Q-40 from Q-41; reject inferred-evidence copy; and verify real citation navigation.

- [ ] **Step 5: Implement complete insight copy and mutation state**

Give every `InsightType` explicit copy and display order. Keep prior content visible while regeneration is pending, disable repeat submission, replace only the successful type, and preserve prior content with a typed error after failure.

- [ ] **Step 6: Run correction and insight tests**

Run: `npm run test -- src/App.test.tsx -t "redesign (detail|insight)"`

Expected: status edits, event edits, failures, all insight types, regeneration, and citations pass.

### Task 8: Make Settings Operational And Chat Honest

**Files:**
- Modify: `frontend/src/redesign/pages/SettingsPage.tsx`
- Modify: `frontend/src/redesign/ChatDrawer.tsx`
- Modify: `frontend/src/redesign/pages/DeveloperPage.tsx`
- Modify: `frontend/src/featureStatus/featureStatusRegistry.ts` only if verified status metadata is missing
- Test: `frontend/src/App.test.tsx` or focused component tests

**Interfaces:**
- Consumes: `checkLlmProviderHealthConfigProvidersLlmHealthPost()`.
- Produces: no network request and no local message mutation from unavailable chat controls.

- [ ] **Step 1: Write failing provider and scheduler Settings tests**

Assert provider and interval selections change only after a successful `PUT /config/providers`, failures preserve prior selection, controls disable while pending, and successful provider selection triggers the health endpoint.

- [ ] **Step 2: Implement atomic Settings updates and health state**

Keep a pending update separate from confirmed `ProviderConfigResponse`. Render health using existing status visual language. Do not show Azure or Ollama as operational when the health response reports unavailable.

- [ ] **Step 3: Correct connected-account wording**

List all stored connections without implying all are synchronized. Mark only the backend-selected default account as active when that information is available; otherwise use neutral stored-connection wording.

- [ ] **Step 4: Write failing unavailable-chat tests**

Assert the drawer retains its structure, reports Phase 5 unavailability, disables suggestions, input, and Ask, ignores Enter, sends no `/chat` request, and never appends the canned assistant response.

- [ ] **Step 5: Remove fake chat behavior without changing layout**

Delete the canned response and `ask()` mutation. Keep the same drawer width, header, suggestions, input row, button dimensions, and animation; add native `disabled` behavior and honest copy.

- [ ] **Step 6: Write and implement registry-backed developer status tests**

Import verified status from `featureStatusRegistry` through a small local adapter instead of optimistic `DEV_ROWS`. Ensure chat is planned and partially integrated corrections are not labeled fully live until their tests pass.

- [ ] **Step 7: Run Settings, chat, and developer tests**

Run: `npm run test -- src/App.test.tsx -t "redesign (settings|chat|developer)"`

Expected: atomic Settings behavior, health, neutral inbox wording, disabled chat, and verified developer status pass.

### Task 9: Publish The Backend Capability Inventory

**Files:**
- Modify: `docs/design/redesign-backend-coverage.md`

**Interfaces:**
- Produces: separate tables for verified unexposed features, incomplete integrations, incomplete backend work, and later-phase features.

- [ ] **Step 1: Correct route names and current integration status**

Use `/config/providers`, `/config/providers/llm/health`, and `/local-data/wipe`. Mark the funnel, exact metric drill-down, event correction, developer registry, and scheduler status according to verified implementation rather than endpoint existence alone.

- [ ] **Step 2: Convert the unexposed list into evidence-backed tables**

Each row must include:

```markdown
| Route or service | Capability | Phase / IDs | Verification evidence | Why unexposed |
| --- | --- | --- | --- | --- |
```

Reference exact pytest files or API tests. Separate `GET /chat/history` as a working unexposed read from `POST /chat` as later Phase 5 work.

- [ ] **Step 3: Verify documentation against registered routes and tests**

Run: `rg '(/providers|POST /wipe|Already existed|Added 2026)' docs/design/redesign-backend-coverage.md`

Expected: no obsolete route names or unsupported implementation claims remain.

### Task 10: Add The Critical Redesign Smoke Path

**Files:**
- Modify: `frontend/tests/smoke/phase0-shell.pw.ts`

**Interfaces:**
- Consumes: private-data-free mocked responses for current OpenAPI routes.
- Produces: one critical path through Overview, Applications, detail correction, Insights, Settings, unavailable chat, and Developer status.

- [ ] **Step 1: Add deterministic redesign route fixtures**

Define fixed backend responses, including deliberately distinct funnel stage counts, typed correction responses, real insight citations, provider health, and one typed Settings error. Do not calculate expected metric truth in browser test code.

- [ ] **Step 2: Write the redesign smoke journey**

Exercise:

1. `/` overview values and five-stage funnel.
2. `/applications?status=interview` across table, board, and timeline.
3. `/applications/app-analytics` status and event correction.
4. `/insights` Q-40/Q-41 labels, regeneration, and citation.
5. `/settings` Gmail authorization response and one scheduler update.
6. Chat drawer disabled behavior with no `/chat` request.
7. `/dev` verified status and Phase 5 label.

- [ ] **Step 3: Run the focused Playwright test**

Run: `npx playwright test tests/smoke/phase0-shell.pw.ts --project=chromium`

Expected: the complete private-data-free redesign journey passes in desktop Chromium.

### Task 11: Run Full Verification And Visual-Freeze Review

**Files:**
- Verify all modified files.

- [ ] **Step 1: Synchronize backend dependencies**

Run from repository root: `uv sync --project backend --group dev`

Expected: dependency synchronization succeeds without modifying application source.

- [ ] **Step 2: Run backend quality gates**

Run from `backend/`:

```bash
uv run ruff check app tests
uv run mypy
uv run pytest
```

Expected: Ruff, strict mypy, and the complete pytest suite pass.

- [ ] **Step 3: Regenerate and validate the frontend API contract**

Run from `frontend/`: `npm run check`

Expected: OpenAPI generation is stable, TypeScript compiles, ESLint has zero warnings, all Vitest tests pass, and Vite builds.

- [ ] **Step 4: Run the Playwright suite**

Run from `frontend/`: `npm run test:smoke`

Expected: all smoke tests pass in configured Chromium.

- [ ] **Step 5: Confirm no unintended visual-system changes**

Run from repository root:

```bash
git diff -- frontend/src/redesign/redesign.css frontend/src/redesign/theme.ts
git diff --check
git status --short
```

Expected: no redesign CSS or theme-value diff, no whitespace errors, and only intended files are changed. Inspect the redesign component diff to confirm that existing layout and style declarations were preserved.

- [ ] **Step 6: Reconcile completion against the approved design**

Confirm every current control is functional or honestly unavailable, no production fake data remains, displayed metrics come from deterministic endpoints, the capability inventory matches tests, and no Phase 5 implementation entered scope.
