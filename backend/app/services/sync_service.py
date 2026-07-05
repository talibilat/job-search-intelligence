from __future__ import annotations

from datetime import UTC, datetime

from app.db.repositories.sync_state import SyncStateRepository
from app.models.records import EmailSyncStateRecord
from app.providers.email import EmailAccountRef, EmailProviderCursor


class SyncService:
    """Business seam for email sync state used by full and incremental runs."""

    def __init__(self, *, sync_state_repository: SyncStateRepository) -> None:
        self._sync_state_repository = sync_state_repository

    def get_sync_cursor(self, account: EmailAccountRef) -> EmailProviderCursor | None:
        return self._sync_state_repository.get_cursor(account)

    def store_sync_cursor(
        self,
        cursor: EmailProviderCursor,
        *,
        updated_at: datetime | None = None,
    ) -> EmailSyncStateRecord:
        return self._sync_state_repository.save_cursor(
            cursor,
            updated_at=updated_at or datetime.now(UTC),
        )
