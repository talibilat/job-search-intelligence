# JT-027 LLMProvider Interface Design

## Context

JT-027 defines the Phase 0 `LLMProvider` strategy seam for the local-first JobTracker backend.
The interface supports later classification, extraction, insights, and chat work without introducing provider implementations or application-specific behavior.

## Scope

This ticket owns only the provider-neutral interface, request and response DTOs, typed errors, package exports, tests, and a small documentation update.
Azure OpenAI implementation is deferred to JT-086.
Ollama implementation is deferred to JT-087.
Provider health checks are deferred to JT-088.
Classification prompts and prompt versioning are deferred to JT-089.
Classification DTOs are deferred to JT-090.
Extraction schemas and extraction services are deferred to JT-093 and JT-094.
Insight generation is deferred to JT-184.
Embedding methods and embedding DTOs are deferred to JT-198.

## Requirements

This design maps to FR-0, FR-6, NFR-5, NFR-8, and Phase 0.
It preserves the local-first architecture by keeping credentials out of provider DTOs and by avoiding telemetry or shared credentials.
It preserves the `applications` plus `application_events` invariant because it introduces no database writes, aggregation behavior, or metric behavior.
It preserves the raw SQL constraint because the interface does not accept SQL or expose any SQL execution behavior.

## Architecture

The backend package `app.providers.llm` will expose the public strategy seam.
The interface will be an async `Protocol` named `LLMProvider`.
The interface will use one generic generation method so downstream services can compose classification, extraction, insights, and chat behavior without coupling provider code to domain DTOs.

Expected public modules are:

- `app/providers/llm/provider.py` for `LLMProvider`.
- `app/providers/llm/types.py` for provider-neutral Pydantic DTOs and enums.
- `app/providers/llm/errors.py` for typed provider errors.
- `app/providers/llm/__init__.py` for stable exports.

## Interface Shape

`LLMProvider.generate()` will accept an `LLMGenerationRequest` and return an `LLMGenerationResponse`.
The method will be asynchronous to support network providers and local model servers without blocking the FastAPI event loop.
Provider-specific adapters will own credential lookup, HTTP clients, retry wiring, response translation, and provider payload parsing in later tickets.

The provider DTOs will model only generic LLM concepts.
They will include messages, roles, optional generation options, optional response format hints, response content, finish reason, model name, and optional token usage.
They will not include API keys, OAuth tokens, client secrets, provider registry behavior, persistence, cost math, or application-specific schemas.

## Error Handling

Provider failures will use typed exceptions derived from `LLMProviderError`.
Public-safe error types will distinguish unavailable providers, request failures, invalid responses, and timeouts.
Errors must not include raw prompts, private email content, API keys, OAuth tokens, tracebacks, or raw provider payloads.

## Testing

Contract tests will define a fake provider that satisfies `LLMProvider`.
Tests will cover valid generation round trips, Pydantic validation, public package exports, token usage validation, and typed error inheritance.
Tests will also assert that request and response models do not expose credential-shaped fields.

## Verification

The backend verification gate for this ticket is:

- `uv run pytest`
- `uv run mypy`
- `uv run ruff check .`
- `uv run ruff format --check .`

The golden-set eval is not required because JT-027 does not change classification prompts, model behavior, categories, extraction schemas, or persisted classifications.

## Worktree And Branch

All implementation work must happen in the current dedicated git worktree.
The implementation branch is `jt-027-llm-provider-interface` based on `origin/main`.

## Acceptance Mapping

The ticket behavior is implemented when downstream code can import and type against `LLMProvider` without knowing whether the concrete provider is Azure OpenAI, Ollama, or a future provider.
Relevant DTOs and boundaries are typed through Pydantic models and a Python protocol.
Tests provide the user-visible backlog artifact for this Phase 0 infrastructure ticket.
No classification behavior changes, no database invariants change, and no LLM-generated SQL path is introduced.
