from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app.pipeline.classify import AcceptedLLMExtraction, parse_llm_extraction_response
from app.providers.llm import LLMFinishReason, LLMGenerationResponse
from pydantic import BaseModel, Field, ValidationError

MIN_PRECISION = 0.90
MIN_RECALL = 0.85
DEFAULT_FIXTURE_PATH = Path(__file__).with_name("golden_set.jsonl")
DEFAULT_PROMPT_VERSION = "classification-golden-set-v1"


class GoldenSetEntry(BaseModel):
    email_id: str = Field(min_length=1)
    expected_is_job_related: bool
    llm_response: LLMGenerationResponse
    prompt_version: str = Field(default=DEFAULT_PROMPT_VERSION, min_length=1)


class GoldenSetExpectedClassification(BaseModel):
    is_job_related: bool
    category: str = Field(min_length=1)


class GoldenSetCase(BaseModel):
    schema_version: Literal["1"]
    case_id: str = Field(min_length=1)
    contains_private_data: Literal[False]
    expected: GoldenSetExpectedClassification


class EvalReport(BaseModel):
    total: int = Field(ge=0)
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    true_negatives: int = Field(ge=0)
    false_negatives: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    passed: bool

    def to_text(self) -> str:
        status = "passed" if self.passed else "failed"
        return "\n".join(
            [
                f"status: {status}",
                f"total: {self.total}",
                f"precision: {self.precision:.3f}",
                f"recall: {self.recall:.3f}",
                f"true_positives: {self.true_positives}",
                f"false_positives: {self.false_positives}",
                f"true_negatives: {self.true_negatives}",
                f"false_negatives: {self.false_negatives}",
                f"pass: {str(self.passed).lower()}",
            ]
        )


def evaluate_golden_set(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    min_precision: float = MIN_PRECISION,
    min_recall: float = MIN_RECALL,
) -> EvalReport:
    entries = load_golden_set(fixture_path)
    true_positives = 0
    false_positives = 0
    true_negatives = 0
    false_negatives = 0
    classified_at = datetime.now(UTC)

    for entry in entries:
        result = parse_llm_extraction_response(
            email_id=entry.email_id,
            response=entry.llm_response,
            prompt_version=entry.prompt_version,
            classified_at=classified_at,
        )
        predicted_is_job_related = (
            isinstance(result, AcceptedLLMExtraction) and result.classification.is_job_related
        )

        if predicted_is_job_related and entry.expected_is_job_related:
            true_positives += 1
        elif predicted_is_job_related and not entry.expected_is_job_related:
            false_positives += 1
        elif not predicted_is_job_related and entry.expected_is_job_related:
            false_negatives += 1
        else:
            true_negatives += 1

    predicted_positives = true_positives + false_positives
    expected_positives = true_positives + false_negatives
    precision = true_positives / predicted_positives if predicted_positives else 0.0
    recall = true_positives / expected_positives if expected_positives else 0.0

    return EvalReport(
        total=len(entries),
        true_positives=true_positives,
        false_positives=false_positives,
        true_negatives=true_negatives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        passed=precision >= min_precision and recall >= min_recall,
    )


def load_golden_set(fixture_path: Path) -> list[GoldenSetEntry]:
    entries: list[GoldenSetEntry] = []
    for line_number, line in enumerate(fixture_path.read_text(encoding="utf-8").splitlines(), 1):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        try:
            raw_entry = json.loads(stripped_line)
        except json.JSONDecodeError as exc:
            msg = f"{fixture_path}:{line_number}: invalid JSON"
            raise ValueError(msg) from exc
        try:
            entries.append(_golden_set_entry_from_json(raw_entry))
        except ValidationError as exc:
            msg = f"{fixture_path}:{line_number}: invalid golden-set entry"
            raise ValueError(msg) from exc

    if not entries:
        msg = f"{fixture_path}: golden set is empty"
        raise ValueError(msg)
    return entries


def _golden_set_entry_from_json(raw_entry: object) -> GoldenSetEntry:
    try:
        return GoldenSetEntry.model_validate(raw_entry)
    except ValidationError:
        pass

    case = GoldenSetCase.model_validate(raw_entry)
    return GoldenSetEntry(
        email_id=case.case_id,
        expected_is_job_related=case.expected.is_job_related,
        llm_response=_synthetic_llm_response_from_case(case),
    )


def _synthetic_llm_response_from_case(case: GoldenSetCase) -> LLMGenerationResponse:
    return LLMGenerationResponse(
        content=json.dumps(
            {
                "is_job_related": case.expected.is_job_related,
                "category": case.expected.category,
                "confidence": 1.0,
            }
        ),
        model="synthetic-golden-set",
        finish_reason=LLMFinishReason.STOP,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the classification golden-set eval.")
    parser.add_argument(
        "fixture_path",
        nargs="?",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--golden-set",
        type=Path,
        default=None,
        help="Path to the classification golden-set JSONL fixture.",
    )
    args = parser.parse_args(argv)

    fixture_path = args.golden_set or args.fixture_path or DEFAULT_FIXTURE_PATH
    report = evaluate_golden_set(fixture_path)
    print(report.to_text())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
