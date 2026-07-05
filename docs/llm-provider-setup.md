# LLM Provider Setup Guide

This guide explains the values a user needs before the first-run setup wizard can configure an LLM provider.
It maps to FR-0, FR-6, NFR-5, NFR-8, and Phase 0.

The current Phase 0 app has a typed provider registry, setup status shell, and Gmail OAuth setup action.
Concrete Azure OpenAI and Ollama adapters are implemented in later provider tickets, so this document is the setup contract for those screens and adapters.
The current backend has the `SecretStore` protocol, backend selector settings, the default keyring adapter, and the encrypted Fernet fallback.

## Setup Principles

- No shared or bundled credentials are allowed in this repository.
- Bring your own Azure OpenAI resource or your own local Ollama runtime.
- Store secret values through the configured `SecretStore`, not in `backend/.env`.
- Use `backend/.env` only for non-secret local overrides such as endpoints, model names, deployment names, and `classification_mode`.
- Keep the app local-first: Ollama keeps LLM calls on the machine, while Azure OpenAI sends only configured LLM requests to the user's Azure resource.
- Keep LLM providers behind the configured app provider path; providers must never execute raw SQL or produce authoritative dashboard counts.
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

When JT-096 and JT-097 land, verify before a bulk classification pass that the selected mode shows a token and cost estimate.
Hosted Azure calls should be used through the configured provider path only, never by ad hoc scripts that bypass redaction or prompt-version tracking.

## Ollama

Ollama requires a local Ollama server and locally pulled chat and embedding models.
It does not require an API key in the Phase 0 provider registry.

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

Keep the base URL local unless a later hosting decision explicitly approves a remote Ollama endpoint.
If you change model names, update both the setup value and any local model pulls so the provider adapter can resolve them consistently.

## Readiness Checklist

- The selected LLM provider is either `azure_openai` or `ollama`.
- `classification_mode` follows the intended default pairing for that provider unless the user explicitly chooses another provider-valid mode; Azure OpenAI still rejects `local`.
- Azure OpenAI has endpoint, API version, chat deployment, embedding deployment, and an API key stored through `SecretStore`.
- Ollama has a reachable local base URL and the configured chat and embedding models are pulled locally.
- Gmail setup still uses `gmail.readonly` and a user-owned Google OAuth client.
- LLM output is routed through application code that uses deterministic queries or constrained query builders for facts, never raw SQL emitted by the model.
- No API keys, OAuth tokens, client secrets, or provider credentials are committed to the repository.
