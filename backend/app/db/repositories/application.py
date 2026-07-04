from __future__ import annotations

import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import ApplicationRecord


class ApplicationRepository(BaseRepository[ApplicationRecord]):
    """Repository seam for canonical job applications."""

    def map_row(self, row: sqlite3.Row) -> ApplicationRecord:
        return ApplicationRecord.model_validate(row_to_dict(row))
