from __future__ import annotations

import json
from json import JSONDecodeError
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import GMAIL_READONLY_SCOPE, AppSettings, EmailProviderName
from app.providers.email.provider import (
    EmailAttachmentPolicy,
    EmailAuthorizationCallbackRequest,
    EmailAuthorizationStartRequest,
    EmailAuthorizationStartResult,
    EmailBodyBatch,
    EmailBodyFetchRequest,
    EmailConnection,
    EmailMetadataListRequest,
    EmailMetadataPage,
    EmailProviderAuthError,
    EmailProviderCapabilities,
    EmailProviderError,
)

_GMAIL_RUNTIME_NOT_IMPLEMENTED = "Gmail provider runtime is not implemented yet."
_GMAIL_MAX_BODY_BATCH_SIZE = 100


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
    """Gmail `EmailProvider` skeleton for Phase 1 ingestion work."""

    name = EmailProviderName.GMAIL

    def __init__(self, *, settings: AppSettings) -> None:
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
        raise _gmail_runtime_not_implemented()

    async def refresh_connection(self, connection: EmailConnection) -> EmailConnection:
        raise _gmail_runtime_not_implemented()

    async def list_message_metadata(
        self,
        connection: EmailConnection,
        request: EmailMetadataListRequest,
    ) -> EmailMetadataPage:
        raise _gmail_runtime_not_implemented()

    async def fetch_message_bodies(
        self,
        connection: EmailConnection,
        request: EmailBodyFetchRequest,
    ) -> EmailBodyBatch:
        raise _gmail_runtime_not_implemented()

    def _load_client_config(self) -> GoogleOAuthClientConfig:
        try:
            payload = json.loads(self._client_config_file.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise EmailProviderAuthError(
                public_message="Google OAuth client config file was not found."
            ) from error
        except (OSError, JSONDecodeError) as error:
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


def _gmail_runtime_not_implemented() -> EmailProviderError:
    return EmailProviderError(public_message=_GMAIL_RUNTIME_NOT_IMPLEMENTED)
