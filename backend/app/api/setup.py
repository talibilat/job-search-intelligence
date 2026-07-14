from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_email_connection_repository,
    get_llm_provider,
    get_llm_secret_store,
    get_provider_configuration_repository,
    get_provider_readiness_service,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail, ApiErrorResponse
from app.api.provider_config import get_active_sync_scheduler, get_provider_registry
from app.config import AppSettings, get_settings
from app.db.repositories import ProviderConfigurationRepository
from app.db.repositories.connection import EmailConnectionRepository
from app.models import SetupStatusResponse, SetupSubmitRequest, SetupSubmitResponse
from app.providers import ProviderRegistry
from app.security import SecretStore, SecretStoreError
from app.services.provider_config import SyncSchedulerConfigurationError
from app.services.readiness import ProviderReadinessService
from app.services.setup_status import build_setup_status
from app.services.setup_submission import SetupSubmissionValidationError, submit_setup
from app.services.sync_service import SyncScheduler

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(
    settings: Annotated[AppSettings, Depends(get_settings)],
    readiness_service: Annotated[
        ProviderReadinessService,
        Depends(get_provider_readiness_service),
    ],
) -> SetupStatusResponse:
    """Report setup status plus current and recommended classification modes."""

    return build_setup_status(settings, await readiness_service.check())


@router.post(
    "",
    response_model=SetupSubmitResponse,
    summary="Submit first-run setup choices",
    description=(
        "Durably stores provider choices and write-only credentials through the same "
        "service as provider settings. When classification_mode is omitted, the backend "
        "applies the selected provider recommendation before validation."
    ),
    responses={400: {"model": ApiErrorResponse}, 422: {"model": ApiErrorResponse}},
)
async def setup_submit(
    request: SetupSubmitRequest,
    settings: Annotated[AppSettings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    repository: Annotated[
        ProviderConfigurationRepository,
        Depends(get_provider_configuration_repository),
    ],
    secret_store: Annotated[SecretStore, Depends(get_llm_secret_store)],
    connection_repository: Annotated[
        EmailConnectionRepository,
        Depends(get_email_connection_repository),
    ],
    sync_scheduler: Annotated[SyncScheduler, Depends(get_active_sync_scheduler)],
) -> SetupSubmitResponse:
    try:
        return await submit_setup(
            request,
            settings,
            registry,
            repository=repository,
            secret_store=secret_store,
            sync_scheduler=sync_scheduler,
            readiness_service_factory=lambda: ProviderReadinessService(
                settings=settings,
                registry=registry,
                connection_reader=connection_repository,
                secret_store=secret_store,
                llm_provider=get_llm_provider(settings, secret_store),
            ),
        )
    except SetupSubmissionValidationError as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message=error.message,
            details=[
                ApiErrorDetail(
                    field=setting,
                    message="Required for selected provider.",
                    type="missing_provider_setting",
                )
                for setting in error.missing_settings
            ],
        ) from error
    except SyncSchedulerConfigurationError as error:
        raise ApiError(
            status_code=503,
            code=ApiErrorCode.SERVICE_UNAVAILABLE,
            message="Sync scheduler settings could not be applied.",
        ) from error
    except (SecretStoreError, ValueError) as error:
        raise ApiError(
            status_code=400,
            code=ApiErrorCode.BAD_REQUEST,
            message=(
                str(error)
                if isinstance(error, ValueError)
                else "Credential storage is unavailable."
            ),
        ) from error
