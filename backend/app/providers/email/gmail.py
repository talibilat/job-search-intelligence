from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import getaddresses, parsedate_to_datetime
from typing import NoReturn, Protocol, cast
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
    EmailProviderErrorCode,
    EmailProviderTransientError,
    EmailProviderUserAction,
    EmailSyncCursorExpiredError,
    EmailSyncMode,
)
from app.security import (
    GMAIL_OAUTH_CLIENT_REF,
    SecretKind,
    SecretRef,
    SecretStore,
    SecretStoreUnavailableError,
)

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
_TOKEN_REFRESH_SKEW = timedelta(minutes=5)
_GMAIL_SYSTEM_LABELS = {
    "CHAT",
    "CATEGORY_FORUMS",
    "CATEGORY_PERSONAL",
    "CATEGORY_PRIMARY",
    "CATEGORY_PROMOTIONS",
    "CATEGORY_SOCIAL",
    "CATEGORY_UPDATES",
    "DRAFT",
    "IMPORTANT",
    "INBOX",
    "SENT",
    "SPAM",
    "STARRED",
    "TRASH",
    "UNREAD",
}


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


class GoogleOAuthRefreshTokenResponse(BaseModel):
    """Google OAuth refresh response validated before secret-store persistence."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    access_token: SecretStr = Field(min_length=1)
    expires_in: int = Field(gt=0)
    scope: str | None = None
    token_type: str = Field(min_length=1)


class StoredGoogleOAuthCredential(BaseModel):
    """SecretStore payload for Gmail OAuth tokens."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    access_token: SecretStr = Field(min_length=1)
    refresh_token: SecretStr | None = None
    expires_at: datetime | None = None
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

        client_config = await self._load_client_config()
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

        client_config = await self._load_client_config()
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
                _serialize_stored_credential(
                    access_token=token_response.access_token,
                    refresh_token=token_response.refresh_token,
                    expires_at=credential_expires_at,
                    scope=token_response.scope,
                    token_type=token_response.token_type,
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
        if connection.account.provider is not EmailProviderName.GMAIL:
            raise EmailProviderAuthError(
                public_message="Gmail credential refresh can only refresh Gmail connections."
            )
        if self._secret_store is None:
            raise EmailProviderAuthError(public_message="Gmail token storage is not configured.")

        stored_credential = await self._read_refreshable_credential(connection)
        refresh_token = stored_credential.refresh_token
        if refresh_token is None:
            raise EmailProviderAuthError(public_message="Reconnect Gmail to continue syncing.")
        client_config = await self._load_client_config()
        token_response = await self._exchange_refresh_token(
            client_config=client_config,
            refresh_token=refresh_token,
        )
        granted_scope = token_response.scope or stored_credential.scope
        granted_scopes = tuple(granted_scope.split())
        if granted_scopes != self._scopes:
            raise EmailProviderAuthError(
                public_message="Gmail authorization is limited to gmail.readonly in v1."
            )

        refreshed_at = datetime.now(UTC)
        credential_expires_at = refreshed_at + timedelta(seconds=token_response.expires_in)

        try:
            await self._secret_store.set_secret(
                connection.credential_ref,
                _serialize_stored_credential(
                    access_token=token_response.access_token,
                    refresh_token=refresh_token,
                    expires_at=credential_expires_at,
                    scope=granted_scope,
                    token_type=token_response.token_type,
                ),
            )
        except SecretStoreUnavailableError as error:
            raise EmailProviderAuthError(
                public_message="Gmail token persistence failed."
            ) from error

        return connection.model_copy(
            update={
                "granted_scopes": granted_scopes,
                "credential_expires_at": credential_expires_at,
                "reauth_required": False,
            }
        )

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        if self._message_lister is None:
            raise EmailProviderError(public_message="Gmail metadata sync is not implemented yet.")
        refreshed_connection = await self._refresh_connection_if_needed(connection)
        return await self._message_lister.list_message_metadata(refreshed_connection, request)

    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        if self._message_lister is None:
            raise EmailProviderError(public_message="Gmail body fetching is not implemented yet.")
        refreshed_connection = await self._refresh_connection_if_needed(connection)
        return await self._message_lister.fetch_message_bodies(refreshed_connection, request)

    async def _refresh_connection_if_needed(
        self,
        connection: EmailConnection,
    ) -> EmailConnection:
        if self._secret_store is None:
            return connection

        try:
            stored_token = await self._secret_store.get_secret(connection.credential_ref)
        except SecretStoreUnavailableError as error:
            raise EmailProviderAuthError(
                public_message="Gmail token storage is not configured."
            ) from error
        if stored_token is None:
            return connection

        stored_credential = _stored_credential_from_secret(stored_token)
        if stored_credential is None:
            return connection

        expires_at = stored_credential.expires_at or connection.credential_expires_at
        if expires_at is None or expires_at > datetime.now(UTC) + _TOKEN_REFRESH_SKEW:
            return connection

        return await self.refresh_connection(connection)

    async def _read_refreshable_credential(
        self,
        connection: EmailConnection,
    ) -> StoredGoogleOAuthCredential:
        if self._secret_store is None:
            raise EmailProviderAuthError(public_message="Gmail token storage is not configured.")

        try:
            stored_token = await self._secret_store.get_secret(connection.credential_ref)
        except SecretStoreUnavailableError as error:
            raise EmailProviderAuthError(
                public_message="Gmail token storage is not configured."
            ) from error
        if stored_token is None:
            raise EmailProviderAuthError(public_message="Gmail authorization is required")

        stored_credential = _stored_credential_from_secret(stored_token)
        if stored_credential is None or stored_credential.refresh_token is None:
            raise EmailProviderAuthError(public_message="Reconnect Gmail to continue syncing.")
        return stored_credential

    async def _load_client_config(self) -> GoogleOAuthClientConfig:
        payload: object
        if self._secret_store is not None:
            try:
                stored = await self._secret_store.get_secret(GMAIL_OAUTH_CLIENT_REF)
            except SecretStoreUnavailableError:
                stored = None
            if stored is not None:
                try:
                    payload = json.loads(stored.get_secret_value())
                except json.JSONDecodeError as error:
                    raise EmailProviderAuthError(
                        public_message="Stored Google OAuth client JSON is invalid."
                    ) from error
                return self._validate_client_config(payload)

        # The path remains a bootstrap fallback for existing environment-based installs.
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

        return self._validate_client_config(payload)

    @staticmethod
    def _validate_client_config(payload: object) -> GoogleOAuthClientConfig:
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

    async def _exchange_refresh_token(
        self,
        *,
        client_config: GoogleOAuthClientConfig,
        refresh_token: SecretStr,
    ) -> GoogleOAuthRefreshTokenResponse:
        try:
            response = await self._token_transport.post_form_json(
                client_config.installed.token_uri,
                form=(
                    ("client_id", client_config.installed.client_id),
                    (
                        "client_secret",
                        client_config.installed.client_secret.get_secret_value(),
                    ),
                    ("grant_type", "refresh_token"),
                    ("refresh_token", refresh_token.get_secret_value()),
                ),
            )
        except EmailProviderAuthError:
            raise
        except EmailProviderError:
            raise
        except Exception as error:
            raise EmailProviderAuthError(public_message="Gmail token refresh failed.") from error

        try:
            return GoogleOAuthRefreshTokenResponse.model_validate(response)
        except ValidationError as error:
            raise EmailProviderAuthError(
                public_message="Gmail token refresh returned invalid data."
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
    reason: str | None = None


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
            raise GmailApiRequestError(
                status_code=error.code,
                reason=_gmail_error_reason(error),
            ) from error
        except URLError as error:
            raise GmailApiRequestError(status_code=None) from error

        try:
            raw_response = response_body.decode("utf-8")
            decoded_response = json.loads(raw_response)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise EmailProviderError(
                public_message=_INVALID_DATA_MESSAGE,
                error_code=EmailProviderErrorCode.INVALID_PROVIDER_RESPONSE,
            ) from None

        if not isinstance(decoded_response, dict):
            raise EmailProviderError(
                public_message=_INVALID_DATA_MESSAGE,
                error_code=EmailProviderErrorCode.INVALID_PROVIDER_RESPONSE,
            )
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
            message_metadata = await self._fetch_message_metadata(
                connection=connection,
                message=list_item,
                access_token=access_token,
            )
            if message_metadata is not None:
                metadata_messages.append(message_metadata)

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
            await self._get_metadata_json(
                _HISTORY_PATH,
                query=history_query,
                access_token=access_token,
            ),
        )

        metadata_messages: list[EmailMessageMetadata] = []
        for list_item in _history_added_messages(history_response):
            message_metadata = await self._fetch_message_metadata(
                connection=connection,
                message=list_item,
                access_token=access_token,
            )
            if message_metadata is not None:
                metadata_messages.append(message_metadata)

        next_sync_cursor = None
        if history_response.next_page_token is None:
            next_sync_cursor = EmailProviderCursor(
                account=connection.account,
                value=_normalize_required_id(history_response.history_id),
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
            await self._get_metadata_json(
                _PROFILE_PATH,
                query=(("fields", _PROFILE_HISTORY_FIELDS),),
                access_token=access_token,
            ),
        )
        return EmailProviderCursor(
            account=connection.account,
            value=_normalize_required_id(profile.history_id),
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
                        query=(("fields", _MESSAGE_BODY_FIELDS), ("format", "full")),
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
            except EmailProviderError:
                # One malformed provider payload must not abort the whole
                # batch, or a resumable backfill can never advance past it.
                failures.append(
                    EmailBodyFetchFailure(
                        ref=ref,
                        reason=EmailBodyFetchFailureReason.INVALID_DATA,
                    )
                )
                continue
            if gmail_body.id != ref.message_id:
                failures.append(
                    EmailBodyFetchFailure(
                        ref=ref,
                        reason=EmailBodyFetchFailureReason.INVALID_DATA,
                    )
                )
                continue

            try:
                retained_body = _retained_body_from_payload(
                    gmail_body.payload,
                    max_body_bytes=request.max_body_bytes,
                )
            except EmailProviderError:
                failures.append(
                    EmailBodyFetchFailure(
                        ref=ref,
                        reason=EmailBodyFetchFailureReason.INVALID_DATA,
                    )
                )
                continue
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
                failures.append(
                    EmailBodyFetchFailure(
                        ref=ref,
                        reason=EmailBodyFetchFailureReason.INVALID_DATA,
                    )
                )

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
            _raise_gmail_api_request_error(path=path, error=error)

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
            raise GmailApiRequestError(
                status_code=error.code,
                reason=_gmail_error_reason(error),
            ) from error
        except URLError as error:
            raise GmailApiRequestError(status_code=None) from error

    async def _fetch_message_metadata(
        self,
        *,
        connection: EmailConnection,
        message: GmailMessageListItem,
        access_token: SecretStr,
    ) -> EmailMessageMetadata | None:
        try:
            raw_metadata = await self._transport.get_json(
                f"{_MESSAGES_PATH}/{message.id}",
                query=(("fields", _MESSAGE_METADATA_FIELDS), ("format", "metadata"))
                + tuple(("metadataHeaders", header) for header in GMAIL_METADATA_HEADERS),
                access_token=access_token,
            )
        except GmailApiRequestError as error:
            if error.status_code == 404:
                return None
            _raise_gmail_api_request_error(
                path=f"{_MESSAGES_PATH}/{message.id}",
                error=error,
            )

        gmail_metadata = _validate_gmail_response(
            GmailMessageMetadataResponse,
            raw_metadata,
        )
        headers = _metadata_headers(gmail_metadata)
        return EmailMessageMetadata(
            ref=EmailMessageRef(
                account=connection.account,
                message_id=_normalize_required_id(gmail_metadata.id),
                thread_id=_normalize_optional_id(gmail_metadata.thread_id)
                or _normalize_optional_id(message.thread_id),
            ),
            rfc822_message_id=_first_header(headers, "message-id"),
            from_addr=_first_email_address(headers, "from"),
            to_addrs=_email_addresses(headers, "to"),
            cc_addrs=_email_addresses(headers, "cc"),
            subject=_first_header(headers, "subject"),
            sent_at=_parse_email_datetime(_first_header(headers, "date")),
            labels=_normalize_label_ids(gmail_metadata.label_ids),
            size_bytes=gmail_metadata.size_estimate,
        )


def _list_query(request: EmailMetadataListRequest) -> tuple[tuple[str, str], ...]:
    if request.page_size > GMAIL_MAX_METADATA_PAGE_SIZE:
        raise EmailProviderError(
            public_message=f"Gmail metadata page size cannot exceed {GMAIL_MAX_METADATA_PAGE_SIZE}"
        )

    query = [("fields", _MESSAGE_LIST_FIELDS), ("maxResults", str(request.page_size))]
    date_query = _gmail_date_query(request)
    if date_query is not None:
        query.append(("q", date_query))
    if request.page_token is not None:
        query.append(("pageToken", request.page_token))
    return tuple(query)


def _gmail_date_query(request: EmailMetadataListRequest) -> str | None:
    terms: list[str] = []
    if request.since_date is not None:
        terms.append(f"after:{request.since_date:%Y/%m/%d}")
    if request.before_date is not None:
        terms.append(f"before:{request.before_date:%Y/%m/%d}")
    if not terms:
        return None
    return " ".join(terms)


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


def _metadata_headers(metadata: GmailMessageMetadataResponse) -> dict[str, tuple[str, ...]]:
    headers: dict[str, list[str]] = {}
    for header in metadata.payload.headers if metadata.payload is not None else ():
        header_name = header.name.strip().lower()
        if not header_name:
            continue
        headers.setdefault(header_name, []).append(header.value)
    return {name: tuple(values) for name, values in headers.items()}


def _first_header(headers: dict[str, tuple[str, ...]], name: str) -> str | None:
    values = headers.get(name)
    if values is None:
        return None
    return _normalize_optional_header(values[0])


def _first_email_address(headers: dict[str, tuple[str, ...]], name: str) -> EmailAddress | None:
    addresses = _email_addresses(headers, name)
    if not addresses:
        return None
    return addresses[0]


def _email_addresses(headers: dict[str, tuple[str, ...]], name: str) -> tuple[EmailAddress, ...]:
    values = headers.get(name, ())
    addresses: list[EmailAddress] = []
    seen_addresses: set[str] = set()
    for display_name, address in getaddresses(values):
        normalized_address = address.strip().lower()
        if not normalized_address or normalized_address in seen_addresses:
            continue
        seen_addresses.add(normalized_address)
        addresses.append(
            EmailAddress(
                address=normalized_address,
                display_name=_normalize_optional_display_name(display_name),
            )
        )
    return tuple(addresses)


def _parse_email_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_required_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise EmailProviderError(public_message=_INVALID_DATA_MESSAGE)
    return normalized


def _normalize_optional_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_optional_header(value: str) -> str | None:
    normalized = value.strip()
    return normalized or None


def _normalize_optional_display_name(value: str) -> str | None:
    normalized = " ".join(value.strip().split())
    return normalized or None


def _normalize_label_ids(label_ids: tuple[str, ...]) -> tuple[str, ...]:
    labels: list[str] = []
    seen_labels: set[str] = set()
    for label_id in label_ids:
        normalized = _normalize_label_id(label_id)
        if normalized is None or normalized in seen_labels:
            continue
        seen_labels.add(normalized)
        labels.append(normalized)
    return tuple(labels)


def _normalize_label_id(label_id: str) -> str | None:
    normalized = label_id.strip()
    if not normalized:
        return None
    uppercase = normalized.upper()
    if uppercase in _GMAIL_SYSTEM_LABELS:
        return uppercase
    return normalized


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


def _stored_credential_from_secret(
    stored_token: SecretStr,
) -> StoredGoogleOAuthCredential | None:
    raw_token = stored_token.get_secret_value()
    try:
        decoded_token = json.loads(raw_token)
    except json.JSONDecodeError:
        return None

    if not isinstance(decoded_token, dict):
        return None
    try:
        return StoredGoogleOAuthCredential.model_validate(decoded_token)
    except ValidationError:
        return None


def _serialize_stored_credential(
    *,
    access_token: SecretStr,
    refresh_token: SecretStr,
    expires_at: datetime,
    scope: str,
    token_type: str,
) -> SecretStr:
    return SecretStr(
        json.dumps(
            {
                "access_token": access_token.get_secret_value(),
                "refresh_token": refresh_token.get_secret_value(),
                "expires_at": expires_at.isoformat(),
                "scope": scope,
                "token_type": token_type,
            },
            sort_keys=True,
        )
    )


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
        raise EmailProviderError(
            public_message=public_message,
            error_code=EmailProviderErrorCode.INVALID_PROVIDER_RESPONSE,
        ) from None


def _raise_gmail_api_request_error(*, path: str, error: GmailApiRequestError) -> NoReturn:
    if path == _HISTORY_PATH and error.status_code == 404:
        raise EmailSyncCursorExpiredError(
            public_message="Gmail incremental sync cursor expired"
        ) from error

    if error.status_code == 401:
        raise EmailProviderAuthError(
            public_message="Reconnect Gmail to continue syncing.",
            error_code=EmailProviderErrorCode.AUTHORIZATION_REQUIRED,
            user_action=EmailProviderUserAction.RECONNECT_EMAIL,
        ) from error

    if error.status_code == 403 and error.reason in {
        "dailyLimitExceeded",
        "rateLimitExceeded",
        "userRateLimitExceeded",
        "quotaExceeded",
        "RESOURCE_EXHAUSTED",
    }:
        raise EmailProviderTransientError(
            public_message="Gmail rate limit reached. Try syncing again later.",
            error_code=EmailProviderErrorCode.RATE_LIMITED,
            user_action=EmailProviderUserAction.TRY_AGAIN_LATER,
        ) from error

    if error.status_code == 403:
        raise EmailProviderAuthError(
            public_message="Grant Gmail read-only access to continue syncing.",
            error_code=EmailProviderErrorCode.INSUFFICIENT_SCOPE,
            user_action=EmailProviderUserAction.RECONNECT_EMAIL,
        ) from error

    if error.status_code == 429:
        raise EmailProviderTransientError(
            public_message="Gmail rate limit reached. Try syncing again later.",
            error_code=EmailProviderErrorCode.RATE_LIMITED,
            user_action=EmailProviderUserAction.TRY_AGAIN_LATER,
        ) from error

    if error.status_code in {500, 502, 503, 504, None}:
        raise EmailProviderTransientError(
            public_message="Gmail is temporarily unavailable. Try syncing again later.",
            error_code=EmailProviderErrorCode.TEMPORARILY_UNAVAILABLE,
            user_action=EmailProviderUserAction.TRY_AGAIN_LATER,
        ) from error

    raise EmailProviderError(
        public_message="Gmail metadata listing failed. Try syncing again later.",
        error_code=EmailProviderErrorCode.PROVIDER_REQUEST_FAILED,
        user_action=EmailProviderUserAction.TRY_AGAIN_LATER,
    ) from error


def _gmail_error_reason(error: HTTPError) -> str | None:
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    error_payload = payload.get("error")
    if not isinstance(error_payload, dict):
        return None

    errors = error_payload.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if not isinstance(item, dict):
                continue
            reason = item.get("reason")
            if isinstance(reason, str) and reason:
                return reason
    status = error_payload.get("status")
    if isinstance(status, str) and status:
        return status
    return None
