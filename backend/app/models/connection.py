from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models._json import parse_json_column


class EmailConnectionRecord(BaseModel):
    provider: str
    account_id: str
    display_email: str | None
    credential_ref_kind: str
    credential_ref_provider: str
    credential_ref_name: str
    granted_scopes: list[str]
    connected_at: datetime
    credential_expires_at: datetime | None
    reauth_required: bool
    updated_at: datetime

    @field_validator("granted_scopes", mode="before")
    @classmethod
    def parse_granted_scopes(cls, value: object) -> object:
        return parse_json_column(value)
