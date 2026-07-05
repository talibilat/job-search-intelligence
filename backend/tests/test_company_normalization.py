from __future__ import annotations

import pytest
from app.services.normalization import normalize_company_name


@pytest.mark.parametrize(
    ("raw_company", "normalized_company"),
    [
        ("  OpenAI, Inc.  ", "openai"),
        ("ACME Corporation", "acme"),
        ("The Example Group LLC", "example group"),
        ("Johnson & Johnson", "johnson and johnson"),
        ("Johnson and Johnson", "johnson and johnson"),
        ("jobs.example.com", "example"),
        ("www.data.ai", "data"),
        ("Acme---Labs", "acme labs"),
        ("Example L.L.C.", "example"),
        ("Example S.A.R.L.", "example"),
        ("Example P.T.E.", "example"),
    ],
)
def test_normalize_company_name_produces_stable_grouping_key(
    raw_company: str,
    normalized_company: str,
) -> None:
    assert normalize_company_name(raw_company) == normalized_company


def test_normalize_company_name_returns_empty_key_for_blank_input() -> None:
    assert normalize_company_name(" \t\n ") == ""
