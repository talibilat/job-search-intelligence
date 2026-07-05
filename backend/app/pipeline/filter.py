from __future__ import annotations

from collections.abc import Iterable

HEURISTIC_ATS_SENDER_DOMAIN_TERMS: tuple[str, ...] = (
    "greenhouse.io",
    "greenhouse-mail.io",
    "lever.co",
    "ashbyhq.com",
    "myworkday.com",
    "myworkdayjobs.com",
    "workday.com",
    "icims.com",
    "workable.com",
    "workablemail.com",
    "smartrecruiters.com",
    "smartrecruitersmail.com",
    "jobvite.com",
    "bamboohr.com",
    "recruitee.com",
    "teamtailor.com",
    "eightfold.ai",
    "taleo.net",
    "successfactors.com",
)

HEURISTIC_RECRUITER_SENDER_DOMAIN_TERMS: tuple[str, ...] = (
    "linkedin.com",
    "linkedinmail.com",
    "indeed.com",
    "indeedemail.com",
    "ziprecruiter.com",
    "ziprecruiteremail.com",
    "dice.com",
    "wellfound.com",
)

HEURISTIC_SENDER_DOMAIN_TERMS: tuple[str, ...] = tuple(
    dict.fromkeys(
        HEURISTIC_ATS_SENDER_DOMAIN_TERMS + HEURISTIC_RECRUITER_SENDER_DOMAIN_TERMS,
    ),
)


def sender_matches_heuristic_sender_domain(sender_address: str | None) -> bool:
    """Return whether a sender belongs to a known ATS or recruiter domain."""

    return sender_matches_domain_terms(sender_address, HEURISTIC_SENDER_DOMAIN_TERMS)


def sender_matches_domain_terms(sender_address: str | None, domain_terms: Iterable[str]) -> bool:
    """Match sender domains by exact domain or subdomain, never raw suffix text."""

    domain = _extract_sender_domain(sender_address)
    if domain is None:
        return False

    return any(
        domain == term or domain.endswith(f".{term}")
        for term in _normalize_domain_terms(domain_terms)
    )


def _extract_sender_domain(sender_address: str | None) -> str | None:
    if sender_address is None:
        return None

    _local_part, separator, domain = sender_address.strip().lower().rpartition("@")
    if not separator:
        return None

    normalized_domain = domain.strip().strip("<>").strip(".")
    if not normalized_domain or any(character.isspace() for character in normalized_domain):
        return None
    return normalized_domain


def _normalize_domain_terms(domain_terms: Iterable[str]) -> tuple[str, ...]:
    normalized_terms: list[str] = []
    for term in domain_terms:
        normalized = term.strip().lower().removeprefix("@").strip(".")
        if normalized:
            normalized_terms.append(normalized)
    return tuple(dict.fromkeys(normalized_terms))
