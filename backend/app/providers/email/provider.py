from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.config import EmailProviderName
from app.security import SecretRef


class EmailSyncMode(StrEnum):
    FULL_BACKFILL = "full_backfill"
    INCREMENTAL = "incremental"


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
    """Provider-neutral request to complete an authorization flow."""

    model_config = ConfigDict(frozen=True)

    provider: EmailProviderName
    redirect_uri: str = Field(min_length=1)
    state: str = Field(min_length=1)
    code: str = Field(min_length=1)


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


class EmailMetadataListRequest(BaseModel):
    """Request one provider-normalized metadata page."""

    model_config = ConfigDict(frozen=True)

    mode: EmailSyncMode
    page_size: int = Field(ge=1)
    page_token: str | None = Field(default=None, min_length=1)
    sync_cursor: EmailProviderCursor | None = None


class EmailMessageRef(BaseModel):
    """Provider-neutral stable reference to a single email message."""

    model_config = ConfigDict(frozen=True)

    account: EmailAccountRef
    message_id: str = Field(min_length=1)
    thread_id: str | None = None


class EmailMessageMetadata(BaseModel):
    """Provider-normalized metadata only; body text is fetched separately."""

    model_config = ConfigDict(frozen=True)

    ref: EmailMessageRef
    rfc822_message_id: str | None = None
    from_addr: EmailAddress | None = None
    to_addrs: tuple[EmailAddress, ...] = ()
    cc_addrs: tuple[EmailAddress, ...] = ()
    subject: str | None = None
    snippet: str | None = None
    sent_at: datetime | None = None
    received_at: datetime | None = None
    labels: tuple[str, ...] = ()
    has_attachments: bool = False
    size_bytes: int | None = Field(default=None, ge=0)
    body_text: None = None


class EmailMetadataPage(BaseModel):
    """One metadata page plus provider-owned continuation and sync cursors."""

    model_config = ConfigDict(frozen=True)
    messages: tuple[EmailMessageMetadata, ...]
    next_page_token: str | None = None
    next_sync_cursor: EmailProviderCursor | None = None


class EmailBodyFetchRequest(BaseModel):
    """Fetch retained body text only for caller-selected candidate messages."""

    model_config = ConfigDict(frozen=True)
    refs: tuple[EmailMessageRef, ...] = Field(min_length=1)
    max_body_bytes: int | None = Field(default=None, ge=1)


class EmailMessageBody(BaseModel):
    """Provider-normalized retained plain-text body content."""

    model_config = ConfigDict(frozen=True)
    ref: EmailMessageRef
    body_text: str
    body_source: EmailBodySource
    truncated: bool
    fetched_at: datetime


class EmailBodyFetchFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    ref: EmailMessageRef
    reason: EmailBodyFetchFailureReason


class EmailBodyBatch(BaseModel):
    model_config = ConfigDict(frozen=True)
    bodies: tuple[EmailMessageBody, ...]
    failures: tuple[EmailBodyFetchFailure, ...] = ()


class EmailProviderError(RuntimeError):
    """Base error for email-provider failures."""


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
