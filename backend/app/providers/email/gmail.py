from __future__ import annotations

import asyncio
import json
from datetime import datetime
from email.utils import getaddresses, parsedate_to_datetime
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.config import GMAIL_READONLY_SCOPE, AppSettings, EmailProviderName
from app.providers.email.provider import (
    EmailAddress,
    EmailAttachmentPolicy,
    EmailAuthorizationCallbackRequest,
    EmailAuthorizationStartRequest,
    EmailAuthorizationStartResult,
    EmailBodyBatch,
    EmailBodyFetchRequest,
    EmailConnection,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProviderAuthError,
    EmailProviderCapabilities,
    EmailProviderError,
    EmailProviderTransientError,
    EmailSyncMode,
)
from app.security import SecretStore

GMAIL_METADATA_HEADERS = (
    "From",
    "To",
    "Cc",
    "Subject",
    "Date",
    "Message-ID",
)

GMAIL_API_BASE_URL = "https://gmail.googleapis.com"
GMAIL_MAX_METADATA_PAGE_SIZE = 500
_GMAIL_MAX_BODY_BATCH_SIZE = 100
_MESSAGES_PATH = "/gmail/v1/users/me/messages"
_MESSAGE_LIST_FIELDS = "messages(id,threadId),nextPageToken"
_MESSAGE_METADATA_FIELDS = "id,threadId,labelIds,sizeEstimate,payload/headers(name,value)"
_INVALID_DATA_MESSAGE = "Gmail metadata listing returned invalid data"


class GoogleOAuthInstalledClientConfig(BaseModel):
    """Subset of a Google Desktop OAuth client JSON needed to start auth."""

    model_config = ConfigDict(frozen=True)

    client_id: str = Field(min_length=1)
    auth_uri: str = Field(min_length=1)


class GoogleOAuthClientConfig(BaseModel):
    """Google OAuth client config without exposing client secret values."""

    model_config = ConfigDict(frozen=True)

    installed: GoogleOAuthInstalledClientConfig


class GmailEmailProvider:
    """Gmail adapter with OAuth start and optional SecretStore-backed metadata listing."""

    name = EmailProviderName.GMAIL

    def __init__(
        self,
        *,
        settings: AppSettings,
        secret_store: SecretStore | None = None,
        transport: GmailApiTransport | None = None,
    ) -> None:
        if tuple(settings.gmail_scopes) != (GMAIL_READONLY_SCOPE,):
            raise EmailProviderError(
                public_message="Gmail provider requires only the gmail.readonly scope."
            )

        self._client_config_file = settings.gmail_client_config_file
        self._scopes = tuple(settings.gmail_scopes)
        self.capabilities = EmailProviderCapabilities(
            provider=EmailProviderName.GMAIL,
            required_scopes=self._scopes,
            supports_oauth=True,
            supports_full_backfill=True,
            supports_incremental_sync=True,
            attachment_policy=EmailAttachmentPolicy.IGNORED,
            max_metadata_page_size=settings.gmail_page_size,
            max_body_batch_size=_GMAIL_MAX_BODY_BATCH_SIZE,
        )
        self._message_lister = (
            GmailMessageLister(secret_store=secret_store, transport=transport)
            if secret_store is not None
            else None
        )

    async def start_authorization(
        self,
        request: EmailAuthorizationStartRequest,
    ) -> EmailAuthorizationStartResult:
        if request.provider is not EmailProviderName.GMAIL:
            raise EmailProviderAuthError(
                public_message="Gmail authorization can only start for Gmail."
            )
        if self._scopes != (GMAIL_READONLY_SCOPE,):
            raise EmailProviderAuthError(
                public_message="Gmail authorization is limited to gmail.readonly in v1."
            )

        client_config = self._load_client_config()
        return EmailAuthorizationStartResult(
            provider=EmailProviderName.GMAIL,
            authorization_url=self._build_authorization_url(
                client_config=client_config,
                request=request,
            ),
            state=request.state,
            requested_scopes=self._scopes,
        )

    async def complete_authorization(
        self,
        request: EmailAuthorizationCallbackRequest,
    ) -> EmailConnection:
        raise EmailProviderAuthError(public_message="Gmail OAuth callback is not implemented yet.")

    async def refresh_connection(self, connection: EmailConnection) -> EmailConnection:
        raise EmailProviderAuthError(
            public_message="Gmail credential refresh is not implemented yet."
        )

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        if self._message_lister is None:
            raise EmailProviderError(public_message="Gmail metadata sync is not implemented yet.")
        return await self._message_lister.list_message_metadata(connection, request)

    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        raise EmailProviderError(public_message="Gmail body fetching is not implemented yet.")

    def _load_client_config(self) -> GoogleOAuthClientConfig:
        try:
            payload = json.loads(self._client_config_file.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise EmailProviderAuthError(
                public_message="Google OAuth client config file was not found."
            ) from error
        except (OSError, json.JSONDecodeError) as error:
            raise EmailProviderAuthError(
                public_message="Google OAuth client config file could not be read."
            ) from error

        try:
            return GoogleOAuthClientConfig.model_validate(payload)
        except ValidationError as error:
            raise EmailProviderAuthError(
                public_message="Google OAuth client config file is invalid."
            ) from error

    def _build_authorization_url(
        self,
        *,
        client_config: GoogleOAuthClientConfig,
        request: EmailAuthorizationStartRequest,
    ) -> str:
        query = urlencode(
            {
                "access_type": "offline",
                "client_id": client_config.installed.client_id,
                "include_granted_scopes": "true",
                "prompt": "consent",
                "redirect_uri": request.redirect_uri,
                "response_type": "code",
                "scope": " ".join(self._scopes),
                "state": request.state,
            }
        )
        separator = "&" if "?" in client_config.installed.auth_uri else "?"
        return f"{client_config.installed.auth_uri}{separator}{query}"


class GmailApiTransport(Protocol):
    async def get_json(
        self,
        path: str,
        *,
        query: tuple[tuple[str, str], ...],
        access_token: SecretStr,
    ) -> dict[str, object]:
        """Return a decoded Gmail API JSON object without exposing token material."""
        ...


class UrllibGmailApiTransport:
    def __init__(self, *, base_url: str = GMAIL_API_BASE_URL, timeout_seconds: int = 30) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def get_json(
        self,
        path: str,
        *,
        query: tuple[tuple[str, str], ...],
        access_token: SecretStr,
    ) -> dict[str, object]:
        return await asyncio.to_thread(
            self._get_json_sync,
            path,
            query=query,
            access_token=access_token,
        )

    def _get_json_sync(
        self,
        path: str,
        *,
        query: tuple[tuple[str, str], ...],
        access_token: SecretStr,
    ) -> dict[str, object]:
        query_string = urlencode(query)
        url = f"{self._base_url}{path}"
        if query_string:
            url = f"{url}?{query_string}"

        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token.get_secret_value()}",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = response.read()
        except HTTPError as error:
            if error.code in {401, 403}:
                raise EmailProviderAuthError(
                    public_message="Gmail authorization is required"
                ) from error
            if error.code in {429, 500, 502, 503, 504}:
                raise EmailProviderTransientError(
                    public_message="Gmail metadata listing is temporarily unavailable"
                ) from error
            raise EmailProviderError(public_message="Gmail metadata listing failed") from error
        except URLError as error:
            raise EmailProviderTransientError(
                public_message="Gmail metadata listing is temporarily unavailable"
            ) from error

        try:
            raw_response = response_body.decode("utf-8")
            decoded_response = json.loads(raw_response)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise EmailProviderError(public_message=_INVALID_DATA_MESSAGE) from None

        if not isinstance(decoded_response, dict):
            raise EmailProviderError(public_message=_INVALID_DATA_MESSAGE)
        return cast(dict[str, object], decoded_response)


class GmailMessageListItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    id: str = Field(min_length=1)
    thread_id: str | None = Field(default=None, alias="threadId")


class GmailMessageListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    messages: tuple[GmailMessageListItem, ...] = ()
    next_page_token: str | None = Field(default=None, alias="nextPageToken")


class GmailMessageHeader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str = Field(min_length=1)
    value: str = ""


class GmailMessagePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    headers: tuple[GmailMessageHeader, ...] = ()


class GmailMessageMetadataResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    id: str = Field(min_length=1)
    thread_id: str | None = Field(default=None, alias="threadId")
    label_ids: tuple[str, ...] = Field(default=(), alias="labelIds")
    size_estimate: int | None = Field(default=None, ge=0, alias="sizeEstimate")
    payload: GmailMessagePayload | None = None


class GmailMessageLister:
    """List Gmail full-backfill pages without fetching snippets or body content."""

    def __init__(
        self,
        *,
        secret_store: SecretStore,
        transport: GmailApiTransport | None = None,
    ) -> None:
        self._secret_store = secret_store
        self._transport = transport or UrllibGmailApiTransport()

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        if request.mode is not EmailSyncMode.FULL_BACKFILL:
            raise EmailProviderError(
                public_message="Gmail incremental metadata sync is not implemented yet"
            )

        list_query = _list_query(request)
        access_token = await self._secret_store.get_secret(connection.credential_ref)
        if access_token is None:
            raise EmailProviderAuthError(public_message="Gmail authorization is required")

        list_response = _validate_gmail_response(
            GmailMessageListResponse,
            await self._transport.get_json(
                _MESSAGES_PATH,
                query=list_query,
                access_token=access_token,
            ),
        )

        metadata_messages: list[EmailMessageMetadata] = []
        for list_item in list_response.messages:
            metadata_messages.append(
                await self._fetch_message_metadata(
                    connection=connection,
                    message=list_item,
                    access_token=access_token,
                )
            )

        return EmailMetadataPage(
            messages=tuple(metadata_messages),
            next_page_token=list_response.next_page_token,
            next_sync_cursor=None,
        )

    async def _fetch_message_metadata(
        self,
        *,
        connection: EmailConnection,
        message: GmailMessageListItem,
        access_token: SecretStr,
    ) -> EmailMessageMetadata:
        gmail_metadata = _validate_gmail_response(
            GmailMessageMetadataResponse,
            await self._transport.get_json(
                f"{_MESSAGES_PATH}/{message.id}",
                query=_metadata_query(),
                access_token=access_token,
            ),
        )
        headers = _metadata_headers(gmail_metadata)
        return EmailMessageMetadata(
            ref=EmailMessageRef(
                account=connection.account,
                message_id=gmail_metadata.id,
                thread_id=gmail_metadata.thread_id or message.thread_id,
            ),
            rfc822_message_id=_first_header(headers, "message-id"),
            from_addr=_first_email_address(headers, "from"),
            to_addrs=_email_addresses(headers, "to"),
            cc_addrs=_email_addresses(headers, "cc"),
            subject=_first_header(headers, "subject"),
            sent_at=_parse_email_datetime(_first_header(headers, "date")),
            labels=gmail_metadata.label_ids,
            size_bytes=gmail_metadata.size_estimate,
        )


def _list_query(request: EmailMetadataListRequest) -> tuple[tuple[str, str], ...]:
    if request.page_size > GMAIL_MAX_METADATA_PAGE_SIZE:
        raise EmailProviderError(
            public_message=f"Gmail metadata page size cannot exceed {GMAIL_MAX_METADATA_PAGE_SIZE}"
        )

    query = [("fields", _MESSAGE_LIST_FIELDS), ("maxResults", str(request.page_size))]
    if request.page_token is not None:
        query.append(("pageToken", request.page_token))
    return tuple(query)


def _metadata_query() -> tuple[tuple[str, str], ...]:
    return (("fields", _MESSAGE_METADATA_FIELDS), ("format", "metadata")) + tuple(
        ("metadataHeaders", header) for header in GMAIL_METADATA_HEADERS
    )


def _metadata_headers(metadata: GmailMessageMetadataResponse) -> dict[str, tuple[str, ...]]:
    headers: dict[str, list[str]] = {}
    for header in metadata.payload.headers if metadata.payload is not None else ():
        headers.setdefault(header.name.lower(), []).append(header.value)
    return {name: tuple(values) for name, values in headers.items()}


def _first_header(headers: dict[str, tuple[str, ...]], name: str) -> str | None:
    values = headers.get(name)
    if values is None:
        return None
    return values[0]


def _first_email_address(headers: dict[str, tuple[str, ...]], name: str) -> EmailAddress | None:
    addresses = _email_addresses(headers, name)
    if not addresses:
        return None
    return addresses[0]


def _email_addresses(headers: dict[str, tuple[str, ...]], name: str) -> tuple[EmailAddress, ...]:
    values = headers.get(name, ())
    return tuple(
        EmailAddress(address=address, display_name=display_name or None)
        for display_name, address in getaddresses(values)
        if address
    )


def _parse_email_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None


def _validate_gmail_response[ModelT: BaseModel](
    model: type[ModelT],
    response: object,
) -> ModelT:
    try:
        return model.model_validate(response)
    except ValidationError:
        raise EmailProviderError(public_message=_INVALID_DATA_MESSAGE) from None
