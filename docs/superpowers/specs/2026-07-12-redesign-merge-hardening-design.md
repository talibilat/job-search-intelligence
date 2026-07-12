# Redesign Merge Hardening Design

## Status

Approved in conversation on 2026-07-12.

This addendum hardens the redesign integration before it is merged into `main`.
It addresses defects found during pre-merge review without introducing a partial-data product mode or a general operation coordinator.

## Product Scope

The changes protect these requirements:

- FR-1.2 full historical backfill.
- FR-3.1 foundational counts.
- FR-3.6 deterministic metric integrity.
- FR-6.3 complete local data deletion.
- NFR-2 honest cost and runtime transparency.
- NFR-4 reliable and resumable synchronization.
- NFR-5 typed, maintainable code.
- Q-10 authoritative live-application reporting.

The design does not add sync cancellation, a partial-history dashboard mode, or provider-side message counting.

## Invariants

1. A Gmail account without a completed historical backfill always runs an unbounded lifetime backfill.
2. Date and message-count limits affect only accounts whose historical backfill is complete and whose incremental cursor exists.
3. Sync estimates describe the operation that `POST /sync` will actually execute for the same account state.
4. Sync and local-data wipe never run concurrently in one backend process.
5. A successful wipe cannot be followed by an already-running sync recreating deleted local data.
6. Dashboard live-application counts are computed by deterministic backend queries and returned through a typed API contract.
7. The complete backend and frontend verification gates pass before merge.

## Sync Scope Policy

`ConfiguredEmailSyncRuntime` remains responsible for selecting full backfill or incremental sync from durable backfill and cursor state.

When full backfill is required, the runtime passes unbounded `EmailSyncOptions` into the full-backfill service.
This normalization happens at the backend lifecycle boundary so direct API clients cannot accidentally create an incomplete source of truth.

The request may still contain date or message-count limits, but those limits are not applied until the account is eligible for incremental sync.
The frontend will present the lifetime scope honestly when backfill is required.

Focused tests will prove that a bounded first request lists all historical pages, completes the backfill, and promotes the replacement cursor only after the real final page.

## Sync Estimate Contract

The estimate path will inspect the same durable backfill and incremental-cursor state used by sync execution.

The estimate response will distinguish a required full backfill from an incremental sync.
A required full backfill will not use the `unknown_incremental` basis and will not be described as new mail only.
The estimate remains local and deterministic and does not call Gmail merely to count messages.

The frontend will map the full-backfill basis to copy that states the entire mailbox history will be processed and that the duration depends on mailbox size.
Incremental copy remains available only after historical backfill completion.

## Wipe Coordination

The existing `EmailSyncStatusStore` run lock will coordinate sync and wipe.
No new general lifecycle coordinator will be introduced.

The wipe API will attempt to acquire the shared run lock before resolving secret references or deleting data.
If another sync or wipe owns the lock, the endpoint will return a typed `409` conflict and make no deletion attempt.
The wipe operation will hold the lock through secret deletion and filesystem deletion, then release it in a `finally` block.

Scheduled and manual sync already enter through the configured sync runtime and therefore use this lock.
Holding the lock prevents a new scheduled run from starting while deletion is in progress.
Rejecting wipe while a sync is active avoids unsafe cancellation and avoids a request that blocks for an entire historical backfill.

## Live Application Metric

The backend metrics repository and summary service will define the statuses that count as live.
The summary DTO will expose a `live_applications` integer computed with the same composed filters as the other summary metrics.

The frontend overview will remove its local status-list calculation and render `summary.live_applications`.
The applications list remains available for activity and navigation, but it is not the authority for dashboard counts.

Repository, service, API, generated-client, and frontend tests will reconcile the live count against deterministic fixture data.

## Type Safety

The changed wipe tests will receive explicit fixture and helper annotations.
Dependency overrides will use exported typed dependency functions rather than dynamically typed or private module access.
No behavioral assertion will be weakened to satisfy mypy.

## Error Handling

Concurrent wipe returns the existing standard API error shape with HTTP `409` and a stable conflict code.
The response will not expose filesystem paths, secret references, scheduler internals, or sync details beyond the user action needed to retry.

Existing secret-deletion and unsafe-target failures retain their current public-safe behavior.
Full-backfill option normalization is not an error because lifetime history is the required first-sync contract.

## Data Model And Migration Impact

No new database table or migration is required.
The existing insight-citation migration remains unchanged.

The metrics response schema changes through the existing generated OpenAPI workflow.
No persisted compatibility layer is required because the application and generated client ship together as one local product.

## Verification

Focused backend tests will cover:

- A bounded first sync becoming an unbounded lifetime backfill.
- Cursor promotion only after the true final historical page.
- Full-backfill and incremental estimate bases.
- Wipe conflict while sync owns the operation lock.
- Lock release after successful and failed wipe operations.
- Deterministic live-application counts with composed filters.
- Typed wipe test setup under mypy.

Focused frontend tests will cover:

- Honest lifetime-backfill estimate copy.
- Rendering the backend `live_applications` value without local status semantics.
- Updated generated API contracts.

Final verification will run backend Ruff, mypy, pytest, the frontend `npm run check` gate, and the critical Playwright smoke suite.
The branch will be reviewed again after the fixes and before the pull request is merged.
