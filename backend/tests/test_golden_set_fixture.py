from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Self

from app.models.records import JobEmailCategory
from pydantic import BaseModel, ConfigDict, Field, model_validator

GOLDEN_SET_PATH = Path(__file__).resolve().parents[1] / "evals" / "golden_set.jsonl"
FORBIDDEN_PRIVATE_MARKERS = (
    "talib",
    "@gmail.com",
    "@outlook.com",
    "@hotmail.com",
    "@icloud.com",
    "@yahoo.com",
)
REQUIRED_POSITIVE_CATEGORIES = {
    JobEmailCategory.APPLICATION_CONFIRMATION,
    JobEmailCategory.REJECTION,
    JobEmailCategory.INTERVIEW_INVITE,
    JobEmailCategory.RECRUITER_OUTREACH,
    JobEmailCategory.OFFER,
    JobEmailCategory.ASSESSMENT,
    JobEmailCategory.FOLLOW_UP,
}


class GoldenSetEmail(BaseModel):
    """Synthetic email payload for a single golden-set eval case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Literal["gmail"]
    from_addr: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    body_text: str = Field(min_length=1, repr=False)


class GoldenSetExpectedClassification(BaseModel):
    """Expected classifier label for one golden-set eval case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_job_related: bool
    category: JobEmailCategory


class GoldenSetCase(BaseModel):
    """Versioned JSONL record contract for the private-data-free golden set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"]
    case_id: str = Field(min_length=1)
    contains_private_data: Literal[False]
    email: GoldenSetEmail
    expected: GoldenSetExpectedClassification
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_negative_cases_are_other(self) -> Self:
        if (
            not self.expected.is_job_related
            and self.expected.category is not JobEmailCategory.OTHER
        ):
            msg = "non-job golden-set cases must use the other category"
            raise ValueError(msg)
        return self


def test_golden_set_fixture_is_valid_private_data_free_jsonl() -> None:
    cases = load_golden_set_cases()

    assert len(cases) >= 30
    assert all(case.contains_private_data is False for case in cases)


def test_golden_set_fixture_uses_unique_ids_and_synthetic_addresses() -> None:
    cases = load_golden_set_cases()
    case_ids = [case.case_id for case in cases]

    assert len(case_ids) == len(set(case_ids))
    for case in cases:
        assert_synthetic_sender(case.email.from_addr)
        assert_no_private_markers(case)


def test_golden_set_fixture_covers_job_vs_not_and_core_categories() -> None:
    cases = load_golden_set_cases()
    positive_categories = {
        case.expected.category for case in cases if case.expected.is_job_related
    }
    negative_cases = [case for case in cases if not case.expected.is_job_related]

    assert REQUIRED_POSITIVE_CATEGORIES.issubset(positive_categories)
    assert len(negative_cases) >= 5


def load_golden_set_cases() -> tuple[GoldenSetCase, ...]:
    assert GOLDEN_SET_PATH.exists()
    lines = GOLDEN_SET_PATH.read_text().splitlines()
    assert lines
    return tuple(GoldenSetCase.model_validate(json.loads(line)) for line in lines)


def assert_synthetic_sender(address: str) -> None:
    local_part, separator, domain = address.rpartition("@")

    assert local_part
    assert separator == "@"
    assert domain == "example.test" or domain.endswith(".example")


def assert_no_private_markers(case: GoldenSetCase) -> None:
    haystack = "\n".join(
        (
            case.email.from_addr,
            case.email.subject,
            case.email.body_text,
        )
    ).lower()

    assert not any(marker in haystack for marker in FORBIDDEN_PRIVATE_MARKERS)
