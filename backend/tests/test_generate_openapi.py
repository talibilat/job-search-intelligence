from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from types import ModuleType

import pytest


def import_generate_openapi() -> ModuleType:
    try:
        return import_module("scripts.generate_openapi")
    except ModuleNotFoundError as error:
        pytest.fail(f"OpenAPI generator script is missing: {error}")


def test_generate_openapi_schema_uses_backend_app_factory() -> None:
    generator = import_generate_openapi()

    schema = generator.generate_openapi_schema()

    assert schema["info"]["title"] == "Job Search Intelligence API"
    assert schema["paths"]["/health"]["get"]["responses"]["200"]["description"]


def test_ghost_inference_openapi_advertises_validation_errors() -> None:
    generator = import_generate_openapi()

    schema = generator.generate_openapi_schema()

    responses = schema["paths"]["/applications/ghost-inference"]["post"]["responses"]
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }


def test_sync_openapi_advertises_validation_errors() -> None:
    generator = import_generate_openapi()

    schema = generator.generate_openapi_schema()

    responses = schema["paths"]["/sync"]["post"]["responses"]
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }


def test_classification_run_openapi_advertises_validation_errors() -> None:
    generator = import_generate_openapi()

    schema = generator.generate_openapi_schema()

    responses = schema["paths"]["/classification/run"]["post"]["responses"]
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }


def test_write_openapi_schema_writes_deterministic_json(tmp_path: Path) -> None:
    generator = import_generate_openapi()
    output_path = tmp_path / "nested" / "openapi.json"

    written_path = generator.write_openapi_schema(output_path)

    assert written_path == output_path
    content = output_path.read_text(encoding="utf-8")
    assert content.endswith("\n")
    assert json.loads(content)["paths"]["/setup/status"]["get"]
    assert content == json.dumps(json.loads(content), indent=2, sort_keys=True) + "\n"


def test_main_writes_schema_to_requested_output_path(tmp_path: Path) -> None:
    generator = import_generate_openapi()
    output_path = tmp_path / "openapi.json"

    exit_code = generator.main(["--output", str(output_path)])

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["openapi"].startswith("3.")
