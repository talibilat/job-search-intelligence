from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.pipeline.classify import parse_classification_prompt_output

DEFAULT_GOLDEN_SET_PATH = Path(__file__).with_name("golden_set.jsonl")
PRECISION_THRESHOLD = 0.90
RECALL_THRESHOLD = 0.85


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the classification prompt golden-set eval.",
    )
    parser.add_argument(
        "--golden-set",
        type=Path,
        default=DEFAULT_GOLDEN_SET_PATH,
        help="Path to a JSONL golden set with expected labels and prompt outputs.",
    )
    args = parser.parse_args()

    report = run_eval(args.golden_set)
    passed = (
        report["precision"] >= PRECISION_THRESHOLD
        and report["recall"] >= RECALL_THRESHOLD
    )

    print(f"examples: {report['examples']}")
    print(f"true_positives: {report['true_positives']}")
    print(f"false_positives: {report['false_positives']}")
    print(f"false_negatives: {report['false_negatives']}")
    print(f"precision: {report['precision']:.3f}")
    print(f"recall: {report['recall']:.3f}")
    print(f"pass: {str(passed).lower()}")

    return 0 if passed else 1


def run_eval(golden_set_path: Path) -> dict[str, int | float]:
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    examples = 0

    for line_number, record in _load_jsonl(golden_set_path):
        expected, output = _coerce_eval_record(record, golden_set_path, line_number)

        parsed = parse_classification_prompt_output(json.dumps(output))
        predicted = parsed.is_job_related
        examples += 1

        if predicted and expected:
            true_positives += 1
        elif predicted and not expected:
            false_positives += 1
        elif not predicted and expected:
            false_negatives += 1

    if examples == 0:
        msg = f"{golden_set_path} has no eval examples"
        raise ValueError(msg)

    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives

    precision = (
        true_positives / precision_denominator if precision_denominator else 0.0
    )
    recall = true_positives / recall_denominator if recall_denominator else 0.0

    return {
        "examples": examples,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
    }


def _load_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            record = json.loads(stripped)
            if not isinstance(record, dict):
                msg = f"{path}:{line_number} must contain a JSON object"
                raise ValueError(msg)

            records.append((line_number, record))

    return records


def _coerce_eval_record(
    record: dict[str, Any],
    path: Path,
    line_number: int,
) -> tuple[bool, dict[str, Any]]:
    expected = record.get("expected_is_job_related")
    output = record.get("prompt_output")
    if isinstance(expected, bool) and isinstance(output, dict):
        return expected, output

    expected_record = record.get("expected")
    if not isinstance(expected_record, dict):
        msg = f"{path}:{line_number} expected must be an object"
        raise ValueError(msg)

    expected = expected_record.get("is_job_related")
    if not isinstance(expected, bool):
        msg = f"{path}:{line_number} expected.is_job_related must be boolean"
        raise ValueError(msg)

    category = expected_record.get("category")
    if not isinstance(category, str):
        msg = f"{path}:{line_number} expected.category must be string"
        raise ValueError(msg)

    return expected, {
        "is_job_related": expected,
        "category": category,
        "confidence": 1.0,
        "company": None,
        "role_title": None,
        "application_status": None,
        "event_type": None,
        "event_at": None,
        "salary_min": None,
        "salary_max": None,
        "currency": None,
        "location": None,
        "work_mode": None,
        "seniority": None,
        "sponsorship": "unknown",
        "tech_stack": [],
        "rejection_reason": None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
