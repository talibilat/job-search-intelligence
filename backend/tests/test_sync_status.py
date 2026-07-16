from app.main import create_app
from fastapi.testclient import TestClient


def test_sync_status_endpoint_exposes_typed_idle_status() -> None:
    client = TestClient(create_app())

    response = client.get("/sync/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "idle"
    assert payload["provider"] is None
    assert payload["account_id"] is None
    assert payload["mode"] is None
    assert payload["started_at"] is None
    assert payload["finished_at"] is None
    assert payload["page_count"] == 0
    assert payload["message_count"] == 0
    assert payload["raw_email_count"] == 0
    assert payload["recovered_from_expired_cursor"] is False
    assert payload["last_error"] is None


def test_sync_status_endpoint_is_documented_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/sync/status"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/EmailSyncStatus"
