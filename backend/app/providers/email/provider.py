from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.config import EmailProviderName
from app.providers.email.html_normalization import (
    email_body_contains_html,
    normalize_email_html_to_text,
)
from app.security import SecretRef


class EmailSyncMode(StrEnum):
    FULL_BACKFILL = "full_backfill"
    INCREMENTAL = "incremental"


class EmailCandidateQueryStrategy(StrEnum):
    BROAD_JOB_SEARCH = "broad_job_search"


class EmailAttachmentPolicy(StrEnum):
    IGNORED = "ignored"


class EmailBodySource(StrEnum):
    TEXT_PLAIN = "text_plain"
    HTML_CONVERTED = "html_converted"
    EMPTY = "empty"


class EmailBodyFetchFailureReason(StrEnum):
    NOT_FOUND = "not_found"
    EMPTY = "empty"
    TOO_LARGE = "too_large"
    UNSUPPORTED_CONTENT = "unsupported_content"
    PERMISSION_DENIED = "permission_denied"


class EmailProviderCapabilities(BaseModel):
    """Static capabilities advertised by an email provider adapter."""

    model_config = ConfigDict(frozen=True)

    provider: EmailProviderName
    required_scopes: tuple[str, ...]
    supports_oauth: bool
    supports_full_backfill: bool
    supports_incremental_sync: bool
    attachment_policy: EmailAttachmentPolicy = EmailAttachmentPolicy.IGNORED
    max_metadata_page_size: int = Field(ge=1)
    max_body_batch_size: int = Field(ge=1)


class EmailAuthorizationStartRequest(BaseModel):
    """Provider-neutral request to start an authorization flow."""

    model_config = ConfigDict(frozen=True)

    provider: EmailProviderName
    redirect_uri: str = Field(min_length=1)
    state: str = Field(min_length=1)


class EmailAuthorizationStartResult(BaseModel):
    """Provider-neutral authorization URL and scope request."""

    model_config = ConfigDict(frozen=True)

    provider: EmailProviderName
    authorization_url: str = Field(min_length=1)
    state: str = Field(min_length=1)
    requested_scopes: tuple[str, ...] = Field(min_length=1)


class EmailAuthorizationCallbackRequest(BaseModel):
    """Provider-neutral callback request whose auth code is treated as secret."""

    model_config = ConfigDict(frozen=True)

    provider: EmailProviderName
    redirect_uri: str = Field(min_length=1)
    state: str = Field(min_length=1)
    code: SecretStr = Field(min_length=1)


class EmailAddress(BaseModel):
    model_config = ConfigDict(frozen=True)

    address: str = Field(min_length=1)
    display_name: str | None = None


class EmailAccountRef(BaseModel):
    """Provider-neutral stable reference to a connected mailbox account."""

    model_config = ConfigDict(frozen=True)

    provider: EmailProviderName
    account_id: str = Field(min_length=1)


class EmailConnection(BaseModel):
    """Stored account connection metadata without raw OAuth token material."""

    model_config = ConfigDict(frozen=True)

    account: EmailAccountRef
    display_email: EmailAddress | None = None
    credential_ref: SecretRef
    granted_scopes: tuple[str, ...] = Field(min_length=1)
    connected_at: datetime
    credential_expires_at: datetime | None = None
    reauth_required: bool = False


class EmailProviderCursor(BaseModel):
    """Opaque provider-owned cursor for resume and incremental sync state."""

    model_config = ConfigDict(frozen=True)

    account: EmailAccountRef
    value: str = Field(min_length=1)
    issued_at: datetime


class EmailCandidateQuery(BaseModel):
    """Provider-neutral metadata signals for selecting body-retention candidates.

    Candidate queries run over normalized metadata after provider listing
    instead of becoming provider-specific search filters.
    """

    model_config = ConfigDict(frozen=True)

    strategy: EmailCandidateQueryStrategy
    sender_domain_terms: tuple[str, ...] = ()
    keyword_terms: tuple[str, ...] = ()
    excluded_label_terms: tuple[str, ...] = ()

    @field_validator("sender_domain_terms", "keyword_terms", "excluded_label_terms")
    @classmethod
    def normalize_terms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(term.strip().lower() for term in value)
        if any(not term for term in normalized):
            msg = "candidate query terms must not be blank"
            raise ValueError(msg)
        return tuple(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_at_least_one_positive_signal(self) -> EmailCandidateQuery:
        if not self.sender_domain_terms and not self.keyword_terms:
            msg = "candidate query requires at least one sender domain or keyword signal"
            raise ValueError(msg)
        return self

    def matches_metadata(self, metadata: EmailMessageMetadata) -> bool:
        normalized_labels = {label.strip().lower() for label in metadata.labels}
        if normalized_labels.intersection(self.excluded_label_terms):
            return False
        return self._matches_sender_domain(metadata) or self._matches_subject_keyword(metadata)

    def _matches_sender_domain(self, metadata: EmailMessageMetadata) -> bool:
        if metadata.from_addr is None:
            return False
        _local_part, separator, domain = metadata.from_addr.address.strip().lower().rpartition("@")
        if not separator or not domain:
            return False
        domain = domain.strip(">")
        return any(
            domain == term or domain.endswith(f".{term}") for term in self.sender_domain_terms
        )

    def _matches_subject_keyword(self, metadata: EmailMessageMetadata) -> bool:
        subject = (metadata.subject or "").lower()
        return any(term in subject for term in self.keyword_terms)


def build_broad_candidate_query() -> EmailCandidateQuery:
    """Build the default broad job-search candidate query signals.

    The query contains static sender-domain, subject keyword, and excluded-label
    terms only; it carries no snippets, body text, or private message content.
    """

    return EmailCandidateQuery(
        strategy=EmailCandidateQueryStrategy.BROAD_JOB_SEARCH,
        sender_domain_terms=(
            "greenhouse.io",
            "greenhouse-mail.io",
            "lever.co",
            "jobs.lever.co",
            "ashbyhq.com",
            "myworkday.com",
            "workday.com",
            "icims.com",
            "workable.com",
            "workablemail.com",
            "smartrecruiters.com",
            "jobvite.com",
            "bamboohr.com",
            "recruitee.com",
            "teamtailor.com",
            "eightfold.ai",
        ),
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
        ),
        excluded_label_terms=("spam", "trash", "chats"),
    )


class EmailMetadataListRequest(BaseModel):
    """Request one provider-normalized metadata page.

    `page_token` continues pagination within the current listing run.
    `sync_cursor` is provider-owned incremental state and is required only for
    incremental sync.
    Candidate filters are intentionally excluded from provider listing requests.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: EmailSyncMode
    page_size: int = Field(ge=1)
    page_token: str | None = Field(default=None, min_length=1)
    sync_cursor: EmailProviderCursor | None = None

    @model_validator(mode="after")
    def validate_cursor_for_mode(self) -> EmailMetadataListRequest:
        if self.mode is EmailSyncMode.INCREMENTAL and self.sync_cursor is None:
            msg = "sync_cursor is required for incremental metadata sync"
            raise ValueError(msg)
        if self.mode is EmailSyncMode.FULL_BACKFILL and self.sync_cursor is not None:
            msg = "sync_cursor is not allowed for full metadata backfill"
            raise ValueError(msg)
        return self


class EmailMessageRef(BaseModel):
    """Provider-neutral stable reference to a single email message."""

    model_config = ConfigDict(frozen=True)

    account: EmailAccountRef
    message_id: str = Field(min_length=1)
    thread_id: str | None = None


class EmailMessageMetadata(BaseModel):
    """Provider-normalized metadata only; body text is fetched separately."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: EmailMessageRef
    rfc822_message_id: str | None = None
    from_addr: EmailAddress | None = None
    to_addrs: tuple[EmailAddress, ...] = ()
    cc_addrs: tuple[EmailAddress, ...] = ()
    subject: str | None = None
    sent_at: datetime | None = None
    received_at: datetime | None = None
    labels: tuple[str, ...] = ()
    has_attachments: bool = False
    size_bytes: int | None = Field(default=None, ge=0)
    body_text: None = None


class EmailMetadataPage(BaseModel):
    """One metadata page plus provider-owned continuation and sync cursors.

    `next_page_token` continues the current listing run.
    `next_sync_cursor` is the opaque cursor the sync service can persist after a
    successful provider page or run, depending on adapter semantics.
    """

    model_config = ConfigDict(frozen=True)
    messages: tuple[EmailMessageMetadata, ...]
    next_page_token: str | None = None
    next_sync_cursor: EmailProviderCursor | None = None


class EmailBodyFetchRequest(BaseModel):
    """Fetch retained body text only for caller-selected messages.

    Callers select messages eligible for body retention, such as job-search
    candidates or reconciliation/debug messages.
    """

    model_config = ConfigDict(frozen=True)
    refs: tuple[EmailMessageRef, ...] = Field(min_length=1)
    max_body_bytes: int | None = Field(default=None, ge=1)


class EmailMessageBody(BaseModel):
    """Provider-normalized retained plain-text body content."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    ref: EmailMessageRef
    body_text: str = Field(repr=False)
    body_source: EmailBodySource
    truncated: bool
    fetched_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_html_body_source(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        body_data = cast(dict[str, object], data)
        body_source = body_data.get("body_source")
        body_text = body_data.get("body_text")
        is_html_source = body_source in {
            EmailBodySource.HTML_CONVERTED,
            EmailBodySource.HTML_CONVERTED.value,
        }
        if isinstance(body_text, str) and (is_html_source or email_body_contains_html(body_text)):
            normalized_data = body_data.copy()
            normalized_data["body_text"] = normalize_email_html_to_text(body_text)
            return normalized_data
        return data


class EmailBodyFetchFailure(BaseModel):
    """A message body that could not be returned for retention.

    Use `EmailBodySource.EMPTY` with an empty `body_text` when an empty body is
    successfully normalized; use `EmailBodyFetchFailureReason.EMPTY` when the
    provider could not produce a retained body for the requested message.
    """

    model_config = ConfigDict(frozen=True)
    ref: EmailMessageRef
    reason: EmailBodyFetchFailureReason


class EmailBodyBatch(BaseModel):
    model_config = ConfigDict(frozen=True)
    bodies: tuple[EmailMessageBody, ...]
    failures: tuple[EmailBodyFetchFailure, ...] = ()


class EmailProviderError(RuntimeError):
    """Base error for public-safe email-provider failures."""

    public_message: str

    def __init__(self, *, public_message: str) -> None:
        self.public_message = public_message
        super().__init__(public_message)


class EmailProviderAuthError(EmailProviderError):
    """Raised when authorization, credentials, or reauth fail."""


class EmailSyncCursorExpiredError(EmailProviderError):
    """Raised when incremental sync state is no longer accepted."""


class EmailProviderTransientError(EmailProviderError):
    """Raised for retryable provider failures such as rate limits."""


@runtime_checkable
class EmailProvider(Protocol):
    """Strategy seam implemented by Gmail and future email providers."""

    name: EmailProviderName
    capabilities: EmailProviderCapabilities

    async def start_authorization(
        self,
        request: EmailAuthorizationStartRequest,
    ) -> EmailAuthorizationStartResult:
        """Return a provider authorization URL without exposing secrets."""
        ...

    async def complete_authorization(
        self,
        request: EmailAuthorizationCallbackRequest,
    ) -> EmailConnection:
        """Complete authorization and return non-secret connection metadata."""
        ...

    async def refresh_connection(self, connection: EmailConnection) -> EmailConnection:
        """Refresh stored credentials through the provider adapter."""
        ...

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        """Return one metadata-only page for full backfill or incremental sync."""
        ...

    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        """Return normalized body text for selected messages, ignoring attachments."""
        ...
