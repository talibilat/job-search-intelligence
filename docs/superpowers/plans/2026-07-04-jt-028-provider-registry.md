# JT-028 Provider Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a typed provider registry that declares supported email and LLM providers, their non-secret configuration requirements, secret references, and settings validation rules for JT-028.

**Architecture:** The registry is a pure backend provider-layer seam.
It uses the existing `AppSettings`, `EmailProviderName`, `LLMProviderName`, and `ClassificationMode` types from `app.config` and the existing `SecretRef` model from `app.security`.
It marks requirements as either declarative metadata or selected-provider validation requirements with `ProviderRequirementEnforcement`.
Gmail config and OAuth token requirements are declarative until setup/auth owns OAuth file lifecycle and secret storage.
Azure OpenAI and Ollama non-secret LLM settings are enforced when selected.
It does not instantiate adapters, call networks, read files, read secrets, or expose API routes.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI backend package layout, `uv`, `pytest`, `mypy`, and `ruff`.

## Global Constraints

- Work only in the current dedicated git worktree.
- Base the branch on `origin/main`, not the stale main checkout branch.
- Implement only GitHub issue `JT-028` / `#28`.
- Keep changes local-first and do not introduce telemetry.
- Do not add shared credentials, API keys, OAuth tokens, passwords, or client secrets to settings, `.env.example`, logs, tests, or registry output.
- Keep Gmail as the only email provider in this ticket.
- Keep Azure OpenAI and Ollama as the only LLM providers in this ticket.
- Do not add OpenAI, Anthropic, Outlook, IMAP, or other later-phase providers.
- Do not implement `EmailProvider` or `LLMProvider` strategy interfaces in this ticket because `JT-026` and `JT-027` own those contracts.
- Do not implement `GET|PUT /config/providers` because `JT-031` owns the API shell.
- Do not validate secret presence because setup and secret-store adapter tickets own secret reads and writes.
- Do not require the Gmail OAuth client JSON file to exist because first-run setup may not have created it yet.
- Do not push or create a PR until all implementation, verification, and `/no-mistakes` are clean, per the user instruction.
- Make the local commit required by `no-mistakes axi run` before starting that gate because no-mistakes validates committed history, not an uncommitted working tree.

---

## File Structure

- Create `backend/app/providers/__init__.py` to export the provider registry seam.
- Create `backend/app/providers/registry.py` to define provider registry DTOs, registry entries, lookup methods, and settings validation.
- Create `backend/tests/test_provider_registry.py` to verify registry contents, secret metadata, settings validation, and non-leakage behavior.
- Leave `backend/app/api/` unchanged because `JT-031` owns provider config API routes.
- Leave `backend/app/providers/email/` and `backend/app/providers/llm/` unchanged because `JT-026` and `JT-027` own provider interfaces.
- Leave `.env.example` unchanged because it already defines the provider settings needed by this ticket.

---

### Task 1: Registry Contract Tests

**Files:**

- Create: `backend/tests/test_provider_registry.py`
- Read: `backend/app/config.py`
- Read: `backend/app/security/secret_store.py`

**Interfaces:**

- Consumes: `AppSettings`, `ClassificationMode`, `EmailProviderName`, `LLMProviderName`, and `SecretKind`.
- Produces: executable test expectations for `ProviderRegistry`, `ProviderRequirementEnforcement`, `ProviderConfigurationError`, and `provider_registry`.

- [ ] **Step 1: Write failing tests for registry contents and metadata**

```python
from __future__ import annotations

import pytest
from app.config import AppSettings, ClassificationMode, EmailProviderName, LLMProviderName
from app.providers import (
    ProviderConfigurationError,
    ProviderRegistry,
    ProviderRequirementEnforcement,
    provider_registry,
)
from app.security import SecretKind


def test_registry_includes_exact_phase_zero_provider_names() -> None:
    assert {provider.name for provider in provider_registry.email_providers()} == set(EmailProviderName)
    assert {provider.name for provider in provider_registry.llm_providers()} == set(LLMProviderName)


def test_registry_declares_gmail_oauth_secret_ref_without_secret_values() -> None:
    gmail = provider_registry.get_email_provider(EmailProviderName.GMAIL)

    assert gmail.display_name == "Gmail"
    assert [requirement.setting_name for requirement in gmail.config_requirements] == [
        "gmail_client_config_file",
        "gmail_scopes",
    ]
    assert {requirement.enforcement for requirement in gmail.config_requirements} == {
        ProviderRequirementEnforcement.DECLARATIVE,
    }
    assert len(gmail.secret_requirements) == 1
    secret_ref = gmail.secret_requirements[0].ref
    assert secret_ref.kind is SecretKind.OAUTH_TOKEN
    assert secret_ref.provider == "gmail"
    assert secret_ref.name == "refresh_token"
    assert gmail.secret_requirements[0].enforcement is ProviderRequirementEnforcement.DECLARATIVE
    assert "token-value" not in gmail.model_dump_json()


def test_registry_declares_ollama_as_local_without_api_key_secret() -> None:
    ollama = provider_registry.get_llm_provider(LLMProviderName.OLLAMA)

    assert ollama.display_name == "Ollama"
    assert ollama.is_local is True
    assert ollama.secret_requirements == ()
    assert [requirement.setting_name for requirement in ollama.config_requirements] == [
        "ollama_base_url",
        "ollama_chat_model",
        "ollama_embedding_model",
    ]
    assert {requirement.enforcement for requirement in ollama.config_requirements} == {
        ProviderRequirementEnforcement.SELECTION,
    }


def test_registry_declares_azure_openai_api_key_ref_without_secret_value() -> None:
    azure = provider_registry.get_llm_provider(LLMProviderName.AZURE_OPENAI)

    assert azure.display_name == "Azure OpenAI"
    assert azure.is_local is False
    assert [requirement.setting_name for requirement in azure.config_requirements] == [
        "azure_openai_endpoint",
        "azure_openai_api_version",
        "azure_openai_chat_deployment",
        "azure_openai_embedding_deployment",
    ]
    assert len(azure.secret_requirements) == 1
    secret_ref = azure.secret_requirements[0].ref
    assert secret_ref.kind is SecretKind.LLM_API_KEY
    assert secret_ref.provider == "azure_openai"
    assert secret_ref.name == "api_key"
    assert azure.secret_requirements[0].enforcement is ProviderRequirementEnforcement.DECLARATIVE
    assert "super-secret" not in azure.model_dump_json()
```

- [ ] **Step 2: Write failing tests for settings validation**

```python
def test_default_settings_pass_provider_registry_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_name in AppSettings.env_var_names():
        monkeypatch.delenv(env_name, raising=False)

    settings = AppSettings(_env_file=None)

    provider_registry.validate_settings(settings)


def test_azure_openai_requires_non_secret_provider_metadata() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="",
        azure_openai_chat_deployment="",
        azure_openai_embedding_deployment="",
    )

    with pytest.raises(ProviderConfigurationError) as error:
        provider_registry.validate_settings(settings)

    assert error.value.provider_name == "azure_openai"
    assert error.value.missing_settings == (
        "azure_openai_endpoint",
        "azure_openai_chat_deployment",
        "azure_openai_embedding_deployment",
    )


def test_gmail_requirements_are_declarative_metadata_not_selection_validation() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.OLLAMA,
        classification_mode=ClassificationMode.LOCAL,
        gmail_client_config_file="   ",
    )

    provider_registry.validate_settings(settings)


def test_azure_openai_rejects_whitespace_only_provider_metadata() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="   ",
        azure_openai_chat_deployment="\t",
        azure_openai_embedding_deployment="\n",
    )

    with pytest.raises(ProviderConfigurationError) as error:
        provider_registry.validate_settings(settings)

    assert error.value.provider_name == "azure_openai"
    assert error.value.missing_settings == (
        "azure_openai_endpoint",
        "azure_openai_chat_deployment",
        "azure_openai_embedding_deployment",
    )


def test_azure_openai_rejects_local_classification_mode() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.LOCAL,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embeddings",
    )

    with pytest.raises(ProviderConfigurationError) as error:
        provider_registry.validate_settings(settings)

    assert error.value.provider_name == "azure_openai"
    assert error.value.message == "Azure OpenAI cannot be used with local classification mode."
    assert error.value.missing_settings == ()


def test_azure_openai_with_hybrid_mode_and_metadata_passes_validation() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider=LLMProviderName.AZURE_OPENAI,
        classification_mode=ClassificationMode.HYBRID,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embeddings",
    )

    provider_registry.validate_settings(settings)


def test_registry_can_be_instantiated_for_future_tests() -> None:
    registry = ProviderRegistry.default()

    assert registry.get_email_provider(EmailProviderName.GMAIL).name is EmailProviderName.GMAIL
    assert registry.get_llm_provider(LLMProviderName.OLLAMA).name is LLMProviderName.OLLAMA
```

- [ ] **Step 3: Run tests to verify they fail before implementation**

Run: `uv run pytest tests/test_provider_registry.py -v`

Expected: fail during import with a missing `app.providers` export or missing `registry` implementation.

---

### Task 2: Provider Registry Implementation

**Files:**

- Create: `backend/app/providers/__init__.py`
- Create: `backend/app/providers/registry.py`
- Test: `backend/tests/test_provider_registry.py`

**Interfaces:**

- Consumes: `AppSettings`, `ClassificationMode`, `EmailProviderName`, `LLMProviderName`, `SecretKind`, and `SecretRef`.
- Produces: `ProviderConfigRequirement`, `ProviderSecretRequirement`, `EmailProviderRegistration`, `LLMProviderRegistration`, `ProviderRequirementEnforcement`, `ProviderConfigurationError`, `ProviderRegistry`, and `provider_registry`.

- [ ] **Step 1: Add provider registry implementation**

```python
from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.config import AppSettings, ClassificationMode, EmailProviderName, LLMProviderName
from app.security import SecretKind, SecretRef


class ProviderRequirementEnforcement(StrEnum):
    DECLARATIVE = "declarative"
    SELECTION = "selection"


class ProviderConfigRequirement(BaseModel):
    """Non-secret setting required by a provider."""

    model_config = ConfigDict(frozen=True)

    setting_name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    required: bool = True
    enforcement: ProviderRequirementEnforcement = ProviderRequirementEnforcement.SELECTION


class ProviderSecretRequirement(BaseModel):
    """Secret-store reference required by a provider."""

    model_config = ConfigDict(frozen=True)

    ref: SecretRef
    label: str = Field(min_length=1)
    required: bool = True
    enforcement: ProviderRequirementEnforcement = ProviderRequirementEnforcement.DECLARATIVE


class EmailProviderRegistration(BaseModel):
    """Registry metadata for a supported email provider."""

    model_config = ConfigDict(frozen=True)

    name: EmailProviderName
    display_name: str = Field(min_length=1)
    config_requirements: tuple[ProviderConfigRequirement, ...] = ()
    secret_requirements: tuple[ProviderSecretRequirement, ...] = ()


class LLMProviderRegistration(BaseModel):
    """Registry metadata for a supported LLM provider."""

    model_config = ConfigDict(frozen=True)
    name: LLMProviderName
    display_name: str = Field(min_length=1)
    is_local: bool
    config_requirements: tuple[ProviderConfigRequirement, ...] = ()
    secret_requirements: tuple[ProviderSecretRequirement, ...] = ()


class ProviderConfigurationError(ValueError):
    """Raised when selected provider settings are incomplete or incompatible."""

    def __init__(
        self,
        *,
        provider_name: str,
        message: str,
        missing_settings: Sequence[str] = (),
    ) -> None:
        self.provider_name = provider_name
        self.message = message
        self.missing_settings = tuple(missing_settings)
        super().__init__(message)


class ProviderRegistry:
    """Typed registry for supported provider metadata and settings validation."""

    def __init__(
        self,
        *,
        email_providers: Iterable[EmailProviderRegistration],
        llm_providers: Iterable[LLMProviderRegistration],
    ) -> None:
        self._email_providers: dict[EmailProviderName, EmailProviderRegistration] = {
            provider.name: provider for provider in email_providers
        }
        self._llm_providers: dict[LLMProviderName, LLMProviderRegistration] = {
            provider.name: provider for provider in llm_providers
        }

        email_names = set(self._email_providers)
        llm_names = set(self._llm_providers)
        if email_names != set(EmailProviderName):
            raise ValueError("email provider registry must match EmailProviderName")
        if llm_names != set(LLMProviderName):
            raise ValueError("LLM provider registry must match LLMProviderName")

    @classmethod
    def default(cls) -> ProviderRegistry:
        return cls(
            email_providers=(
                EmailProviderRegistration(
                    name=EmailProviderName.GMAIL,
                    display_name="Gmail",
                    config_requirements=(
                        ProviderConfigRequirement(
                            setting_name="gmail_client_config_file",
                            label="Google OAuth client JSON path",
                            enforcement=ProviderRequirementEnforcement.DECLARATIVE,
                        ),
                        ProviderConfigRequirement(
                            setting_name="gmail_scopes",
                            label="Gmail OAuth scopes",
                            enforcement=ProviderRequirementEnforcement.DECLARATIVE,
                        ),
                    ),
                    secret_requirements=(
                        ProviderSecretRequirement(
                            ref=SecretRef(
                                kind=SecretKind.OAUTH_TOKEN,
                                provider="gmail",
                                name="refresh_token",
                            ),
                            label="Gmail OAuth refresh token",
                        ),
                    ),
                ),
            ),
            llm_providers=(
                LLMProviderRegistration(
                    name=LLMProviderName.AZURE_OPENAI,
                    display_name="Azure OpenAI",
                    is_local=False,
                    config_requirements=(
                        ProviderConfigRequirement(
                            setting_name="azure_openai_endpoint",
                            label="Azure OpenAI endpoint",
                        ),
                        ProviderConfigRequirement(
                            setting_name="azure_openai_api_version",
                            label="Azure OpenAI API version",
                        ),
                        ProviderConfigRequirement(
                            setting_name="azure_openai_chat_deployment",
                            label="Azure OpenAI chat deployment",
                        ),
                        ProviderConfigRequirement(
                            setting_name="azure_openai_embedding_deployment",
                            label="Azure OpenAI embedding deployment",
                        ),
                    ),
                    secret_requirements=(
                        ProviderSecretRequirement(
                            ref=SecretRef(
                                kind=SecretKind.LLM_API_KEY,
                                provider="azure_openai",
                                name="api_key",
                            ),
                            label="Azure OpenAI API key",
                        ),
                    ),
                ),
                LLMProviderRegistration(
                    name=LLMProviderName.OLLAMA,
                    display_name="Ollama",
                    is_local=True,
                    config_requirements=(
                        ProviderConfigRequirement(
                            setting_name="ollama_base_url",
                            label="Ollama base URL",
                        ),
                        ProviderConfigRequirement(
                            setting_name="ollama_chat_model",
                            label="Ollama chat model",
                        ),
                        ProviderConfigRequirement(
                            setting_name="ollama_embedding_model",
                            label="Ollama embedding model",
                        ),
                    ),
                ),
            ),
        )

    def email_providers(self) -> tuple[EmailProviderRegistration, ...]:
        return tuple(self._email_providers.values())

    def llm_providers(self) -> tuple[LLMProviderRegistration, ...]:
        return tuple(self._llm_providers.values())

    def get_email_provider(self, name: EmailProviderName) -> EmailProviderRegistration:
        return self._email_providers[name]

    def get_llm_provider(self, name: LLMProviderName) -> LLMProviderRegistration:
        return self._llm_providers[name]

    @staticmethod
    def _is_missing_required_setting(value: object) -> bool:
        if isinstance(value, str):
            return not value.strip()

        return not value

    def validate_settings(self, settings: AppSettings) -> None:
        self.get_email_provider(settings.email_provider)
        llm_provider = self.get_llm_provider(settings.llm_provider)
        missing_settings = tuple(
            requirement.setting_name
            for requirement in llm_provider.config_requirements
            if requirement.required
            and requirement.enforcement is ProviderRequirementEnforcement.SELECTION
            and self._is_missing_required_setting(getattr(settings, requirement.setting_name))
        )
        if missing_settings:
            raise ProviderConfigurationError(
                provider_name=settings.llm_provider.value,
                message="Selected LLM provider is missing required non-secret settings.",
                missing_settings=missing_settings,
            )
        if (
            settings.llm_provider is LLMProviderName.AZURE_OPENAI
            and settings.classification_mode is ClassificationMode.LOCAL
        ):
            raise ProviderConfigurationError(
                provider_name=settings.llm_provider.value,
                message="Azure OpenAI cannot be used with local classification mode.",
            )


provider_registry = ProviderRegistry.default()
```

- [ ] **Step 2: Export registry symbols from `backend/app/providers/__init__.py`**

```python
"""Provider registry and adapter seams."""

from .registry import (
    EmailProviderRegistration,
    LLMProviderRegistration,
    ProviderConfigRequirement,
    ProviderConfigurationError,
    ProviderRegistry,
    ProviderRequirementEnforcement,
    ProviderSecretRequirement,
    provider_registry,
)

__all__ = [
    "EmailProviderRegistration",
    "LLMProviderRegistration",
    "ProviderConfigRequirement",
    "ProviderConfigurationError",
    "ProviderRegistry",
    "ProviderRequirementEnforcement",
    "ProviderSecretRequirement",
    "provider_registry",
]
```

- [ ] **Step 3: Run focused provider registry tests**

Run: `uv run pytest tests/test_provider_registry.py -v`

Expected: all provider registry tests pass.

---

### Task 3: Verification, Issue Workflow, And Release Hygiene

**Files:**

- Read: `backend/app/providers/registry.py`
- Read: `backend/tests/test_provider_registry.py`
- Read: `docs/superpowers/plans/2026-07-04-jt-028-provider-registry.md`

**Interfaces:**

- Consumes: implemented provider registry and tests from Tasks 1 and 2.
- Produces: verified branch, final commit, pushed branch, PR targeting `main`, and updated GitHub issue workflow state.

- [ ] **Step 1: Run full backend tests**

Run: `uv run pytest`

Expected: all backend tests pass.

- [ ] **Step 2: Run backend type checking**

Run: `uv run mypy`

Expected: mypy reports success with no errors.

- [ ] **Step 3: Run backend lint check**

Run: `uv run ruff check .`

Expected: ruff reports no lint errors.

- [ ] **Step 4: Run backend format check**

Run: `uv run ruff format --check .`

Expected: ruff reports all files are already formatted.

- [ ] **Step 5: Inspect final diff before the local no-mistakes commit**

Run: `git status --short`

Expected: only JT-028 files are modified or added.

Run: `git diff -- backend/app/providers/__init__.py backend/app/providers/registry.py backend/tests/test_provider_registry.py README.md docs/conventions.md docs/superpowers/plans/2026-07-04-jt-028-provider-registry.md`

Expected: diff contains only the provider registry, tests, and documentation updates.

- [ ] **Step 6: Create the local commit required by no-mistakes**

Run: `git add backend/app/providers/__init__.py backend/app/providers/registry.py backend/tests/test_provider_registry.py README.md docs/conventions.md docs/superpowers/plans/2026-07-04-jt-028-provider-registry.md`

Run: `git commit -m "feat(config): add provider registry for JT-028"`

Expected: one local commit is created on `jt-028-provider-registry`, with no push yet.

- [ ] **Step 7: Run `/no-mistakes`**

Run the `no-mistakes` skill from the repository worktree.

Expected: the skill reports no remaining problems after any required fixes and repeated verification.

- [ ] **Step 8: Inspect final state before pushing**

Run: `git status --short`

Expected: working tree is clean after no-mistakes, or only no-mistakes-approved fix commits are present.

Run: `git log --oneline origin/main..HEAD`

Expected: commit history contains only JT-028 provider registry work.

- [ ] **Step 9: Push and create PR only after no-mistakes passes**

Run: `git push -u origin jt-028-provider-registry`

Run: `gh pr create --base main --head jt-028-provider-registry --title "feat(config): add provider registry" --body "Closes #28"`

Expected: PR is created targeting `main` and references `Closes #28`.

- [ ] **Step 10: Update GitHub issue**

Run: `gh issue comment 28 --body "Implemented in the JT-028 provider registry PR. Verification completed before PR creation."`

Expected: issue `#28` contains an implementation status comment.


---

## Self-Review

Spec coverage: this plan covers typed provider selection metadata, provider config validation, declarative requirement metadata, secret-reference metadata without secret values, local-first behavior, tests, and verification.

Scope gaps: no gap for JT-028; API route work remains intentionally assigned to JT-031, provider interfaces remain assigned to JT-026 and JT-027, and provider adapters remain later work.

Placeholder scan: the plan contains no TBD, TODO, or unspecified implementation steps.

Type consistency: later tasks use exactly the exported names defined in Task 2.
