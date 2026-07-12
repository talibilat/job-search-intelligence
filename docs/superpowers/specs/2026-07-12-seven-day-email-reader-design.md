# Seven-Day Synced Email Reader Design

## Product Mapping

This change supports FR-1.2, FR-1.3, and FR-1.5 in Phase 1.
It improves visibility into Gmail ingestion without running Phase 2 classification or changing deterministic application metrics.

The selected sync scope controls which Gmail messages are checked.
Choosing `Last 7 days` must never classify the full local database or automatically invoke an LLM.

## Problem

The Overview panel titled `Latest from your inbox` currently reads recent application events.
After a successful metadata sync, it can therefore display `Nothing yet - run a sync to read your inbox` even when thousands of raw email rows exist locally.
The message is false because the panel is not reading synced inbox metadata.

The current recent-email endpoint also returns a fixed list without stable pagination, omits a frontend-safe row identifier, and cannot retrieve message content on demand.

## User Experience

The Overview page will show a scrollable Gmail-style list under `Latest from your inbox`.
The list displays ten rows per page.
Each row shows public-safe summary fields such as sender domain, subject availability or subject when permitted by the existing privacy contract, sent date, body-retention state, and filter status.

The list provides `Previous`, numbered page buttons, and `Next`.
The current page is visibly and accessibly selected.
Pagination does not trigger classification.
The list container has a stable height and scrolls independently so changing pages does not move the surrounding dashboard.

After a successful sync, the list returns to page one and refreshes.
For a seven-day sync, the list is constrained to the same seven-day period.
If the period has no messages, the panel says `No emails found in the selected period.`

Clicking one email opens a compact modal dialog.
The dialog has a visible close icon, supports Escape, traps focus, and restores focus to the clicked row when closed.
The dialog shows a loading state while content is retrieved and clear unavailable and retry states when retrieval fails.

The modal renders sanitized plain text only.
It does not render raw HTML or fetch attachments.

## Data And API Design

### Paginated Metadata

Replace the Overview panel's application-event request with a paginated raw-email metadata request.
The backend endpoint accepts:

- `page`, starting at 1.
- `page_size`, fixed to 10 from this UI and bounded by the API.
- `sent_after` and `sent_before` for the selected sync period.
- `order`, fixed to newest `sent_at` first for this panel.

The response contains:

- `items` with public-safe metadata and an opaque local email identifier.
- `page`, `page_size`, `total_items`, and `total_pages`.

The opaque identifier is the local raw-email primary key.
Provider message IDs, thread IDs, OAuth material, body snippets, and secrets are not exposed in list responses.
Ordering is deterministic by `sent_at` descending with the local identifier as the tie-breaker.

### On-Demand Content

A detail endpoint accepts the opaque local email identifier.
The service resolves the matching local record and Gmail connection internally.

If a retained plain-text body already exists locally, the endpoint returns it without contacting Gmail.
Otherwise, the Gmail provider fetches the message body on demand using the existing readonly OAuth connection and normalizes it to plain text.
An on-demand body fetched for a metadata-only message is returned transiently and is not persisted merely because the user opened the message.

The endpoint returns public-safe headers needed by the modal plus normalized plain text.
It returns typed not-found, reauthentication-required, provider-unavailable, and content-unavailable errors.

## Component Boundaries

The Overview page owns the selected page and selected-email modal state.
A focused email-list component owns list rendering, scroll containment, and pagination controls.
A focused email-reader dialog owns content loading, retry, accessibility, and close behavior.

Generated API DTOs remain the frontend boundary.
FastAPI routes remain thin.
Pagination queries belong in the email repository, period and pagination coordination belongs in a service, and Gmail body retrieval stays behind the `EmailProvider` adapter.

## Scope State

The sync menu already maps `Last 7 days` to `max_age_days: 7`.
The successful sync result will publish the completed scope to the Overview email list so its period matches the user's request.
The default incremental scope shows the newest locally stored mailbox messages because the provider cursor, rather than a fixed date, defines that sync.

Changing pages reads local metadata only and never calls Gmail.
Opening a metadata-only message is the only action that may call Gmail after synchronization.

## Privacy And Security

The feature preserves `gmail.readonly` scope.
It does not fetch or expose attachments.
It does not render raw HTML.
It does not log message content, provider identifiers, OAuth tokens, or secrets.
It does not broaden body retention beyond the existing candidate-retention rules.
All list and detail access remains local to the single-user backend.

## Error Handling

List failures keep the panel visible and show a retry action without implying that Gmail is disconnected.
An empty page caused by a changed total moves to the last valid page or page one.
Content retrieval failures remain inside the modal and do not clear the email list.
Reauthentication errors direct the user to Settings.
Provider 404 responses report that the message is no longer available and do not fail the overall sync state.

## Verification

Backend tests will verify deterministic pagination, seven-day bounds, stable ordering, invalid page validation, opaque identifier lookup, retained-body reuse, transient Gmail body retrieval, missing messages, and public-safe errors.

Frontend tests will verify ten rows per page, numbered navigation, Previous and Next states, independent scrolling, refresh to page one after sync, seven-day query propagation, modal loading and retry states, close-button and Escape behavior, and the absence of classification requests.

The Playwright smoke flow will select `Last 7 days`, run sync, confirm that real metadata rows replace the false empty state, change pages, open one message, close the modal, and confirm that no classification request occurs.

Required verification is backend Ruff, mypy, focused pytest, frontend `npm run test`, frontend `npm run check`, and the critical Playwright smoke flow.

## Out Of Scope

This change does not run classification, create applications, populate dashboard metrics, store attachments, render email HTML, add full mailbox search, or provide message mutation actions such as archive, delete, reply, or mark unread.
