from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import getaddresses, parsedate_to_datetime
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.config import GMAIL_READONLY_SCOPE, AppSettings, EmailProviderName
from app.providers.email.provider import (
    EmailAccountRef,
    EmailAddress,
    EmailAttachmentPolicy,
    EmailAuthorizationCallbackRequest,
    EmailAuthorizationStartRequest,
    EmailAuthorizationStartResult,
    EmailBodyBatch,
    EmailBodyFetchFailure,
    EmailBodyFetchFailureReason,
    EmailBodyFetchRequest,
    EmailBodySource,
    EmailConnection,
    EmailMessageBody,
    EmailMessageMetadata,
    EmailMessageRef,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProviderAuthError,
    EmailProviderCapabilities,
    EmailProviderCursor,
    EmailProviderError,
    EmailProviderTransientError,
    EmailSyncCursorExpiredError,
    EmailSyncMode,
)
from app.security import SecretKind, SecretRef, SecretStore, SecretStoreUnavailableError

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
_PROFILE_PATH = "/gmail/v1/users/me/profile"
_MESSAGES_PATH = "/gmail/v1/users/me/messages"
_HISTORY_PATH = "/gmail/v1/users/me/history"
_MESSAGE_LIST_FIELDS = "messages(id,threadId),nextPageToken"
_MESSAGE_METADATA_FIELDS = "id,threadId,labelIds,sizeEstimate,payload/headers(name,value)"
_PROFILE_EMAIL_FIELDS = "emailAddress"
_PROFILE_HISTORY_FIELDS = "historyId"
_HISTORY_LIST_FIELDS = "history(id,messagesAdded(message(id,threadId))),nextPageToken,historyId"
_MESSAGE_BODY_FIELDS = "id,threadId,payload"
_INVALID_DATA_MESSAGE = "Gmail metadata listing returned invalid data"
_INVALID_BODY_DATA_MESSAGE = "Gmail body fetching returned invalid data"
_FULL_BACKFILL_PAGE_TOKEN_PREFIX = "gmail-full-backfill:"


class GoogleOAuthInstalledClientConfig(BaseModel):
    """Subset of a Google Desktop OAuth client JSON needed to start auth."""

    model_config = ConfigDict(frozen=True)

    client_id: str = Field(min_length=1)
    client_secret: SecretStr = Field(min_length=1)
    auth_uri: str = Field(min_length=1)
    token_uri: str = Field(min_length=1)


class GoogleOAuthClientConfig(BaseModel):
    """Google OAuth client config without exposing client secret values."""

    model_config = ConfigDict(frozen=True)

    installed: GoogleOAuthInstalledClientConfig


class GoogleOAuthTokenResponse(BaseModel):
    """Google OAuth token response validated before secret-store persistence."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    access_token: SecretStr = Field(min_length=1)
    refresh_token: SecretStr | None = None
    expires_in: int = Field(gt=0)
    scope: str = Field(min_length=1)
    token_type: str = Field(min_length=1)


class GmailAccountProfileResponse(BaseModel):
    """Minimal Gmail profile used to scope the stored credential."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    email_address: str = Field(min_length=1, alias="emailAddress")


class GmailEmailProvider:
    """Gmail adapter with OAuth plus SecretStore-backed metadata and body reads."""

    name = EmailProviderName.GMAIL

    def __init__(
        self,
        *,
        settings: AppSettings,
        secret_store: SecretStore | None = None,
        transport: GmailApiTransport | None = None,
        token_transport: GoogleOAuthTokenTransport | None = None,
    ) -> None:
        if tuple(settings.gmail_scopes) != (GMAIL_READONLY_SCOPE,):
            raise EmailProviderError(
                public_message="Gmail provider requires only the gmail.readonly scope."
            )

        self._client_config_file = settings.gmail_client_config_file
        self._scopes = tuple(settings.gmail_scopes)
        self._secret_store = secret_store
        self._gmail_transport = transport or UrllibGmailApiTransport()
        self._token_transport = token_transport or UrllibGoogleOAuthTokenTransport()
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
            GmailMessageLister(secret_store=secret_store, transport=self._gmail_transport)
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
        if request.provider is not EmailProviderName.GMAIL:
            raise EmailProviderAuthError(
                public_message="Gmail authorization can only complete for Gmail."
            )
        if self._secret_store is None:
            raise EmailProviderAuthError(public_message="Gmail token storage is not configured.")

        client_config = self._load_client_config()
        token_response = await self._exchange_authorization_code(
            client_config=client_config,
            request=request,
        )
        granted_scopes = tuple(token_response.scope.split())
        if granted_scopes != self._scopes:
            raise EmailProviderAuthError(
                public_message="Gmail authorization is limited to gmail.readonly in v1."
            )
        if token_response.refresh_token is None:
            raise EmailProviderAuthError(public_message="Gmail refresh token was not returned.")

        profile = _validate_gmail_response(
            GmailAccountProfileResponse,
            await self._gmail_transport.get_json(
                _PROFILE_PATH,
                query=(("fields", _PROFILE_EMAIL_FIELDS),),
                access_token=token_response.access_token,
            ),
        )
        account_id = profile.email_address.lower()
        account = EmailAccountRef(provider=EmailProviderName.GMAIL, account_id=account_id)
        credential_ref = _credential_ref_for_account(account_id)
        connected_at = datetime.now(UTC)
        credential_expires_at = connected_at + timedelta(seconds=token_response.expires_in)

        try:
            await self._secret_store.set_secret(
                credential_ref,
                SecretStr(
                    json.dumps(
                        {
                            "access_token": token_response.access_token.get_secret_value(),
                            "refresh_token": token_response.refresh_token.get_secret_value(),
                            "expires_at": credential_expires_at.isoformat(),
                            "scope": token_response.scope,
                            "token_type": token_response.token_type,
                        },
                        sort_keys=True,
                    )
                ),
            )
        except SecretStoreUnavailableError as error:
            raise EmailProviderAuthError(
                public_message="Gmail token persistence failed."
            ) from error

        return EmailConnection(
            account=account,
            display_email=EmailAddress(address=account_id),
            credential_ref=credential_ref,
            granted_scopes=granted_scopes,
            connected_at=connected_at,
            credential_expires_at=credential_expires_at,
        )

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
        if self._message_lister is None:
            raise EmailProviderError(public_message="Gmail body fetching is not implemented yet.")
        return await self._message_lister.fetch_message_bodies(connection, request)

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

    async def _exchange_authorization_code(
        self,
        *,
        client_config: GoogleOAuthClientConfig,
        request: EmailAuthorizationCallbackRequest,
    ) -> GoogleOAuthTokenResponse:
        try:
            response = await self._token_transport.post_form_json(
                client_config.installed.token_uri,
                form=(
                    ("client_id", client_config.installed.client_id),
                    (
                        "client_secret",
                        client_config.installed.client_secret.get_secret_value(),
                    ),
                    ("code", request.code.get_secret_value()),
                    ("grant_type", "authorization_code"),
                    ("redirect_uri", request.redirect_uri),
                ),
            )
        except EmailProviderAuthError:
            raise
        except EmailProviderError:
            raise
        except Exception as error:
            raise EmailProviderAuthError(public_message="Gmail token exchange failed.") from error

        try:
            return GoogleOAuthTokenResponse.model_validate(response)
        except ValidationError as error:
            raise EmailProviderAuthError(
                public_message="Gmail token exchange returned invalid data."
            ) from error


class GoogleOAuthTokenTransport(Protocol):
    async def post_form_json(
        self,
        url: str,
        *,
        form: tuple[tuple[str, str], ...],
    ) -> dict[str, object]:
        """POST a form to Google's token endpoint without logging token material."""
        ...


class UrllibGoogleOAuthTokenTransport:
    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self._timeout_seconds = timeout_seconds

    async def post_form_json(
        self,
        url: str,
        *,
        form: tuple[tuple[str, str], ...],
    ) -> dict[str, object]:
        return await asyncio.to_thread(self._post_form_json_sync, url, form=form)

    def _post_form_json_sync(
        self,
        url: str,
        *,
        form: tuple[tuple[str, str], ...],
    ) -> dict[str, object]:
        request = Request(
            url,
            data=urlencode(form).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = response.read()
        except HTTPError as error:
            if error.code in {400, 401, 403}:
                raise EmailProviderAuthError(
                    public_message="Gmail token exchange failed."
                ) from error
            if error.code in {429, 500, 502, 503, 504}:
                raise EmailProviderTransientError(
                    public_message="Gmail token exchange is temporarily unavailable"
                ) from error
            raise EmailProviderError(public_message="Gmail token exchange failed") from error
        except URLError as error:
            raise EmailProviderTransientError(
                public_message="Gmail token exchange is temporarily unavailable"
            ) from error

        try:
            raw_response = response_body.decode("utf-8")
            decoded_response = json.loads(raw_response)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise EmailProviderAuthError(
                public_message="Gmail token exchange returned invalid data."
            ) from None

        if not isinstance(decoded_response, dict):
            raise EmailProviderAuthError(
                public_message="Gmail token exchange returned invalid data."
            )
        return cast(dict[str, object], decoded_response)


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


@dataclass(frozen=True)
class GmailApiRequestError(RuntimeError):
    status_code: int | None


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
            if path == _HISTORY_PATH and error.code == 404:
                raise EmailSyncCursorExpiredError(
                    public_message="Gmail incremental sync cursor expired"
                ) from error
            raise GmailApiRequestError(status_code=error.code) from error
        except URLError as error:
            raise GmailApiRequestError(status_code=None) from error

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


class GmailProfileResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    history_id: str = Field(min_length=1, alias="historyId")


class GmailHistoryMessageAdded(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    message: GmailMessageListItem


class GmailHistoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    id: str | None = None
    messages_added: tuple[GmailHistoryMessageAdded, ...] = Field(
        default=(),
        alias="messagesAdded",
    )


class GmailHistoryListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    history: tuple[GmailHistoryRecord, ...] = ()
    next_page_token: str | None = Field(default=None, alias="nextPageToken")
    history_id: str = Field(min_length=1, alias="historyId")


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


class GmailMessageBodyData(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    data: str | None = None
    size: int | None = Field(default=None, ge=0)
    attachment_id: str | None = Field(default=None, alias="attachmentId")


class GmailMessageBodyPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    mime_type: str | None = Field(default=None, alias="mimeType")
    filename: str = ""
    body: GmailMessageBodyData | None = None
    parts: tuple[GmailMessageBodyPayload, ...] = ()


class GmailMessageBodyResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    id: str = Field(min_length=1)
    thread_id: str | None = Field(default=None, alias="threadId")
    payload: GmailMessageBodyPayload | None = None


@dataclass(frozen=True)
class RetainedGmailBody:
    body_text: str
    body_source: EmailBodySource
    truncated: bool


class GmailMessageLister:
    """List Gmail metadata and fetch retained bodies through separate calls."""

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
        if request.mode is EmailSyncMode.FULL_BACKFILL:
            list_query = _list_query(request)
            stored_token = await self._secret_store.get_secret(connection.credential_ref)
            if stored_token is None:
                raise EmailProviderAuthError(public_message="Gmail authorization is required")
            access_token = _stored_access_token(stored_token)
            return await self._list_full_backfill_metadata(
                connection=connection,
                list_query=list_query,
                access_token=access_token,
            )

        stored_token = await self._secret_store.get_secret(connection.credential_ref)
        if stored_token is None:
            raise EmailProviderAuthError(public_message="Gmail authorization is required")
        access_token = _stored_access_token(stored_token)
        history_query = _history_query(request)
        return await self._list_incremental_metadata(
            connection=connection,
            history_query=history_query,
            access_token=access_token,
        )

    async def _list_full_backfill_metadata(
        self,
        *,
        connection: EmailConnection,
        list_query: tuple[tuple[str, str], ...],
        access_token: SecretStr,
    ) -> EmailMetadataPage:
        page_token = _query_value(list_query, "pageToken")
        if page_token is None:
            sync_cursor = await self._fetch_current_history_cursor(
                connection=connection,
                access_token=access_token,
            )
        else:
            page_token, sync_cursor = _decode_full_backfill_page_token(page_token)
            list_query = _replace_query_value(list_query, "pageToken", page_token)

        list_response = _validate_gmail_response(
            GmailMessageListResponse,
            await self._get_metadata_json(
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

        next_page_token = None
        next_sync_cursor: EmailProviderCursor | None = sync_cursor
        if list_response.next_page_token is not None:
            next_page_token = _encode_full_backfill_page_token(
                page_token=list_response.next_page_token,
                sync_cursor=sync_cursor,
            )
            next_sync_cursor = None

        return EmailMetadataPage(
            messages=tuple(metadata_messages),
            next_page_token=next_page_token,
            next_sync_cursor=next_sync_cursor,
        )

    async def _list_incremental_metadata(
        self,
        *,
        connection: EmailConnection,
        history_query: tuple[tuple[str, str], ...],
        access_token: SecretStr,
    ) -> EmailMetadataPage:
        history_response = _validate_gmail_response(
            GmailHistoryListResponse,
            await self._transport.get_json(
                _HISTORY_PATH,
                query=history_query,
                access_token=access_token,
            ),
        )

        metadata_messages: list[EmailMessageMetadata] = []
        for list_item in _history_added_messages(history_response):
            metadata_messages.append(
                await self._fetch_message_metadata(
                    connection=connection,
                    message=list_item,
                    access_token=access_token,
                )
            )

        next_sync_cursor = None
        if history_response.next_page_token is None:
            next_sync_cursor = EmailProviderCursor(
                account=connection.account,
                value=history_response.history_id,
                issued_at=datetime.now(UTC),
            )

        return EmailMetadataPage(
            messages=tuple(metadata_messages),
            next_page_token=history_response.next_page_token,
            next_sync_cursor=next_sync_cursor,
        )

    async def _fetch_current_history_cursor(
        self,
        *,
        connection: EmailConnection,
        access_token: SecretStr,
    ) -> EmailProviderCursor:
        profile = _validate_gmail_response(
            GmailProfileResponse,
            await self._transport.get_json(
                _PROFILE_PATH,
                query=_profile_query(),
                access_token=access_token,
            ),
        )
        return EmailProviderCursor(
            account=connection.account,
            value=profile.history_id,
            issued_at=datetime.now(UTC),
        )

    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        if len(request.refs) > _GMAIL_MAX_BODY_BATCH_SIZE:
            raise EmailProviderError(
                public_message=(f"Gmail body batch size cannot exceed {_GMAIL_MAX_BODY_BATCH_SIZE}")
            )

        stored_token = await self._secret_store.get_secret(connection.credential_ref)
        if stored_token is None:
            raise EmailProviderAuthError(public_message="Gmail authorization is required")
        access_token = _stored_access_token(stored_token)

        bodies: list[EmailMessageBody] = []
        failures: list[EmailBodyFetchFailure] = []
        fetched_at = datetime.now(UTC)

        for ref in request.refs:
            try:
                gmail_body = _validate_gmail_response(
                    GmailMessageBodyResponse,
                    await self._get_body_json(
                        f"{_MESSAGES_PATH}/{ref.message_id}",
                        query=_body_query(),
                        access_token=access_token,
                    ),
                    public_message=_INVALID_BODY_DATA_MESSAGE,
                )
            except GmailApiRequestError as error:
                if error.status_code == 404:
                    failures.append(
                        EmailBodyFetchFailure(
                            ref=ref,
                            reason=EmailBodyFetchFailureReason.NOT_FOUND,
                        )
                    )
                    continue
                if error.status_code == 403:
                    failures.append(
                        EmailBodyFetchFailure(
                            ref=ref,
                            reason=EmailBodyFetchFailureReason.PERMISSION_DENIED,
                        )
                    )
                    continue
                if error.status_code in {429, 500, 502, 503, 504, None}:
                    raise EmailProviderTransientError(
                        public_message="Gmail body fetching is temporarily unavailable"
                    ) from error
                raise EmailProviderError(public_message="Gmail body fetching failed") from error
            except URLError as error:
                raise EmailProviderTransientError(
                    public_message="Gmail body fetching is temporarily unavailable"
                ) from error
            if gmail_body.id != ref.message_id:
                raise EmailProviderError(public_message=_INVALID_BODY_DATA_MESSAGE)

            retained_body = _retained_body_from_payload(
                gmail_body.payload,
                max_body_bytes=request.max_body_bytes,
            )
            if isinstance(retained_body, EmailBodyFetchFailureReason):
                failures.append(EmailBodyFetchFailure(ref=ref, reason=retained_body))
                continue

            try:
                bodies.append(
                    EmailMessageBody(
                        ref=ref,
                        body_text=retained_body.body_text,
                        body_source=retained_body.body_source,
                        truncated=retained_body.truncated,
                        fetched_at=fetched_at,
                    )
                )
            except ValidationError:
                raise EmailProviderError(public_message=_INVALID_BODY_DATA_MESSAGE) from None

        return EmailBodyBatch(bodies=tuple(bodies), failures=tuple(failures))

    async def _get_metadata_json(
        self,
        path: str,
        *,
        query: tuple[tuple[str, str], ...],
        access_token: SecretStr,
    ) -> dict[str, object]:
        try:
            return await self._transport.get_json(
                path,
                query=query,
                access_token=access_token,
            )
        except GmailApiRequestError as error:
            if path == _HISTORY_PATH and error.status_code == 404:
                raise EmailSyncCursorExpiredError(
                    public_message="Gmail incremental sync cursor expired"
                ) from error
            if error.status_code in {401, 403}:
                raise EmailProviderAuthError(
                    public_message="Gmail authorization is required"
                ) from error
            if error.status_code in {429, 500, 502, 503, 504, None}:
                raise EmailProviderTransientError(
                    public_message="Gmail metadata listing is temporarily unavailable"
                ) from error
            raise EmailProviderError(public_message="Gmail metadata listing failed") from error

    async def _get_body_json(
        self,
        path: str,
        *,
        query: tuple[tuple[str, str], ...],
        access_token: SecretStr,
    ) -> dict[str, object]:
        try:
            return await self._transport.get_json(
                path,
                query=query,
                access_token=access_token,
            )
        except HTTPError as error:
            raise GmailApiRequestError(status_code=error.code) from error
        except URLError as error:
            raise GmailApiRequestError(status_code=None) from error

    async def _fetch_message_metadata(
        self,
        *,
        connection: EmailConnection,
        message: GmailMessageListItem,
        access_token: SecretStr,
    ) -> EmailMessageMetadata:
        gmail_metadata = _validate_gmail_response(
            GmailMessageMetadataResponse,
            await self._get_metadata_json(
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


def _query_value(query: tuple[tuple[str, str], ...], name: str) -> str | None:
    for key, value in query:
        if key == name:
            return value
    return None


def _replace_query_value(
    query: tuple[tuple[str, str], ...],
    name: str,
    replacement: str,
) -> tuple[tuple[str, str], ...]:
    return tuple((key, replacement if key == name else value) for key, value in query)


def _encode_full_backfill_page_token(
    *,
    page_token: str,
    sync_cursor: EmailProviderCursor,
) -> str:
    payload = json.dumps(
        {
            "page_token": page_token,
            "sync_cursor": sync_cursor.model_dump(mode="json"),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{_FULL_BACKFILL_PAGE_TOKEN_PREFIX}{base64.urlsafe_b64encode(payload).decode('ascii')}"


def _decode_full_backfill_page_token(page_token: str) -> tuple[str, EmailProviderCursor]:
    if not page_token.startswith(_FULL_BACKFILL_PAGE_TOKEN_PREFIX):
        raise EmailProviderError(public_message="Gmail full backfill page token is invalid")

    encoded_payload = page_token.removeprefix(_FULL_BACKFILL_PAGE_TOKEN_PREFIX)
    try:
        decoded_payload = base64.urlsafe_b64decode(encoded_payload.encode("ascii"))
        payload = json.loads(decoded_payload.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        decoded_page_token = payload.get("page_token")
        decoded_sync_cursor = payload.get("sync_cursor")
        if not isinstance(decoded_page_token, str):
            raise ValueError
        sync_cursor = EmailProviderCursor.model_validate(decoded_sync_cursor)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError):
        raise EmailProviderError(
            public_message="Gmail full backfill page token is invalid"
        ) from None

    return decoded_page_token, sync_cursor


def _history_query(request: EmailMetadataListRequest) -> tuple[tuple[str, str], ...]:
    if request.page_size > GMAIL_MAX_METADATA_PAGE_SIZE:
        raise EmailProviderError(
            public_message=f"Gmail metadata page size cannot exceed {GMAIL_MAX_METADATA_PAGE_SIZE}"
        )
    if request.sync_cursor is None:
        raise EmailProviderError(public_message="Gmail incremental sync requires a cursor")

    query = [
        ("fields", _HISTORY_LIST_FIELDS),
        ("historyTypes", "messageAdded"),
        ("maxResults", str(request.page_size)),
        ("startHistoryId", request.sync_cursor.value),
    ]
    if request.page_token is not None:
        query.append(("pageToken", request.page_token))
    return tuple(query)


def _history_added_messages(response: GmailHistoryListResponse) -> tuple[GmailMessageListItem, ...]:
    messages: list[GmailMessageListItem] = []
    seen_message_ids: set[str] = set()
    for history_record in response.history:
        for added_message in history_record.messages_added:
            message = added_message.message
            if message.id in seen_message_ids:
                continue
            seen_message_ids.add(message.id)
            messages.append(message)
    return tuple(messages)


def _metadata_query() -> tuple[tuple[str, str], ...]:
    return (("fields", _MESSAGE_METADATA_FIELDS), ("format", "metadata")) + tuple(
        ("metadataHeaders", header) for header in GMAIL_METADATA_HEADERS
    )


def _profile_query() -> tuple[tuple[str, str], ...]:
    return (("fields", _PROFILE_HISTORY_FIELDS),)


def _body_query() -> tuple[tuple[str, str], ...]:
    return (("fields", _MESSAGE_BODY_FIELDS), ("format", "full"))


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


def _credential_ref_for_account(account_id: str) -> SecretRef:
    return SecretRef(
        kind=SecretKind.OAUTH_TOKEN,
        provider=EmailProviderName.GMAIL.value,
        name=_secret_name_for_account(account_id),
    )


def _secret_name_for_account(account_id: str) -> str:
    normalized = account_id.strip().lower()
    secret_name = re.sub(r"[^a-z0-9_.:-]+", "-", normalized).strip("-._:")
    return secret_name or "default"


def _stored_access_token(stored_token: SecretStr) -> SecretStr:
    raw_token = stored_token.get_secret_value()
    try:
        decoded_token = json.loads(raw_token)
    except json.JSONDecodeError:
        return stored_token

    if not isinstance(decoded_token, dict):
        return stored_token
    access_token = decoded_token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return stored_token
    return SecretStr(access_token)


def _retained_body_from_payload(
    payload: GmailMessageBodyPayload | None,
    *,
    max_body_bytes: int | None,
) -> RetainedGmailBody | EmailBodyFetchFailureReason:
    if payload is None:
        return EmailBodyFetchFailureReason.EMPTY

    plain_parts: list[tuple[str, bool]] = []
    html_parts: list[tuple[str, bool]] = []
    saw_text_payload = False

    for part in _walk_body_payload(payload):
        if _is_attachment_payload(part):
            continue

        mime_type = _normalized_mime_type(part.mime_type)
        if mime_type not in {"text/plain", "text/html"}:
            continue

        saw_text_payload = True
        if part.body is None or part.body.data is None:
            continue

        body_text, truncated = _decode_body_text(
            part.body.data,
            max_body_bytes=max_body_bytes,
        )
        if mime_type == "text/plain":
            plain_parts.append((body_text, truncated))
        else:
            html_parts.append((body_text, truncated))

    plain_body = _retained_body_from_parts(plain_parts, EmailBodySource.TEXT_PLAIN)
    html_body = _retained_body_from_parts(html_parts, EmailBodySource.HTML_CONVERTED)
    if plain_body is not None and plain_body.body_text:
        return plain_body
    if html_body is not None and html_body.body_text:
        return html_body
    if plain_body is not None:
        return plain_body
    if html_body is not None:
        return html_body
    if saw_text_payload:
        return EmailBodyFetchFailureReason.EMPTY
    return EmailBodyFetchFailureReason.UNSUPPORTED_CONTENT


def _walk_body_payload(payload: GmailMessageBodyPayload) -> tuple[GmailMessageBodyPayload, ...]:
    parts: list[GmailMessageBodyPayload] = [payload]
    for child in payload.parts:
        parts.extend(_walk_body_payload(child))
    return tuple(parts)


def _is_attachment_payload(payload: GmailMessageBodyPayload) -> bool:
    return bool(payload.filename) or (
        payload.body is not None and payload.body.attachment_id is not None
    )


def _normalized_mime_type(mime_type: str | None) -> str:
    if mime_type is None:
        return ""
    return mime_type.split(";", maxsplit=1)[0].strip().lower()


def _decode_body_text(encoded_body: str, *, max_body_bytes: int | None) -> tuple[str, bool]:
    padding = "=" * (-len(encoded_body) % 4)
    try:
        body_bytes = base64.urlsafe_b64decode(f"{encoded_body}{padding}".encode("ascii"))
    except (binascii.Error, UnicodeEncodeError) as error:
        raise EmailProviderError(public_message=_INVALID_BODY_DATA_MESSAGE) from error

    try:
        body_text = body_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EmailProviderError(public_message=_INVALID_BODY_DATA_MESSAGE) from error

    truncated = max_body_bytes is not None and len(body_bytes) > max_body_bytes
    if max_body_bytes is not None and truncated:
        body_text = body_bytes[:max_body_bytes].decode("utf-8", errors="ignore")
    return body_text, truncated


def _retained_body_from_parts(
    parts: list[tuple[str, bool]],
    body_source: EmailBodySource,
) -> RetainedGmailBody | None:
    if not parts:
        return None
    body_text = "\n\n".join(text for text, _truncated in parts)
    return RetainedGmailBody(
        body_text=body_text,
        body_source=EmailBodySource.EMPTY if body_text == "" else body_source,
        truncated=any(truncated for _text, truncated in parts),
    )


def _validate_gmail_response[ModelT: BaseModel](
    model: type[ModelT],
    response: object,
    *,
    public_message: str = _INVALID_DATA_MESSAGE,
) -> ModelT:
    try:
        return model.model_validate(response)
    except ValidationError:
        raise EmailProviderError(public_message=public_message) from None
