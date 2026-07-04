from __future__ import annotations

import logging
import sys

from app.security.redaction import (
    EMAIL_CONTENT_REDACTED,
    REDACTED,
    RedactingFilter,
    redact_mapping,
    redact_text,
    redact_value,
)


def test_redact_mapping_scrubs_secret_fields_case_insensitively() -> None:
    payload: dict[str, object] = {
        "access_token": "ya29.oauth-token",
        "RefreshToken": "refresh-token",
        "client_secret": "client-secret",
        "apiKey": "provider-api-key",
        "safe_name": "JobTracker",
        "attempts": 2,
    }

    redacted = redact_mapping(payload)

    assert redacted == {
        "access_token": REDACTED,
        "RefreshToken": REDACTED,
        "client_secret": REDACTED,
        "apiKey": REDACTED,
        "safe_name": "JobTracker",
        "attempts": 2,
    }


def test_redact_mapping_scrubs_private_email_content_fields() -> None:
    payload: dict[str, object] = {
        "email_id": "message-123",
        "body_text": "Hi Talib, unfortunately we moved forward with another candidate.",
        "body_html": "<p>Private interview feedback</p>",
        "snippet": "Private recruiter note",
    }

    redacted = redact_mapping(payload)

    assert redacted == {
        "email_id": "message-123",
        "body_text": EMAIL_CONTENT_REDACTED,
        "body_html": EMAIL_CONTENT_REDACTED,
        "snippet": EMAIL_CONTENT_REDACTED,
    }


def test_redact_value_recurses_through_nested_structures() -> None:
    payload: dict[str, object] = {
        "provider": "gmail",
        "oauth": {
            "access_token": "token-value",
            "history": [
                {"body_text": "private email"},
                {"status": "synced"},
            ],
        },
    }

    redacted = redact_value(payload)

    assert redacted == {
        "provider": "gmail",
        "oauth": {
            "access_token": REDACTED,
            "history": [
                {"body_text": EMAIL_CONTENT_REDACTED},
                {"status": "synced"},
            ],
        },
    }


def test_redact_text_scrubs_common_inline_secret_patterns() -> None:
    message = (
        "Authorization: Bearer ya29.oauth-token "
        "api_key=provider-key "
        "refresh_token=refresh-token"
    )

    redacted = redact_text(message)

    assert "ya29.oauth-token" not in redacted
    assert "provider-key" not in redacted
    assert "refresh-token" not in redacted
    assert redacted == (
        f"Authorization: Bearer {REDACTED} api_key={REDACTED} refresh_token={REDACTED}"
    )


def test_redact_text_scrubs_json_and_dict_style_secret_values() -> None:
    message = "{'access_token': 'oauth-token', \"apiKey\": \"provider-key\"}"

    redacted = redact_text(message)

    assert "oauth-token" not in redacted
    assert "provider-key" not in redacted
    assert redacted == f"{{'access_token': '{REDACTED}', \"apiKey\": \"{REDACTED}\"}}"


def test_redact_text_scrubs_generic_and_prefixed_secret_keys() -> None:
    message = (
        "token=raw-token "
        "secret=raw-secret "
        "OPENAI_API_KEY=provider-key "
        "{'GOOGLE_CLIENT_SECRET': 'client-secret'}"
    )

    redacted = redact_text(message)

    assert "raw-token" not in redacted
    assert "raw-secret" not in redacted
    assert "provider-key" not in redacted
    assert "client-secret" not in redacted
    assert redacted == (
        f"token={REDACTED} "
        f"secret={REDACTED} "
        f"OPENAI_API_KEY={REDACTED} "
        f"{{'GOOGLE_CLIENT_SECRET': '{REDACTED}'}}"
    )


def test_redacting_filter_scrubs_positional_email_body_logs() -> None:
    record = logging.LogRecord(
        name="jobtracker.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="body_text=%s",
        args=("Hi Talib, this private rejection body has spaces.",),
        exc_info=None,
    )

    RedactingFilter().filter(record)

    assert record.getMessage() == f"body_text={EMAIL_CONTENT_REDACTED}"


def test_redacting_filter_scrubs_log_record_message_and_args() -> None:
    record = logging.LogRecord(
        name="jobtracker.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Syncing %s with Authorization: Bearer raw-token",
        args=({"body_text": "private email body", "email_id": "message-123"},),
        exc_info=None,
    )

    should_log = RedactingFilter().filter(record)

    assert should_log is True
    assert record.getMessage() == (
        "Syncing {'body_text': '[REDACTED_EMAIL_CONTENT]', "
        "'email_id': 'message-123'} with Authorization: Bearer [REDACTED]"
    )


def test_redacting_filter_scrubs_structured_extra_fields() -> None:
    record = logging.LogRecord(
        name="jobtracker.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="refresh failed",
        args=(),
        exc_info=None,
    )
    setattr(record, "access_token", "oauth-token")
    setattr(record, "body_text", "private email body")
    setattr(record, "safe_status", "failed")

    RedactingFilter().filter(record)

    assert getattr(record, "access_token") == REDACTED
    assert getattr(record, "body_text") == EMAIL_CONTENT_REDACTED
    assert getattr(record, "safe_status") == "failed"


def test_redacting_filter_scrubs_exception_text() -> None:
    try:
        raise RuntimeError("refresh_token=raw-refresh-token")
    except RuntimeError:
        record = logging.LogRecord(
            name="jobtracker.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="sync failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    RedactingFilter().filter(record)

    assert record.exc_text is not None
    assert "raw-refresh-token" not in record.exc_text
    assert f"refresh_token={REDACTED}" in record.exc_text
