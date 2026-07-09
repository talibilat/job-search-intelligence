from __future__ import annotations

import sqlite3

from app.db.repositories.base import BaseRepository
from app.models.company_profile import CompanyProfileRecord, CompanyProfileSource, CompanyType


class CompanyProfileRepository(BaseRepository[CompanyProfileRecord]):
    def upsert_profile(
        self,
        *,
        normalized_company: str,
        display_company: str,
        company_type: CompanyType,
        industry: str | None,
        source: CompanyProfileSource,
        updated_at: str,
    ) -> CompanyProfileRecord:
        normalized = normalized_company.strip().lower()
        display = display_company.strip()
        self.execute(
            """
            INSERT INTO company_profiles (
                normalized_company, display_company, company_type, industry,
                source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_company) DO UPDATE SET
                display_company = excluded.display_company,
                company_type = excluded.company_type,
                industry = excluded.industry,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                normalized,
                display,
                company_type,
                industry.strip() if industry is not None else None,
                source,
                updated_at,
                updated_at,
            ),
        )
        self.connection.commit()
        profile = self.get_profile(normalized)
        if profile is None:
            msg = f"Company profile was not persisted: {normalized}"
            raise RuntimeError(msg)
        return profile

    def get_profile(self, normalized_company: str) -> CompanyProfileRecord | None:
        row = self.execute(
            """
            SELECT normalized_company, display_company, company_type, industry,
                source, created_at, updated_at
            FROM company_profiles
            WHERE normalized_company = ?
            """,
            (normalized_company.strip().lower(),),
        ).fetchone()
        if row is None:
            return None
        return self.map_row(row)

    def map_row(self, row: sqlite3.Row) -> CompanyProfileRecord:
        return CompanyProfileRecord(
            normalized_company=str(row["normalized_company"]),
            display_company=str(row["display_company"]),
            company_type=row["company_type"],
            industry=None if row["industry"] is None else str(row["industry"]),
            source=row["source"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
