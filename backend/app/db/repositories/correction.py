from __future__ import annotations

import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import ApplicationCorrectionRecord


class CorrectionRepository(BaseRepository[ApplicationCorrectionRecord]):
    """Repository seam for audited application corrections."""

    def map_row(self, row: sqlite3.Row) -> ApplicationCorrectionRecord:
        return ApplicationCorrectionRecord.model_validate(row_to_dict(row))
