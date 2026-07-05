from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.config import EmailProviderName
from app.models.synthetic_fixture import (
    SyntheticApplication,
    SyntheticApplicationEvent,
    SyntheticApplicationSource,
    SyntheticApplicationStatus,
    SyntheticBodyRetentionState,
    SyntheticEmailClassification,
    SyntheticEventType,
    SyntheticFixtureFile,
    SyntheticJobEmailCategory,
    SyntheticRawEmail,
    SyntheticSponsorship,
    SyntheticWorkMode,
)
from pydantic import ValidationError

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)


def make_valid_fixture() -> SyntheticFixtureFile:
    email = SyntheticRawEmail(
        id="email-application-confirmation",
        provider=EmailProviderName.GMAIL,
        thread_id="thread-synthetic-1",
        from_addr="no-reply@ats.example",
        to_addr="jobseeker@example.test",
        subject="Application received for Backend Engineer",
        sent_at=NOW,
        body_text="Thank you for applying to Example Systems.",
        body_retention_state=SyntheticBodyRetentionState.RETAINED,
        labels=("INBOX",),
        ingested_at=NOW,
    )
    classification = SyntheticEmailClassification(
        email_id=email.id,
        is_job_related=True,
        category=SyntheticJobEmailCategory.APPLICATION_CONFIRMATION,
        confidence=0.98,
        model="synthetic-classifier",
        prompt_version="synthetic-v1",
        classified_at=NOW,
    )
    application = SyntheticApplication(
        id="application-example-systems-backend-engineer",
        company="Example Systems",
        role_title="Backend Engineer",
        source=SyntheticApplicationSource.COMPANY_SITE,
        first_seen_at=NOW,
        current_status=SyntheticApplicationStatus.APPLIED,
        salary_min=120_000,
        salary_max=150_000,
        currency="USD",
        location="Remote",
        work_mode=SyntheticWorkMode.REMOTE,
        seniority="senior",
        sponsorship=SyntheticSponsorship.UNKNOWN,
        tech_stack=("Python", "FastAPI"),
        last_activity_at=NOW,
        manual_lock=False,
        created_at=NOW,
        updated_at=NOW,
    )
    event = SyntheticApplicationEvent(
        id="event-application-submitted",
        application_id=application.id,
        email_id=email.id,
        event_type=SyntheticEventType.APPLIED,
        event_at=NOW,
        extract_note="Application confirmation received.",
    )

    return SyntheticFixtureFile(
        schema_version="1",
        fixture_id="basic-job-search",
        description="Private-data-free job-search fixture for backend smoke tests.",
        contains_private_data=False,
        emails=(email,),
        classifications=(classification,),
        applications=(application,),
        events=(event,),
    )


def test_fixture_format_models_core_tables_without_private_data() -> None:
    fixture = make_valid_fixture()

    assert fixture.schema_version == "1"
    assert fixture.contains_private_data is False
    assert fixture.emails[0].body_text == "Thank you for applying to Example Systems."
    assert "Thank you for applying" not in repr(fixture.emails[0])

    dumped = fixture.model_dump(mode="json")

    assert dumped["emails"][0]["id"] == "email-application-confirmation"
    assert dumped["classifications"][0]["email_id"] == "email-application-confirmation"
    assert dumped["applications"][0]["id"] == "application-example-systems-backend-engineer"
    assert dumped["events"][0]["application_id"] == ("application-example-systems-backend-engineer")


def test_fixture_rejects_private_data_flag() -> None:
    fixture_data = make_valid_fixture().model_dump(mode="json")
    fixture_data["contains_private_data"] = True

    with pytest.raises(ValidationError):
        SyntheticFixtureFile.model_validate(fixture_data)


def test_fixture_requires_schema_version_and_private_data_attestation() -> None:
    fixture_data = make_valid_fixture().model_dump(mode="json")

    for required_field in ("schema_version", "contains_private_data"):
        invalid_data = fixture_data | {required_field: None}
        invalid_data.pop(required_field)

        with pytest.raises(ValidationError):
            SyntheticFixtureFile.model_validate(invalid_data)


def test_fixture_rejects_unknown_email_payload_fields() -> None:
    email_data = make_valid_fixture().emails[0].model_dump(mode="json")
    email_data["raw_html"] = "<p>Do not retain raw HTML in synthetic fixtures.</p>"

    with pytest.raises(ValidationError):
        SyntheticRawEmail.model_validate(email_data)


def test_fixture_rejects_inconsistent_email_body_retention_state() -> None:
    email_data = make_valid_fixture().emails[0].model_dump(mode="json")

    with pytest.raises(ValidationError, match="metadata-only raw emails cannot retain body_text"):
        SyntheticRawEmail.model_validate(
            email_data
            | {
                "body_text": "Retained text without a retained state.",
                "body_retention_state": SyntheticBodyRetentionState.METADATA_ONLY,
            }
        )

    with pytest.raises(ValidationError, match="retained raw emails must include body_text"):
        SyntheticRawEmail.model_validate(
            email_data
            | {
                "body_text": None,
                "body_retention_state": SyntheticBodyRetentionState.RETAINED,
            }
        )

    with pytest.raises(ValidationError, match="retained raw emails must include body_text"):
        SyntheticRawEmail.model_validate(
            email_data
            | {
                "body_text": None,
                "body_retention_state": SyntheticBodyRetentionState.DEBUGGING,
            }
        )


def test_fixture_validates_unique_ids_and_cross_references() -> None:
    fixture = make_valid_fixture()

    with pytest.raises(ValidationError, match="duplicate email ids"):
        SyntheticFixtureFile(
            schema_version="1",
            fixture_id="duplicate-email",
            description="Duplicate email identifiers are invalid.",
            contains_private_data=False,
            emails=(fixture.emails[0], fixture.emails[0]),
            classifications=fixture.classifications,
            applications=fixture.applications,
            events=fixture.events,
        )

    missing_email_classification = fixture.classifications[0].model_copy(
        update={"email_id": "missing-email"}
    )
    with pytest.raises(ValidationError, match="unknown email ids"):
        SyntheticFixtureFile(
            schema_version="1",
            fixture_id="missing-classification-email",
            description="Classifications must reference emails in the fixture.",
            contains_private_data=False,
            emails=fixture.emails,
            classifications=(missing_email_classification,),
            applications=fixture.applications,
            events=fixture.events,
        )

    missing_application_event = fixture.events[0].model_copy(
        update={"application_id": "missing-application"}
    )
    with pytest.raises(ValidationError, match="unknown application ids"):
        SyntheticFixtureFile(
            schema_version="1",
            fixture_id="missing-event-application",
            description="Events must reference applications in the fixture.",
            contains_private_data=False,
            emails=fixture.emails,
            classifications=fixture.classifications,
            applications=fixture.applications,
            events=(missing_application_event,),
        )


def test_sample_synthetic_fixture_file_matches_format() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    fixture_path = backend_root / "tests" / "fixtures" / "synthetic" / "basic_job_search.json"

    fixture = SyntheticFixtureFile.model_validate(json.loads(fixture_path.read_text()))

    assert fixture.fixture_id == "basic-job-search"
    assert fixture.emails
    assert fixture.classifications
    assert fixture.applications
    assert fixture.events
