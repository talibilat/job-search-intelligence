# JT-027 LLMProvider Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the provider-neutral async `LLMProvider` strategy seam for classification, extraction, insights, and chat consumers.

**Architecture:** Add a small `app.providers.llm` package with a protocol, Pydantic DTOs, and typed errors.
The interface exposes one generic generation method so later services can compose domain-specific behavior outside provider adapters.
The package contains no concrete provider implementations, no credentials, no embedding methods, no database access, and no API routes.

**Tech Stack:** Python 3.12, FastAPI backend package layout, Pydantic v2, async `Protocol`, pytest, mypy strict mode, Ruff.

## Global Constraints

- Work only in the current dedicated git worktree.
- Work only on GitHub issue JT-027.
- Keep all changes isolated to branch `jt-027-llm-provider-interface`.
- Keep JT-027 in Phase 0 and map it to FR-0, FR-6, NFR-5, NFR-8.
- Do not implement Azure OpenAI or Ollama clients.
- Do not add provider health checks.
- Do not add classification prompts, classification DTOs, extraction schemas, insight generation, chat routing, or embedding methods.
- Do not add telemetry, shared credentials, auto-apply behavior, autonomous outbound email, or multi-user SaaS assumptions.
- Do not add credential fields to LLM request or response DTOs.
- Do not introduce any SQL execution path.
- Do not commit until implementation, verification, and no-mistakes pass cleanly when a commit is explicitly requested.

---

## File Structure

- Create `backend/app/providers/llm/types.py` for provider-neutral Pydantic DTOs and enums.
- Create `backend/app/providers/llm/errors.py` for typed provider exceptions.
- Create `backend/app/providers/llm/provider.py` for the async `LLMProvider` protocol.
- Create `backend/app/providers/llm/__init__.py` for stable public exports.
- Delete `backend/app/providers/llm/.gitkeep` because the package will contain real source files.
- Create `backend/tests/test_llm_provider_contract.py` for contract and validation tests.
- Modify `README.md` to document the new backend LLM provider seam.
- Modify `docs/conventions.md` to clarify that LLM calls must go through `LLMProvider`.

---

### Task 1: Add Failing LLM Provider Contract Tests

**Files:**
- Create: `backend/tests/test_llm_provider_contract.py`

**Interfaces:**
- Consumes: public imports from `app.providers.llm` that do not exist yet.
- Produces: tests that define the required public API for Task 2 and Task 3.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/test_llm_provider_contract.py` with this content:

```python
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from app.providers.llm import (
    LLMFinishReason,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMMessage,
    LLMMessageRole,
    LLMProvider,
    LLMProviderError,
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
    LLMResponseFormat,
    LLMTokenUsage,
)
from pydantic import BaseModel, ValidationError


class FakeLLMProvider:
    provider_name = "fake"

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        return LLMGenerationResponse(
            content=request.messages[-1].content,
            model=request.model or "fake-model",
            finish_reason=LLMFinishReason.STOP,
            usage=LLMTokenUsage(
                prompt_tokens=3,
                completion_tokens=5,
                total_tokens=8,
            ),
        )


def test_fake_provider_satisfies_llm_provider_protocol() -> None:
    assert isinstance(FakeLLMProvider(), LLMProvider)


def test_llm_provider_generation_round_trip() -> None:
    provider = FakeLLMProvider()
    request = LLMGenerationRequest(
        messages=(
            LLMMessage(
                role=LLMMessageRole.SYSTEM,
                content="Answer using only grounded context.",
            ),
            LLMMessage(
                role=LLMMessageRole.USER,
                content="Summarize this application event.",
            ),
        ),
        model="fake-chat-model",
        response_format=LLMResponseFormat.TEXT,
        options=LLMGenerationOptions(
            temperature=0,
            max_output_tokens=256,
        ),
    )

    response = asyncio.run(provider.generate(request))

    assert response.content == "Summarize this application event."
    assert response.model == "fake-chat-model"
    assert response.finish_reason is LLMFinishReason.STOP
    assert response.usage == LLMTokenUsage(
        prompt_tokens=3,
        completion_tokens=5,
        total_tokens=8,
    )


def test_generation_request_requires_at_least_one_message() -> None:
    with pytest.raises(ValidationError):
        LLMGenerationRequest(messages=())


def test_generation_message_requires_content() -> None:
    with pytest.raises(ValidationError):
        LLMMessage(role=LLMMessageRole.USER, content="")


@pytest.mark.parametrize("temperature", [-0.1, 2.1])
def test_generation_options_reject_out_of_range_temperature(
    temperature: float,
) -> None:
    with pytest.raises(ValidationError):
        LLMGenerationOptions(temperature=temperature)


def test_generation_options_reject_non_positive_max_output_tokens() -> None:
    with pytest.raises(ValidationError):
        LLMGenerationOptions(max_output_tokens=0)


def test_token_usage_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        LLMTokenUsage(prompt_tokens=-1)


def test_llm_provider_errors_are_typed() -> None:
    errors = [
        LLMProviderUnavailableError(public_message="provider is unavailable"),
        LLMProviderRequestError(public_message="provider request failed"),
        LLMProviderResponseError(public_message="provider response was invalid"),
        LLMProviderTimeoutError(public_message="provider request timed out"),
    ]

    assert all(isinstance(error, LLMProviderError) for error in errors)


def test_llm_provider_errors_expose_only_public_message() -> None:
    error = LLMProviderRequestError(public_message="provider request failed")

    assert error.public_message == "provider request failed"
    assert str(error) == "provider request failed"
    assert error.args == ("provider request failed",)


def test_llm_provider_errors_reject_positional_messages() -> None:
    error_type: type[Any] = LLMProviderRequestError

    with pytest.raises(TypeError):
        error_type("raw provider payload")


def test_llm_boundary_models_do_not_define_credential_fields() -> None:
    credential_field_names = {
        "api_key",
        "access_token",
        "refresh_token",
        "client_secret",
        "password",
        "credential",
        "credentials",
        "oauth_token",
    }
    boundary_models: tuple[type[BaseModel], ...] = (
        LLMMessage,
        LLMGenerationOptions,
        LLMGenerationRequest,
        LLMGenerationResponse,
    )

    for model in boundary_models:
        assert credential_field_names.isdisjoint(model.model_fields)
```

- [ ] **Step 2: Run the contract tests to verify they fail**

Run from `backend/`:

```bash
uv run pytest tests/test_llm_provider_contract.py -v
```

Expected result: fail during import because `app.providers.llm` does not export the requested names.

---

### Task 2: Add LLM Provider Types And Errors

**Files:**
- Create: `backend/app/providers/llm/types.py`
- Create: `backend/app/providers/llm/errors.py`

**Interfaces:**
- Consumes: none.
- Produces: `LLMMessageRole`, `LLMResponseFormat`, `LLMFinishReason`, `LLMMessage`, `LLMGenerationOptions`, `LLMGenerationRequest`, `LLMTokenUsage`, `LLMGenerationResponse`, `LLMProviderError`, `LLMProviderUnavailableError`, `LLMProviderRequestError`, `LLMProviderResponseError`, and `LLMProviderTimeoutError`.

- [ ] **Step 1: Add provider-neutral Pydantic DTOs**

Create `backend/app/providers/llm/types.py` with this content:

```python
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LLMMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMResponseFormat(StrEnum):
    TEXT = "text"
    JSON_OBJECT = "json_object"


class LLMFinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"
    UNKNOWN = "unknown"


class LLMMessage(BaseModel):
    """One provider-neutral chat message."""

    model_config = ConfigDict(frozen=True)

    role: LLMMessageRole
    content: str = Field(min_length=1)


class LLMGenerationOptions(BaseModel):
    """Provider-neutral generation controls."""

    model_config = ConfigDict(frozen=True)

    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1)


class LLMGenerationRequest(BaseModel):
    """Provider-neutral request for text or JSON-object generation."""

    model_config = ConfigDict(frozen=True)

    messages: tuple[LLMMessage, ...] = Field(min_length=1)
    model: str | None = Field(default=None, min_length=1)
    response_format: LLMResponseFormat = LLMResponseFormat.TEXT
    options: LLMGenerationOptions = Field(default_factory=LLMGenerationOptions)


class LLMTokenUsage(BaseModel):
    """Provider-neutral token accounting returned by a provider when available."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class LLMGenerationResponse(BaseModel):
    """Provider-neutral generated content and metadata."""

    model_config = ConfigDict(frozen=True)

    content: str
    model: str = Field(min_length=1)
    finish_reason: LLMFinishReason = LLMFinishReason.UNKNOWN
    usage: LLMTokenUsage | None = None
```

- [ ] **Step 2: Add typed provider errors**

Create `backend/app/providers/llm/errors.py` with this content:

```python
from __future__ import annotations


class LLMProviderError(RuntimeError):
    """Base error for public-safe LLM provider failures."""

    public_message: str

    def __init__(self, *, public_message: str) -> None:
        self.public_message = public_message
        super().__init__(public_message)


class LLMProviderUnavailableError(LLMProviderError):
    """Raised when the configured LLM provider cannot be used."""


class LLMProviderRequestError(LLMProviderError):
    """Raised when a provider request fails before a valid response is returned."""


class LLMProviderResponseError(LLMProviderError):
    """Raised when a provider returns an invalid or unsupported response."""


class LLMProviderTimeoutError(LLMProviderError):
    """Raised when a provider request times out."""
```

- [ ] **Step 3: Run the contract tests to confirm the next missing interface**

Run from `backend/`:

```bash
uv run pytest tests/test_llm_provider_contract.py -v
```

Expected result: fail because `LLMProvider` and package exports are not wired yet.

---

### Task 3: Add LLMProvider Protocol And Package Exports

**Files:**
- Create: `backend/app/providers/llm/provider.py`
- Create: `backend/app/providers/llm/__init__.py`
- Delete: `backend/app/providers/llm/.gitkeep`

**Interfaces:**
- Consumes: `LLMGenerationRequest` and `LLMGenerationResponse` from `types.py`.
- Produces: async runtime-checkable `LLMProvider` protocol with `provider_name: str` and `generate(request: LLMGenerationRequest) -> LLMGenerationResponse`.

- [ ] **Step 1: Add the provider protocol**

Create `backend/app/providers/llm/provider.py` with this content:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import LLMGenerationRequest, LLMGenerationResponse


@runtime_checkable
class LLMProvider(Protocol):
    """Strategy seam for provider-specific LLM generation adapters."""

    provider_name: str

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        """Generate provider-neutral content for a typed request."""
        ...
```

- [ ] **Step 2: Add stable package exports**

Create `backend/app/providers/llm/__init__.py` with this content:

```python
"""Provider-neutral LLM strategy interface."""

from .errors import (
    LLMProviderError,
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from .provider import LLMProvider
from .types import (
    LLMFinishReason,
    LLMGenerationOptions,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMMessage,
    LLMMessageRole,
    LLMResponseFormat,
    LLMTokenUsage,
)

__all__ = [
    "LLMFinishReason",
    "LLMGenerationOptions",
    "LLMGenerationRequest",
    "LLMGenerationResponse",
    "LLMMessage",
    "LLMMessageRole",
    "LLMProvider",
    "LLMProviderError",
    "LLMProviderRequestError",
    "LLMProviderResponseError",
    "LLMProviderTimeoutError",
    "LLMProviderUnavailableError",
    "LLMResponseFormat",
    "LLMTokenUsage",
]
```

- [ ] **Step 3: Remove the placeholder file**

Delete `backend/app/providers/llm/.gitkeep`.

- [ ] **Step 4: Run the focused contract tests**

Run from `backend/`:

```bash
uv run pytest tests/test_llm_provider_contract.py -v
```

Expected result: all tests in `test_llm_provider_contract.py` pass.

---

### Task 4: Document The LLM Provider Seam

**Files:**
- Modify: `README.md`
- Modify: `docs/conventions.md`

**Interfaces:**
- Consumes: public package name `app.providers.llm` and interface name `LLMProvider` from Task 3.
- Produces: documentation that makes JT-027 visible as a Phase 0 architecture artifact.

- [ ] **Step 1: Update the README architecture table**

Add this row to the `Architecture at a glance` table in `README.md` after the `LLM providers` row:

```markdown
| LLM provider seam | Backend `app.providers.llm.LLMProvider` protocol with typed Pydantic generation DTOs |
```

- [ ] **Step 2: Update backend development notes**

In the `Development` section of `README.md`, update the backend description sentence so it includes the LLM provider seam:

```markdown
The backend has an initial FastAPI app factory, typed API error DTOs in `backend/app/api/errors.py`, the `app.providers.llm.LLMProvider` strategy seam, a `backend/pyproject.toml` with strict mypy defaults plus `uv` project metadata, `backend/pytest.ini`, and `backend/.env.example` documenting expected v1 operational settings.
```

- [ ] **Step 3: Update coding conventions**

Add this bullet to the `Architecture patterns` section of `docs/conventions.md` after the Strategy pattern bullet:

```markdown
- LLM calls go through the `app.providers.llm.LLMProvider` protocol using provider-neutral Pydantic generation DTOs; concrete provider adapters own vendor payloads and credential lookup.
```

- [ ] **Step 4: Run documentation-adjacent tests**

Run from `backend/`:

```bash
uv run pytest tests/test_llm_provider_contract.py tests/test_smoke.py -v
```

Expected result: the focused LLM provider contract tests and smoke test pass.

---

### Task 5: Run Full Verification And Prepare Final Review

**Files:**
- Read: changed files only.

**Interfaces:**
- Consumes: all outputs from Tasks 1 through 4.
- Produces: verified JT-027 implementation ready for no-mistakes.

- [ ] **Step 1: Run full backend tests**

Run from `backend/`:

```bash
uv run pytest
```

Expected result: all backend tests pass.

- [ ] **Step 2: Run strict type checking**

Run from `backend/`:

```bash
uv run mypy
```

Expected result: `Success: no issues found`.

- [ ] **Step 3: Run Ruff lint**

Run from `backend/`:

```bash
uv run ruff check .
```

Expected result: `All checks passed!`.

- [ ] **Step 4: Run Ruff format check**

Run from `backend/`:

```bash
uv run ruff format --check .
```

Expected result: all backend files are already formatted.

- [ ] **Step 5: Inspect changed files**

Run from the repository root:

```bash
git status --short
git diff --check
git diff --stat
```

Expected result: only JT-027 files are changed, no whitespace errors are reported, and no generated cache or virtualenv files are tracked.

- [ ] **Step 6: Run no-mistakes**

Run the repository's `/no-mistakes` flow from the JT-027 worktree.
Resolve every reported issue, then repeat this task's verification commands until no-mistakes reports no remaining problems.

- [ ] **Step 7: Commit only after no-mistakes passes**

After no-mistakes passes cleanly, inspect `git status`, `git diff`, and `git log --oneline -10`.
Stage only JT-027 files and commit with this message:

```bash
git commit -m "feat(backend): add LLM provider interface"
```

- [ ] **Step 8: Push and open the PR**

Push branch `jt-027-llm-provider-interface` and open a PR targeting `main`.
The PR body must include `Closes #27` and the verification evidence.

---

## Self-Review

- Spec coverage: Tasks 1 through 4 implement the provider-neutral interface, typed DTOs, typed errors, tests, and documentation artifact required by JT-027.
- Scope control: The plan excludes provider implementations, health checks, classification prompts, extraction schemas, insights, chat routing, embeddings, credentials, telemetry, database behavior, and API routes.
- Type consistency: The protocol method is consistently `generate(request: LLMGenerationRequest) -> LLMGenerationResponse`.
- Verification coverage: Task 5 runs pytest, mypy, Ruff lint, Ruff format, diff checks, no-mistakes, commit, push, and PR steps in the required order.
