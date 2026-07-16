from __future__ import annotations

from app.providers.email.provider import (
    EmailCandidateQuery,
    EmailCandidateQueryStrategy,
)

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
    "linkedinmail.com",
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


def build_broad_candidate_query() -> EmailCandidateQuery:
    """Build safe static metadata signals for broad job-search selection.

    The query carries known ATS/recruiter sender domains, subject keywords,
    and excluded-label terms only; it carries no snippets, body text, or
    private message content.
    """

    return EmailCandidateQuery(
        strategy=EmailCandidateQueryStrategy.BROAD_JOB_SEARCH,
        sender_domain_terms=HEURISTIC_SENDER_DOMAIN_TERMS,
        keyword_terms=(
            "application",
            "applied",
            "thank you for applying",
            "we received your application",
            "candidate",
            "recruiter",
            "interview",
            "next steps",
            "assessment",
            "take-home",
            "unfortunately",
            "regret to inform",
            "moving forward with other candidates",
            "offer",
            "congratulations",
            "job opportunity",
            "position",
            "role",
            "sponsorship",
            "phone screen",
            "onsite",
            "challenge",
            "work sample",
            "job search",
            "hiring event",
        ),
        excluded_label_terms=("spam", "trash", "chats"),
    )
