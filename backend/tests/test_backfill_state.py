from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import GMAIL_READONLY_SCOPE, EmailProviderName
from app.db.repositories import BackfillStateRepository
from app.models.records import EmailBackfillStatus
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailAttachmentPolicy,
    EmailConnection,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProviderCapabilities,
    EmailProviderCursor,
)
from app.security import SecretKind, SecretRef
from app.services.sync_service import BackfillStateService, EmailSyncService

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 5, 14, 0, tzinfo=UTC)


def migrated_connection(tmp_path: Path) -> sqlite3.Connection:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return sqlite3.connect(database_path)


def test_backfill_state_records_page_progress_and_resume_token(tmp_path: Path) -> None:
    account = gmail_account()
    repository = BackfillStateRepository(migrated_connection(tmp_path))
    service = BackfillStateService(backfill_state_repository=repository)

    service.start_or_resume_backfill(account, started_at=NOW)
    progress = service.record_backfill_page(
        account,
        page=metadata_page(account, ("msg-1", "msg-2"), next_page_token="page-2"),
        updated_at=NOW + timedelta(seconds=5),
    )

    assert progress.status is EmailBackfillStatus.RUNNING
    assert progress.next_page_token == "page-2"
    assert progress.processed_page_count == 1
    assert progress.processed_message_count == 2
    assert progress.sync_cursor is None
    assert progress.started_at == NOW

    resumed_service = BackfillStateService(backfill_state_repository=repository)
    resumed = resumed_service.start_or_resume_backfill(
        account,
        started_at=NOW + timedelta(minutes=30),
    )

    assert resumed.status is EmailBackfillStatus.RUNNING
    assert resumed.next_page_token == "page-2"
    assert resumed.processed_page_count == 1
    assert resumed.processed_message_count == 2
    assert resumed.started_at == NOW


def test_backfill_state_marks_completion_and_persists_replacement_cursor(
    tmp_path: Path,
) -> None:
    account = gmail_account()
    repository = BackfillStateRepository(migrated_connection(tmp_path))
    service = BackfillStateService(backfill_state_repository=repository)
    sync_cursor = EmailProviderCursor(
        account=account,
        value="history-complete",
        issued_at=NOW + timedelta(minutes=5),
    )

    service.start_or_resume_backfill(account, started_at=NOW)
    service.record_backfill_page(
        account,
        page=metadata_page(account, ("msg-1",), next_page_token="page-2"),
        updated_at=NOW + timedelta(seconds=5),
    )
    completed = service.record_backfill_page(
        account,
        page=metadata_page(
            account,
            ("msg-2", "msg-3"),
            next_sync_cursor=sync_cursor,
        ),
        updated_at=NOW + timedelta(minutes=5),
    )

    assert completed.status is EmailBackfillStatus.COMPLETED
    assert completed.next_page_token is None
    assert completed.processed_page_count == 2
    assert completed.processed_message_count == 3
    assert completed.sync_cursor == "history-complete"
    assert completed.cursor_issued_at == NOW + timedelta(minutes=5)
    assert completed.completed_at == NOW + timedelta(minutes=5)


def test_failed_backfill_resumes_from_persisted_page_token(tmp_path: Path) -> None:
    account = gmail_account()
    repository = BackfillStateRepository(migrated_connection(tmp_path))
    service = BackfillStateService(backfill_state_repository=repository)

    service.start_or_resume_backfill(account, started_at=NOW)
    service.record_backfill_page(
        account,
        page=metadata_page(account, ("msg-1", "msg-2"), next_page_token="page-2"),
        updated_at=NOW + timedelta(seconds=5),
    )
    failed = service.mark_backfill_failed(
        account,
        public_error="provider rate limit",
        updated_at=NOW + timedelta(seconds=10),
    )

    assert failed.status is EmailBackfillStatus.FAILED
    assert failed.next_page_token == "page-2"
    assert failed.processed_page_count == 1
    assert failed.processed_message_count == 2
    assert failed.last_error == "provider rate limit"

    resumed = service.start_or_resume_backfill(
        account,
        started_at=NOW + timedelta(minutes=30),
    )

    assert resumed.status is EmailBackfillStatus.RUNNING
    assert resumed.next_page_token == "page-2"
    assert resumed.processed_page_count == 1
    assert resumed.processed_message_count == 2
    assert resumed.last_error is None


def test_sync_service_uses_persisted_backfill_resume_token(tmp_path: Path) -> None:
    repository = BackfillStateRepository(migrated_connection(tmp_path))
    backfill_state_service = BackfillStateService(backfill_state_repository=repository)
    provider = PaginatedBackfillProvider()
    sync_service = EmailSyncService(provider=provider, page_size=250)
    connection = email_connection()

    first = asyncio.run(
        sync_service.run_backfill_page(
            connection=connection,
            backfill_state_service=backfill_state_service,
            updated_at=NOW,
        )
    )
    second = asyncio.run(
        sync_service.run_backfill_page(
            connection=connection,
            backfill_state_service=backfill_state_service,
            updated_at=NOW + timedelta(minutes=1),
        )
    )

    assert [request.page_token for request in provider.requests] == [None, "page-2"]
    assert first.state.status is EmailBackfillStatus.RUNNING
    assert first.state.next_page_token == "page-2"
    assert second.state.status is EmailBackfillStatus.COMPLETED
    assert second.state.next_page_token is None
    assert second.state.processed_page_count == 2
    assert second.state.processed_message_count == 2
    assert second.state.sync_cursor == "history-complete"


class PaginatedBackfillProvider:
    name = EmailProviderName.GMAIL
    capabilities = EmailProviderCapabilities(
        provider=EmailProviderName.GMAIL,
        required_scopes=(GMAIL_READONLY_SCOPE,),
        supports_oauth=True,
        supports_full_backfill=True,
        supports_incremental_sync=True,
        attachment_policy=EmailAttachmentPolicy.IGNORED,
        max_metadata_page_size=500,
        max_body_batch_size=100,
    )

    def __init__(self) -> None:
        self.requests: list[EmailMetadataListRequest] = []

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        self.requests.append(request)
        if request.page_token is None:
            return metadata_page(
                connection.account,
                ("msg-1",),
                next_page_token="page-2",
            )

        return metadata_page(
            connection.account,
            ("msg-2",),
            next_sync_cursor=EmailProviderCursor(
                account=connection.account,
                value="history-complete",
                issued_at=NOW + timedelta(minutes=1),
            ),
        )


def email_connection() -> EmailConnection:
    account = gmail_account()
    return EmailConnection(
        account=account,
        display_email=EmailAddress(address=account.account_id),
        credential_ref=SecretRef(
            kind=SecretKind.OAUTH_TOKEN,
            provider="gmail",
            name="me-example-com",
        ),
        granted_scopes=(GMAIL_READONLY_SCOPE,),
        connected_at=NOW,
    )


def gmail_account() -> EmailAccountRef:
    return EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")


def metadata_page(
    account: EmailAccountRef,
    message_ids: tuple[str, ...],
    *,
    next_page_token: str | None = None,
    next_sync_cursor: EmailProviderCursor | None = None,
) -> EmailMetadataPage:
    return EmailMetadataPage(
        messages=tuple(
            EmailMessageMetadata(
                ref=EmailMessageRef(
                    account=account,
                    message_id=message_id,
                    thread_id=f"thread-{message_id}",
                )
            )
            for message_id in message_ids
        ),
        next_page_token=next_page_token,
        next_sync_cursor=next_sync_cursor,
    )
