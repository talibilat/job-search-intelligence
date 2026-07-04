from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail
from app.config import AppSettings, get_settings
from app.models import ProviderConfigResponse, ProviderConfigUpdateRequest
from app.providers import ProviderConfigurationError, ProviderRegistry, provider_registry
from app.services.provider_config import (
    apply_provider_config_update,
    build_provider_config_response,
)

router = APIRouter(prefix="/config", tags=["config"])


def get_provider_registry() -> ProviderRegistry:
    return provider_registry


def _settings_validation_details(error: ValidationError) -> list[ApiErrorDetail]:
    return [
        ApiErrorDetail(
            field=".".join(str(part) for part in validation_error.get("loc", ())),
            message=str(validation_error.get("msg", "Invalid provider config value.")),
            type=str(validation_error.get("type", "value_error")),
        )
        for validation_error in error.errors()
    ]


@router.get("/providers", response_model=ProviderConfigResponse)
def get_provider_config(
    settings: Annotated[AppSettings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> ProviderConfigResponse:
    """Return selected provider config and non-secret supported-provider metadata."""

    return build_provider_config_response(settings, registry)


@router.put("/providers", response_model=ProviderConfigResponse)
def update_provider_config(
    request: ProviderConfigUpdateRequest,
    settings: Annotated[AppSettings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> ProviderConfigResponse:
    """Validate and update the in-process provider config shell."""

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
        raise ApiError(
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
        ) from error
