from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from alembic import command
from alembic.config import Config
from app.api.auth import (
    get_email_connection_repository,
    get_gmail_email_provider,
    get_gmail_secret_store,
    get_oauth_state_store,
)
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
    EmailProviderError,
    EmailProviderTransientError,
)
from app.security import SecretKind, SecretRef, SecretStoreUnavailableError
from app.services.gmail_auth import InMemoryOAuthStateStore
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]


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


def migrate_test_database(database_path: Path) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")


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


class FailingGmailProvider(FakeGmailProvider):
    def __init__(self, error: EmailProviderError) -> None:
        super().__init__()
        self.error = error

    async def complete_authorization(
        self,
        request: EmailAuthorizationCallbackRequest,
    ) -> EmailConnection:
        self.callback_request = request
        raise self.error


class CapturingConnectionRepository:
    def __init__(self) -> None:
        self.saved_connections: list[EmailConnection] = []

    def save_connection(self, connection: EmailConnection) -> EmailConnection:
        self.saved_connections.append(connection)
        return connection


class DisconnectConnectionRepository:
    def __init__(self, stored: EmailConnection) -> None:
        self.stored = stored
        self.deleted = False

    def fetch_connection_metadata(self, account: EmailAccountRef) -> EmailConnection | None:
        return None if self.deleted or account != self.stored.account else self.stored

    def delete_connection(self, account: EmailAccountRef) -> EmailConnection | None:
        if self.deleted or account != self.stored.account:
            return None
        self.deleted = True
        return self.stored


class DisconnectSecretStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deleted: list[SecretRef] = []

    async def delete_secret(self, ref: SecretRef) -> None:
        if self.fail:
            raise SecretStoreUnavailableError("private keyring failure")
        self.deleted.append(ref)


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


def test_gmail_auth_endpoint_uses_configured_public_api_url() -> None:
    fastapi_app = create_app()
    fake_provider = FakeGmailProvider()
    fastapi_app.dependency_overrides[get_gmail_email_provider] = lambda: fake_provider
    fastapi_app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        api_public_url="http://localhost:8000",
    )
    client = TestClient(fastapi_app, base_url="http://backend:8000")

    response = client.get("/auth/gmail")

    assert response.status_code == 200
    assert fake_provider.start_request is not None
    assert fake_provider.start_request.redirect_uri == "http://localhost:8000/auth/gmail/callback"


def test_disconnect_connection_maps_secret_store_failure_and_keeps_metadata() -> None:
    connection = EmailConnection(
        account=EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com"),
        credential_ref=SecretRef(kind=SecretKind.OAUTH_TOKEN, provider="gmail", name="me"),
        granted_scopes=(GMAIL_READONLY_SCOPE,),
        connected_at=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
    )
    repository = DisconnectConnectionRepository(connection)
    app = create_app()
    app.dependency_overrides[get_email_connection_repository] = lambda: repository
    app.dependency_overrides[get_gmail_secret_store] = lambda: DisconnectSecretStore(fail=True)

    response = TestClient(app).delete("/auth/connections/gmail/me@example.com")

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "service_unavailable",
        "message": "Stored credentials could not be removed. Try again.",
        "details": [],
    }
    assert repository.fetch_connection_metadata(connection.account) == connection
    assert "private keyring failure" not in response.text


def test_disconnect_connection_removes_secret_and_metadata() -> None:
    connection = EmailConnection(
        account=EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com"),
        credential_ref=SecretRef(kind=SecretKind.OAUTH_TOKEN, provider="gmail", name="me"),
        granted_scopes=(GMAIL_READONLY_SCOPE,),
        connected_at=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
    )
    repository = DisconnectConnectionRepository(connection)
    secret_store = DisconnectSecretStore()
    app = create_app()
    app.dependency_overrides[get_email_connection_repository] = lambda: repository
    app.dependency_overrides[get_gmail_secret_store] = lambda: secret_store

    response = TestClient(app).delete("/auth/connections/gmail/me@example.com")

    assert response.status_code == 200
    assert secret_store.deleted == [connection.credential_ref]
    assert repository.fetch_connection_metadata(connection.account) is None


def test_gmail_auth_callback_completes_authorization_without_echoing_code() -> None:
    fastapi_app = create_app()
    fake_provider = FakeGmailProvider()
    state_store = InMemoryOAuthStateStore()
    connection_repository = CapturingConnectionRepository()
    fastapi_app.dependency_overrides[get_gmail_email_provider] = lambda: fake_provider
    fastapi_app.dependency_overrides[get_oauth_state_store] = lambda: state_store
    fastapi_app.dependency_overrides[get_email_connection_repository] = lambda: (
        connection_repository
    )
    fastapi_app.dependency_overrides[get_settings] = lambda: AppSettings(_env_file=None)
    client = TestClient(fastapi_app, base_url="http://127.0.0.1:8000")

    start_response = client.get("/auth/gmail")
    state = start_response.json()["state"]

    response = client.get(
        "/auth/gmail/callback",
        params={"code": "authorization-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "http://127.0.0.1:5173/settings?gmail=connected"
    assert "authorization-code" not in response.text
    assert state not in response.text

    assert fake_provider.callback_request is not None
    assert fake_provider.callback_request.provider is EmailProviderName.GMAIL
    assert fake_provider.callback_request.redirect_uri == (
        "http://127.0.0.1:8000/auth/gmail/callback"
    )
    assert fake_provider.callback_request.state == state
    assert fake_provider.callback_request.code.get_secret_value() == "authorization-code"
    assert connection_repository.saved_connections


def test_gmail_auth_callback_persists_connection_with_real_repository_dependency(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jobtracker.sqlite3"
    migrate_test_database(database_path)
    fastapi_app = create_app()
    fake_provider = FakeGmailProvider()
    state_store = InMemoryOAuthStateStore()
    fastapi_app.dependency_overrides[get_gmail_email_provider] = lambda: fake_provider
    fastapi_app.dependency_overrides[get_oauth_state_store] = lambda: state_store
    fastapi_app.dependency_overrides[get_settings] = lambda: AppSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
    )
    client = TestClient(fastapi_app, base_url="http://127.0.0.1:8000")
    state = client.get("/auth/gmail").json()["state"]

    response = client.get(
        "/auth/gmail/callback",
        params={"code": "authorization-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT provider, account_id, credential_ref_name
            FROM email_connections
            """,
        ).fetchall()

    assert rows == [("gmail", "me@example.com", "me-example-com")]


def test_gmail_auth_callback_rejects_unissued_state_before_token_exchange() -> None:
    fastapi_app = create_app()
    fake_provider = FakeGmailProvider()
    state_store = InMemoryOAuthStateStore()
    fastapi_app.dependency_overrides[get_gmail_email_provider] = lambda: fake_provider
    fastapi_app.dependency_overrides[get_oauth_state_store] = lambda: state_store
    fastapi_app.dependency_overrides[get_email_connection_repository] = lambda: (
        CapturingConnectionRepository()
    )
    fastapi_app.dependency_overrides[get_settings] = lambda: AppSettings(_env_file=None)
    client = TestClient(fastapi_app, base_url="http://127.0.0.1:8000")

    response = client.get(
        "/auth/gmail/callback",
        params={"code": "authorization-code", "state": "csrf-state"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "bad_request",
            "message": "Gmail authorization state is invalid or expired.",
            "details": [],
        }
    }
    assert fake_provider.callback_request is None


def test_gmail_auth_callback_consumes_state_once() -> None:
    fastapi_app = create_app()
    fake_provider = FakeGmailProvider()
    state_store = InMemoryOAuthStateStore()
    fastapi_app.dependency_overrides[get_gmail_email_provider] = lambda: fake_provider
    fastapi_app.dependency_overrides[get_oauth_state_store] = lambda: state_store
    fastapi_app.dependency_overrides[get_email_connection_repository] = lambda: (
        CapturingConnectionRepository()
    )
    fastapi_app.dependency_overrides[get_settings] = lambda: AppSettings(_env_file=None)
    client = TestClient(fastapi_app, base_url="http://127.0.0.1:8000")
    state = client.get("/auth/gmail").json()["state"]

    first_response = client.get(
        "/auth/gmail/callback",
        params={"code": "authorization-code", "state": state},
        follow_redirects=False,
    )
    second_response = client.get(
        "/auth/gmail/callback",
        params={"code": "authorization-code", "state": state},
    )

    assert first_response.status_code == 303
    assert second_response.status_code == 400
    assert second_response.json()["error"]["message"] == (
        "Gmail authorization state is invalid or expired."
    )


def test_gmail_auth_callback_maps_provider_transient_errors() -> None:
    fastapi_app = create_app()
    fake_provider = FailingGmailProvider(
        EmailProviderTransientError(public_message="Gmail provider is temporarily unavailable.")
    )
    state_store = InMemoryOAuthStateStore()
    fastapi_app.dependency_overrides[get_gmail_email_provider] = lambda: fake_provider
    fastapi_app.dependency_overrides[get_oauth_state_store] = lambda: state_store
    fastapi_app.dependency_overrides[get_email_connection_repository] = lambda: (
        CapturingConnectionRepository()
    )
    fastapi_app.dependency_overrides[get_settings] = lambda: AppSettings(_env_file=None)
    client = TestClient(fastapi_app, base_url="http://127.0.0.1:8000")
    state = client.get("/auth/gmail").json()["state"]

    response = client.get(
        "/auth/gmail/callback",
        params={"code": "authorization-code", "state": state},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Gmail provider is temporarily unavailable.",
            "details": [],
        }
    }


def test_gmail_auth_callback_maps_general_provider_errors() -> None:
    fastapi_app = create_app()
    fake_provider = FailingGmailProvider(
        EmailProviderError(public_message="Gmail profile lookup returned invalid data.")
    )
    state_store = InMemoryOAuthStateStore()
    fastapi_app.dependency_overrides[get_gmail_email_provider] = lambda: fake_provider
    fastapi_app.dependency_overrides[get_oauth_state_store] = lambda: state_store
    fastapi_app.dependency_overrides[get_email_connection_repository] = lambda: (
        CapturingConnectionRepository()
    )
    fastapi_app.dependency_overrides[get_settings] = lambda: AppSettings(_env_file=None)
    client = TestClient(fastapi_app, base_url="http://127.0.0.1:8000")
    state = client.get("/auth/gmail").json()["state"]

    response = client.get(
        "/auth/gmail/callback",
        params={"code": "authorization-code", "state": state},
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "bad_gateway",
            "message": "Gmail profile lookup returned invalid data.",
            "details": [],
        }
    }
