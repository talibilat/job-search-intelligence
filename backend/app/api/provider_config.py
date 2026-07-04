from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.errors import ApiError, ApiErrorCode, ApiErrorDetail
from app.config import AppSettings, get_settings
from app.models import ProviderConfigResponse, ProviderConfigUpdateRequest
from app.providers import ProviderConfigurationError, provider_registry
from app.services.provider_config import (
    apply_provider_config_update,
    build_provider_config_response,
)

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/providers", response_model=ProviderConfigResponse)
def get_provider_config(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> ProviderConfigResponse:
    """Return selected provider config and non-secret supported-provider metadata."""

    return build_provider_config_response(settings, provider_registry)


@router.put("/providers", response_model=ProviderConfigResponse)
def update_provider_config(
    request: ProviderConfigUpdateRequest,
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> ProviderConfigResponse:
    """Validate and update the in-process provider config shell."""

    try:
        return apply_provider_config_update(settings, request, provider_registry)
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
