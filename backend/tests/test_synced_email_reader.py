from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.config import EmailProviderName
from app.models import RawEmailBodyRetentionState, RawEmailReaderRecord
from app.providers.email import (
    EmailAccountRef,
    EmailAddress,
    EmailBodyBatch,
    EmailBodyFetchFailure,
    EmailBodyFetchFailureReason,
    EmailBodyFetchRequest,
    EmailBodySource,
    EmailConnection,
    EmailMessageBody,
    EmailProviderAuthError,
    EmailProviderTransientError,
)
from app.security import SecretKind, SecretRef
from app.services.synced_email_reader import (
    SyncedEmailContentUnavailableError,
    SyncedEmailNotFoundError,
    SyncedEmailReaderService,
)

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_read_email_returns_retained_body_without_calling_provider() -> None:
    connection = email_connection()
    repository = FakeEmailRepository(
        records={
            "public-retained": reader_record(
                public_id="public-retained",
                provider_message_id="msg-1",
                body_text="Stored plain text",
                body_retention_state=RawEmailBodyRetentionState.RETAINED,
            ),
        }
    )
    provider = FakeEmailProvider()
    service = SyncedEmailReaderService(
        repository=repository,
        provider=provider,
        connection=connection,
        provider_name=EmailProviderName.GMAIL,
    )

    detail = await service.read_email("public-retained")

    assert detail.body_text == "Stored plain text"
    assert provider.fetch_requests == []
    assert repository.persisted_body_writes == []


@pytest.mark.anyio
async def test_read_email_fetches_transient_body_for_metadata_only_message() -> None:
    connection = email_connection()
    repository = FakeEmailRepository(
        records={
            "public-metadata-only": reader_record(
                public_id="public-metadata-only",
                provider_message_id="msg-2",
                body_text=None,
                body_retention_state=RawEmailBodyRetentionState.METADATA_ONLY,
            ),
        }
    )
    provider = FakeEmailProvider(
        body_text_by_message_id={"msg-2": "Fetched plain text"},
    )
    service = SyncedEmailReaderService(
        repository=repository,
        provider=provider,
        connection=connection,
        provider_name=EmailProviderName.GMAIL,
    )

    detail = await service.read_email("public-metadata-only")

    assert detail.body_text == "Fetched plain text"
    assert len(provider.fetch_requests) == 1
    assert provider.fetch_requests[0].refs[0].message_id == "msg-2"
    assert repository.persisted_body_writes == []


@pytest.mark.anyio
async def test_read_email_raises_not_found_for_unknown_public_id() -> None:
    connection = email_connection()
    repository = FakeEmailRepository(records={})
    provider = FakeEmailProvider()
    service = SyncedEmailReaderService(
        repository=repository,
        provider=provider,
        connection=connection,
        provider_name=EmailProviderName.GMAIL,
    )

    with pytest.raises(SyncedEmailNotFoundError):
        await service.read_email("unknown-public-id")


@pytest.mark.anyio
async def test_read_email_scopes_lookup_to_configured_provider() -> None:
    connection = email_connection()
    repository = FakeEmailRepository(records={})
    provider = FakeEmailProvider()
    service = SyncedEmailReaderService(
        repository=repository,
        provider=provider,
        connection=connection,
        provider_name=EmailProviderName.GMAIL,
    )

    with pytest.raises(SyncedEmailNotFoundError):
        await service.read_email("public-wrong-provider")

    assert repository.lookups == [("public-wrong-provider", EmailProviderName.GMAIL)]


@pytest.mark.anyio
async def test_read_email_raises_content_unavailable_for_empty_provider_body() -> None:
    connection = email_connection()
    repository = FakeEmailRepository(
        records={
            "public-empty": reader_record(
                public_id="public-empty",
                provider_message_id="msg-empty",
                body_text=None,
                body_retention_state=RawEmailBodyRetentionState.METADATA_ONLY,
            ),
        }
    )
    provider = FakeEmailProvider(
        failures_by_message_id={
            "msg-empty": EmailBodyFetchFailureReason.EMPTY,
        }
    )
    service = SyncedEmailReaderService(
        repository=repository,
        provider=provider,
        connection=connection,
        provider_name=EmailProviderName.GMAIL,
    )

    with pytest.raises(SyncedEmailContentUnavailableError):
        await service.read_email("public-empty")


@pytest.mark.anyio
async def test_read_email_raises_content_unavailable_when_provider_reports_not_found() -> None:
    connection = email_connection()
    repository = FakeEmailRepository(
        records={
            "public-missing": reader_record(
                public_id="public-missing",
                provider_message_id="msg-missing",
                body_text=None,
                body_retention_state=RawEmailBodyRetentionState.METADATA_ONLY,
            ),
        }
    )
    provider = FakeEmailProvider(
        failures_by_message_id={
            "msg-missing": EmailBodyFetchFailureReason.NOT_FOUND,
        }
    )
    service = SyncedEmailReaderService(
        repository=repository,
        provider=provider,
        connection=connection,
        provider_name=EmailProviderName.GMAIL,
    )

    with pytest.raises(SyncedEmailContentUnavailableError):
        await service.read_email("public-missing")


@pytest.mark.anyio
async def test_read_email_propagates_provider_reauthentication_error() -> None:
    connection = email_connection()
    repository = FakeEmailRepository(
        records={
            "public-reauth": reader_record(
                public_id="public-reauth",
                provider_message_id="msg-reauth",
                body_text=None,
                body_retention_state=RawEmailBodyRetentionState.METADATA_ONLY,
            ),
        }
    )
    provider = FakeEmailProvider(
        raises_by_message_id={
            "msg-reauth": EmailProviderAuthError(public_message="Reauthentication required."),
        }
    )
    service = SyncedEmailReaderService(
        repository=repository,
        provider=provider,
        connection=connection,
        provider_name=EmailProviderName.GMAIL,
    )

    with pytest.raises(EmailProviderAuthError):
        await service.read_email("public-reauth")


@pytest.mark.anyio
async def test_read_email_propagates_transient_provider_failure() -> None:
    connection = email_connection()
    repository = FakeEmailRepository(
        records={
            "public-transient": reader_record(
                public_id="public-transient",
                provider_message_id="msg-transient",
                body_text=None,
                body_retention_state=RawEmailBodyRetentionState.METADATA_ONLY,
            ),
        }
    )
    provider = FakeEmailProvider(
        raises_by_message_id={
            "msg-transient": EmailProviderTransientError(
                public_message="Gmail is temporarily unavailable.",
            ),
        }
    )
    service = SyncedEmailReaderService(
        repository=repository,
        provider=provider,
        connection=connection,
        provider_name=EmailProviderName.GMAIL,
    )

    with pytest.raises(EmailProviderTransientError):
        await service.read_email("public-transient")


def email_connection() -> EmailConnection:
    account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id="me@example.com")
    return EmailConnection(
        account=account,
        display_email=EmailAddress(address="me@example.com"),
        credential_ref=SecretRef(
            kind=SecretKind.OAUTH_TOKEN,
            provider="gmail",
            name="me-example-com",
        ),
        granted_scopes=(GMAIL_READONLY_SCOPE,),
        connected_at=NOW,
    )


def reader_record(
    *,
    public_id: str,
    provider_message_id: str,
    body_text: str | None,
    body_retention_state: RawEmailBodyRetentionState,
) -> RawEmailReaderRecord:
    return RawEmailReaderRecord(
        public_id=public_id,
        provider_message_id=provider_message_id,
        thread_id=f"thread-{provider_message_id}",
        from_addr="jobs@example.com",
        to_addr="me@example.com",
        subject="Application received",
        sent_at=NOW,
        body_text=body_text,
        body_retention_state=body_retention_state,
        provider=EmailProviderName.GMAIL.value,
    )


class FakeEmailRepository:
    def __init__(
        self,
        *,
        records: dict[str, RawEmailReaderRecord],
    ) -> None:
        self._records = records
        self.persisted_body_writes: list[EmailMessageBody] = []
        self.lookups: list[tuple[str, EmailProviderName]] = []

    def get_reader_record(
        self,
        public_id: str,
        provider: EmailProviderName,
    ) -> RawEmailReaderRecord | None:
        self.lookups.append((public_id, provider))
        return self._records.get(public_id)


class FakeEmailProvider:
    def __init__(
        self,
        *,
        body_text_by_message_id: dict[str, str] | None = None,
        failures_by_message_id: dict[str, EmailBodyFetchFailureReason] | None = None,
        raises_by_message_id: dict[str, Exception] | None = None,
    ) -> None:
        self._body_text_by_message_id = body_text_by_message_id or {}
        self._failures_by_message_id = failures_by_message_id or {}
        self._raises_by_message_id = raises_by_message_id or {}
        self.fetch_requests: list[EmailBodyFetchRequest] = []

    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        del connection
        self.fetch_requests.append(request)
        ref = request.refs[0]
        if ref.message_id in self._raises_by_message_id:
            raise self._raises_by_message_id[ref.message_id]
        if ref.message_id in self._failures_by_message_id:
            return EmailBodyBatch(
                bodies=(),
                failures=(
                    EmailBodyFetchFailure(
                        ref=ref,
                        reason=self._failures_by_message_id[ref.message_id],
                    ),
                ),
            )
        body_text = self._body_text_by_message_id.get(ref.message_id, "")
        return EmailBodyBatch(
            bodies=(
                EmailMessageBody(
                    ref=ref,
                    body_text=body_text,
                    body_source=EmailBodySource.TEXT_PLAIN,
                    truncated=False,
                    fetched_at=NOW,
                ),
            ),
        )
