from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.config import EmailProviderName
from app.main import create_app
from app.models import SyncJobCounts, SyncJobError, SyncJobPhase, SyncJobStatus
from app.services.sync_service import build_idle_sync_status
from fastapi.testclient import TestClient
from pydantic import ValidationError

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_sync_job_status_tracks_phase_counts_errors_timestamps_and_progress() -> None:
    status = SyncJobStatus(
        phase=SyncJobPhase.METADATA_SYNC,
        provider=EmailProviderName.GMAIL,
        account_id="me@example.com",
        counts=SyncJobCounts(
            metadata_pages=2,
            metadata_messages=125,
            raw_emails_written=120,
            retained_bodies=18,
            errors=1,
        ),
        errors=(SyncJobError(message="provider rate limit", occurred_at=NOW),),
        started_at=NOW,
        updated_at=NOW + timedelta(seconds=30),
        completed_at=None,
        progress=0.25,
    )

    assert status.phase is SyncJobPhase.METADATA_SYNC
    assert status.counts.metadata_messages == 125
    assert status.errors[0].message == "provider rate limit"
    assert status.started_at == NOW
    assert status.updated_at == NOW + timedelta(seconds=30)
    assert status.progress == 0.25


def test_sync_job_status_rejects_invalid_progress() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        SyncJobStatus(
            phase=SyncJobPhase.METADATA_SYNC,
            counts=SyncJobCounts(),
            errors=(),
            started_at=NOW,
            updated_at=NOW,
            completed_at=None,
            progress=1.1,
        )


def test_sync_job_status_rejects_timestamps_before_start() -> None:
    with pytest.raises(ValidationError, match="updated_at cannot be before started_at"):
        SyncJobStatus(
            phase=SyncJobPhase.METADATA_SYNC,
            counts=SyncJobCounts(),
            errors=(),
            started_at=NOW,
            updated_at=NOW - timedelta(seconds=1),
            completed_at=None,
            progress=0,
        )


def test_build_idle_sync_status_returns_zero_progress_snapshot() -> None:
    status = build_idle_sync_status(now=NOW)

    assert status.phase is SyncJobPhase.IDLE
    assert status.provider is None
    assert status.account_id is None
    assert status.counts == SyncJobCounts()
    assert status.errors == ()
    assert status.started_at is None
    assert status.updated_at == NOW
    assert status.completed_at is None
    assert status.progress == 0


def test_sync_status_endpoint_exposes_typed_idle_status() -> None:
    client = TestClient(create_app())

    response = client.get("/sync/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "idle"
    assert payload["provider"] is None
    assert payload["account_id"] is None
    assert payload["counts"] == {
        "metadata_pages": 0,
        "metadata_messages": 0,
        "raw_emails_written": 0,
        "retained_bodies": 0,
        "errors": 0,
    }
    assert payload["errors"] == []
    assert payload["started_at"] is None
    assert payload["completed_at"] is None
    assert payload["progress"] == 0
    assert isinstance(datetime.fromisoformat(payload["updated_at"]), datetime)


def test_sync_status_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")


    assert response.status_code == 200
    operation = response.json()["paths"]["/sync/status"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/SyncJobStatus"
