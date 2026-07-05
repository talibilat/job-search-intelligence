from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.config import EmailProviderName
from app.providers.email import (
    EmailAccountRef,
    EmailCandidateQuery,
    EmailCandidateQueryStrategy,
    EmailMetadataListRequest,
    EmailProviderCursor,
    EmailSyncMode,
    build_broad_candidate_query,
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


def test_metadata_list_request_carries_candidate_query_for_provider_adapters() -> None:
    request = EmailMetadataListRequest(
        mode=EmailSyncMode.FULL_BACKFILL,
        page_size=500,
        candidate_query=build_broad_candidate_query(),
    )

    assert request.candidate_query is not None
    assert request.candidate_query.strategy is EmailCandidateQueryStrategy.BROAD_JOB_SEARCH
    assert "interview" in request.candidate_query.keyword_terms


def test_incremental_metadata_request_can_reuse_candidate_query_with_cursor() -> None:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    cursor = EmailProviderCursor(account=account, value="history-1", issued_at=NOW)

    request = EmailMetadataListRequest(
        mode=EmailSyncMode.INCREMENTAL,
        page_size=500,
        sync_cursor=cursor,
        candidate_query=build_broad_candidate_query(),
    )

    assert request.sync_cursor == cursor
    assert request.candidate_query is not None
    assert "greenhouse.io" in request.candidate_query.sender_domain_terms


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
