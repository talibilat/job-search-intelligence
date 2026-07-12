from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models._json import parse_json_column


class RawEmailBodyRetentionState(StrEnum):
    """Explicit body retention state for raw email DTO boundaries."""

    METADATA_ONLY = "metadata_only"
    RETAINED = "retained"
    DEBUGGING = "debugging"


class RawEmailRecord(BaseModel):
    """Raw email row DTO with explicit retained-body consistency checks."""

    id: str
    thread_id: str | None
    from_addr: str | None
    to_addr: str | None
    subject: str | None
    sent_at: datetime | None
    body_text: str | None = Field(repr=False)
    body_retention_state: RawEmailBodyRetentionState
    labels: list[str]
    provider: str
    ingested_at: datetime

    @field_validator("labels", mode="before")
    @classmethod
    def parse_labels(cls, value: object) -> object:
        return parse_json_column(value)

    @model_validator(mode="after")
    def validate_body_retention_state(self) -> Self:
        if (
            self.body_retention_state is RawEmailBodyRetentionState.METADATA_ONLY
            and self.body_text is not None
        ):
            msg = "metadata-only raw emails cannot retain body_text"
            raise ValueError(msg)

        if self.has_retained_body and self.body_text is None:
            msg = "retained raw emails must include body_text"
            raise ValueError(msg)

        return self

    @property
    def has_retained_body(self) -> bool:
        """Return whether pipeline stages can read retained body text."""

        return self.body_retention_state in {
            RawEmailBodyRetentionState.RETAINED,
            RawEmailBodyRetentionState.DEBUGGING,
        }


class RawEmailPreviewOrder(StrEnum):
    """Supported deterministic orderings for the raw-email preview list."""

    SENT_AT = "sent_at"
    INGESTED_AT = "ingested_at"


MAX_EMAIL_PREVIEW_PAGE_SIZE = 100


class RawEmailPreviewRecord(BaseModel):
    """Public-safe raw email metadata preview without body text."""

    public_id: str
    from_domain: str | None
    to_domains: list[str]
    subject: str | None
    subject_present: bool
    sent_at: datetime | None
    body_retention_state: RawEmailBodyRetentionState
    has_retained_body: bool
    provider: str
    ingested_at: datetime
    filter_outcome: str | None = None
    filter_reason: str | None = None
    classification_category: str | None = None
    classification_is_job_related: bool | None = None


class RawEmailPreviewPage(BaseModel):
    """A validated page of raw email metadata previews."""

    items: tuple[RawEmailPreviewRecord, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_EMAIL_PREVIEW_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class RawEmailDetail(BaseModel):
    """Public-safe on-demand email content for the reader dialog."""

    public_id: str
    from_domain: str | None
    subject: str | None
    sent_at: datetime | None
    body_retention_state: RawEmailBodyRetentionState
    body_text: str


class RawEmailReaderRecord(BaseModel):
    """A raw email resolved through its opaque public identifier.

    ``body_text`` is populated only when the retention state allows it; the
    repository query enforces that before this DTO is constructed.
    """

    public_id: str
    provider_message_id: str = Field(repr=False)
    thread_id: str | None = Field(repr=False)
    from_addr: str | None
    to_addr: str | None
    subject: str | None
    sent_at: datetime | None
    body_text: str | None = Field(default=None, repr=False)
    body_retention_state: RawEmailBodyRetentionState
    provider: str
