from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_application_detail_service
from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.models import ApplicationRecord
from app.services.applications import ApplicationDetailService, ApplicationNotFoundError

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get(
    "/{application_id}",
    response_model=ApplicationRecord,
    responses={404: {"model": ApiErrorResponse}},
    summary="Get Application Detail",
    description="Returns one canonical application row from the local SQLite source of truth.",
)
def get_application_detail(
    application_id: str,
    service: Annotated[
        ApplicationDetailService,
        Depends(get_application_detail_service),
    ],
) -> ApplicationRecord:
    try:
        return service.get_application(application_id)
    except ApplicationNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Application not found.",
        ) from error
