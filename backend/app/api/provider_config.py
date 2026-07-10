from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail, ApiErrorResponse
from app.config import AppSettings, get_settings
from app.models import (
    LLMProviderHealthCheckApiRequest,
    ProviderConfigResponse,
    ProviderConfigUpdateRequest,
)
from app.providers import ProviderConfigurationError, ProviderRegistry, provider_registry
from app.providers.llm import (
    LLMProvider,
    LLMProviderHealthCheckResponse,
    LLMProviderUnavailableError,
)
from app.services.llm_health import check_configured_llm_provider_health
from app.services.provider_config import (
    apply_provider_config_update,
    build_provider_config_response,
)

router = APIRouter(prefix="/config", tags=["config"])


def get_provider_registry() -> ProviderRegistry:
    return provider_registry


def get_configured_llm_provider(
    settings: Annotated[AppSettings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> LLMProvider:
    try:
        registry.validate_settings(settings)
    except ProviderConfigurationError as error:
        raise _provider_configuration_error(error) from error

    raise LLMProviderUnavailableError(public_message="LLM provider adapter is not configured.")


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
    responses={400: {"model": ApiErrorResponse}, 422: {"model": ApiErrorResponse}},
)
def update_provider_config(
    request: ProviderConfigUpdateRequest,
    settings: Annotated[AppSettings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> ProviderConfigResponse:
    """Validate and update provider config, applying recommendations on provider changes."""

    try:
        return apply_provider_config_update(settings, request, registry)
    except ValidationError as error:
        raise ApiError(
            status_code=422,
            code=ApiErrorCode.VALIDATION_ERROR,
            message="Provider config validation failed.",
            details=_settings_validation_details(error),
        ) from error
    except ProviderConfigurationError as error:
        raise _provider_configuration_error(error) from error


@router.post("/providers/llm/health", response_model=LLMProviderHealthCheckResponse)
async def check_llm_provider_health(
    request: Request,
    settings: Annotated[AppSettings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    llm_provider: Annotated[LLMProvider, Depends(get_configured_llm_provider)],
) -> LLMProviderHealthCheckResponse:
    """Verify selected LLM provider models through the configured provider adapter."""

    raw_body = await request.body()
    if raw_body.strip():
        try:
            LLMProviderHealthCheckApiRequest.model_validate_json(raw_body)
        except ValidationError as error:
            raise ApiError(
                status_code=422,
                code=ApiErrorCode.VALIDATION_ERROR,
                message="LLM provider health request validation failed.",
                details=_settings_validation_details(error),
            ) from error

    try:
        return await check_configured_llm_provider_health(
            settings,
            llm_provider,
            registry,
        )
    except ProviderConfigurationError as error:
        raise _provider_configuration_error(error) from error
