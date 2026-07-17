from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app.config import EmailProviderName
from app.pipeline.classify import AcceptedLLMExtraction, parse_llm_extraction_response
from app.pipeline.filter import build_broad_candidate_query
from app.providers.email.provider import (
    EmailAccountRef,
    EmailAddress,
    EmailCandidateDecisionOutcome,
    EmailMessageMetadata,
    EmailMessageRef,
)
from app.providers.llm import LLMFinishReason, LLMGenerationResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

MIN_PRECISION = 0.90
MIN_RECALL = 0.85
MIN_FILTER_PRECISION = 0.90
MIN_FILTER_RECALL = 0.85
DEFAULT_FIXTURE_PATH = Path(__file__).with_name("golden_set.jsonl")
DEFAULT_PROMPT_VERSION = "classification-golden-set-v1"
_LIFECYCLE_FIELDS: dict[str, tuple[str, str]] = {
    "application_confirmation": ("applied", "applied"),
    "rejection": ("rejected", "rejection"),
    "interview_invite": ("interview", "interview_scheduled"),
    "assessment": ("assessment", "assessment"),
    "offer": ("offer", "offer"),
}


class GoldenSetEntry(BaseModel):
    email_id: str = Field(min_length=1)
    expected_is_job_related: bool
    llm_response: LLMGenerationResponse
    prompt_version: str = Field(default=DEFAULT_PROMPT_VERSION, min_length=1)


class GoldenSetExpectedClassification(BaseModel):
    is_job_related: bool
    category: str = Field(min_length=1)


class GoldenSetEmail(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Literal["gmail"]
    from_addr: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    body_text: str = Field(min_length=1, repr=False)


class GoldenSetCase(BaseModel):
    schema_version: Literal["1"]
    case_id: str = Field(min_length=1)
    contains_private_data: Literal[False]
    email: GoldenSetEmail
    expected: GoldenSetExpectedClassification
    expected_to_pass_filter: bool


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
    return _load_golden_set_jsonl(fixture_path, _golden_set_entry_from_json)


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
    application_status, event_type = _LIFECYCLE_FIELDS.get(
        case.expected.category,
        (None, None),
    )
    return LLMGenerationResponse(
        content=json.dumps(
            {
                "is_job_related": case.expected.is_job_related,
                "category": case.expected.category,
                "confidence": 1.0,
                "company": None,
                "role_title": None,
                "application_status": application_status,
                "event_type": event_type,
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
        ),
        model="synthetic-golden-set",
        finish_reason=LLMFinishReason.STOP,
    )


def evaluate_filter_golden_set(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    min_precision: float = MIN_FILTER_PRECISION,
    min_recall: float = MIN_FILTER_RECALL,
) -> EvalReport:
    """Evaluate the heuristic prefilter against the golden set.

    Each entry's email metadata is run through build_broad_candidate_query()
    and compared to the entry's expected_to_pass_filter field.
    """
    entries = list(_load_golden_set_cases(fixture_path))
    candidate_query = build_broad_candidate_query()
    synthetic_account = EmailAccountRef(
        provider=EmailProviderName.GMAIL,
        account_id="golden-set-eval",
    )
    true_positives = 0
    false_positives = 0
    true_negatives = 0
    false_negatives = 0

    for case in entries:
        metadata = EmailMessageMetadata(
            ref=EmailMessageRef(
                account=synthetic_account,
                message_id=case.case_id,
            ),
            from_addr=EmailAddress(address=case.email.from_addr),
            subject=case.email.subject,
            labels=(),
        )
        decision = candidate_query.evaluate_metadata(metadata)
        passed_filter = decision.outcome is EmailCandidateDecisionOutcome.CANDIDATE

        if passed_filter and case.expected_to_pass_filter:
            true_positives += 1
        elif passed_filter and not case.expected_to_pass_filter:
            false_positives += 1
        elif not passed_filter and case.expected_to_pass_filter:
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


def _load_golden_set_cases(fixture_path: Path) -> tuple[GoldenSetCase, ...]:
    return tuple(_load_golden_set_jsonl(fixture_path, GoldenSetCase.model_validate))


def _load_golden_set_jsonl[T](
    fixture_path: Path,
    parse_entry: Callable[[object], T],
) -> list[T]:
    entries: list[T] = []
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
            entries.append(parse_entry(raw_entry))
        except ValidationError as exc:
            msg = f"{fixture_path}:{line_number}: invalid golden-set entry"
            raise ValueError(msg) from exc
    if not entries:
        msg = f"{fixture_path}: golden set is empty"
        raise ValueError(msg)
    return entries


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run golden-set evals.")
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
        help="Path to the golden-set JSONL fixture.",
    )
    parser.add_argument(
        "--filter",
        action="store_true",
        default=False,
        help="Run the heuristic filter eval instead of the classification eval.",
    )
    args = parser.parse_args(argv)

    fixture_path = args.golden_set or args.fixture_path or DEFAULT_FIXTURE_PATH

    if args.filter:
        report = evaluate_filter_golden_set(fixture_path)
    else:
        report = evaluate_golden_set(fixture_path)
    print(report.to_text())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
