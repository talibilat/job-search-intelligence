from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.config import EmailProviderName
from app.pipeline.filter import build_broad_candidate_query
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailCandidateDecisionOutcome,
    EmailCandidateQuery,
    EmailCandidateQueryStrategy,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailProviderCursor,
    EmailSyncMode,
)
from pydantic import ValidationError

NOW = datetime(2026, 7, 5, 9, 0, tzinfo=UTC)


def test_broad_candidate_query_uses_multiple_job_search_signal_families() -> None:
    query = build_broad_candidate_query()

    assert query.strategy is EmailCandidateQueryStrategy.BROAD_JOB_SEARCH
    assert len(query.sender_domain_terms) >= 10
    assert len(query.keyword_terms) >= 12
    assert {"greenhouse.io", "lever.co", "ashbyhq.com", "myworkday.com"}.issubset(
        query.sender_domain_terms,
    )
    assert {
        "application",
        "thank you for applying",
        "interview",
        "assessment",
        "unfortunately",
        "regret to inform",
        "offer",
    }.issubset(query.keyword_terms)
    assert query.excluded_label_terms == ("spam", "trash", "chats")


def test_broad_candidate_query_is_safe_static_metadata_filter_data() -> None:
    query = build_broad_candidate_query()
    serialized = query.model_dump()

    assert "body_text" not in serialized
    assert "snippet" not in serialized
    assert "raw_html" not in serialized
    assert "private" not in query.model_dump_json().lower()


def test_metadata_list_request_rejects_candidate_query_filters() -> None:
    with pytest.raises(ValidationError):
        EmailMetadataListRequest.model_validate(
            {
                "mode": EmailSyncMode.FULL_BACKFILL,
                "page_size": 500,
                "candidate_query": build_broad_candidate_query(),
            },
        )


def test_incremental_metadata_request_keeps_candidate_query_out_of_provider_listing() -> None:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    cursor = EmailProviderCursor(account=account, value="history-1", issued_at=NOW)

    request = EmailMetadataListRequest(
        mode=EmailSyncMode.INCREMENTAL,
        page_size=500,
        sync_cursor=cursor,
    )

    assert request.sync_cursor == cursor


def test_candidate_query_matches_metadata_with_executable_any_signal_semantics() -> None:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    query = build_broad_candidate_query()

    sender_domain_match = EmailMessageMetadata(
        ref=EmailMessageRef(account=account, message_id="msg-1"),
        from_addr=EmailAddress(address="notifications@mail.greenhouse.io"),
        subject="Your weekly newsletter",
        labels=("INBOX",),
    )
    subject_keyword_match = EmailMessageMetadata(
        ref=EmailMessageRef(account=account, message_id="msg-2"),
        from_addr=EmailAddress(address="recruiting@example.com"),
        subject="Next steps for your interview",
        labels=("INBOX",),
    )
    non_match = EmailMessageMetadata(
        ref=EmailMessageRef(account=account, message_id="msg-3"),
        from_addr=EmailAddress(address="news@example.com"),
        subject="Weekly product update",
        labels=("INBOX",),
    )

    assert query.matches_metadata(sender_domain_match)
    assert query.matches_metadata(subject_keyword_match)
    assert not query.matches_metadata(non_match)


def test_candidate_query_matches_keywords_across_subject_and_normalized_body_text() -> None:
    query = build_broad_candidate_query()

    assert query.matches_keywords(
        subject="General update from ExampleCo",
        normalized_body_text="Thank you for applying to ExampleCo. We received your application.",
    )
    assert query.matches_keywords(
        subject="Next steps for your interview",
        normalized_body_text=None,
    )
    assert not query.matches_keywords(
        subject="Weekly product update",
        normalized_body_text="Your account digest is ready.",
    )


def test_broad_candidate_query_does_not_match_broad_consumer_platform_roots() -> None:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    query = build_broad_candidate_query()

    linkedin_update = EmailMessageMetadata(
        ref=EmailMessageRef(account=account, message_id="msg-1"),
        from_addr=EmailAddress(address="notifications@linkedin.com"),
        subject="Your weekly update",
        labels=("INBOX",),
    )
    indeed_update = EmailMessageMetadata(
        ref=EmailMessageRef(account=account, message_id="msg-2"),
        from_addr=EmailAddress(address="updates@indeed.com"),
        subject="Your account update",
        labels=("INBOX",),
    )
    indeed_job_signal = EmailMessageMetadata(
        ref=EmailMessageRef(account=account, message_id="msg-3"),
        from_addr=EmailAddress(address="alerts@indeedemail.com"),
        subject="Your weekly update",
        labels=("INBOX",),
    )

    assert not query.matches_metadata(linkedin_update)
    assert not query.matches_metadata(indeed_update)
    assert query.matches_metadata(indeed_job_signal)


def test_candidate_query_explains_filter_outcome_and_reason_without_private_metadata() -> None:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    query = build_broad_candidate_query()
    sender_domain_match = EmailMessageMetadata(
        ref=EmailMessageRef(account=account, message_id="msg-1"),
        from_addr=EmailAddress(address="notifications@mail.greenhouse.io"),
        subject="Your weekly newsletter",
        labels=("INBOX",),
    )
    blocked_label_match = EmailMessageMetadata(
        ref=EmailMessageRef(account=account, message_id="msg-2"),
        from_addr=EmailAddress(address="notifications@mail.greenhouse.io"),
        subject="Application received",
        labels=("SPAM",),
    )
    no_signal_match = EmailMessageMetadata(
        ref=EmailMessageRef(account=account, message_id="msg-3"),
        from_addr=EmailAddress(address="news@example.com"),
        subject="Personal inbox subject that should not be stored",
        labels=("INBOX",),
    )

    sender_decision = query.evaluate_metadata(sender_domain_match)
    blocked_decision = query.evaluate_metadata(blocked_label_match)
    no_signal_decision = query.evaluate_metadata(no_signal_match)

    assert sender_decision.outcome is EmailCandidateDecisionOutcome.CANDIDATE
    assert sender_decision.reason == "sender_domain:greenhouse.io"
    assert blocked_decision.outcome is EmailCandidateDecisionOutcome.REJECTED
    assert blocked_decision.reason == "excluded_label:spam"
    assert no_signal_decision.outcome is EmailCandidateDecisionOutcome.REJECTED
    assert no_signal_decision.reason == "no_filter_signal"
    assert "Personal inbox subject" not in no_signal_decision.model_dump_json()


def test_candidate_query_excludes_metadata_with_blocked_labels() -> None:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    query = build_broad_candidate_query()
    spam_metadata = EmailMessageMetadata(
        ref=EmailMessageRef(account=account, message_id="msg-1"),
        from_addr=EmailAddress(address="notifications@mail.greenhouse.io"),
        subject="Application received",
        labels=("SPAM",),
    )

    assert not query.matches_metadata(spam_metadata)


def test_candidate_query_requires_at_least_one_signal() -> None:
    with pytest.raises(ValidationError):
        EmailCandidateQuery(
            strategy=EmailCandidateQueryStrategy.BROAD_JOB_SEARCH,
            sender_domain_terms=(),
            keyword_terms=(),
        )


def test_candidate_query_rejects_blank_terms() -> None:
    with pytest.raises(ValidationError):
        EmailCandidateQuery(
            strategy=EmailCandidateQueryStrategy.BROAD_JOB_SEARCH,
            sender_domain_terms=("greenhouse.io", " "),
            keyword_terms=("application",),
        )
