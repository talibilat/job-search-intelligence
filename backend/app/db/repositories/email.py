from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime

from app.config import EmailProviderName
from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import RawEmailBodyRetentionState, RawEmailRecord
from app.providers.email import EmailAddress, EmailMessageMetadata


class EmailRepository(BaseRepository[RawEmailRecord]):
    """Repository seam for raw email records with typed retention validation."""

    def upsert_raw_emails(self, records: Iterable[RawEmailRecord]) -> None:
        """Write raw email rows idempotently without downgrading retained bodies."""

        record_tuple = tuple(records)
        if not record_tuple:
            return

        should_commit = not self.connection.in_transaction
        with self.transaction():
            self.execute_many(
                """
                INSERT INTO raw_emails (
                    id,
                    thread_id,
                    from_addr,
                    to_addr,
                    subject,
                    sent_at,
                    body_text,
                    body_retention_state,
                    labels,
                    provider,
                    ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    from_addr = excluded.from_addr,
                    to_addr = excluded.to_addr,
                    subject = excluded.subject,
                    sent_at = excluded.sent_at,
                    body_text = CASE
                        WHEN raw_emails.body_retention_state IN ('retained', 'debugging')
                            AND excluded.body_retention_state = 'metadata_only'
                        THEN raw_emails.body_text
                        ELSE excluded.body_text
                    END,
                    body_retention_state = CASE
                        WHEN raw_emails.body_retention_state IN ('retained', 'debugging')
                            AND excluded.body_retention_state = 'metadata_only'
                        THEN raw_emails.body_retention_state
                        ELSE excluded.body_retention_state
                    END,
                    labels = excluded.labels,
                    provider = excluded.provider,
                    ingested_at = excluded.ingested_at
                WHERE raw_emails.provider = excluded.provider
                """,
                [
                    (
                        record.id,
                        record.thread_id,
                        record.from_addr,
                        record.to_addr,
                        record.subject,
                        record.sent_at.isoformat() if record.sent_at is not None else None,
                        record.body_text,
                        record.body_retention_state.value,
                        json.dumps(record.labels, separators=(",", ":")),
                        record.provider,
                        record.ingested_at.isoformat(),
                    )
                    for record in record_tuple
                ],
            )

        if should_commit:
            self.connection.commit()

    def upsert_metadata_only(
        self,
        messages: tuple[EmailMessageMetadata, ...],
        *,
        ingested_at: datetime,
    ) -> int:
        """Persist provider metadata without overwriting retained body content."""

        self.upsert_raw_emails(
            RawEmailRecord(
                id=message.ref.message_id,
                thread_id=message.ref.thread_id,
                from_addr=_format_email_address(message.from_addr),
                to_addr=_format_email_addresses(message.to_addrs),
                subject=message.subject,
                sent_at=message.sent_at or message.received_at,
                body_text=None,
                body_retention_state=RawEmailBodyRetentionState.METADATA_ONLY,
                labels=list(message.labels),
                provider=message.ref.account.provider.value,
                ingested_at=ingested_at,
            )
            for message in messages
        )
        return len(messages)

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

    def list_raw_email_ids(self, *, provider: EmailProviderName) -> list[str]:
        rows = self.execute(
            "SELECT id FROM raw_emails WHERE provider = ? ORDER BY id",
            (provider.value,),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def map_row(self, row: sqlite3.Row) -> RawEmailRecord:
        return RawEmailRecord.model_validate(row_to_dict(row))


def _format_email_address(address: EmailAddress | None) -> str | None:
    if address is None:
        return None
    if address.display_name is None:
        return address.address
    return f"{address.display_name} <{address.address}>"


def _format_email_addresses(addresses: tuple[EmailAddress, ...]) -> str | None:
    if not addresses:
        return None
    return ", ".join(
        address for address in (_format_email_address(item) for item in addresses) if address
    )


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _format_json_array(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), separators=(",", ":"))
