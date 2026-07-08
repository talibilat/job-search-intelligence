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


class RawEmailPreviewRecord(BaseModel):
    """Public-safe raw email metadata preview without body text."""

    id: str
    thread_id: str | None
    from_addr: str | None
    to_addr: str | None
    subject: str | None
    sent_at: datetime | None
    body_retention_state: RawEmailBodyRetentionState
    has_retained_body: bool
    labels: list[str]
    provider: str
    ingested_at: datetime
    filter_outcome: str | None = None
    filter_reason: str | None = None

    @field_validator("labels", mode="before")
    @classmethod
    def parse_preview_labels(cls, value: object) -> object:
        return parse_json_column(value)
