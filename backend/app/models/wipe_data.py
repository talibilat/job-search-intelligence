from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WIPE_DATA_CONFIRMATION = "wipe-local-data"


class WipeDataRequest(BaseModel):
    confirmation: Literal["wipe-local-data"] = Field(
        description="Must exactly equal wipe-local-data to confirm local data deletion.",
    )


class WipeDataResponse(BaseModel):
    status: Literal["wiped"]
    deleted_paths: list[str] = Field(
        default_factory=list,
        description="Canonical local filesystem paths deleted by the wipe operation.",
    )
    missing_paths: list[str] = Field(
        default_factory=list,
        description="Canonical local filesystem paths that were already absent.",
    )
