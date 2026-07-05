from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.providers.email import (
    EmailConnection,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProviderCursor,
    EmailSyncCursorExpiredError,
    EmailSyncMode,
)


class MetadataListingProvider(Protocol):
    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        """Return one provider-normalized metadata page."""
        ...


class EmailSyncPageResult(BaseModel):
    """One metadata sync page plus the mode that produced it."""

    model_config = ConfigDict(frozen=True)

    mode: EmailSyncMode
    page: EmailMetadataPage
    recovered_from_expired_cursor: bool = False


class EmailSyncService:
    """Service-layer coordination for resumable provider metadata sync."""

    def __init__(self, *, provider: MetadataListingProvider, page_size: int) -> None:
        if page_size < 1:
            msg = "page_size must be at least 1"
            raise ValueError(msg)
        self._provider = provider
        self._page_size = page_size

    async def list_metadata_page(
        self,
        *,
        connection: EmailConnection,
        mode: EmailSyncMode | None = None,
        sync_cursor: EmailProviderCursor | None = None,
        page_token: str | None = None,
    ) -> EmailSyncPageResult:
        """List one metadata page, falling back when an incremental cursor expires.

        A stale Gmail history ID invalidates incremental sync. When the provider
        reports that state, restart as a full metadata reconciliation page. The
        returned provider page keeps its `next_page_token` and `next_sync_cursor`
        so the caller can persist progress and continue the reconciliation.
        """

        if page_token is not None and sync_cursor is not None and mode is None:
            msg = "mode is required when continuing paginated sync with a cursor"
            raise ValueError(msg)

        sync_mode = mode or (
            EmailSyncMode.INCREMENTAL if sync_cursor is not None else EmailSyncMode.FULL_BACKFILL
        )

        if sync_mode is EmailSyncMode.FULL_BACKFILL:
            page = await self._list_full_backfill_page(connection, page_token=page_token)
            return EmailSyncPageResult(mode=EmailSyncMode.FULL_BACKFILL, page=page)

        if sync_cursor is None:
            msg = "sync_cursor is required for incremental metadata sync"
            raise ValueError(msg)

        try:
            page = await self._provider.list_message_metadata(
                connection,
                EmailMetadataListRequest(
                    mode=EmailSyncMode.INCREMENTAL,
                    page_size=self._page_size,
                    page_token=page_token,
                    sync_cursor=sync_cursor,
                ),
            )
        except EmailSyncCursorExpiredError:
            page = await self._list_full_backfill_page(connection, page_token=None)
            return EmailSyncPageResult(
                mode=EmailSyncMode.FULL_BACKFILL,
                page=page,
                recovered_from_expired_cursor=True,
            )

        return EmailSyncPageResult(mode=EmailSyncMode.INCREMENTAL, page=page)

    async def _list_full_backfill_page(
        self,
        connection: EmailConnection,
        *,
        page_token: str | None,
    ) -> EmailMetadataPage:
        return await self._provider.list_message_metadata(
            connection,
            EmailMetadataListRequest(
                mode=EmailSyncMode.FULL_BACKFILL,
                page_size=self._page_size,
                page_token=page_token,
            ),
        )
