from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.config import EmailProviderName
from app.models import (
    EmailCandidateQueryStrategy as EmailCandidateQueryStrategy,
)
from app.models import (
    EmailFilterDecisionOutcome as EmailFilterDecisionOutcome,
)
from app.providers.email.html_normalization import (
    email_body_contains_html,
    normalize_email_html_to_text,
)
from app.security import SecretRef

EmailCandidateDecisionOutcome = EmailFilterDecisionOutcome


class EmailSyncMode(StrEnum):
    FULL_BACKFILL = "full_backfill"
    INCREMENTAL = "incremental"


class EmailCandidateDecision(BaseModel):
    """Safe, provider-neutral heuristic filter decision."""

    model_config = ConfigDict(frozen=True)

    strategy: EmailCandidateQueryStrategy
    outcome: EmailCandidateDecisionOutcome
    reason: str = Field(min_length=1)


class EmailAttachmentPolicy(StrEnum):
    IGNORED = "ignored"


class EmailBodySource(StrEnum):
    """Source format used to produce retained plain-text body content."""

    TEXT_PLAIN = "text_plain"
    HTML_CONVERTED = "html_converted"
    EMPTY = "empty"


class EmailBodyFetchFailureReason(StrEnum):
    NOT_FOUND = "not_found"
    EMPTY = "empty"
    TOO_LARGE = "too_large"
    UNSUPPORTED_CONTENT = "unsupported_content"
    PERMISSION_DENIED = "permission_denied"


class EmailProviderErrorCode(StrEnum):
    """Stable public error codes for provider failures crossing the API boundary."""

    AUTHORIZATION_REQUIRED = "email_authorization_required"
    INSUFFICIENT_SCOPE = "email_insufficient_scope"
    RATE_LIMITED = "email_rate_limited"
    TEMPORARILY_UNAVAILABLE = "email_temporarily_unavailable"
    INVALID_PROVIDER_RESPONSE = "email_invalid_provider_response"
    PROVIDER_REQUEST_FAILED = "email_provider_request_failed"
    SYNC_CURSOR_EXPIRED = "email_sync_cursor_expired"


class EmailProviderUserAction(StrEnum):
    """Stable public actions clients can use to guide recovery UI."""

    CHECK_CONFIGURATION = "check_configuration"
    RECONNECT_EMAIL = "reconnect_email"
    RESTART_FULL_SYNC = "restart_full_sync"
    TRY_AGAIN_LATER = "try_again_later"


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
    """Provider-normalized email address plus optional display name.

    Provider adapters should lower-case parsed addresses, trim display names,
    and deduplicate repeated recipients before returning metadata DTOs.
    """

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
    """Opaque provider-owned cursor for resume and incremental sync state.

    Adapters may trim surrounding whitespace but must not case-fold or parse
    cursor values because providers own their semantics.
    """

    model_config = ConfigDict(frozen=True)

    account: EmailAccountRef
    value: str = Field(min_length=1)
    issued_at: datetime


class EmailCandidateQuery(BaseModel):
    """Provider-neutral signals for broad job-search candidate matching.

    Candidate queries run over normalized metadata after provider listing instead
    of becoming provider-specific search filters, and keyword terms may also be
    applied to already-normalized retained body text when a caller has it.
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
        return self.evaluate_metadata(metadata).outcome is EmailCandidateDecisionOutcome.CANDIDATE

    def matches_keywords(
        self,
        *,
        subject: str | None,
        normalized_body_text: str | None,
    ) -> bool:
        """Return whether subject or normalized body text contains a keyword signal."""

        return self._matches_keyword_text(subject) or self._matches_keyword_text(
            normalized_body_text,
        )

    def evaluate_metadata(self, metadata: EmailMessageMetadata) -> EmailCandidateDecision:
        normalized_labels = {label.strip().lower() for label in metadata.labels}
        for excluded_label in self.excluded_label_terms:
            if excluded_label in normalized_labels:
                return EmailCandidateDecision(
                    strategy=self.strategy,
                    outcome=EmailCandidateDecisionOutcome.REJECTED,
                    reason=f"excluded_label:{excluded_label}",
                )

        matched_sender_domain = self._matching_sender_domain(metadata)
        if matched_sender_domain is not None:
            return EmailCandidateDecision(
                strategy=self.strategy,
                outcome=EmailCandidateDecisionOutcome.CANDIDATE,
                reason=f"sender_domain:{matched_sender_domain}",
            )

        matched_subject_keyword = self._matching_subject_keyword(metadata)
        if matched_subject_keyword is not None:
            return EmailCandidateDecision(
                strategy=self.strategy,
                outcome=EmailCandidateDecisionOutcome.CANDIDATE,
                reason=f"subject_keyword:{matched_subject_keyword}",
            )

        return EmailCandidateDecision(
            strategy=self.strategy,
            outcome=EmailCandidateDecisionOutcome.REJECTED,
            reason="no_filter_signal",
        )

    def _matches_keyword_text(self, text: str | None) -> bool:
        normalized_text = (text or "").lower()
        return any(term in normalized_text for term in self.keyword_terms)

    def _matches_sender_domain(self, metadata: EmailMessageMetadata) -> bool:
        return self._matching_sender_domain(metadata) is not None

    def _matching_sender_domain(self, metadata: EmailMessageMetadata) -> str | None:
        if metadata.from_addr is None:
            return None
        _local_part, separator, domain = metadata.from_addr.address.strip().lower().rpartition("@")
        if not separator or not domain:
            return None
        domain = domain.strip(">")
        for term in self.sender_domain_terms:
            if domain == term or domain.endswith(f".{term}"):
                return term
        return None

    def _matches_subject_keyword(self, metadata: EmailMessageMetadata) -> bool:
        return self._matching_subject_keyword(metadata) is not None

    def _matching_subject_keyword(self, metadata: EmailMessageMetadata) -> str | None:
        subject = (metadata.subject or "").lower()
        for term in self.keyword_terms:
            if term in subject:
                return term
        return None


def build_broad_candidate_query() -> EmailCandidateQuery:
    """Build the default broad job-search candidate query signals.

    The query contains static sender-domain, keyword, and excluded-label terms
    only; it carries no snippets, body text, or private message content.
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
    """Provider-neutral stable reference to a single email message.

    Adapters may trim surrounding whitespace from opaque message and thread IDs
    but must preserve provider-owned casing.
    """

    model_config = ConfigDict(frozen=True)

    account: EmailAccountRef
    message_id: str = Field(min_length=1)
    thread_id: str | None = None


class EmailMessageMetadata(BaseModel):
    """Provider-normalized metadata only; body text is fetched separately.

    Metadata timestamps should be timezone-aware UTC when providers expose a
    parseable sent date. Provider adapters own label canonicalization before
    returning this DTO.
    """

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
    successful provider page or run, depending on adapter semantics. Full
    backfills only complete when the final page carries a replacement sync
    cursor that can be promoted atomically with page progress.
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
    """Provider-normalized retained plain-text body content.

    HTML source bodies are converted to normalized text before this DTO is
    retained, and raw HTML fields or mislabelled HTML text are rejected.
    """

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
        if not isinstance(body_text, str):
            return data
        if is_html_source:
            normalized_data = body_data.copy()
            normalized_data["body_text"] = normalize_email_html_to_text(body_text)
            return normalized_data
        if email_body_contains_html(body_text):
            msg = "plain-text email bodies must not contain raw HTML"
            raise ValueError(msg)
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
    """Base error for public-safe email-provider failures.

    Providers attach a stable public error code and a user-action hint so API
    handlers can return actionable sync failures without exposing provider
    payloads, OAuth tokens, or private email content.
    """

    public_message: str
    error_code: EmailProviderErrorCode
    user_action: EmailProviderUserAction

    def __init__(
        self,
        *,
        public_message: str,
        error_code: EmailProviderErrorCode = EmailProviderErrorCode.PROVIDER_REQUEST_FAILED,
        user_action: EmailProviderUserAction = EmailProviderUserAction.TRY_AGAIN_LATER,
    ) -> None:
        self.public_message = public_message
        self.error_code = error_code
        self.user_action = user_action
        super().__init__(public_message)


class EmailProviderAuthError(EmailProviderError):
    """Raised when authorization, credentials, or reauth fail."""

    def __init__(
        self,
        *,
        public_message: str,
        error_code: EmailProviderErrorCode = EmailProviderErrorCode.AUTHORIZATION_REQUIRED,
        user_action: EmailProviderUserAction = EmailProviderUserAction.RECONNECT_EMAIL,
    ) -> None:
        super().__init__(
            public_message=public_message,
            error_code=error_code,
            user_action=user_action,
        )


class EmailSyncCursorExpiredError(EmailProviderError):
    """Raised when incremental sync state is no longer accepted."""

    def __init__(
        self,
        *,
        public_message: str,
        error_code: EmailProviderErrorCode = EmailProviderErrorCode.SYNC_CURSOR_EXPIRED,
        user_action: EmailProviderUserAction = EmailProviderUserAction.RESTART_FULL_SYNC,
    ) -> None:
        super().__init__(
            public_message=public_message,
            error_code=error_code,
            user_action=user_action,
        )


class EmailProviderTransientError(EmailProviderError):
    """Raised for retryable provider failures such as rate limits."""

    def __init__(
        self,
        *,
        public_message: str,
        error_code: EmailProviderErrorCode = EmailProviderErrorCode.TEMPORARILY_UNAVAILABLE,
        user_action: EmailProviderUserAction = EmailProviderUserAction.TRY_AGAIN_LATER,
    ) -> None:
        super().__init__(
            public_message=public_message,
            error_code=error_code,
            user_action=user_action,
        )


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
        """Return normalized plain text for selected messages, ignoring attachments."""
        ...
