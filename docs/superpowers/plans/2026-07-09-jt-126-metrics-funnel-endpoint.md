# JT-126 Metrics Funnel Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic `GET /metrics/funnel` using the approved Q-16 funnel stage contract.

**Architecture:** Keep the route thin, put response assembly in `MetricsFunnelService`, and keep SQL in `MetricsRepository`. The endpoint accepts the shared `MetricsFilter` query fields so dashboard filters can compose consistently with funnel numbers.

**Tech Stack:** FastAPI, Pydantic v2 DTOs, SQLite repository queries, pytest, ruff, mypy, generated OpenAPI TypeScript client.

---

### Task 1: Backend Funnel DTO And Repository Contract

**Files:**
- Modify: `backend/app/models/metrics.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/repositories/metrics.py`
- Test: `backend/tests/test_metrics_repository_queries.py`

- [ ] Write failing repository tests that expect funnel stages `applied`, `screen`, `interview`, `final`, and `offer`.
- [ ] Run `uv run --project backend pytest backend/tests/test_metrics_repository_queries.py -q` and verify the current `response`/`assessment` contract fails.
- [ ] Change `MetricFunnelStageName` to the approved stage names and add `MetricsFunnelResponse`.
- [ ] Update `MetricsRepository.get_funnel_metrics(filters=None)` so `screen` counts applications with any response-like evidence, `interview` counts `interview_scheduled`, `final` returns `0`, and `offer` counts offers after interviews.
- [ ] Rerun the focused repository tests and verify they pass.

### Task 2: Backend API Endpoint

**Files:**
- Modify: `backend/app/services/metrics.py`
- Modify: `backend/app/api/dependencies.py`
- Modify: `backend/app/api/metrics.py`
- Test: create `backend/tests/test_metrics_funnel_api.py`

- [ ] Write failing API tests for `GET /metrics/funnel`, OpenAPI documentation, and filter composition.
- [ ] Run `uv run --project backend pytest backend/tests/test_metrics_funnel_api.py -q` and verify it fails because the route is missing.
- [ ] Add `MetricsFunnelService`, FastAPI dependency, and `/metrics/funnel` route using the shared `get_metrics_filter` dependency.
- [ ] Rerun the focused API test and verify it passes.

### Task 3: Contract Generation And Documentation

**Files:**
- Modify: `frontend/src/api/openapi.json`
- Modify: `frontend/src/api/generated.ts`
- Create: `docs/tickets/JT-126.md`

- [ ] Run `npm run generate:api` from `frontend/` to regenerate frontend contracts.
- [ ] Add `docs/tickets/JT-126.md` documenting the approved funnel contract, including `final = 0 until final-round evidence exists`.
- [ ] Run backend verification: `uv run --project backend pytest backend/tests/test_metrics_funnel_api.py backend/tests/test_metrics_repository_queries.py -q`, `uv run --project backend ruff check backend`, and `cd backend && uv run mypy`.
- [ ] Run frontend contract verification: `cd frontend && npm run check`.
- [ ] Commit with `feat: add metrics funnel endpoint`.
