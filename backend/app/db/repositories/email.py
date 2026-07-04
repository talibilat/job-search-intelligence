from __future__ import annotations

import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import RawEmailRecord


class EmailRepository(BaseRepository[RawEmailRecord]):
    """Repository seam for retained raw email records."""

    def map_row(self, row: sqlite3.Row) -> RawEmailRecord:
        return RawEmailRecord.model_validate(row_to_dict(row))
