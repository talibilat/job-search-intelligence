from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

type CompanyType = Literal[
    "startup",
    "enterprise",
    "public_company",
    "agency",
    "nonprofit",
    "education",
    "government",
    "unknown",
    "other",
]
type CompanyProfileSource = Literal["manual", "imported", "extracted", "unknown"]


class CompanyProfileRecord(BaseModel):
    normalized_company: str
    display_company: str
    company_type: CompanyType
    industry: str | None
    source: CompanyProfileSource
    created_at: str
    updated_at: str
