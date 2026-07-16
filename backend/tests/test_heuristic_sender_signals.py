from __future__ import annotations

import pytest
from app.pipeline.filter import (
    HEURISTIC_ATS_SENDER_DOMAIN_TERMS,
    HEURISTIC_RECRUITER_SENDER_DOMAIN_TERMS,
    HEURISTIC_SENDER_DOMAIN_TERMS,
    build_broad_candidate_query,
)
from app.providers.email.provider import sender_matches_domain_terms


def test_heuristic_sender_domains_cover_ats_and_recruiter_families() -> None:
    assert {
        "greenhouse.io",
        "greenhouse-mail.io",
        "lever.co",
        "ashbyhq.com",
        "myworkday.com",
        "myworkdayjobs.com",
        "icims.com",
        "workable.com",
        "workablemail.com",
        "smartrecruiters.com",
        "smartrecruitersmail.com",
        "jobvite.com",
        "taleo.net",
        "successfactors.com",
    }.issubset(HEURISTIC_ATS_SENDER_DOMAIN_TERMS)
    assert {
        "linkedinmail.com",
        "indeedemail.com",
        "ziprecruiter.com",
        "ziprecruiteremail.com",
        "dice.com",
        "wellfound.com",
    }.issubset(HEURISTIC_RECRUITER_SENDER_DOMAIN_TERMS)
    assert len(HEURISTIC_SENDER_DOMAIN_TERMS) == len(set(HEURISTIC_SENDER_DOMAIN_TERMS))


@pytest.mark.parametrize(
    "sender",
    [
        "notifications@mail.greenhouse.io",
        "no-reply@myworkdayjobs.com",
        "candidate@updates.smartrecruitersmail.com",
        "messages@notifications.linkedinmail.com",
        "apply@indeedemail.com",
        "jobs@alerts.ziprecruiteremail.com",
    ],
)
def test_heuristic_sender_signal_matches_ats_and_recruiter_domains(sender: str) -> None:
    assert sender_matches_domain_terms(sender, HEURISTIC_SENDER_DOMAIN_TERMS)


@pytest.mark.parametrize(
    "sender",
    [
        None,
        "",
        "not-an-email-address",
        "alerts@notgreenhouse.io",
        "notifications@linkedin.com",
        "updates@indeed.com",
        "jobs@linkedin.com.evil.test",
        "updates@indeedemail.com.example.test",
    ],
)
def test_heuristic_sender_signal_rejects_missing_or_impostor_domains(
    sender: str | None,
) -> None:
    assert not sender_matches_domain_terms(sender, HEURISTIC_SENDER_DOMAIN_TERMS)


def test_sender_domain_terms_match_exact_domains_and_subdomains_only() -> None:
    terms = ("greenhouse.io",)

    assert sender_matches_domain_terms("jobs@greenhouse.io", terms)
    assert sender_matches_domain_terms("jobs@mail.greenhouse.io", terms)
    assert not sender_matches_domain_terms("jobs@notgreenhouse.io", terms)
    assert not sender_matches_domain_terms("jobs@greenhouse.io.example.test", terms)


def test_broad_candidate_query_uses_heuristic_sender_domain_terms() -> None:
    query = build_broad_candidate_query()

    assert query.sender_domain_terms == HEURISTIC_SENDER_DOMAIN_TERMS
