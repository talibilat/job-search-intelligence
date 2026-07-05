from __future__ import annotations

from datetime import UTC, datetime

from app.api.sync import get_email_sync_runtime
from app.config import EmailProviderName
from app.main import create_app
from app.providers.email import EmailSyncMode
from app.services.sync_service import EmailSyncRunState, EmailSyncStatus
from fastapi.testclient import TestClient

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


class FakeSyncRuntime:
    def __init__(self) -> None:
        self.run_count = 0
        self.status = EmailSyncStatus(state=EmailSyncRunState.IDLE)

    async def run_manual_sync(self) -> EmailSyncStatus:
        self.run_count += 1
        self.status = EmailSyncStatus(
            state=EmailSyncRunState.SUCCEEDED,
            provider=EmailProviderName.GMAIL,
            account_id="me@example.com",
            mode=EmailSyncMode.FULL_BACKFILL,
            started_at=NOW,
            finished_at=NOW,
            page_count=1,
            message_count=2,
            raw_email_count=2,
            recovered_from_expired_cursor=False,
        )
        return self.status

    def current_status(self) -> EmailSyncStatus:
        return self.status


def test_post_sync_runs_injected_manual_sync_runtime() -> None:
    runtime = FakeSyncRuntime()
    app = create_app()
    app.dependency_overrides[get_email_sync_runtime] = lambda: runtime
    client = TestClient(app)

    response = client.post("/sync")

    assert response.status_code == 200
    assert runtime.run_count == 1
    assert response.json() == {
        "state": "succeeded",
        "provider": "gmail",
        "account_id": "me@example.com",
        "mode": "full_backfill",
        "started_at": "2026-07-05T12:00:00Z",
        "finished_at": "2026-07-05T12:00:00Z",
        "page_count": 1,
        "message_count": 2,
        "raw_email_count": 2,
        "recovered_from_expired_cursor": False,
        "last_error": None,
    }


def test_get_sync_status_returns_current_runtime_status() -> None:
    runtime = FakeSyncRuntime()
    app = create_app()
    app.dependency_overrides[get_email_sync_runtime] = lambda: runtime
    client = TestClient(app)

    response = client.get("/sync/status")

    assert response.status_code == 200
    assert response.json()["state"] == "idle"


def test_post_sync_returns_typed_error_until_gmail_connection_is_configured() -> None:
    client = TestClient(create_app())

    response = client.post("/sync")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "bad_request",
            "message": "Gmail connection is not configured yet.",
            "details": [],
        }
    }
