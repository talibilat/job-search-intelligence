# Redesign Contract-First Integration Design

## Status

Approved for implementation on 2026-07-11.

## Goal

Make the new frontend function correctly against the existing backend architecture while preserving its visual design.

Every visible control must either perform its intended supported operation or state honestly that its roadmap capability is not available yet.
The frontend must not fabricate data or imply that a failed request is an empty result.

## Product And Phase Mapping

This work integrates capabilities already planned through Phase 4 without advancing the Phase 5 chat implementation.

- `FR-0.1`, `FR-0.3`: setup and provider configuration.
- `FR-1.1`, `FR-1.5`: Gmail connection and sync controls.
- `FR-2.8`: audited application and event corrections.
- `FR-3.1` through `FR-3.6`: deterministic dashboard data, filtering, and metric integrity.
- `FR-4.1` through `FR-4.3`: cached, grounded insights and regeneration.
- `Q-01` through `Q-46`: only where the redesign currently exposes the corresponding capability.

`FR-5.1` through `FR-5.6` and `Q-47` through `Q-50` remain Phase 5 work.
The chat drawer remains visually present but must not return a fabricated answer or claim that grounded chat is operational.

## Constraints

### Visual Freeze

Do not change the redesign's layout, typography, spacing, color system, visual hierarchy, or responsive structure.
Behavioral states may use the containers and visual language that already exist.
Any required accessibility fix must preserve the intended appearance.

### Backend Scope

Backend changes are allowed only when an existing frontend interaction cannot work correctly without them.
Such changes must preserve the established FastAPI route, service, repository, dependency injection, Pydantic DTO, and typed-error boundaries.

Do not add speculative endpoints, source-email body APIs, or Phase 5 chat generation.
The user-approved sole migration exception is the existing persisted insight-citations migration required to expose validated narrative evidence across reloads.
No other migration is approved by this design.

### Existing Worktree

The repository contains extensive user-owned uncommitted frontend and backend changes.
Implementation must work with those changes and must not revert, replace, or reformat unrelated work.

## Architecture

### API Boundary

Frontend application code imports API functions and DTOs through `frontend/src/api`.
It must not import directly from the generated client implementation.

FastAPI OpenAPI remains the wire-contract source of truth.
Generated artifacts are refreshed and checked through the existing frontend verification command when an API contract changes.

### Data Authority

The backend remains authoritative for application records, timelines, metrics, sync state, provider state, and insights.

Dashboard counts, rates, funnel stages, and date calculations come from deterministic backend endpoints.
The frontend may format values for display but must not redefine metric semantics.

### Minimal Backend Seams

The implementation completes these narrowly required seams:

- Resolve the existing Azure OpenAI adapter through normal LLM provider dependency injection when Azure is selected.
- Apply supported runtime sync-setting updates to the active scheduler rather than only mutating a settings object.

The implementation must prefer existing services and adapters over frontend-specific orchestration endpoints.
API DTOs change only if verification proves that an existing redesign interaction cannot be represented by the current contract.

## Interaction Design

### Gmail Connection

The Settings Gmail action calls `GET /auth/gmail`, validates the typed response, and redirects the browser to `authorization_url`.
It must not navigate directly to the JSON API route.

OAuth tokens and client secrets remain behind the backend `SecretStore` boundary.
The frontend receives no secret values.

### Sync

The existing sync menu submits supported scope options to `POST /sync` and reflects returned or subsequently fetched sync state.
Fixed historical custom-date defaults are replaced by values derived at interaction time or left empty until the user selects them.

Concurrent, unauthenticated, rate-limited, and provider failures surface the backend's public typed error message and appropriate retry behavior in the existing UI structure.

### Overview Metrics

Overview cards use `GET /metrics/summary` and `GET /metrics/rates` for their defined values.
The funnel uses `GET /metrics/funnel` rather than browser-constructed stages.

Links described as showing the applications behind a value must apply a filter that actually represents that value.
If the existing application-list contract cannot express a metric population, the UI must not claim that the resulting list is exact.

### Applications And Filters

Application filter state is represented in the route query string.
Reloading, browser navigation, and sharing the URL preserve the selected filter.

Supported backend filters are sent to `GET /applications` rather than reimplementing their semantics in the browser.
Composite presentation filters such as closed applications may map to a documented set of canonical backend statuses.

Table, board, and timeline views must apply the active filter consistently.
Timeline event requests occur only when the timeline view is active and only for the currently filtered applications.
This work does not add a speculative batch timeline endpoint.

### Application Detail And Corrections

Status changes call the existing audited status-correction endpoint and refresh local detail state from the typed response.

Each visible timeline correction control opens or activates the existing correction interaction and calls the audited event-edit endpoint.
Validation errors, manual-lock conflicts, missing source records, and not-found responses remain explicit and do not optimistically display a correction that failed.

Source-email labels are not described as links unless a supported destination exists.
This work does not add an API that exposes retained private email bodies.

### Insights

Insight labels and ordering map to the backend insight types and their PRD question contracts.
`why_rejected` represents Q-40 and `recurring_feedback` represents Q-41.

Regeneration calls the existing endpoint, keeps the previous cached insight visible while the request is pending, and replaces it only with a successful typed response.
Citation controls navigate only to real cited applications supported by the response.
Persisted citation records include only evidence IDs that the validated narrative content actually cites, not every evidence item supplied to generation.

Copy must not describe inferred evidence when the grounding contract allows only cited source evidence.

### Settings

Provider choices shown as operational must resolve through backend dependency injection and expose a usable health check.
Provider update failures must remain visible instead of being swallowed.

Runtime sync settings must either reconfigure the active scheduler successfully or report that they were not applied.
The UI must not imply that multiple connected inboxes are synchronized simultaneously if the backend selects only one default connection.

### Chat

The existing chat drawer remains visually unchanged.
Submitting suggestions or free text must not append a fake assistant answer.

Until Phase 5 is implemented, the drawer clearly reports that grounded chat is not yet available and prevents submission using the existing visual language.
Suggestion controls and free-text submission are disabled while chat is unavailable.
No `POST /chat`, LangGraph flow, vector retrieval, streaming protocol, or new chat-generation DTO is added in this work.

### Developer Inventory

Developer-facing capability status must reflect real route and interaction readiness rather than static optimistic labels.
The existing local registry remains the source for these labels and is updated to match verified implementation status.

## Error Handling

All redesigned data surfaces distinguish loading, empty, and failed states.
Overview summary, rates, applications, activity, detail, timeline, status totals, insights, and Settings mutations each preserve this distinction.

The frontend extracts messages from the standard typed API error shape:

```json
{
  "error": {
    "code": "stable_code",
    "message": "Public-safe explanation",
    "details": []
  }
}
```

Raw exception strings, secrets, OAuth tokens, email bodies, and provider payloads must not be displayed or logged.

Mutations disable duplicate submission while pending and restore controls after success or failure.
Frontend state updates only after the backend accepts a mutation, unless a reversible optimistic update is already safely implemented.

## Backend Capability Inventory

Create or update a Markdown document that lists backend capabilities which are implemented and verified but not exposed in the redesign.

For each capability, record:

- Route or service entry point.
- User-facing capability.
- Product phase and requirement or question IDs when applicable.
- Verification evidence.
- Reason it is intentionally not exposed.

The inventory must distinguish working unexposed capabilities from incomplete backend work and later-phase capabilities.

## Verification

### Frontend

Add focused Vitest coverage for:

- Gmail authorization redirect behavior.
- Deterministic overview and funnel endpoint usage.
- URL-backed application filters across views.
- Status and timeline event correction behavior.
- Insight type mapping, regeneration, and citations.
- Provider and scheduler settings success and failure states.
- Typed request failure rendering.
- Honest unavailable-chat behavior.

Update the tiny Playwright smoke suite to cover the redesign's critical route and interaction path.
The smoke suite must not depend on private inbox content.

Run `npm run check` from `frontend/` after backend dependencies are synchronized with `uv`.
Run the frontend test command explicitly for redesigned behavior.
Run the Playwright smoke suite for critical paths.

### Backend

Add focused tests only for backend behavior changed by this integration, especially provider resolution and live scheduler reconfiguration.

Run Ruff, mypy, and relevant pytest tests from `backend/`.
If API contracts change, regenerate and validate the TypeScript client.

### Visual Regression Guard

Inspect the final diff for redesign CSS, theme, markup hierarchy, and layout changes.
Any such change requires a direct functional or accessibility justification and must preserve the approved appearance.

## Completion Criteria

The work is complete when:

- Every current redesign control either performs its supported intended action or honestly indicates that its later-phase capability is unavailable.
- No production redesign path returns mocked application, metric, insight, sync, or chat results.
- Displayed dashboard values reconcile with deterministic backend endpoints.
- Existing visual design remains unchanged.
- Required frontend and backend checks pass with fresh evidence.
- The backend capability inventory accurately lists verified but unexposed functionality.
