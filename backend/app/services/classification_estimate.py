from __future__ import annotations

from math import ceil

from app.config import AppSettings, ClassificationMode, LLMProviderName
from app.db.repositories import EmailRepository
from app.models import ClassificationPreRunEstimate


def build_classification_pre_run_estimate(
    *,
    settings: AppSettings,
    email_repository: EmailRepository,
) -> ClassificationPreRunEstimate:
    """Estimate candidates, tokens, and cost before bulk classification."""

    classification_model = _classification_model(settings)
    stats = email_repository.get_classification_candidate_stats(
        provider=settings.email_provider,
        model=classification_model,
        prompt_version=settings.classification_prompt_version,
    )
    body_tokens = ceil(
        stats.body_text_char_count / settings.classification_estimate_chars_per_unit,
    )
    prompt_tokens = body_tokens + (
        stats.candidate_count * settings.classification_estimate_prompt_overhead_units
    )
    completion_tokens = (
        stats.candidate_count * settings.classification_estimate_completion_units_per_candidate
    )
    total_tokens = prompt_tokens + completion_tokens
    estimated_cost_usd, cost_estimate_available = _estimate_cost_usd(
        settings=settings,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    return ClassificationPreRunEstimate(
        candidate_count=stats.candidate_count,
        estimated_prompt_tokens=prompt_tokens,
        estimated_completion_tokens=completion_tokens,
        estimated_total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
        currency="USD",
        cost_estimate_available=cost_estimate_available,
        classification_mode=settings.classification_mode,
        llm_provider=settings.llm_provider,
        model=classification_model,
        prompt_version=settings.classification_prompt_version,
        token_estimate_method=(
            "ceil(body_text_chars / "
            f"{settings.classification_estimate_chars_per_unit}) + "
            f"{settings.classification_estimate_prompt_overhead_units} prompt overhead "
            "tokens per candidate; "
            f"{settings.classification_estimate_completion_units_per_candidate} completion tokens "
            "per candidate"
        ),
    )


def _estimate_cost_usd(
    *,
    settings: AppSettings,
    prompt_tokens: int,
    completion_tokens: int,
) -> tuple[float | None, bool]:
    if settings.classification_mode is ClassificationMode.LOCAL:
        return 0.0, True

    input_rate = settings.classification_input_cost_per_1k_units_usd
    output_rate = settings.classification_output_cost_per_1k_units_usd
    if input_rate == 0 or output_rate == 0:
        return None, False

    cost = (prompt_tokens / 1000 * input_rate) + (completion_tokens / 1000 * output_rate)
    return round(cost, 6), True


def _classification_model(settings: AppSettings) -> str:
    if settings.llm_provider is LLMProviderName.AZURE_OPENAI:
        return settings.azure_openai_chat_deployment or "unconfigured"
    return settings.ollama_chat_model
