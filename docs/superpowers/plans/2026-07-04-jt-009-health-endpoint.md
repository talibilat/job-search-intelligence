# JT-009 Health Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `GET /health` as the first backend smoke endpoint for Phase 0.

**Architecture:** Keep `backend/app/main.py` unchanged because the JT-008 app factory already registers `api_router`.
Add a focused health route under `backend/app/api/`, a Pydantic DTO under `backend/app/models/`, and a smoke test that exercises the endpoint through the real FastAPI app factory.
The endpoint is liveness-only and must not check SQLite, providers, secrets, telemetry, or later-phase readiness state.

**Tech Stack:** FastAPI, Pydantic v2, pytest, strict mypy, ruff.

---

## File Structure

- Create `backend/app/api/health.py` for the `GET /health` route.
- Modify `backend/app/api/router.py` to include the health router.
- Create `backend/app/models/__init__.py` to export boundary DTOs.
- Create `backend/app/models/health.py` for `HealthResponse`.
- Create `backend/tests/test_health.py` for route and OpenAPI smoke coverage.
- Modify `README.md` to document the current backend health smoke endpoint.

## Task 0: Treehouse Worktree

**Files:** none.

- [ ] **Step 1: Lease an isolated worktree**

Run from the main repository checkout:

```bash
treehouse get --lease --lease-holder JT-009
```

Expected: Treehouse prints an absolute path to a dedicated worktree.

- [ ] **Step 2: Create the feature branch**

Run in the leased worktree:

```bash
git fetch origin
git switch -c jt-009-health-endpoint origin/main
git status --short --branch
```

Expected: branch `jt-009-health-endpoint` tracks `origin/main` and the worktree is clean.

## Task 1: Failing Health Tests

**Files:**

- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.mark.smoke
def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/health"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/HealthResponse"
```

- [ ] **Step 2: Run the tests to verify RED**

Run from `backend/`:

```bash
python3 -m pytest tests/test_health.py -v
```

Expected: tests fail because `/health` does not exist yet.

## Task 2: Health DTO

**Files:**

- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/health.py`

- [ ] **Step 1: Add the model package export**

```python
"""Pydantic DTOs used at application boundaries."""

from .health import HealthResponse

__all__ = ["HealthResponse"]
```

- [ ] **Step 2: Add the typed health response DTO**

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
```

## Task 3: Health Route

**Files:**

- Create: `backend/app/api/health.py`
- Modify: `backend/app/api/router.py`

- [ ] **Step 1: Add the health route**

```python
from __future__ import annotations

from fastapi import APIRouter

from app.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
```

- [ ] **Step 2: Register the health router**

```python
from __future__ import annotations

from fastapi import APIRouter

from .health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
```

- [ ] **Step 3: Run the focused tests to verify GREEN**

Run from `backend/`:

```bash
python3 -m pytest tests/test_health.py -v
```

Expected: both health tests pass.

## Task 4: README Update

**Files:**

- Modify: `README.md`

- [ ] **Step 1: Update the status and development sections**

Update the status text so it says the backend has an app factory, router registration, and `GET /health` smoke endpoint.
Add a development bullet documenting that `GET /health` returns `{"status": "ok"}`.

## Task 5: Verification

**Files:** none.

- [ ] **Step 1: Run focused route and app-factory tests**

Run from `backend/`:

```bash
python3 -m pytest tests/test_health.py tests/test_app_factory.py
```

Expected: all tests pass.

- [ ] **Step 2: Run smoke tests**

Run from `backend/`:

```bash
python3 -m pytest -m smoke
```

Expected: all selected smoke tests pass.

- [ ] **Step 3: Run full backend tests**

Run from `backend/`:

```bash
python3 -m pytest
```

Expected: all backend tests pass.

- [ ] **Step 4: Run strict type checking**

Run from `backend/`:

```bash
python3 -m mypy --config-file pyproject.toml
```

Expected: mypy exits successfully.

- [ ] **Step 5: Run linting**

Run from `backend/`:

```bash
python3 -m ruff check app tests
```

Expected: ruff exits successfully.

## Task 6: Commit And PR

**Files:** only the JT-009 files listed above.

- [ ] **Step 1: Inspect changes**

```bash
git status --short
git diff
git log --oneline -10
```

Expected: only JT-009 changes are present.

- [ ] **Step 2: Commit the implementation**

```bash
git add README.md backend/app/api/health.py backend/app/api/router.py backend/app/models/__init__.py backend/app/models/health.py backend/tests/test_health.py docs/superpowers/plans/2026-07-04-jt-009-health-endpoint.md
git commit -m "feat(backend): add health endpoint" -m "Closes #9"
```

- [ ] **Step 3: Push and create the PR**

```bash
git push -u origin jt-009-health-endpoint
gh pr create --base main --head jt-009-health-endpoint --title "feat(backend): add health endpoint" --body "Closes #9"
```

Expected: GitHub creates a PR that links and closes issue `#9` on merge.

## Task 7: Issue Update

**Files:** none.

- [ ] **Step 1: Comment on issue #9**

Use `gh issue comment 9` with a concise completion note that lists implementation files, verification commands, and that golden-set eval was not applicable.
