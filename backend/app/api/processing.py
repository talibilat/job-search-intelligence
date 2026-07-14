from __future__ import annotations

from threading import Lock
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_processing_orchestration_service,
    get_readonly_email_repository,
)
from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.config import AppSettings, get_settings
from app.db.repositories import EmailRepository
from app.models import (
    ProcessingRunRequest,
    ProcessingRunResult,
    ProcessingRunState,
    ProcessingStatus,
)
from app.services.processing import ProcessingOrchestrationService, build_processing_status

router = APIRouter(prefix="/processing", tags=["processing"])


class ProcessingStatusStore:
    def __init__(self) -> None:
        self._run_lock = Lock()
        self._status: ProcessingStatus | None = None

    def acquire_run(self) -> bool:
        return self._run_lock.acquire(blocking=False)

    def set_status(self, status: ProcessingStatus) -> None:
        self._status = status

    def current(self, fallback: ProcessingStatus) -> ProcessingStatus:
        return self._status or fallback

    def fail(self, fallback: ProcessingStatus) -> None:
        self._status = fallback.model_copy(
            update={"state": ProcessingRunState.FAILED, "last_error": "Processing failed."}
        )

    def release_run(self) -> None:
        self._run_lock.release()


_status_store = ProcessingStatusStore()


def get_processing_status_store() -> ProcessingStatusStore:
    return _status_store


@router.get("/status", response_model=ProcessingStatus, summary="Get Processing Status")
def processing_status(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_repository: Annotated[EmailRepository, Depends(get_readonly_email_repository)],
    store: Annotated[ProcessingStatusStore, Depends(get_processing_status_store)],
) -> ProcessingStatus:
    return store.current(
        build_processing_status(settings=settings, email_repository=email_repository)
    )


@router.post(
    "/run",
    response_model=ProcessingRunResult,
    responses={409: {"model": ApiErrorResponse}},
    summary="Run Pending Email Processing",
)
async def processing_run(
    request: ProcessingRunRequest,
    service: Annotated[
        ProcessingOrchestrationService,
        Depends(get_processing_orchestration_service),
    ],
    store: Annotated[ProcessingStatusStore, Depends(get_processing_status_store)],
) -> ProcessingRunResult:
    if not store.acquire_run():
        raise ApiError(
            status_code=409,
            code=ApiErrorCode.CONFLICT,
            message="Email processing is already running.",
        )
    try:
        return await service.run(request, status_callback=store.set_status)
    except Exception:
        store.fail(service.status())
        raise
    finally:
        store.release_run()
