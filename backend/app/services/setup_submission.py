from __future__ import annotations

from typing import Any

from app.config import AppSettings
from app.models import SetupSubmitRequest, SetupSubmitResponse
from app.providers import ProviderConfigurationError, ProviderRegistry, provider_registry
from app.services.setup_status import build_setup_status


class SetupSubmissionValidationError(ValueError):
    """Raised when submitted non-secret setup choices are not usable."""

    def __init__(
        self,
        *,
        message: str,
        missing_settings: tuple[str, ...] = (),
    ) -> None:
        self.message = message
        self.missing_settings = missing_settings
        super().__init__(message)


def submit_setup(
    request: SetupSubmitRequest,
    settings: AppSettings,
    registry: ProviderRegistry = provider_registry,
) -> SetupSubmitResponse:
    candidate_settings = _settings_with_submission(settings, request)
    try:
        registry.validate_settings(candidate_settings)
    except ProviderConfigurationError as error:
        raise SetupSubmissionValidationError(
            message=_setup_submission_error_message(error),
            missing_settings=error.missing_settings,
        ) from error

    status = build_setup_status(candidate_settings)
    return SetupSubmitResponse(status="accepted", **status.model_dump())


def _settings_with_submission(
    settings: AppSettings,
    request: SetupSubmitRequest,
) -> AppSettings:
    values: dict[str, Any] = settings.model_dump()
    values.update(request.model_dump(exclude_none=True))
    return AppSettings(_env_file=None, **values)


def _setup_submission_error_message(error: ProviderConfigurationError) -> str:
    if error.missing_settings:
        return "Submitted setup choices are incomplete."

    return "Submitted setup choices are incompatible."
