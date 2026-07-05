from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.config import GMAIL_READONLY_SCOPE, AppSettings, get_settings
from app.main import create_app
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
