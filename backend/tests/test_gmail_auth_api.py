from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.api.auth import get_gmail_email_provider
from app.config import GMAIL_READONLY_SCOPE, AppSettings, EmailProviderName, get_settings
from app.main import create_app
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailAttachmentPolicy,
    EmailAuthorizationCallbackRequest,
    EmailAuthorizationStartRequest,
    EmailAuthorizationStartResult,
    EmailConnection,
    EmailProviderCapabilities,
)
from app.security import SecretKind, SecretRef
from fastapi.testclient import TestClient


def write_google_oauth_client_config(tmp_path: Path) -> Path:
    client_config = tmp_path / "google-oauth-client.json"
    client_config.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-id.apps.googleusercontent.com",
                    "project_id": "jobtracker-local",
                    "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_secret": "super-secret-client-secret",
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )
    return client_config


def create_test_client(settings: AppSettings) -> TestClient:
    fastapi_app = create_app()
    fastapi_app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(fastapi_app, base_url="http://127.0.0.1:8000")


class FakeGmailProvider:
    name = EmailProviderName.GMAIL
    capabilities = EmailProviderCapabilities(
        provider=EmailProviderName.GMAIL,
        required_scopes=(GMAIL_READONLY_SCOPE,),
        supports_oauth=True,
        supports_full_backfill=True,
        supports_incremental_sync=True,
        attachment_policy=EmailAttachmentPolicy.IGNORED,
        max_metadata_page_size=500,
        max_body_batch_size=100,
    )

    def __init__(self) -> None:
        self.start_request: EmailAuthorizationStartRequest | None = None
        self.callback_request: EmailAuthorizationCallbackRequest | None = None

    async def start_authorization(
        self,
        request: EmailAuthorizationStartRequest,
    ) -> EmailAuthorizationStartResult:
        self.start_request = request
        return EmailAuthorizationStartResult(
            provider=request.provider,
            authorization_url=f"https://example.test/oauth?state={request.state}",
            state=request.state,
            requested_scopes=self.capabilities.required_scopes,
        )

    async def complete_authorization(
        self,
        request: EmailAuthorizationCallbackRequest,
    ) -> EmailConnection:
        self.callback_request = request
        return EmailConnection(
            account=EmailAccountRef(
                provider=request.provider,
                account_id="me@example.com",
            ),
            display_email=EmailAddress(address="me@example.com"),
            credential_ref=SecretRef(
                kind=SecretKind.OAUTH_TOKEN,
                provider="gmail",
                name="me-example-com",
            ),
            granted_scopes=(GMAIL_READONLY_SCOPE,),
            connected_at=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
        )


def test_gmail_auth_endpoint_returns_readonly_authorization_url_without_secrets(
    tmp_path: Path,
) -> None:
    client_config = write_google_oauth_client_config(tmp_path)
    client = create_test_client(AppSettings(_env_file=None, gmail_client_config_file=client_config))

    response = client.get("/auth/gmail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "gmail"
    assert payload["requested_scopes"] == [GMAIL_READONLY_SCOPE]
    assert payload["state"]

    authorization_url = payload["authorization_url"]
    parsed_url = urlparse(authorization_url)
    query = parse_qs(parsed_url.query)

    assert (parsed_url.scheme, parsed_url.netloc, parsed_url.path) == (
        "https",
        "accounts.google.com",
        "/o/oauth2/v2/auth",
    )
    assert query["client_id"] == ["client-id.apps.googleusercontent.com"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8000/auth/gmail/callback"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == [GMAIL_READONLY_SCOPE]
    assert query["state"] == [payload["state"]]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert "super-secret-client-secret" not in response.text
    assert "super-secret-client-secret" not in authorization_url


def test_gmail_auth_endpoint_returns_typed_error_for_missing_client_config(
    tmp_path: Path,
) -> None:
    client = create_test_client(
        AppSettings(_env_file=None, gmail_client_config_file=tmp_path / "missing.json")
    )

    response = client.get("/auth/gmail")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "bad_request",
            "message": "Google OAuth client config file was not found.",
            "details": [],
        }
    }


def test_gmail_auth_endpoint_uses_injected_email_provider() -> None:
    fastapi_app = create_app()
    fake_provider = FakeGmailProvider()
    fastapi_app.dependency_overrides[get_gmail_email_provider] = lambda: fake_provider
    fastapi_app.dependency_overrides[get_settings] = lambda: AppSettings(_env_file=None)
    client = TestClient(fastapi_app, base_url="http://127.0.0.1:8000")

    response = client.get("/auth/gmail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["authorization_url"] == f"https://example.test/oauth?state={payload['state']}"
    assert fake_provider.start_request is not None
    assert fake_provider.start_request.provider is EmailProviderName.GMAIL
    assert fake_provider.start_request.redirect_uri == "http://127.0.0.1:8000/auth/gmail/callback"


def test_gmail_auth_callback_completes_authorization_without_echoing_code() -> None:
    fastapi_app = create_app()
    fake_provider = FakeGmailProvider()
    fastapi_app.dependency_overrides[get_gmail_email_provider] = lambda: fake_provider
    fastapi_app.dependency_overrides[get_settings] = lambda: AppSettings(_env_file=None)
    client = TestClient(fastapi_app, base_url="http://127.0.0.1:8000")

    response = client.get(
        "/auth/gmail/callback",
        params={"code": "authorization-code", "state": "csrf-state"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["account"] == {"provider": "gmail", "account_id": "me@example.com"}
    assert payload["display_email"] == {"address": "me@example.com", "display_name": None}
    assert payload["credential_ref"] == {
        "kind": "oauth_token",
        "provider": "gmail",
        "name": "me-example-com",
    }
    assert payload["granted_scopes"] == [GMAIL_READONLY_SCOPE]
    assert "authorization-code" not in response.text
    assert "csrf-state" not in response.text

    assert fake_provider.callback_request is not None
    assert fake_provider.callback_request.provider is EmailProviderName.GMAIL
    assert fake_provider.callback_request.redirect_uri == (
        "http://127.0.0.1:8000/auth/gmail/callback"
    )
    assert fake_provider.callback_request.state == "csrf-state"
    assert fake_provider.callback_request.code.get_secret_value() == "authorization-code"
