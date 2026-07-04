from __future__ import annotations

import logging
import re
import traceback
from collections.abc import Mapping
from typing import Final

REDACTED: Final = "[REDACTED]"
EMAIL_CONTENT_REDACTED: Final = "[REDACTED_EMAIL_CONTENT]"

_SECRET_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "accesstoken",
        "apikey",
        "authorization",
        "clientsecret",
        "credential",
        "credentials",
        "idtoken",
        "password",
        "refreshtoken",
        "secret",
        "token",
    }
)

_EMAIL_CONTENT_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "bodyhtml",
        "bodytext",
        "emailbody",
        "emailbodyhtml",
        "emailbodytext",
        "htmlbody",
        "messagebody",
        "plainbody",
        "rawbody",
        "rawemailbody",
        "snippet",
    }
)

_SECRET_KEY_TEXT: Final = (
    r"[a-z0-9_-]*(?:access[_-]?token|api[_-]?key|client[_-]?secret|credential|"
    r"id[_-]?token|password|refresh[_-]?token|secret|token)"
)
_EMAIL_CONTENT_KEY_TEXT: Final = (
    r"body[_-]?html|body[_-]?text|email[_-]?body|email[_-]?body[_-]?html|"
    r"email[_-]?body[_-]?text|html[_-]?body|message[_-]?body|plain[_-]?body|"
    r"raw[_-]?body|raw[_-]?email[_-]?body|snippet"
)

_AUTHORIZATION_BEARER_PATTERN: Final = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,;]+)")
_BEARER_PATTERN: Final = re.compile(r"(?i)(\bbearer\s+)([^\s,;]+)")
_SECRET_ASSIGNMENT_PATTERN: Final = re.compile(
    rf"(?i)(\b(?:{_SECRET_KEY_TEXT})\b\s*=\s*)(['\"]?)([^&\s,;'\"}}]+)(\2)"
)
_SECRET_QUOTED_KEY_VALUE_PATTERN: Final = re.compile(
    rf"(?i)((['\"]?)(?:{_SECRET_KEY_TEXT})\2\s*:\s*)(['\"])(.*?)(\3)"
)
_SECRET_UNQUOTED_KEY_VALUE_PATTERN: Final = re.compile(
    rf"(?i)(\b(?:{_SECRET_KEY_TEXT})\b\s*:\s*)([^,\s}}]+)"
)
_EMAIL_QUOTED_KEY_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(rf"(?is)((['\"]?)(?:{_EMAIL_CONTENT_KEY_TEXT})\2\s*:\s*)(['\"])(.*?)(\3)"),
    re.compile(rf"(?is)(\b(?:{_EMAIL_CONTENT_KEY_TEXT})\b\s*=\s*)(['\"])(.*?)(\2)"),
)
_EMAIL_UNQUOTED_KEY_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(rf"(?is)(\b(?:{_EMAIL_CONTENT_KEY_TEXT})\b\s*=\s*).+"),
    re.compile(rf"(?is)(\b(?:{_EMAIL_CONTENT_KEY_TEXT})\b\s*:\s*).+"),
)

_NORMALIZE_KEY_PATTERN: Final = re.compile(r"[^a-z0-9]")
_STANDARD_LOG_RECORD_ATTRS: Final = frozenset(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
) | frozenset({"asctime", "message"})


def redact_text(text: str) -> str:
    redacted = text
    redacted = _AUTHORIZATION_BEARER_PATTERN.sub(
        lambda match: f"{match.group(1)}{REDACTED}", redacted
    )
    redacted = _BEARER_PATTERN.sub(lambda match: f"{match.group(1)}{REDACTED}", redacted)
    redacted = _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}{match.group(4)}",
        redacted,
    )
    redacted = _SECRET_QUOTED_KEY_VALUE_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(3)}{REDACTED}{match.group(5)}",
        redacted,
    )
    redacted = _SECRET_UNQUOTED_KEY_VALUE_PATTERN.sub(
        lambda match: f"{match.group(1)}{REDACTED}", redacted
    )
    for pattern in _EMAIL_QUOTED_KEY_VALUE_PATTERNS:
        redacted = pattern.sub(
            lambda match: (
                f"{match.group(1)}{match.group(3)}{EMAIL_CONTENT_REDACTED}{match.group(5)}"
            ),
            redacted,
        )
    for pattern in _EMAIL_UNQUOTED_KEY_VALUE_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}{EMAIL_CONTENT_REDACTED}", redacted)
    return redacted


def redact_mapping(mapping: Mapping[str, object]) -> dict[str, object]:
    return {key: _redact_field_value(key, value) for key, value in mapping.items()}


def redact_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _redact_any_mapping(value)
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        _redact_extra_fields(record)
        if record.args:
            record.args = _redact_log_args(record.args)
        record.msg = redact_text(record.getMessage())
        record.args = ()
        _redact_exception(record)
        return True


def _redact_log_args(
    args: tuple[object, ...] | Mapping[str, object],
) -> tuple[object, ...] | Mapping[str, object]:
    if isinstance(args, Mapping):
        return redact_mapping(args)
    return tuple(redact_value(item) for item in args)


def _redact_extra_fields(record: logging.LogRecord) -> None:
    for key, value in list(record.__dict__.items()):
        if key not in _STANDARD_LOG_RECORD_ATTRS:
            setattr(record, key, _redact_field_value(key, value))


def _redact_exception(record: logging.LogRecord) -> None:
    if record.exc_info:
        record.exc_text = redact_text("".join(traceback.format_exception(*record.exc_info)))
    elif record.exc_text:
        record.exc_text = redact_text(record.exc_text)


def _redact_any_mapping(mapping: Mapping[object, object]) -> dict[object, object]:
    redacted: dict[object, object] = {}
    for key, value in mapping.items():
        if isinstance(key, str):
            redacted[key] = _redact_field_value(key, value)
        else:
            redacted[key] = redact_value(value)
    return redacted


def _redact_field_value(key: str, value: object) -> object:
    if _is_secret_field(key):
        return REDACTED
    if _is_email_content_field(key):
        return EMAIL_CONTENT_REDACTED
    return redact_value(value)


def _is_secret_field(key: str) -> bool:
    normalized_key = _normalize_key(key)
    return (
        normalized_key in _SECRET_FIELD_NAMES
        or normalized_key.endswith("token")
        or normalized_key.endswith("secret")
        or normalized_key.endswith("apikey")
        or normalized_key.endswith("password")
        or "credential" in normalized_key
    )


def _is_email_content_field(key: str) -> bool:
    return _normalize_key(key) in _EMAIL_CONTENT_FIELD_NAMES


def _normalize_key(key: str) -> str:
    return _NORMALIZE_KEY_PATTERN.sub("", key.lower())
