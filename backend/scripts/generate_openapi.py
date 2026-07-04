from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.main import create_app

OpenAPISchema = dict[str, Any]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "frontend" / "src" / "api" / "openapi.json"


def generate_openapi_schema() -> OpenAPISchema:
    return create_app().openapi()


def write_openapi_schema(output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = generate_openapi_schema()
    output_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the backend OpenAPI schema as deterministic JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output path for the OpenAPI schema. Defaults to {DEFAULT_OUTPUT_PATH}.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(argv)
    output_path = namespace.output
    if not isinstance(output_path, Path):
        raise TypeError("Expected --output to resolve to a pathlib.Path.")

    write_openapi_schema(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
