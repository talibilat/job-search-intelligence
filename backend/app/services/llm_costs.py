from __future__ import annotations


def calculate_llm_cost_usd(
    *,
    is_local_provider: bool,
    input_rate_per_1k_units_usd: float,
    output_rate_per_1k_units_usd: float,
    prompt_tokens: int,
    completion_tokens: int,
) -> tuple[float | None, bool]:
    """Return USD cost and availability for provider-neutral token usage."""

    if is_local_provider:
        return 0.0, True

    if input_rate_per_1k_units_usd == 0 or output_rate_per_1k_units_usd == 0:
        return None, False

    cost = (prompt_tokens / 1000 * input_rate_per_1k_units_usd) + (
        completion_tokens / 1000 * output_rate_per_1k_units_usd
    )
    return round(cost, 6), True
