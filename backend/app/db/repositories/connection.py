from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from app.config import EmailProviderName
from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.records import EmailConnectionRecord
from app.providers.email import EmailAccountRef, EmailAddress, EmailConnection
from app.security import SecretKind, SecretRef


class EmailConnectionRepository(BaseRepository[EmailConnectionRecord]):
    def save_connection(self, connection: EmailConnection) -> EmailConnectionRecord:
        updated_at = datetime.now(UTC)
        should_commit = not self.connection.in_transaction

        with self.transaction():
            self.execute(
                """
                INSERT INTO email_connections (
                    provider,
                    account_id,
                    display_email,
                    credential_ref_kind,
                    credential_ref_provider,
                    credential_ref_name,
                    granted_scopes,
                    connected_at,
                    credential_expires_at,
                    reauth_required,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, account_id) DO UPDATE SET
                    display_email = excluded.display_email,
                    credential_ref_kind = excluded.credential_ref_kind,
                    credential_ref_provider = excluded.credential_ref_provider,
                    credential_ref_name = excluded.credential_ref_name,
                    granted_scopes = excluded.granted_scopes,
                    connected_at = excluded.connected_at,
                    credential_expires_at = excluded.credential_expires_at,
                    reauth_required = excluded.reauth_required,
                    updated_at = excluded.updated_at
                """,
                (
                    connection.account.provider.value,
                    connection.account.account_id,
                    connection.display_email.address
                    if connection.display_email is not None
                    else None,
                    connection.credential_ref.kind.value,
                    connection.credential_ref.provider,
                    connection.credential_ref.name,
                    json.dumps(list(connection.granted_scopes), sort_keys=True),
                    connection.connected_at.isoformat(),
                    connection.credential_expires_at.isoformat()
                    if connection.credential_expires_at is not None
                    else None,
                    int(connection.reauth_required),
                    updated_at.isoformat(),
                ),
            )

        if should_commit:
            self.connection.commit()

        record = self.fetch_connection(connection.account)
        if record is None:
            msg = "stored email connection could not be read back"
            raise RuntimeError(msg)
        return record

    def fetch_connection(self, account: EmailAccountRef) -> EmailConnectionRecord | None:
        return self.fetch_one(
            """
            SELECT
                provider,
                account_id,
                display_email,
                credential_ref_kind,
                credential_ref_provider,
                credential_ref_name,
                granted_scopes,
                connected_at,
                credential_expires_at,
                reauth_required,
                updated_at
            FROM email_connections
            WHERE provider = ? AND account_id = ?
            """,
            (account.provider.value, account.account_id),
        )

    def fetch_connection_metadata(self, account: EmailAccountRef) -> EmailConnection | None:
        record = self.fetch_connection(account)
        if record is None:
            return None
        return _connection_from_record(record)

    def fetch_default_connection_metadata(
        self,
        provider: EmailProviderName,
    ) -> EmailConnection | None:
        record = self.fetch_one(
            """
            SELECT
                provider,
                account_id,
                display_email,
                credential_ref_kind,
                credential_ref_provider,
                credential_ref_name,
                granted_scopes,
                connected_at,
                credential_expires_at,
                reauth_required,
                updated_at
            FROM email_connections
            WHERE provider = ? AND reauth_required = 0
            ORDER BY connected_at DESC, updated_at DESC
            LIMIT 1
            """,
            (provider.value,),
        )
        if record is None:
            return None
        return _connection_from_record(record)

    def map_row(self, row: sqlite3.Row) -> EmailConnectionRecord:
        return EmailConnectionRecord.model_validate(row_to_dict(row))


def _connection_from_record(record: EmailConnectionRecord) -> EmailConnection:
    return EmailConnection(
        account=EmailAccountRef(
            provider=EmailProviderName(record.provider),
            account_id=record.account_id,
        ),
        display_email=None
        if record.display_email is None
        else EmailAddress(address=record.display_email),
        credential_ref=SecretRef(
            kind=SecretKind(record.credential_ref_kind),
            provider=record.credential_ref_provider,
            name=record.credential_ref_name,
        ),
        granted_scopes=tuple(record.granted_scopes),
        connected_at=record.connected_at,
        credential_expires_at=record.credential_expires_at,
        reauth_required=record.reauth_required,
    )
