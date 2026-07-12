# Seven-Day Synced Email Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the misleading Overview activity panel with a ten-at-a-time, period-scoped synced-email reader that fetches sanitized message content on demand without classification.

**Architecture:** Add typed paginated preview and detail DTOs, extend `EmailRepository` with deterministic windowed pagination and local record lookup, and coordinate retained-body reuse or transient provider retrieval through a focused `SyncedEmailReaderService`. Expose thin FastAPI routes, regenerate the TypeScript client, and compose focused list and dialog components into the Overview page while `RedesignApp` passes the completed sync scope.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite, pytest, React 19, TypeScript, generated Orval client, Vitest, Testing Library, Playwright.

---

## File Map

- Modify `backend/app/models/raw_email.py`: define paginated preview and safe detail DTOs.
- Modify `backend/app/models/__init__.py`: export the new DTOs.
- Create `backend/app/db/migrations/versions/20260712_0202_raw_email_public_id.py`: add stable opaque public identifiers for existing and future raw-email rows.
- Modify `backend/app/db/repositories/email.py`: add stable windowed pagination and local reader lookup.
- Create `backend/app/services/synced_email_reader.py`: coordinate list queries, retained-body reuse, and transient provider fetches.
- Modify `backend/app/api/dependencies.py`: provide the reader repository/service connection.
- Modify `backend/app/api/sync.py`: expose paginated list and on-demand content routes with typed errors.
- Modify `backend/tests/test_email_repository.py`: lock down pagination, windows, ordering, and lookup.
- Create `backend/tests/test_synced_email_reader.py`: test service behavior independently of HTTP.
- Modify `backend/tests/test_sync_api.py`: verify API contracts and privacy boundaries.
- Regenerate `frontend/src/api/openapi.json` and `frontend/src/api/generated.ts`: consume the backend contract.
- Create `frontend/src/redesign/components/SyncedEmailList.tsx`: render ten-row pages and navigation.
- Create `frontend/src/redesign/components/EmailReaderDialog.tsx`: fetch and render on-demand content accessibly.
- Create `frontend/src/redesign/components/SyncedEmailList.test.tsx`: test pagination and list states.
- Create `frontend/src/redesign/components/EmailReaderDialog.test.tsx`: test loading, failure, retry, and close behavior.
- Modify `frontend/src/redesign/pages/OverviewPage.tsx`: replace application-event activity with the new reader.
- Modify `frontend/src/redesign/pages/OverviewPage.test.tsx`: verify integration and false-empty-state removal.
- Modify `frontend/src/redesign/RedesignApp.tsx`: pass the completed sync period and refresh token.
- Modify `frontend/src/App.test.tsx`: verify seven-day scope propagation and absence of classification calls.
- Modify `frontend/src/index.css`: add stable scroll, row, pagination, and modal styles.
- Modify `frontend/tests/smoke/phase0-shell.pw.ts`: cover the live seven-day reader path.

### Task 1: Typed Paginated Email Repository

**Files:**
- Create: `backend/app/db/migrations/versions/20260712_0202_raw_email_public_id.py`
- Modify: `backend/app/models/raw_email.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/repositories/email.py`
- Test: `backend/tests/test_email_repository.py`

- [ ] **Step 1: Write failing repository tests**

Add tests that insert 23 Gmail rows across two date windows, then assert page 2 contains ten rows, `total_items == 20`, `total_pages == 2`, and rows are ordered by `sent_at DESC, id DESC`.
Add a migration test that confirms existing rows receive unique 32-character lowercase hexadecimal `public_id` values and newly inserted rows receive a value through repository writes.
Add a lookup test that asserts `get_reader_record(public_id, provider=GMAIL)` resolves the internal provider message ref fields, safe headers, and retained body, while an unknown public ID returns `None`.

```python
page = repository.paginate_email_previews(
    provider=EmailProviderName.GMAIL,
    page=2,
    page_size=10,
    sent_after=datetime(2026, 7, 5, tzinfo=UTC),
    sent_before=datetime(2026, 7, 12, tzinfo=UTC),
)
assert page.page == 2
assert page.page_size == 10
assert page.total_items == 20
assert page.total_pages == 2
assert len(page.items) == 10
assert all(item.public_id for item in page.items)
```

- [ ] **Step 2: Run the repository tests and verify RED**

Run: `cd backend && uv run pytest tests/test_email_repository.py -k 'paginate_email_previews or reader_record' -v`

Expected: FAIL because the migration, `paginate_email_previews`, `get_reader_record`, and the page DTOs do not exist.

- [ ] **Step 3: Add the DTOs and repository queries**

Define:

```python
class RawEmailPreviewRecord(BaseModel):
    public_id: str
    from_domain: str | None
    to_domains: list[str]
    subject: str | None
    sent_at: datetime | None
    body_retention_state: RawEmailBodyRetentionState
    has_retained_body: bool
    provider: str
    ingested_at: datetime
    filter_outcome: str | None = None
    filter_reason: str | None = None


class RawEmailPreviewPage(BaseModel):
    items: list[RawEmailPreviewRecord]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class RawEmailReaderRecord(BaseModel):
    public_id: str
    provider_message_id: str = Field(repr=False)
    thread_id: str | None
    from_addr: str | None
    to_addr: str | None
    subject: str | None
    sent_at: datetime | None
    body_text: str | None = Field(default=None, repr=False)
    body_retention_state: RawEmailBodyRetentionState
    provider: str
```

Add `raw_emails.public_id`, backfill existing rows with `lower(hex(randomblob(16)))`, and create a unique index.
Generate `secrets.token_hex(16)` in repository upserts for new rows while conflict updates preserve the existing public ID.
Implement `paginate_email_previews` with shared `WHERE` clauses for provider, `sent_at >= sent_after`, and `sent_at < sent_before`, a count query, `LIMIT ? OFFSET ?`, and deterministic ordering.
Implement `get_reader_record` as one provider-scoped `public_id` query.
Do not expose `thread_id` or `body_text` through `RawEmailPreviewRecord`.

- [ ] **Step 4: Run repository tests and verify GREEN**

Run: `cd backend && uv run pytest tests/test_email_repository.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the repository increment**

```bash
git add backend/app/db/migrations/versions/20260712_0202_raw_email_public_id.py backend/app/models/raw_email.py backend/app/models/__init__.py backend/app/db/repositories/email.py backend/tests/test_email_repository.py
git commit -m "feat(sync): paginate synced email metadata"
```

### Task 2: On-Demand Reader Service

**Files:**
- Create: `backend/app/services/synced_email_reader.py`
- Test: `backend/tests/test_synced_email_reader.py`

- [ ] **Step 1: Write failing service tests**

Create fakes for `EmailRepository`, `EmailProvider`, and connection resolution.
Test these exact behaviors:

```python
detail = await service.read_email("public-retained")
assert detail.body_text == "Stored plain text"
assert provider.fetch_requests == []

detail = await service.read_email("public-metadata-only")
assert detail.body_text == "Fetched plain text"
assert len(provider.fetch_requests) == 1
assert repository.persisted_body_writes == []
```

Also test unknown local IDs, provider/account mismatch, empty body failure, provider not-found, reauthentication-required, and transient provider failure.

- [ ] **Step 2: Run service tests and verify RED**

Run: `cd backend && uv run pytest tests/test_synced_email_reader.py -v`

Expected: FAIL because `SyncedEmailReaderService` and its typed errors do not exist.

- [ ] **Step 3: Implement the focused service**

Define `SyncedEmailNotFoundError`, `SyncedEmailContentUnavailableError`, and `SyncedEmailReaderService`.
The constructor accepts an `EmailRepository`, `EmailProvider`, `EmailConnection`, and provider name.

```python
async def read_email(self, public_id: str) -> RawEmailDetail:
    record = self._repository.get_reader_record(public_id, provider=self._provider_name)
    if record is None:
        raise SyncedEmailNotFoundError
    if record.body_text is not None:
        return _detail_from_record(record, body_text=record.body_text, source="local")
    batch = await self._provider.fetch_message_bodies(
        self._connection,
        EmailBodyFetchRequest(refs=(_message_ref(record, self._connection),)),
    )
    if not batch.bodies:
        raise SyncedEmailContentUnavailableError(_public_failure_reason(batch))
    return _detail_from_record(record, body_text=batch.bodies[0].body_text, source="provider")
```

The service must never call `upsert_retained_bodies` during an on-demand read.
Map provider failures without logging message content or provider identifiers.

- [ ] **Step 4: Run service tests and verify GREEN**

Run: `cd backend && uv run pytest tests/test_synced_email_reader.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the service increment**

```bash
git add backend/app/services/synced_email_reader.py backend/tests/test_synced_email_reader.py
git commit -m "feat(sync): read email content on demand"
```

### Task 3: Paginated And Detail API Contracts

**Files:**
- Modify: `backend/app/api/dependencies.py`
- Modify: `backend/app/api/sync.py`
- Modify: `backend/tests/test_sync_api.py`

- [ ] **Step 1: Write failing API tests**

Add tests for:

```python
response = client.get(
    "/sync/emails?page=2&page_size=10&sent_after=2026-07-05T00:00:00Z"
)
assert response.status_code == 200
assert response.json()["page"] == 2
assert len(response.json()["items"]) == 10

detail = client.get("/sync/emails/0123456789abcdef0123456789abcdef/content")
assert detail.status_code == 200
assert detail.json()["body_text"] == "Private body"
```

Assert list responses omit `thread_id`, provider message IDs, and body text.
Assert detail 404, 401 reauthentication, 404 provider-message-missing, and 503 transient mappings use the standard public `ApiErrorResponse`.
Assert `page=0`, `page_size=0`, and `page_size=101` return 422.

- [ ] **Step 2: Run API tests and verify RED**

Run: `cd backend && uv run pytest tests/test_sync_api.py -k 'paginated_sync_emails or sync_email_content' -v`

Expected: FAIL with route-not-found responses.

- [ ] **Step 3: Add thin routes and dependencies**

Add `GET /sync/emails` returning `RawEmailPreviewPage` with `page: Query(ge=1)`, `page_size: Query(ge=1, le=100)`, and timezone-aware `sent_after` and `sent_before`.
Add `GET /sync/emails/{public_id}/content` returning `RawEmailDetail`.
Use `EmailRepository` and `SyncedEmailReaderService`; do not place SQL or Gmail parsing in route handlers.
Retain `GET /sync/recent-emails` for existing consumers until all callers migrate.

- [ ] **Step 4: Run API tests and backend static checks**

Run:

```bash
cd backend
uv run pytest tests/test_sync_api.py tests/test_synced_email_reader.py tests/test_email_repository.py -v
uv run ruff check app/models/raw_email.py app/db/repositories/email.py app/services/synced_email_reader.py app/api/sync.py app/api/dependencies.py tests/test_email_repository.py tests/test_synced_email_reader.py tests/test_sync_api.py
uv run mypy app/models/raw_email.py app/db/repositories/email.py app/services/synced_email_reader.py app/api/sync.py app/api/dependencies.py
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit the API increment**

```bash
git add backend/app/api/dependencies.py backend/app/api/sync.py backend/tests/test_sync_api.py
git commit -m "feat(api): expose synced email reader"
```

### Task 4: Regenerate The TypeScript API Client

**Files:**
- Modify generated: `frontend/src/api/openapi.json`
- Modify generated: `frontend/src/api/generated.ts`

- [ ] **Step 1: Generate from the verified FastAPI schema**

Run: `cd frontend && npm run generate:api`

Expected: generated functions for paginated sync emails and email content appear in `src/api/generated.ts`.

- [ ] **Step 2: Verify generated contracts**

Run: `cd frontend && node scripts/check-api-generation.mjs && npm run typecheck`

Expected: both commands exit 0.

- [ ] **Step 3: Commit generated artifacts**

```bash
git add frontend/src/api/openapi.json frontend/src/api/generated.ts
git commit -m "chore(api): generate synced email reader client"
```

### Task 5: Paginated Synced Email List

**Files:**
- Create: `frontend/src/redesign/components/SyncedEmailList.tsx`
- Create: `frontend/src/redesign/components/SyncedEmailList.test.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Write failing component tests**

Render a 23-item response and assert exactly ten row buttons, page buttons `1`, `2`, `3`, disabled `Previous` on page one, and enabled `Next`.
Click page 2 and assert the request contains `page=2&page_size=10` plus the supplied seven-day `sent_after` boundary.
Assert empty text is `No emails found in the selected period.` and list failure renders `Retry` without saying Gmail is disconnected.

- [ ] **Step 2: Run list tests and verify RED**

Run: `cd frontend && npm run test -- src/redesign/components/SyncedEmailList.test.tsx`

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement list rendering and pagination**

Create a controlled component with props:

```ts
interface SyncedEmailListProps {
  refreshToken: number;
  sentAfter?: string;
  sentBefore?: string;
  onOpenEmail: (email: RawEmailPreviewRecord) => void;
}
```

Fetch page size 10, reset to page one when `refreshToken`, `sentAfter`, or `sentBefore` changes, and render a stable `aria-label="Synced emails"` list.
Render a bounded pagination window around the current page rather than hundreds of page buttons.
Use `aria-current="page"` on the active page.

Add CSS with `max-height`, `overflow-y: auto`, stable row grid tracks, and `min-width: 0` on every flexible child.

- [ ] **Step 4: Run list tests and verify GREEN**

Run: `cd frontend && npm run test -- src/redesign/components/SyncedEmailList.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit the list increment**

```bash
git add frontend/src/redesign/components/SyncedEmailList.tsx frontend/src/redesign/components/SyncedEmailList.test.tsx frontend/src/index.css
git commit -m "feat(frontend): paginate synced inbox emails"
```

### Task 6: Accessible Email Reader Dialog

**Files:**
- Create: `frontend/src/redesign/components/EmailReaderDialog.tsx`
- Create: `frontend/src/redesign/components/EmailReaderDialog.test.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Write failing dialog tests**

Assert the dialog initially shows `Loading email`, then plain-text content.
Assert the close icon has accessible name `Close email`, Escape closes the dialog, focus returns to the triggering row, and a failed request shows `Email content could not be loaded` plus a working `Retry` button.
Assert body text is rendered as text and never injected with `dangerouslySetInnerHTML`.

- [ ] **Step 2: Run dialog tests and verify RED**

Run: `cd frontend && npm run test -- src/redesign/components/EmailReaderDialog.test.tsx`

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement the compact modal**

Render `role="dialog"`, `aria-modal="true"`, a labelled heading, metadata header, scrollable `<pre>` or whitespace-preserving text container, retry action, and close icon button.
Use a document keydown effect for Escape and a focus-management effect that focuses the dialog on open and restores the trigger on close.
Do not add a new UI dependency.

- [ ] **Step 4: Run dialog tests and verify GREEN**

Run: `cd frontend && npm run test -- src/redesign/components/EmailReaderDialog.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit the dialog increment**

```bash
git add frontend/src/redesign/components/EmailReaderDialog.tsx frontend/src/redesign/components/EmailReaderDialog.test.tsx frontend/src/index.css
git commit -m "feat(frontend): open synced email content"
```

### Task 7: Overview And Seven-Day Scope Integration

**Files:**
- Modify: `frontend/src/redesign/pages/OverviewPage.tsx`
- Modify: `frontend/src/redesign/pages/OverviewPage.test.tsx`
- Modify: `frontend/src/redesign/RedesignApp.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write failing integration tests**

Update Overview tests so metrics and applications remain independent while the inbox panel requests `/sync/emails` instead of `/applications/events/recent`.
Add an App test that selects `Last 7 days`, completes sync, and asserts the Overview request includes a seven-day `sent_after` boundary and no request path starts with `/classification`.
Assert clicking a row opens the reader dialog and closing it leaves the list on the same page.

- [ ] **Step 2: Run integration tests and verify RED**

Run: `cd frontend && npm run test -- src/redesign/pages/OverviewPage.test.tsx src/App.test.tsx`

Expected: FAIL because Overview still reads recent application events and does not receive sync scope.

- [ ] **Step 3: Pass completed scope state from RedesignApp**

Add an immutable completed-scope value updated only after a successful sync.
For scope `7`, compute the UTC start boundary used by the list; for custom scope, pass the chosen dates; for default incremental scope, omit fixed boundaries.
Pass `reloadKey`, `sentAfter`, and `sentBefore` to `OverviewPage`.

Replace Overview's `RecentApplicationEventRecord` state and fetch with `SyncedEmailList` and `EmailReaderDialog` state.
Remove the false `Nothing yet - run a sync to read your inbox` branch.
Do not change metrics, application cards, or classification behavior.

- [ ] **Step 4: Run integration and all frontend unit tests**

Run:

```bash
cd frontend
npm run test -- src/redesign/pages/OverviewPage.test.tsx src/App.test.tsx
npm run test
```

Expected: all tests pass with no console warnings.

- [ ] **Step 5: Commit the integration increment**

```bash
git add frontend/src/redesign/pages/OverviewPage.tsx frontend/src/redesign/pages/OverviewPage.test.tsx frontend/src/redesign/RedesignApp.tsx frontend/src/App.test.tsx
git commit -m "fix(frontend): show synced emails after scoped sync"
```

### Task 8: End-To-End Verification And Polish

**Files:**
- Modify: `frontend/tests/smoke/phase0-shell.pw.ts`

- [ ] **Step 1: Write the failing Playwright smoke assertion**

Extend the local app smoke test to select `Last 7 days`, run sync, wait for ten email rows, navigate to page 2 when available, open one row, verify the dialog contains plain text or the typed unavailable state, close it, and assert no `/classification` request occurred.

- [ ] **Step 2: Run smoke test and verify it detects missing behavior**

Run: `cd frontend && npm run test:smoke -- phase0-shell.pw.ts`

Expected before final integration: FAIL at the new synced-email row assertion.

- [ ] **Step 3: Run full required verification**

Run:

```bash
cd backend
uv run ruff check app tests
uv run mypy app
uv run pytest tests/test_email_repository.py tests/test_synced_email_reader.py tests/test_sync_api.py tests/test_gmail_email_provider.py tests/test_gmail_message_listing.py

cd ../frontend
npm run check
npm run test:smoke -- phase0-shell.pw.ts
```

Expected: every command exits 0.

- [ ] **Step 4: Perform visual browser verification**

At desktop and mobile viewport sizes, verify ten rows fit without text overlap, the list scrolls independently, pagination controls remain stable, the modal stays within the viewport, long unbroken content wraps, and focus/close behavior remains usable.
Verify the live seven-day request succeeds and the Overview no longer shows the false empty message while raw email rows exist.

- [ ] **Step 5: Commit smoke coverage and final polish**

```bash
git add frontend/tests/smoke/phase0-shell.pw.ts frontend/src/index.css
git commit -m "test: cover scoped synced email reader"
```

## Final Completion Checks

- [ ] Confirm `POST /sync` with `max_age_days: 7` succeeds and does not call classification.
- [ ] Confirm `/sync/emails` returns only the selected period, ten rows per page, and stable totals.
- [ ] Confirm opening retained content does not call Gmail and opening metadata-only content does not persist the transient body.
- [ ] Confirm list responses expose no body, provider message ID, thread ID, OAuth value, or secret.
- [ ] Confirm the modal renders normalized text only and ignores attachments.
- [ ] Confirm unrelated pre-existing worktree changes remain intact and outside feature commits.
