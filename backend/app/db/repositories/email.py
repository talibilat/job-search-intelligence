from __future__ import annotations

import sqlite3

from app.config import EmailProviderName
from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import RawEmailRecord


class EmailRepository(BaseRepository[RawEmailRecord]):
    """Repository seam for retained raw email records."""

    def count_raw_emails(self, *, provider: EmailProviderName | None = None) -> int:
        if provider is None:
            row = self.execute("SELECT COUNT(*) FROM raw_emails").fetchone()
        else:
            row = self.execute(
                "SELECT COUNT(*) FROM raw_emails WHERE provider = ?",
                (provider.value,),
            ).fetchone()

        if row is None:
            return 0
        return int(row[0])

    def map_row(self, row: sqlite3.Row) -> RawEmailRecord:
        return RawEmailRecord.model_validate(row_to_dict(row))
