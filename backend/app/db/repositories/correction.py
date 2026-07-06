from __future__ import annotations

import json
import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.correction import JsonObject
from app.models.records import ApplicationCorrectionRecord, CorrectionType


class CorrectionRepository(BaseRepository[ApplicationCorrectionRecord]):
    """Repository seam for audited application corrections."""

    def list_by_application_id(
        self,
        application_id: str,
    ) -> list[ApplicationCorrectionRecord]:
        return self.fetch_all(
            """
            SELECT *
            FROM application_corrections
            WHERE application_id = ?
            ORDER BY id
            """,
            (application_id,),
        )

    def reassign_application_corrections(
        self,
        *,
        source_application_id: str,
        target_application_id: str,
    ) -> int:
        should_commit = not self.connection.in_transaction
        with self.transaction():
            cursor = self.execute(
                """
                UPDATE application_corrections
                SET application_id = ?
                WHERE application_id = ?
                """,
                (target_application_id, source_application_id),
            )
        if should_commit:
            self.connection.commit()
        return cursor.rowcount

    def create_correction(
        self,
        *,
        application_id: str,
        correction_type: CorrectionType,
        before_json: JsonObject,
        after_json: JsonObject,
        reason: str | None,
        created_at: str,
    ) -> ApplicationCorrectionRecord:
        should_commit = not self.connection.in_transaction
        with self.transaction():
            cursor = self.execute(
                """
                INSERT INTO application_corrections (
                    application_id, correction_type, before_json,
                    after_json, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    correction_type,
                    json.dumps(before_json, separators=(",", ":")),
                    json.dumps(after_json, separators=(",", ":")),
                    reason,
                    created_at,
                ),
            )
            correction_id = cursor.lastrowid
            correction = self.fetch_one(
                "SELECT * FROM application_corrections WHERE id = ?",
                (correction_id,),
            )
        if should_commit:
            self.connection.commit()
        if correction is None:
            msg = "inserted application correction could not be loaded"
            raise RuntimeError(msg)
        return correction

    def map_row(self, row: sqlite3.Row) -> ApplicationCorrectionRecord:
        return ApplicationCorrectionRecord.model_validate(row_to_dict(row))
