# Redesign Merge Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the five pre-merge blockers by enforcing complete first syncs, honest estimates, mutually exclusive sync and wipe operations, deterministic live-application metrics, and a clean type-checking gate.

**Architecture:** Keep lifecycle policy in the existing FastAPI sync and wipe boundaries, reuse `EmailSyncStatusStore` as the single in-process operation lock, and keep metric semantics in `MetricsRepository` and `MetricsSummaryService`. Regenerate the OpenAPI client after backend DTO changes and make React render backend-owned values without duplicating business rules.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite, pytest, mypy, Ruff, React, TypeScript, Vite, Vitest, Playwright, Orval-generated OpenAPI client.

---

## File Map

- `backend/app/api/sync.py`: choose full versus incremental execution and derive estimate lifecycle state.
- `backend/app/services/sync_service.py`: build deterministic estimate DTOs from explicit lifecycle state.
- `backend/app/models/sync.py`: add the full-backfill estimate basis.
- `backend/tests/test_sync_api.py`: prove bounded first-sync options cannot truncate history.
- `backend/tests/test_ui_alignment_api.py`: prove estimate bases match durable account state.
- `backend/app/api/wipe_data.py`: acquire and release the shared sync/wipe operation lock and map conflicts.
- `backend/tests/test_wipe_data_api.py`: cover conflict behavior, lock release, OpenAPI, and typed test dependencies.
- `backend/tests/test_wipe_data_service.py`: type existing secret-store test doubles and helper results.
- `backend/app/db/repositories/metrics.py`: count live applications under composed metric filters.
- `backend/app/services/metrics.py`: include the repository-owned live count in summary output.
- `backend/app/models/metrics.py`: expose `live_applications` in the typed summary DTO.
- `backend/tests/test_metrics_summary_api.py`: verify deterministic live counts and filters.
- `frontend/src/redesign/RedesignApp.tsx`: show honest full-backfill estimate copy.
- `frontend/src/redesign/pages/OverviewPage.tsx`: render `summary.live_applications` and remove browser-owned status semantics.
- `frontend/src/App.test.tsx`: cover sync estimate copy through the app integration surface.
- `frontend/src/redesign/pages/OverviewPage.test.tsx`: cover backend-owned live metric rendering.
- `frontend/src/api/openapi.json`: regenerated OpenAPI schema.
- `frontend/src/api/generated.ts`: regenerated TypeScript API client.

### Task 1: Enforce Lifetime Scope For First Sync

**Files:**
- Modify: `backend/app/api/sync.py:83-124`
- Test: `backend/tests/test_sync_api.py`

- [ ] **Step 1: Write a failing bounded-first-sync regression test**

Add a test that creates a configured runtime with no completed backfill or incremental cursor, invokes `run_manual_sync(EmailSyncOptions(max_age_days=7, max_messages=1))`, and records every `EmailMetadataListRequest` sent to the fake provider.
The provider should return two historical pages and a replacement cursor on the second page.

```python
status = asyncio.run(
    runtime.run_manual_sync(EmailSyncOptions(max_age_days=7, max_messages=1))
)

assert status.state is EmailSyncRunState.COMPLETED
assert [request.page_token for request in provider.metadata_requests] == [None, "page-2"]
assert all(request.since_date is None for request in provider.metadata_requests)
assert all(request.before_date is None for request in provider.metadata_requests)
assert all(request.page_size == settings.gmail_page_size for request in provider.metadata_requests)
assert sync_state_repository.get_cursor(account).sync_cursor == "replacement-cursor"
```

- [ ] **Step 2: Run the focused test and verify the current truncation**

Run: `uv run --project backend pytest backend/tests/test_sync_api.py -k bounded_first_sync -v`

Expected: FAIL because the first request carries a date bound or message cap and the second page is not requested.

- [ ] **Step 3: Normalize options at the execution-mode boundary**

In `ConfiguredEmailSyncRuntime.run_manual_sync`, pass fresh unbounded options only when `should_run_full_backfill` is true.

```python
if should_run_full_backfill:
    return await sync_service.run_full_backfill(
        connection=connection,
        backfill_state_service=BackfillStateService(
            backfill_state_repository=backfill_state_repository,
            sync_state_repository=sync_state_repository,
        ),
        options=EmailSyncOptions(),
    )
return await sync_service.run_manual_sync(connection=connection, options=options)
```

Do not change incremental option handling.
This keeps bounded rechecks available only after durable full-backfill completion and cursor promotion.

- [ ] **Step 4: Run sync API and service tests**

Run: `uv run --project backend pytest backend/tests/test_sync_api.py backend/tests/test_sync_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the first-sync invariant**

```bash
git add backend/app/api/sync.py backend/tests/test_sync_api.py
git commit -m "fix(sync): require complete initial backfill"
```

### Task 2: Make Sync Estimates Lifecycle-Aware

**Files:**
- Modify: `backend/app/models/sync.py:54-74`
- Modify: `backend/app/services/sync_service.py:234-296`
- Modify: `backend/app/api/sync.py:311-346`
- Test: `backend/tests/test_ui_alignment_api.py:261-284`

- [ ] **Step 1: Write failing estimate-state tests**

Split the current estimate-basis test into fresh-account and completed-account cases.
For the fresh account, insert connection metadata without completed backfill or cursor state and assert all requested scopes describe a full backfill.
For the completed account, persist completed backfill and cursor records and retain the existing incremental, message-cap, and local-history assertions.

```python
fresh = client.get("/sync/estimate?max_age_days=7").json()
assert fresh["basis"] == "full_backfill"
assert fresh["estimated_message_count"] is None

incremental = completed_client.get("/sync/estimate").json()
assert incremental["basis"] == "unknown_incremental"
```

- [ ] **Step 2: Run the estimate test and verify it fails**

Run: `uv run --project backend pytest backend/tests/test_ui_alignment_api.py -k sync_estimate -v`

Expected: FAIL because `full_backfill` is not a valid basis and the endpoint does not inspect durable state.

- [ ] **Step 3: Add the full-backfill estimate basis**

Extend the enum in `backend/app/models/sync.py`.

```python
class SyncScopeEstimateBasis(StrEnum):
    FULL_BACKFILL = "full_backfill"
    LOCAL_HISTORY = "local_history"
    MESSAGE_CAP = "message_cap"
    UNKNOWN_INCREMENTAL = "unknown_incremental"
```

Add a required keyword argument to the service helper and return before applying request bounds.

```python
def build_sync_scope_estimate(
    *,
    options: EmailSyncOptions,
    email_repository: EmailRepository,
    now: datetime,
    requires_full_backfill: bool,
) -> SyncScopeEstimate:
    total_local_emails = email_repository.count_raw_emails()
    if requires_full_backfill:
        return SyncScopeEstimate(
            estimated_message_count=None,
            basis=SyncScopeEstimateBasis.FULL_BACKFILL,
            total_local_emails=total_local_emails,
        )
```

- [ ] **Step 4: Derive estimate mode from the same durable state as execution**

In `sync_estimate`, use the repository connection to fetch the default email connection, backfill state, and cursor.
Treat no configured connection, no cursor, or a non-completed backfill as requiring full backfill.
Pass that boolean to `build_sync_scope_estimate`.

```python
connection = email_repository.connection
email_connection = EmailConnectionRepository(connection).fetch_default_connection_metadata(
    settings.email_provider
)
requires_full_backfill = True
if email_connection is not None:
    account = email_connection.account
    backfill_state = BackfillStateRepository(connection).fetch_state(account)
    cursor = SyncStateRepository(connection).get_cursor(account)
    requires_full_backfill = cursor is None or (
        backfill_state is not None
        and backfill_state.status is not EmailBackfillStatus.COMPLETED
    )
```

Inject `AppSettings` into the endpoint with `Depends(get_settings)`.

- [ ] **Step 5: Run focused backend tests**

Run: `uv run --project backend pytest backend/tests/test_ui_alignment_api.py backend/tests/test_sync_api.py -v`

Expected: PASS.

- [ ] **Step 6: Commit lifecycle-aware estimates**

```bash
git add backend/app/models/sync.py backend/app/services/sync_service.py backend/app/api/sync.py backend/tests/test_ui_alignment_api.py
git commit -m "fix(sync): report initial backfill scope"
```

### Task 3: Make Sync And Wipe Mutually Exclusive

**Files:**
- Modify: `backend/app/api/wipe_data.py:1-76`
- Modify: `backend/tests/test_wipe_data_api.py`
- Modify: `backend/tests/test_wipe_data_service.py:1-53`

- [ ] **Step 1: Write failing wipe-lock API tests**

Override `get_sync_status_store` with one shared `EmailSyncStatusStore`.
Acquire it before the request and assert a typed conflict without deletion.
Also add parametrized success and secret-failure tests that assert the lock can be acquired after the request finishes.

```python
status_store = EmailSyncStatusStore()
assert status_store.try_acquire_run()
app.dependency_overrides[get_sync_status_store] = lambda: status_store

response = client.post("/local-data/wipe", json={"confirmation": "wipe-local-data"})

assert response.status_code == 409
assert response.json()["error"]["code"] == "conflict"
assert data_dir.exists()
status_store.release_run()
```

- [ ] **Step 2: Run the wipe API tests and verify failure**

Run: `uv run --project backend pytest backend/tests/test_wipe_data_api.py -v`

Expected: FAIL because wipe does not depend on or acquire the shared operation lock.

- [ ] **Step 3: Acquire the shared lock around the complete destructive operation**

Import `EmailSyncStatusStore` and `get_sync_status_store` from `app.api.sync`.
Add the dependency to `wipe_data`, return a typed conflict before calling the wipe service, and release in `finally`.

```python
if not status_store.try_acquire_run():
    raise ApiError(
        status_code=409,
        code=ApiErrorCode.CONFLICT,
        message="Email sync or local data deletion is already running. Try again later.",
    )
try:
    result = await wipe_local_data(
        settings,
        secret_store=secret_store,
        connection_secret_refs=connection_secret_refs,
    )
except UnsafeWipeTargetError as error:
    raise ApiError(
        status_code=400,
        code=ApiErrorCode.BAD_REQUEST,
        message="Configured local data path is not safe to wipe.",
    ) from error
except WipeSecretDeletionError as error:
    raise ApiError(
        status_code=503,
        code=ApiErrorCode.SERVICE_UNAVAILABLE,
        message="Stored credentials could not be deleted. Local data was not changed.",
    ) from error
finally:
    status_store.release_run()
```

Add `409` to the route's documented responses.

- [ ] **Step 4: Correct test-double and helper annotations without weakening assertions**

Use `SecretStr` for secret values and `WipeDataResult` for the helper result.
Use the typed FastAPI app variable before wrapping it in `TestClient` so dependency overrides are not accessed through `client.app`.

```python
class NoOpSecretStore:
    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        del ref
        return None

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        del ref, value

    async def delete_secret(self, ref: SecretRef) -> None:
        del ref

def run_wipe(settings: AppSettings) -> WipeDataResult:
    return asyncio.run(
        wipe_local_data(
            settings,
            secret_store=NoOpSecretStore(),
            connection_secret_refs=[],
        )
    )
```

Import dependency functions directly from their defining modules rather than reaching through non-exported module attributes.

- [ ] **Step 5: Run wipe tests and mypy**

Run: `uv run --project backend pytest backend/tests/test_wipe_data_api.py backend/tests/test_wipe_data_service.py -v`

Expected: PASS.

Run: `uv run --project backend mypy`

Expected: PASS with no errors.

- [ ] **Step 6: Commit wipe coordination and typing**

```bash
git add backend/app/api/wipe_data.py backend/tests/test_wipe_data_api.py backend/tests/test_wipe_data_service.py
git commit -m "fix(data): serialize sync and local wipe"
```

### Task 4: Move Live-Application Semantics To Backend Metrics

**Files:**
- Modify: `backend/app/db/repositories/metrics.py:506-519`
- Modify: `backend/app/services/metrics.py:65-101`
- Modify: `backend/app/models/metrics.py:208-225`
- Test: `backend/tests/test_metrics_summary_api.py`

- [ ] **Step 1: Write failing deterministic metric tests**

Insert applications across all statuses and assert only the existing live set is counted.
Add a composed-filter case to prove the count uses `_metrics_filter_where_clause`.

```python
response = client.get("/metrics/summary").json()
assert response["live_applications"] == 5

filtered = client.get("/metrics/summary?source=referral&work_mode=remote").json()
assert filtered["live_applications"] == 1
```

The canonical live set for this change is `applied`, `in_review`, `assessment`, `interview`, and `offer`, preserving the redesign's current visible semantics while moving authority to the backend.

- [ ] **Step 2: Run the focused summary tests and verify failure**

Run: `uv run --project backend pytest backend/tests/test_metrics_summary_api.py -k live -v`

Expected: FAIL because `MetricsSummaryResponse` has no `live_applications` field.

- [ ] **Step 3: Add a filtered repository count**

```python
def count_live_applications(self, filters: MetricsFilter | None = None) -> int:
    where_clause, filter_parameters = _metrics_filter_where_clause(filters)
    return self._fetch_count(
        f"""
        SELECT COUNT(*)
        FROM applications
        {where_clause}
        {"WHERE" if not where_clause else "AND"}
            current_status IN ('applied', 'in_review', 'assessment', 'interview', 'offer')
        """,
        filter_parameters,
    )
```

- [ ] **Step 4: Expose the count through the summary DTO and service**

Add the typed field:

```python
live_applications: int = Field(
    ge=0,
    description="Applications whose canonical current status is still live.",
)
```

Populate it in `MetricsSummaryService.get_summary` with `filters=filters`.

- [ ] **Step 5: Run metric and reconciliation tests**

Run: `uv run --project backend pytest backend/tests/test_metrics_summary_api.py backend/tests/test_metric_reconciliation.py backend/tests/test_metrics_api.py -v`

Expected: PASS.

- [ ] **Step 6: Commit deterministic live metrics**

```bash
git add backend/app/db/repositories/metrics.py backend/app/services/metrics.py backend/app/models/metrics.py backend/tests/test_metrics_summary_api.py
git commit -m "fix(metrics): make live count authoritative"
```

### Task 5: Align Generated Contracts And Frontend Copy

**Files:**
- Modify: `frontend/src/redesign/RedesignApp.tsx:307-343`
- Modify: `frontend/src/redesign/pages/OverviewPage.tsx:170-200`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/redesign/pages/OverviewPage.test.tsx`
- Regenerate: `frontend/src/api/openapi.json`
- Regenerate: `frontend/src/api/generated.ts`

- [ ] **Step 1: Write failing frontend tests**

Mock a `full_backfill` estimate and assert the sync menu says the full mailbox will be processed rather than “New mail only.”
Set `summary.live_applications` to a value that differs from the loaded application array and assert the summary value is rendered.

```tsx
expect(await screen.findByText(/Full mailbox history/)).toBeInTheDocument();
expect(screen.queryByText(/New mail only/)).not.toBeInTheDocument();

expect(await screen.findByText("7 still active")).toBeInTheDocument();
```

- [ ] **Step 2: Run focused Vitest files and verify failure**

Run: `npm run test -- src/App.test.tsx src/redesign/pages/OverviewPage.test.tsx`

Working directory: `frontend/`.

Expected: FAIL because the UI does not recognize `full_backfill` and derives the live count from application rows.

- [ ] **Step 3: Render lifecycle-aware estimate copy**

Handle `estimate.basis === "full_backfill"` before the nullable count branch.

```tsx
if (estimate.basis === "full_backfill") {
  setSyncEstimateLabel("Full mailbox history · time depends on mailbox size");
  return;
}
```

Keep “New mail only” only for `unknown_incremental`.

- [ ] **Step 4: Remove browser-owned live-status calculation**

Delete the `useMemo` that filters application statuses.
Render the backend value directly.

```tsx
note: summary
  ? `${summary.live_applications} still active`
  : "Active count unavailable",
```

Preserve application loading and error handling for sections that still consume application rows, but do not use those states to qualify the authoritative summary metric.

- [ ] **Step 5: Regenerate and verify the API client**

Run: `npm run generate:api`

Working directory: `frontend/`.

Expected: `SyncScopeEstimateBasis` includes `full_backfill` and `MetricsSummaryResponse` includes `live_applications` in both generated artifacts.

- [ ] **Step 6: Run focused frontend tests**

Run: `npm run test -- src/App.test.tsx src/redesign/pages/OverviewPage.test.tsx`

Working directory: `frontend/`.

Expected: PASS.

- [ ] **Step 7: Commit frontend and generated contract alignment**

```bash
git add frontend/src/redesign/RedesignApp.tsx frontend/src/redesign/pages/OverviewPage.tsx frontend/src/App.test.tsx frontend/src/redesign/pages/OverviewPage.test.tsx frontend/src/api/openapi.json frontend/src/api/generated.ts
git commit -m "fix(frontend): render authoritative sync and metrics state"
```

### Task 6: Full Verification And Pre-Merge Review

**Files:**
- Verify all files changed since `origin/main`

- [ ] **Step 1: Run complete backend quality gates**

Run: `uv run --project backend ruff format --check backend/app backend/tests`

Expected: PASS.

Run: `uv run --project backend ruff check backend/app backend/tests`

Expected: PASS.

Run: `uv run --project backend mypy`

Expected: PASS.

Run: `uv run --project backend pytest backend/tests -q`

Expected: all tests pass.

- [ ] **Step 2: Run complete frontend gate**

Run: `npm run check`

Working directory: `frontend/`.

Expected: OpenAPI staleness, typecheck, lint, Vitest, and build all pass.

- [ ] **Step 3: Run critical Playwright smoke tests**

Run: `npm run test:smoke`

Working directory: `frontend/`.

Expected: all smoke tests pass.

- [ ] **Step 4: Verify Git integrity**

Run: `git diff --check origin/main...HEAD`

Expected: no output.

Run: `git status --short --branch`

Expected: clean feature branch.

- [ ] **Step 5: Request independent pre-merge review**

Review `origin/main...HEAD` against:

- `docs/prd.md`
- `docs/groundwork-spec.md`
- `docs/questions.md`
- `docs/superpowers/specs/2026-07-11-redesign-contract-first-integration-design.md`
- `docs/superpowers/specs/2026-07-12-redesign-merge-hardening-design.md`

Expected: no Critical or Important findings.

- [ ] **Step 6: Push, create the PR, merge, and synchronize local main**

Inspect `git status`, `git diff origin/main...HEAD`, `git log --oneline -10`, and the complete PR commit range first.
Push the feature branch without force, create the PR with a requirements and verification summary, wait for required checks, and merge through `gh pr merge`.
Then check out local `main`, pull with `--ff-only`, and verify local `HEAD`, `origin/main`, and the merged PR commit agree.
