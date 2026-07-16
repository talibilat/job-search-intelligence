from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_attention_service
from app.api.errors import ApiError, ApiErrorCode, ApiErrorResponse
from app.models.attention import AttentionOverviewResponse, InterviewTaskCompletionResponse
from app.services.attention import AttentionService, InterviewTaskNotFoundError

router = APIRouter(prefix="/attention", tags=["attention"])


@router.get("", response_model=AttentionOverviewResponse, summary="Get Interview Attention")
def get_attention(
    service: Annotated[AttentionService, Depends(get_attention_service)],
) -> AttentionOverviewResponse:
    return service.get_overview()


@router.put(
    "/interviews/{interview_event_id}/complete",
    response_model=InterviewTaskCompletionResponse,
    responses={404: {"model": ApiErrorResponse}},
    summary="Complete Interview Preparation Task",
)
def complete_interview_task(
    interview_event_id: str,
    service: Annotated[AttentionService, Depends(get_attention_service)],
) -> InterviewTaskCompletionResponse:
    try:
        return service.complete(interview_event_id)
    except InterviewTaskNotFoundError as error:
        raise ApiError(
            status_code=404,
            code=ApiErrorCode.NOT_FOUND,
            message="Interview task was not found.",
        ) from error
