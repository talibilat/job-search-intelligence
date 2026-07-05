# LLM Provider Setup Guide

This guide explains the values a user needs before the first-run setup wizard can configure an LLM provider.
It maps to FR-0, FR-6, NFR-5, NFR-8, and Phase 0.

The current app has a typed provider registry, setup status shell, Gmail OAuth setup action, Azure OpenAI and local Ollama chat adapters behind `LLMProvider`, the classification prompt contract, and the structured extraction service.
Embedding calls and later insight, aggregation, and chat provider use remain deferred, so this document is the setup contract for those screens and adapters.
The current backend has the `SecretStore` protocol, backend selector settings, the default keyring adapter, and the encrypted Fernet fallback.

## Setup Principles

- No shared or bundled credentials are allowed in this repository.
- Bring your own Azure OpenAI resource or your own local Ollama runtime.
- Store secret values through the configured `SecretStore`, not in `backend/.env`.
- Use `backend/.env` only for non-secret local overrides such as endpoints, model names, deployment names, and `classification_mode`.
- Keep the app local-first: Ollama keeps LLM calls on the machine, while Azure OpenAI sends only configured LLM requests to the user's Azure resource.
- Keep LLM providers behind the configured app provider path; providers must never execute raw SQL or produce authoritative dashboard counts.
- Classification calls use the app's provider-neutral JSON-object prompt contract and validate responses with Pydantic before any classification or extraction result is stored.
- Structured extraction runs through `StructuredExtractionService`, which stores only accepted classification rows, records local run accounting, and returns malformed provider output as public-safe quarantine metadata.
- Never paste API keys, OAuth tokens, Google client secrets, or raw email content into docs, tickets, commits, logs, or screenshots.

## Choosing A Provider

Use Ollama when privacy and offline local execution matter more than model quality or speed.
Use Azure OpenAI when you want stronger hosted model quality and accept that configured LLM requests leave the machine for your Azure resource.

Default setup recommendations follow the selected provider when the user has not explicitly chosen a mode.
Use `local` with Ollama by default.
Use `hybrid` with Azure OpenAI for the default cost-controlled hosted path, where the heuristic filter narrows the inbox before hosted classification.
Use `llm` only when you intentionally want every ingested email to go through the selected LLM provider; with Azure OpenAI this sends every ingested email selected for classification to the hosted model.

## Azure OpenAI

Azure OpenAI requires a user-owned Azure OpenAI resource, one chat deployment, one embedding deployment, and one API key stored through `SecretStore`.
The API key is secret material and must not be placed in `backend/.env`.
The current Azure adapter supports chat-completions generation; embedding usage remains a later provider slice.

Set these non-secret values through the setup wizard or local environment overrides:

```env
JOBTRACKER_LLM_PROVIDER=azure_openai
JOBTRACKER_CLASSIFICATION_MODE=hybrid
JOBTRACKER_AZURE_OPENAI_ENDPOINT=https://<resource-name>.openai.azure.com
JOBTRACKER_AZURE_OPENAI_API_VERSION=2024-06-01
JOBTRACKER_AZURE_OPENAI_CHAT_DEPLOYMENT=<chat-deployment-name>
JOBTRACKER_AZURE_OPENAI_EMBEDDING_DEPLOYMENT=<embedding-deployment-name>
```

Store the API key under this secret reference when the setup flow or secret-store adapter is available:

```text
kind: llm_api_key
provider: azure_openai
name: api_key
```

Use the keyring setting as the encrypted-at-rest default:

```env
JOBTRACKER_SECRET_STORE_BACKEND=keyring
```

Switch to the documented Fernet fallback when keyring is unavailable and keep the key file inside the app-owned local data directory:

```env
JOBTRACKER_SECRET_STORE_BACKEND=fernet
JOBTRACKER_FERNET_KEY_FILE=./.jobtracker/fernet.key
```

Do not commit the Fernet key file or place it in screenshots, tickets, logs, or setup notes.

JT-096 provides durable local storage for completed-run token and cost accounting.
JT-091 aggregates provider-reported classification token usage on the service result before later run-accounting persistence is wired.
Before a bulk classification pass, call `GET /classification/estimate` to verify that the selected mode shows candidate, token, and cost information.
Before a version-controlled rerun, call `GET /classification/reprocessing-plan` to verify the selected provider has a configured target model and to see which retained candidates are unclassified, stale by model, or stale by prompt version.
Local mode reports zero cost, while hosted modes report cost only when both pricing rates are configured.
Hosted Azure calls should be used through the configured provider path only, never by ad hoc scripts that bypass redaction or prompt-version tracking.

Classification runs also use these non-secret settings:

```env
JOBTRACKER_CLASSIFICATION_BATCH_SIZE=25
JOBTRACKER_CLASSIFICATION_PROMPT_VERSION=v1
```

`JOBTRACKER_CLASSIFICATION_BATCH_SIZE` controls how many non-empty retained candidates one structured extraction batch attempts.
`JOBTRACKER_CLASSIFICATION_PROMPT_VERSION` is embedded in prompts, used to select stale classifications, and stored on accepted `email_classifications` rows plus `classification_runs` accounting.

Optional non-secret estimate settings are available when local heuristics or provider pricing needs to be tuned:

```env
JOBTRACKER_CLASSIFICATION_ESTIMATE_CHARS_PER_UNIT=4
JOBTRACKER_CLASSIFICATION_ESTIMATE_PROMPT_OVERHEAD_UNITS=300
JOBTRACKER_CLASSIFICATION_ESTIMATE_COMPLETION_UNITS_PER_CANDIDATE=500
JOBTRACKER_CLASSIFICATION_INPUT_COST_PER_1K_UNITS_USD=0
JOBTRACKER_CLASSIFICATION_OUTPUT_COST_PER_1K_UNITS_USD=0
```

Leave pricing rates at `0` when provider pricing is unknown; the endpoint still reports candidate and token estimates but marks non-local cost unavailable.

## Ollama

Ollama requires a local Ollama server and locally pulled chat and embedding models.
The current backend can call the configured chat model through `OllamaLLMProvider`; embedding calls are still deferred.
It does not require an API key in the provider registry.

Install Ollama from `https://ollama.com/`, start the local server, then pull the configured models:

```sh
ollama pull llama3.1
ollama pull nomic-embed-text
```

Set these non-secret values through the setup wizard or local environment overrides:

```env
JOBTRACKER_LLM_PROVIDER=ollama
JOBTRACKER_CLASSIFICATION_MODE=local
JOBTRACKER_OLLAMA_BASE_URL=http://127.0.0.1:11434
JOBTRACKER_OLLAMA_CHAT_MODEL=llama3.1
JOBTRACKER_OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

Keep the base URL local: the provider registry and runtime adapter reject non-local Ollama hosts so prompt content is not silently sent to a remote endpoint.
Local calls use a proxy-disabled urllib opener so environment or system HTTP proxy settings do not reroute Ollama traffic.
If you change model names, update both the setup value and any local model pulls so the provider adapter can resolve them consistently.

## Verify Provider Health

After selecting a provider and configuring its visible model or deployment names, call `POST /config/providers/llm/health` before bulk classification, insight, embedding, or chat runs that depend on the LLM.
The request body is empty because the backend derives the provider, chat model, and embedding model from the current non-secret settings.

The response is a provider-neutral `LLMProviderHealthCheckResponse` with the selected provider name, an overall `available` or `unavailable` status, and one check for the configured chat model plus one check for the configured embedding model.
For Azure OpenAI, the checked values are `azure_openai_chat_deployment` and `azure_openai_embedding_deployment`.
For Ollama, the checked values are `ollama_chat_model` and `ollama_embedding_model`.

Provider failures return sanitized typed API errors such as `llm_provider_unavailable`, `llm_provider_request_failed`, `llm_provider_invalid_response`, or `llm_provider_timeout`.
The shared API route exists before concrete Azure OpenAI and Ollama adapter HTTP checks land; until an adapter is dependency-injected, the route reports that the LLM provider adapter is not configured.

## Readiness Checklist

- The selected LLM provider is either `azure_openai` or `ollama`.
- `classification_mode` follows the intended default pairing for that provider unless the user explicitly chooses another provider-valid mode; Azure OpenAI still rejects `local`.
- Pre-run classification estimates show candidate and token counts, and hosted-provider cost only when pricing rates are configured.
- Reprocessing plans show `target_model_configured: true` and bucket retained candidates by stored model and prompt version before reruns are started.
- Azure OpenAI has endpoint, API version, chat deployment, embedding deployment, and an API key stored through `SecretStore`.
- Ollama has a reachable local base URL and the configured chat and embedding models are pulled locally.
- `POST /config/providers/llm/health` returns an `available` response for the configured chat and embedding models once the selected provider adapter is wired.
- Gmail setup still uses `gmail.readonly` and a user-owned Google OAuth client.
- LLM output is routed through application code that uses deterministic queries or constrained query builders for facts, never raw SQL emitted by the model.
- Classification provider responses are JSON objects that match `ClassificationPromptOutput`; malformed or contradictory output is rejected before storage.
- The classification service returns public-safe malformed metadata and does not write classification, application, or event rows directly.
- No API keys, OAuth tokens, client secrets, or provider credentials are committed to the repository.
