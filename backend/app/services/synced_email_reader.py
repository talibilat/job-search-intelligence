from __future__ import annotations

from typing import Protocol

from app.config import EmailProviderName
from app.models._email_address import email_address_domain
from app.models.raw_email import RawEmailDetail, RawEmailReaderRecord
from app.providers.email import (
    EmailBodyBatch,
    EmailBodyFetchRequest,
    EmailConnection,
    EmailMessageRef,
)


class ReaderRepository(Protocol):
    def get_reader_record(
        self,
        public_id: str,
        provider: EmailProviderName,
    ) -> RawEmailReaderRecord | None: ...


class EmailBodyProvider(Protocol):
    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch: ...


class SyncedEmailNotFoundError(LookupError):
    """Raised when no raw email matches the requested opaque identifier."""


class SyncedEmailContentUnavailableError(RuntimeError):
    """Raised when neither a retained body nor a provider fetch can supply content."""


class SyncedEmailReaderService:
    """Resolve on-demand plain-text content for one synced email.

    Retained or debugging bodies are served from local storage. Metadata-only
    messages are fetched from the provider transiently and are never written
    back, so opening a message never expands what is persisted locally.
    """

    def __init__(
        self,
        *,
        repository: ReaderRepository,
        provider: EmailBodyProvider,
        connection: EmailConnection,
        provider_name: EmailProviderName,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._connection = connection
        self._provider_name = provider_name

    async def read_email(self, public_id: str) -> RawEmailDetail:
        record = self._repository.get_reader_record(public_id, provider=self._provider_name)
        if record is None:
            raise SyncedEmailNotFoundError

        if record.body_text is not None:
            return _detail_from_record(record, body_text=record.body_text)

        batch = await self._provider.fetch_message_bodies(
            self._connection,
            EmailBodyFetchRequest(refs=(_message_ref(record, self._connection),)),
        )
        if not batch.bodies:
            raise SyncedEmailContentUnavailableError
        return _detail_from_record(record, body_text=batch.bodies[0].body_text)


def _message_ref(record: RawEmailReaderRecord, connection: EmailConnection) -> EmailMessageRef:
    return EmailMessageRef(
        account=connection.account,
        message_id=record.provider_message_id,
        thread_id=record.thread_id,
    )


def _detail_from_record(record: RawEmailReaderRecord, *, body_text: str) -> RawEmailDetail:
    return RawEmailDetail(
        public_id=record.public_id,
        from_domain=email_address_domain(record.from_addr),
        subject=record.subject,
        sent_at=record.sent_at,
        body_retention_state=record.body_retention_state,
        body_text=body_text,
    )
