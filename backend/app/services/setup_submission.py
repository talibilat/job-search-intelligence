from __future__ import annotations

from collections.abc import Callable

from app.config import AppSettings
from app.db.repositories.provider_config import ProviderConfigurationRepository
from app.models.provider_config import ProviderConfigUpdateRequest
from app.models.setup import SetupSubmitRequest, SetupSubmitResponse
from app.providers import ProviderConfigurationError, ProviderRegistry
from app.security import SecretStore
from app.services.provider_config import apply_provider_config_update
from app.services.readiness import ProviderReadinessService
from app.services.setup_status import build_setup_status
from app.services.sync_service import SyncScheduler


class SetupSubmissionValidationError(ValueError):
    def __init__(self, *, message: str, missing_settings: tuple[str, ...] = ()) -> None:
        self.message = message
        self.missing_settings = missing_settings
        super().__init__(message)


async def submit_setup(
    request: SetupSubmitRequest,
    settings: AppSettings,
    registry: ProviderRegistry,
    *,
    repository: ProviderConfigurationRepository,
    secret_store: SecretStore,
    sync_scheduler: SyncScheduler,
    readiness_service_factory: Callable[[], ProviderReadinessService],
) -> SetupSubmitResponse:
    try:
        await apply_provider_config_update(
            settings,
            ProviderConfigUpdateRequest.model_validate(request.model_dump(exclude_none=True)),
            registry,
            repository=repository,
            secret_store=secret_store,
            sync_scheduler=sync_scheduler,
        )
    except ProviderConfigurationError as error:
        raise SetupSubmissionValidationError(
            message="Submitted setup choices are incomplete."
            if error.missing_settings
            else "Submitted setup choices are incompatible.",
            missing_settings=error.missing_settings,
        ) from error
    status = build_setup_status(settings, await readiness_service_factory().check())
    return SetupSubmitResponse(status="accepted", **status.model_dump())
