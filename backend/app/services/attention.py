from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.db.repositories.attention import AttentionRepository
from app.models.attention import AttentionOverviewResponse, InterviewTaskCompletionResponse

type Clock = Callable[[], datetime]


class InterviewTaskNotFoundError(LookupError):
    pass


class AttentionService:
    """Build persisted interview tasks and unique-company history."""

    def __init__(
        self,
        *,
        repository: AttentionRepository,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def get_overview(self) -> AttentionOverviewResponse:
        now = self._clock()
        interviewed = self._repository.list_interviewed_companies()
        return AttentionOverviewResponse(
            unique_interviewed_company_count=len(interviewed),
            prepare=self._repository.list_prepare(
                active_cutoff_at=(now - timedelta(days=60)).isoformat(),
            ),
            interviewed=interviewed,
            follow_up=self._repository.list_follow_up(
                active_cutoff_at=(now - timedelta(days=60)).isoformat(),
                follow_up_cutoff_at=(now - timedelta(days=7)).isoformat(),
            ),
        )

    def complete(self, interview_event_id: str) -> InterviewTaskCompletionResponse:
        completion = self._repository.complete_interview_task(
            interview_event_id=interview_event_id,
            completed_at=self._clock().isoformat(),
        )
        if completion is None:
            raise InterviewTaskNotFoundError(interview_event_id)
        return completion
