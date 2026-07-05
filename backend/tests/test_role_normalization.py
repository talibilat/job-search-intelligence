from __future__ import annotations

import pytest
from app.services.normalization import normalize_role_title


@pytest.mark.parametrize(
    ("raw_title", "expected"),
    [
        ("  Senior SWE II - Backend (Remote)  ", "back end software engineer"),
        ("Software Engineer, Backend", "back end software engineer"),
        ("Sr. Software Developer - back-end", "back end software engineer"),
        ("Data Scientist III", "data scientist"),
        ("Staff Product Manager - Growth", "growth product manager"),
        ("Machine-Learning Engineer", "machine learning engineer"),
        ("Software Engineer - NYC", "software engineer"),
        ("Software Engineer - New York, NY", "software engineer"),
        ("Backend Engineer", "back end software engineer"),
        ("Frontend Engineer", "front end software engineer"),
        ("Software Engineer IC4", "software engineer"),
        ("Software Engineer E5", "software engineer"),
        ("Software Engineer M2", "software engineer"),
        ("Software Engineer L10", "software engineer"),
        ("Software Engineer Level 10", "software engineer"),
    ],
)
def test_normalize_role_title_canonicalizes_common_title_variants(
    raw_title: str,
    expected: str,
) -> None:
    assert normalize_role_title(raw_title) == expected


@pytest.mark.parametrize("raw_title", [None, "", "   ", "---"])
def test_normalize_role_title_returns_none_for_missing_titles(raw_title: str | None) -> None:
    assert normalize_role_title(raw_title) is None
