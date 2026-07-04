from __future__ import annotations

import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import ApplicationEventRecord


class EventRepository(BaseRepository[ApplicationEventRecord]):
    """Repository seam for application event timeline records."""

    def map_row(self, row: sqlite3.Row) -> ApplicationEventRecord:
        return ApplicationEventRecord.model_validate(row_to_dict(row))
