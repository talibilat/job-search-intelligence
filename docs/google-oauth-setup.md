# Google OAuth Setup Guide

This guide documents the user-created Google OAuth client needed for Gmail ingestion.
It maps to FR-0, FR-0.2, FR-6, FR-6.2, NFR-5, NFR-8, and Phase 0.

Concrete Gmail OAuth runtime behavior is deferred to later Gmail ingestion tickets.
This guide only documents the setup contract the app must follow.

## Security Boundaries

- JobTracker is local-first and single-user.
- Use your own Google Cloud project and OAuth client.
- Do not use shared, bundled, checked-in, or hosted credentials.
- Do not commit Google OAuth client JSON, OAuth tokens, API keys, or generated secret-store files.
- Do not paste client secrets or tokens into issues, logs, screenshots, or chat transcripts.
- Gmail access is read-only in v1 and must use only `https://www.googleapis.com/auth/gmail.readonly`.
- Do not enable Gmail send, compose, modify, or mail settings scopes for v1.
- Do not add telemetry, autonomous outbound email, or auto-apply behavior.

## Create A Google Cloud Project

1. Open the Google Cloud Console at `https://console.cloud.google.com/`.
2. Create a project for this local app, such as `JobTracker Local`.
3. Open `APIs & Services`.
4. Enable the Gmail API for the project.

## Configure OAuth Consent For Personal Use

1. Open `APIs & Services` -> `OAuth consent screen`.
2. Choose the external user type if Google asks for a user type.
3. Keep the app in Testing mode for personal use.
4. Set an app name such as `JobTracker Local`.
5. Set your own Google account as the support email and developer contact email.
6. Add your Gmail account as a test user.
7. Add only the Gmail readonly scope: `https://www.googleapis.com/auth/gmail.readonly`.

Testing mode is enough for a personal local app using your own test user account.
Google verification and CASA are not part of the expected path for this personal test-user setup.
Do not move toward a public multi-user OAuth app unless the product scope changes and Google verification is explicitly planned.

## Create A Desktop OAuth Client

1. Open `APIs & Services` -> `Credentials`.
2. Choose `Create credentials` -> `OAuth client ID`.
3. Select `Desktop app` as the application type.
4. Name the client something local and recognizable, such as `JobTracker Desktop`.
5. Download the OAuth client JSON.

Use a Desktop app client, not a Web application client.
The future local OAuth flow should use the installed-app loopback flow and must not require a hosted callback service.

## Store The Client JSON Outside The Repo

Put the downloaded JSON somewhere outside the repository.
The default backend setting points to this path:

```text
~/.config/jobtracker/google-oauth-client.json
```

Recommended setup:

```sh
mkdir -p ~/.config/jobtracker
mv ~/Downloads/client_secret_*.json ~/.config/jobtracker/google-oauth-client.json
chmod 600 ~/.config/jobtracker/google-oauth-client.json
```

If you use a different path, set `JOBTRACKER_GMAIL_CLIENT_CONFIG_FILE` in your shell or in the local ignored `backend/.env` file:

```sh
JOBTRACKER_GMAIL_CLIENT_CONFIG_FILE=/absolute/path/to/google-oauth-client.json
```

The environment variable should contain only the local file path.
Do not paste the OAuth client JSON contents, client secret, authorization code, access token, or refresh token into `.env`.

## Keep The Scope Read-Only

The example config uses this scope:

```sh
JOBTRACKER_GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly
```

Do not add broader Gmail scopes.
The backend config validates that v1 uses only `gmail.readonly`, preserving read-only ingestion and preventing outbound email behavior.

## Token Storage Contract

When concrete Gmail OAuth behavior lands, OAuth callback codes must be treated as secret values.
Access tokens and refresh tokens must flow through the existing `SecretStore` seam.
The configured `SecretStore` adapter must store token material encrypted at rest, using OS keyring by default or the documented Fernet fallback.

Provider connection records should persist only non-secret metadata and a `SecretRef` to the stored token.
[JT-069 2026-07-05 v2] Incremental sync history IDs are opaque provider cursor state, not token material; store them in local SQLite sync state scoped to the Gmail account and never log them with OAuth tokens or email content.
Logs, API responses, provider DTO dumps, and test fixtures must not expose raw token values.

## Preflight Checklist

- Gmail API is enabled in your own Google Cloud project.
- OAuth consent screen stays in Testing mode for personal use.
- Your Gmail account is listed as a test user.
- The OAuth client type is Desktop app.
- The downloaded client JSON is outside the repository.
- `JOBTRACKER_GMAIL_CLIENT_CONFIG_FILE` points to that file if you did not use the default path.
- The only Gmail scope is `https://www.googleapis.com/auth/gmail.readonly`.
- No credentials, tokens, client JSON, or secret-store files are committed or logged.
