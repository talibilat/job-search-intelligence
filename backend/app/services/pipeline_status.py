from __future__ import annotations

from datetime import UTC, datetime

from app.config import AppSettings
from app.db.repositories.email import EmailRepository
from app.db.repositories.pipeline_status import PipelineStatusRepository
from app.models.pipeline import (
    BackfillProgressState,
    PipelineNextAction,
    PipelineStageCounts,
    PipelineStatus,
)
from app.models.records import EmailBackfillStatus
from app.providers.email import EmailConnection
from app.services.classification_target import resolve_classification_model
from app.services.sync_service import EmailSyncRunState, EmailSyncStatus


def build_pipeline_status(
    *,
    settings: AppSettings,
    pipeline_status_repository: PipelineStatusRepository,
    email_repository: EmailRepository,
    connection: EmailConnection | None,
    sync_status: EmailSyncStatus,
    now: datetime | None = None,
) -> PipelineStatus:
    """Compose the deterministic pipeline overview from local state only."""

    generated_at = now or datetime.now(UTC)
    provider = settings.email_provider

    counts = pipeline_status_repository.fetch_stage_counts(provider=provider)
    backfill = pipeline_status_repository.fetch_latest_backfill_state(provider=provider)
    sync_state = pipeline_status_repository.fetch_latest_sync_state(provider=provider)

    candidate_stats = email_repository.get_classification_candidate_stats(
        provider=provider,
        model=resolve_classification_model(settings),
        prompt_version=settings.classification_prompt_version,
    )
    unclassified_retained_count = candidate_stats.candidate_count

    backfill_state = BackfillProgressState.NOT_STARTED
    if backfill is not None:
        backfill_state = BackfillProgressState(backfill.status.value)

    backfill_complete = backfill is not None and backfill.status is EmailBackfillStatus.COMPLETED
    incremental_sync_ready = backfill_complete and (
        sync_state is not None and sync_state.sync_cursor is not None
    )

    sync_running = sync_status.state is EmailSyncRunState.RUNNING
    last_error = sync_status.last_error or (backfill.last_error if backfill is not None else None)

    next_action, next_action_reason = _resolve_next_action(
        connected=connection is not None,
        sync_running=sync_running,
        sync_failed=sync_status.state is EmailSyncRunState.FAILED,
        backfill_state=backfill_state,
        counts=counts,
        unclassified_retained_count=unclassified_retained_count,
        last_error=last_error,
    )

    return PipelineStatus(
        generated_at=generated_at,
        gmail_connected=connection is not None,
        account_display=_connection_display(connection),
        reauth_required=connection.reauth_required if connection is not None else False,
        sync_running=sync_running,
        sync_mode=sync_status.mode.value if sync_status.mode is not None else None,
        last_sync_started_at=sync_status.started_at,
        last_sync_finished_at=sync_status.finished_at,
        backfill_state=backfill_state,
        backfill_pages_processed=backfill.processed_page_count if backfill is not None else 0,
        backfill_messages_processed=(
            backfill.processed_message_count if backfill is not None else 0
        ),
        backfill_complete=backfill_complete,
        incremental_sync_ready=incremental_sync_ready,
        counts=counts,
        unclassified_retained_count=unclassified_retained_count,
        last_error=last_error,
        next_action=next_action,
        next_action_reason=next_action_reason,
    )


def _connection_display(connection: EmailConnection | None) -> str | None:
    if connection is None:
        return None
    if connection.display_email is not None:
        return connection.display_email.address
    return connection.account.account_id


def _resolve_next_action(
    *,
    connected: bool,
    sync_running: bool,
    sync_failed: bool,
    backfill_state: BackfillProgressState,
    counts: PipelineStageCounts,
    unclassified_retained_count: int,
    last_error: str | None,
) -> tuple[PipelineNextAction, str]:
    if not connected:
        return (
            PipelineNextAction.CONNECT_GMAIL,
            "No Gmail account is connected yet. Connect Gmail on the Setup page first.",
        )
    if sync_running:
        return (
            PipelineNextAction.WAIT_FOR_SYNC,
            "A sync run is in progress. New mail appears here as pages finish.",
        )
    if sync_failed or backfill_state is BackfillProgressState.FAILED:
        detail = f" Last error: {last_error}" if last_error else ""
        return (
            PipelineNextAction.INSPECT_ERROR,
            f"The last sync run failed. Run sync again to resume from saved progress.{detail}",
        )
    if counts.raw_email_count == 0:
        return (
            PipelineNextAction.RUN_SYNC,
            "Gmail is connected but no email metadata is stored yet. Run your first sync.",
        )
    if backfill_state is not BackfillProgressState.COMPLETED:
        return (
            PipelineNextAction.CONTINUE_BACKFILL,
            "The one-time historical backfill has not finished. Each sync resumes it "
            "where it left off, walking from newest mail toward oldest. New mail is "
            "picked up by fast incremental sync only after the backfill completes.",
        )
    if unclassified_retained_count > 0:
        return (
            PipelineNextAction.RUN_CLASSIFICATION,
            f"{unclassified_retained_count} job-search candidate emails are waiting for "
            "classification. Run classification to turn them into applications.",
        )
    if counts.application_count == 0:
        if counts.retained_body_count == 0:
            return (
                PipelineNextAction.REVIEW_DASHBOARD,
                "Sync finished but the heuristic filter kept no job-search candidates, "
                "so there is nothing to classify. Dashboard zeros are real zeros.",
            )
        return (
            PipelineNextAction.REVIEW_DASHBOARD,
            "All candidates are classified and none produced a job application. "
            "Dashboard zeros are real zeros, not a stalled pipeline.",
        )
    return (
        PipelineNextAction.REVIEW_DASHBOARD,
        "The pipeline is up to date. Dashboard metrics reflect all processed email.",
    )
