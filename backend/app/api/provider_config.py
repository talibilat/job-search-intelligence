from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.api.dependencies import (
    get_llm_provider,
    get_llm_secret_store,
    get_provider_configuration_repository,
    get_provider_readiness_service,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail, ApiErrorResponse
from app.config import AppSettings, get_settings
from app.db.repositories import ProviderConfigurationRepository
from app.models import (
    LLMProviderHealthCheckApiRequest,
    ProviderConfigResponse,
    ProviderConfigUpdateRequest,
)
from app.models.provider_config import ProviderReadinessResponse
from app.providers import ProviderConfigurationError, ProviderRegistry, provider_registry
from app.providers.llm import (
    LLMProvider,
    LLMProviderHealthCheckResponse,
)
from app.security import SecretStore, SecretStoreError
from app.services.llm_health import check_configured_llm_provider_health
from app.services.provider_config import (
    SyncSchedulerConfigurationError,
    apply_provider_config_update,
    build_provider_config_response,
)
from app.services.readiness import ProviderReadinessService
from app.services.sync_service import SyncScheduler

router = APIRouter(prefix="/config", tags=["config"])


def get_provider_registry() -> ProviderRegistry:
    return provider_registry


def get_active_sync_scheduler(request: Request) -> SyncScheduler:
    """Return the scheduler owned by the active FastAPI lifespan."""

    sync_scheduler = getattr(request.app.state, "sync_scheduler", None)
    if sync_scheduler is None:
        raise ApiError(
            status_code=503,
            code=ApiErrorCode.SERVICE_UNAVAILABLE,
            message="Sync scheduler is not available.",
        )
    return cast(SyncScheduler, sync_scheduler)


def get_configured_llm_provider(
    settings: Annotated[AppSettings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> LLMProvider:
    try:
        registry.validate_settings(settings)
    except ProviderConfigurationError as error:
        raise _provider_configuration_error(error) from error

    return llm_provider


async def validate_llm_provider_health_request_body(
    request: Request,
) -> LLMProviderHealthCheckApiRequest:
    raw_body = await request.body()
    if not raw_body.strip():
        return LLMProviderHealthCheckApiRequest()

    try:
        return LLMProviderHealthCheckApiRequest.model_validate_json(raw_body)
    except ValidationError as error:
        raise ApiError(
            status_code=422,
            code=ApiErrorCode.VALIDATION_ERROR,
            message="LLM provider health request validation failed.",
            details=_settings_validation_details(error),
        ) from error


def _settings_validation_details(error: ValidationError) -> list[ApiErrorDetail]:
    return [
        ApiErrorDetail(
            field=".".join(str(part) for part in validation_error.get("loc", ())),
            message=str(validation_error.get("msg", "Invalid provider config value.")),
            type=str(validation_error.get("type", "value_error")),
        )
        for validation_error in error.errors()
    ]


def _provider_configuration_error(error: ProviderConfigurationError) -> ApiError:
    return ApiError(
        status_code=400,
        code=ApiErrorCode.BAD_REQUEST,
        message=error.message,
        details=[
            ApiErrorDetail(
                field=setting_name,
                message="Required provider setting is missing.",
                type="missing",
            )
            for setting_name in error.missing_settings
        ],
    )


@router.get("/providers", response_model=ProviderConfigResponse)
def get_provider_config(
    settings: Annotated[AppSettings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> ProviderConfigResponse:
    """Return selected provider config plus recommended classification mode."""

    return build_provider_config_response(settings, registry)


@router.put(
    "/providers",
    response_model=ProviderConfigResponse,
    responses={
        400: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
async def update_provider_config(
    request: ProviderConfigUpdateRequest,
    settings: Annotated[AppSettings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    sync_scheduler: Annotated[SyncScheduler, Depends(get_active_sync_scheduler)],
    repository: Annotated[
        ProviderConfigurationRepository,
        Depends(get_provider_configuration_repository),
    ],
    secret_store: Annotated[SecretStore, Depends(get_llm_secret_store)],
) -> ProviderConfigResponse:
    """Validate and update provider config, applying recommendations on provider changes."""

    try:
        return await apply_provider_config_update(
            settings,
            request,
            registry,
            sync_scheduler=sync_scheduler,
            repository=repository,
            secret_store=secret_store,
        )
    except ValidationError as error:
        raise ApiError(
            status_code=422,
            code=ApiErrorCode.VALIDATION_ERROR,
            message="Provider config validation failed.",
            details=_settings_validation_details(error),
        ) from error
    except ProviderConfigurationError as error:
        raise _provider_configuration_error(error) from error
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


@router.get("/providers/readiness", response_model=ProviderReadinessResponse)
async def provider_readiness(
    service: Annotated[ProviderReadinessService, Depends(get_provider_readiness_service)],
) -> ProviderReadinessResponse:
    """Report readiness for each provider-backed product capability."""

    return await service.check()


@router.post(
    "/providers/llm/health",
    response_model=LLMProviderHealthCheckResponse,
    responses={422: {"model": ApiErrorResponse}},
)
async def check_llm_provider_health(
    _request: Annotated[
        LLMProviderHealthCheckApiRequest,
        Depends(validate_llm_provider_health_request_body),
    ],
    settings: Annotated[AppSettings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    llm_provider: Annotated[LLMProvider, Depends(get_configured_llm_provider)],
) -> LLMProviderHealthCheckResponse:
    """Verify selected LLM provider models through the configured provider adapter."""

    try:
        return await check_configured_llm_provider_health(
            settings,
            llm_provider,
            registry,
        )
    except ProviderConfigurationError as error:
        raise _provider_configuration_error(error) from error
