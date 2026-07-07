from __future__ import annotations

import json
import sqlite3

from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.correction import JsonObject
from app.models.records import (
    ApplicationCorrectionConflictRecord,
    ApplicationCorrectionRecord,
    CorrectionConflictType,
    CorrectionType,
)


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
        created_at: str,
        reason: str | None = None,
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
                    json.dumps(before_json, separators=(",", ":"), sort_keys=True),
                    json.dumps(after_json, separators=(",", ":"), sort_keys=True),
                    reason,
                    created_at,
                ),
            )
            record = self.fetch_one(
                "SELECT * FROM application_corrections WHERE id = ?",
                (cursor.lastrowid,),
            )
        if should_commit:
            self.connection.commit()
        if record is None:
            msg = "Inserted correction record could not be loaded."
            raise RuntimeError(msg)
        return record

    def map_row(self, row: sqlite3.Row) -> ApplicationCorrectionRecord:
        return ApplicationCorrectionRecord.model_validate(row_to_dict(row))


class CorrectionConflictRepository(BaseRepository[ApplicationCorrectionConflictRecord]):
    """Repository seam for automatic evidence conflicts with manual corrections."""

    def list_by_application_id(
        self,
        application_id: str,
    ) -> list[ApplicationCorrectionConflictRecord]:
        return self.fetch_all(
            """
            SELECT *
            FROM application_correction_conflicts
            WHERE application_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (application_id,),
        )

    def upsert_conflict(
        self,
        *,
        application_id: str,
        conflict_key: str,
        conflict_type: CorrectionConflictType,
        existing_json: JsonObject,
        proposed_json: JsonObject,
        created_at: str,
        evidence_email_id: str | None = None,
    ) -> ApplicationCorrectionConflictRecord:
        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute(
                """
                INSERT INTO application_correction_conflicts (
                    application_id, conflict_key, conflict_type, existing_json,
                    proposed_json, evidence_email_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conflict_key) DO UPDATE SET
                    existing_json = excluded.existing_json,
                    proposed_json = excluded.proposed_json,
                    evidence_email_id = excluded.evidence_email_id
                """,
                (
                    application_id,
                    conflict_key,
                    conflict_type,
                    json.dumps(existing_json, separators=(",", ":"), sort_keys=True),
                    json.dumps(proposed_json, separators=(",", ":"), sort_keys=True),
                    evidence_email_id,
                    created_at,
                ),
            )
            record = self.fetch_one(
                "SELECT * FROM application_correction_conflicts WHERE conflict_key = ?",
                (conflict_key,),
            )
        if should_commit:
            self.connection.commit()
        if record is None:
            msg = "Inserted correction conflict record could not be loaded."
            raise RuntimeError(msg)
        return record

    def map_row(self, row: sqlite3.Row) -> ApplicationCorrectionConflictRecord:
        return ApplicationCorrectionConflictRecord.model_validate(row_to_dict(row))
