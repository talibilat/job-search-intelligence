from __future__ import annotations

from app.config import AppSettings
from app.db.repositories import EmailRepository
from app.models import ClassificationReprocessingPlan
from app.services.classification_target import (
    has_configured_classification_model,
    resolve_classification_model,
)

CLASSIFICATION_REPROCESSING_SELECTION_POLICY = (
    "Reprocess retained candidate emails with no classification, a stored model "
    "different from the target model, or a stored prompt_version different from "
    "the target prompt version."
)


def build_classification_reprocessing_plan(
    *,
    settings: AppSettings,
    email_repository: EmailRepository,
) -> ClassificationReprocessingPlan:
    """Build a read-only plan for prompt/model-version controlled reprocessing."""

    classification_model = resolve_classification_model(settings)
    target_model_configured = has_configured_classification_model(settings)
    if target_model_configured:
        stats = email_repository.get_classification_reprocessing_stats(
            provider=settings.email_provider,
            model=classification_model,
            prompt_version=settings.classification_prompt_version,
        )
    else:
        stats = email_repository.get_classification_reprocessing_stats_without_target_model(
            provider=settings.email_provider,
        )

    return ClassificationReprocessingPlan(
        email_provider=settings.email_provider,
        classification_mode=settings.classification_mode,
        llm_provider=settings.llm_provider,
        target_model=classification_model,
        target_model_configured=target_model_configured,
        target_prompt_version=settings.classification_prompt_version,
        retained_candidate_count=stats.retained_candidate_count,
        up_to_date_count=stats.up_to_date_count,
        unclassified_count=stats.unclassified_count,
        stale_model_count=stats.stale_model_count,
        stale_prompt_version_count=stats.stale_prompt_version_count,
        blocked_by_missing_target_model_count=stats.blocked_by_missing_target_model_count,
        reprocess_count=stats.reprocess_count,
        should_reprocess=target_model_configured and stats.reprocess_count > 0,
        selection_policy=CLASSIFICATION_REPROCESSING_SELECTION_POLICY,
    )
