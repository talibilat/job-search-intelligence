# LLM Provider Setup Guide

This guide explains the values a user needs before the first-run setup wizard can configure an LLM provider.
It maps to FR-0, FR-6, NFR-5, NFR-8, and Phase 0.

The current Phase 0 app has a typed provider registry and setup status shell.
Concrete Azure OpenAI and Ollama adapters are implemented in later provider tickets, so this document is the setup contract for those screens and adapters.

## Setup Principles

- No shared or bundled credentials are allowed in this repository.
- Bring your own Azure OpenAI resource or your own local Ollama runtime.
- Store secret values through the configured `SecretStore`, not in `backend/.env`.
- Use `backend/.env` only for non-secret local overrides such as endpoints, model names, deployment names, and `classification_mode`.
- Keep the app local-first: Ollama keeps LLM calls on the machine, while Azure OpenAI sends only configured LLM requests to the user's Azure resource.
- Never paste API keys, OAuth tokens, Google client secrets, or raw email content into docs, tickets, commits, logs, or screenshots.

## Choosing A Provider

Use Ollama when privacy and offline local execution matter more than model quality or speed.
Use Azure OpenAI when you want stronger hosted model quality and accept that configured LLM requests leave the machine for your Azure resource.

`classification_mode` must match the provider choice.
Use `local` with Ollama.
Use `hybrid` with Azure OpenAI for the default cost-controlled path, or `llm` when you intentionally want every candidate to go through the hosted model.

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

Before running a bulk classification pass, verify that the selected mode will show a token and cost estimate.
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
- `classification_mode` is compatible with that provider.
- Azure OpenAI has endpoint, API version, chat deployment, embedding deployment, and an API key stored through `SecretStore`.
- Ollama has a reachable local base URL and the configured chat and embedding models are pulled locally.
- Gmail setup still uses `gmail.readonly` and a user-owned Google OAuth client.
- No API keys, OAuth tokens, client secrets, or provider credentials are committed to the repository.
