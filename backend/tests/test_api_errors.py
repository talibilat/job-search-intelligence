from __future__ import annotations

import app.main as main
import pytest
from app.api.errors import ApiError, ApiErrorCode
from fastapi import APIRouter, HTTPException, Query
from fastapi.testclient import TestClient


def test_api_error_maps_to_typed_error_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_router = APIRouter()

    @probe_router.get("/conflict")
    def conflict() -> None:
        raise ApiError(
            status_code=409,
            code=ApiErrorCode.CONFLICT,
            message="Application already exists.",
        )

    monkeypatch.setattr(main, "api_router", probe_router)

    client = TestClient(main.create_app())
    response = client.get("/conflict")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": "Application already exists.",
            "details": [],
        },
    }


def test_request_validation_error_uses_typed_error_without_raw_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_router = APIRouter()

    @probe_router.get("/items")
    def list_items(limit: int = Query(gt=0)) -> dict[str, int]:
        return {"limit": limit}

    monkeypatch.setattr(main, "api_router", probe_router)

    client = TestClient(main.create_app())
    response = client.get("/items?limit=not-an-integer")

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Request validation failed."
    assert payload["error"]["details"][0]["field"] == "query.limit"
    assert payload["error"]["details"][0]["type"]
    assert "integer" in payload["error"]["details"][0]["message"].lower()
    assert "input" not in response.text
    assert "not-an-integer" not in response.text


def test_http_exception_maps_to_typed_not_found_response() -> None:
    client = TestClient(main.create_app())

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not found.",
            "details": [],
        },
    }


def test_unmapped_http_exception_detail_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_router = APIRouter()

    @probe_router.get("/rate-limited")
    def rate_limited() -> None:
        raise HTTPException(status_code=429, detail="api key leaked")

    monkeypatch.setattr(main, "api_router", probe_router)

    client = TestClient(main.create_app())
    response = client.get("/rate-limited")

    assert response.status_code == 429
    assert response.json() == {
        "error": {
            "code": "http_error",
            "message": "HTTP error.",
            "details": [],
        },
    }
    assert "api key leaked" not in response.text


def test_unhandled_exception_returns_sanitized_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_router = APIRouter()

    @probe_router.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password leaked")

    monkeypatch.setattr(main, "api_router", probe_router)

    client = TestClient(main.create_app(), raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error.",
            "details": [],
        },
    }
    assert "database password leaked" not in response.text
