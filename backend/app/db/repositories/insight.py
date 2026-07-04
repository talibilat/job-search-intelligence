from __future__ import annotations

import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import InsightRecord


class InsightRepository(BaseRepository[InsightRecord]):
    """Repository seam for cached narrative insights."""

    def map_row(self, row: sqlite3.Row) -> InsightRecord:
        return InsightRecord.model_validate(row_to_dict(row))
