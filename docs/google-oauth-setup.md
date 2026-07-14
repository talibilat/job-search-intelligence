# Google OAuth Setup Guide

This guide documents the user-created Google OAuth client needed for Gmail ingestion.
It maps to FR-0, FR-0.2, FR-1.1, FR-6, FR-6.2, NFR-5, NFR-8, and Phase 1.

Gmail message listing and retained-body fetching read OAuth token material only through `SecretStore`.
The setup page can start Gmail OAuth through `GET /auth/gmail`, show the backend-built Google authorization URL, and report callback completion from `GET /setup/status`.
The backend completes the local callback with `GET /auth/gmail/callback`.
The callback exchanges the authorization code, validates the returned `gmail.readonly` scope, stores token material through the configured `SecretStore`, and persists only non-secret connection metadata in SQLite.
The Gmail provider refreshes expired stored credentials before metadata listing or retained-body fetching, preserves the stored refresh token, and keeps refreshed token material behind `SecretStore`.
Default sync resolves the latest non-reauth Gmail connection metadata from SQLite, runs full backfill until the replacement history cursor is promoted, and then uses the persisted incremental cursor on later syncs.
This guide documents the setup and runtime security contract the app must follow.

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
The local OAuth start endpoint builds a callback URL on the running backend at `/auth/gmail/callback`, and that callback is handled by the backend while the local process is running.

## Store The Client JSON Securely

Paste the downloaded Desktop OAuth client JSON into the Setup or Settings credential field.
The backend accepts it as `SecretStr`, validates its installed-client shape, and stores it through `SecretStore` under `oauth_client:gmail:desktop_client_json`.
The value is never returned by setup, configuration, readiness, or auth responses.

Existing environment-based installations may continue to use a file outside the repository as a bootstrap fallback.
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

## Start Gmail Authorization

After the backend is running, open `http://127.0.0.1:5173/setup`, save the downloaded Desktop client JSON, and use `Connect Gmail` to request an authorization URL from the backend.
The setup page shows a `Continue to Google` link and the requested `gmail.readonly` scope.

You can also request the same authorization URL directly from the backend:

```sh
curl http://127.0.0.1:8000/auth/gmail
```

The response contains the provider, requested scopes, OAuth state, and Google authorization URL:

```json
{
  "provider": "gmail",
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "generated-state",
  "requested_scopes": ["https://www.googleapis.com/auth/gmail.readonly"]
}
```

Open the `authorization_url`, or use the setup page's `Continue to Google` link, to authorize Gmail read-only access.
The backend does not return the Google client secret, access tokens, refresh tokens, or authorization codes from this endpoint.
If the client JSON is missing, unreadable, or invalid, the endpoint returns the standard typed `400` API error with a public-safe message.

## Complete Gmail Authorization

After you approve the Google consent prompt, Google redirects back to the running backend at `/auth/gmail/callback` with a one-time authorization code and the issued state.
The callback consumes the state once, treats the code as secret input, exchanges it with Google, verifies the granted scope is exactly `https://www.googleapis.com/auth/gmail.readonly`, fetches the Gmail profile email address, and returns non-secret connection metadata.

Example response shape:

```json
{
  "account": { "provider": "gmail", "account_id": "me@example.com" },
  "display_email": { "address": "me@example.com" },
  "credential_ref": {
    "kind": "oauth_token",
    "provider": "gmail",
    "name": "me-example-com"
  },
  "granted_scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
  "connected_at": "2026-07-05T00:00:00Z",
  "credential_expires_at": "2026-07-05T01:00:00Z",
  "reauth_required": false
}
```

The response never includes the raw authorization code, Google client secret, access token, or refresh token.
OAuth callback provider auth failures return typed `400` errors, transient Google failures return `503`, and other provider failures return `502` with public-safe messages.
Metadata-listing provider failures return typed `401`, `403`, `409`, `429`, `502`, or `503` errors with stable email-specific error codes and a `user_action` detail.
After callback metadata is persisted, `GET /setup/status` reports `gmail_connected: true` and the setup page shows `Gmail callback complete`.
Before migrations or OAuth have created `email_connections`, setup status safely reports `gmail_connected: false`.

## Token Storage Contract

Current Gmail metadata listing reads access tokens through the existing `SecretStore` seam.
OAuth callback codes are treated as secret values at the API boundary.
Access tokens and refresh tokens flow through `SecretStore`.
Refresh requests read the stored refresh token from `SecretStore`, exchange it with Google, validate the granted scope remains `gmail.readonly`, preserve the existing refresh token, and write the refreshed payload back through `SecretStore`.
The configured `SecretStore` adapter must store token material encrypted at rest, using OS keyring by default or the documented Fernet fallback.

Provider connection records persist only non-secret metadata and a `SecretRef` to the stored token.
Incremental sync history IDs are opaque provider cursor state, not token material; store them in local SQLite sync state scoped to the Gmail account and never log them with OAuth tokens or email content.
Logs, API responses, provider DTO dumps, and test fixtures must not expose raw token values.

## Metadata Listing Boundary

Current Gmail message listing is a safe metadata-only step for broad full backfill and incremental sync.
Full backfill captures the current Gmail profile `historyId` before the first page, calls Gmail message list pages with `maxResults` and `pageToken`, then fetches each listed message with `format=metadata` and Gmail partial fields.
When a full backfill has more pages, the Gmail page token is wrapped with that captured history cursor and the replacement sync cursor is withheld until the final page.
Incremental sync calls Gmail `users.history.list` with the stored history cursor, requests only `messageAdded` history records, de-duplicates repeated message IDs within a history page, and returns the replacement history cursor only after all history pages are drained.
Those partial fields include message IDs, thread IDs, labels, size estimates, and selected headers (`From`, `To`, `Cc`, `Subject`, `Date`, and `Message-ID`).
They deliberately exclude snippets, payload bodies, raw MIME content, and attachments.
Before metadata leaves the Gmail adapter, opaque message IDs, thread IDs, and history cursors are trimmed without case changes; email addresses are lowercased and deduplicated; display names and headers are trimmed; Gmail system labels are canonicalized while custom label IDs keep their casing; and parsed message timestamps are converted to timezone-aware UTC.
[JT-066 2026-07-05 v2] Backfill state and final replacement cursor promotion are repository-backed so full metadata backfills can resume safely.
Incremental sync cursors, metadata-only repository writes, and retained-body repository writes now flow through the sync service, `email_sync_state`, and `raw_emails` tables.
Broad job-search filter outcomes now flow through the sync service into `email_filter_decisions`, keyed by raw email ID and strategy.
The sync service evaluates metadata pages as batches so same-page candidate thread siblings use the same deterministic decision path for retained-body selection and audit rows.
Stored filter reasons are static signal tokens and must not include raw subjects, body text, snippets, OAuth tokens, Gmail thread IDs, or Gmail payloads.
Retained-body repository writes are insert-or-update, so an explicit candidate, debugging, or reconciliation body fetch can create a minimal `raw_emails` row before metadata arrives.
Gmail history `404` responses are treated as expired sync cursors so the sync service can fall back to resumable full metadata reconciliation.
Metadata-listing failures are mapped into public-safe provider errors: authorization failures ask the client to reconnect Gmail, insufficient scopes ask for read-only access, rate limits and temporary outages ask the client to try again later, invalid Gmail responses are reported without raw payloads, and generic provider failures do not expose OAuth tokens or Gmail response bodies.

Manual sync already uses the persisted non-secret connection metadata to pass a `SecretRef`-backed account to the Gmail provider and to persist public-safe filter decision audit rows after metadata persistence.
Thread-promoted audit rows use the static `thread_signal:candidate_thread` reason and never store the raw Gmail thread ID.
Expired credentials are refreshed inside the provider before Gmail metadata calls, and richer product-page behavior remains separate Phase 1 work.

## Retained Body Fetching Boundary

Current Gmail retained-body fetching is separate from broad metadata listing.
Callers must provide selected message refs, such as broad job-search candidates or explicit debugging and reconciliation refs.
The Gmail adapter fetches those messages with `format=full` and partial fields for IDs, thread IDs, and payload content only; it does not request snippets.
It prefers `text/plain`, converts `text/html` MIME bodies to normalized plain text through the provider DTO path, ignores attachments, reports typed empty-body failures, and keeps token material behind `SecretStore`.
Manual sync stores retained bodies for broad job-search candidate messages, including same-page candidate thread siblings, after metadata persistence.
Other explicit retained or debugging body fetches can be persisted safely even when the metadata row is not present yet.

## Preflight Checklist

- Gmail API is enabled in your own Google Cloud project.
- OAuth consent screen stays in Testing mode for personal use.
- Your Gmail account is listed as a test user.
- The OAuth client type is Desktop app.
- The downloaded client JSON is outside the repository.
- `JOBTRACKER_GMAIL_CLIENT_CONFIG_FILE` points to that file if you did not use the default path.
- The only Gmail scope is `https://www.googleapis.com/auth/gmail.readonly`.
- The `/setup` page can start Gmail OAuth and must show only the backend-built authorization URL, requested scope, and non-secret setup status.
- `GET /auth/gmail` returns a Google authorization URL and never returns client secrets or tokens.
- `GET /auth/gmail/callback` returns only non-secret connection metadata and stores token material through `SecretStore`.
- `POST /sync` uses the persisted non-secret Gmail connection metadata, refreshes expired Gmail credentials behind the provider seam, persists only public-safe filter decision reasons, and keeps OAuth token material behind `SecretStore`.
- No credentials, tokens, client JSON, or secret-store files are committed or logged.
