# JT-159 Company Metadata Design

## Context

JT-159 asks the dashboard to answer Q-24: which company types, such as startup or enterprise, respond best.

The current application source of truth has `applications.company`, but it does not store company type, industry, startup, enterprise, or equivalent segmentation data.
Because dashboard metrics must be deterministic, Q-24 cannot be implemented by asking an LLM to classify companies at query time.

This design adds a prerequisite company metadata slice before the Q-24 dashboard work.

## Goals

Add deterministic, local-first company metadata that can support company-type and industry breakdown metrics.

Keep the existing `applications` and `application_events` invariant intact.

Allow unknown company metadata without blocking metrics.

Keep all dashboard counts and rates deterministic SQL or typed Python logic.

## Non-Goals

Do not add external enrichment APIs.

Do not classify company type live with an LLM during dashboard reads.

Do not change aggregation grouping rules for applications.

Do not make Q-24 depend on multi-user or SaaS assumptions.

## Data Model

Add a `company_profiles` table keyed by normalized company name.

Suggested columns:

- `normalized_company` as primary key.
- `display_company` for readable UI labels.
- `company_type` constrained to `startup`, `enterprise`, `public_company`, `agency`, `nonprofit`, `education`, `government`, `unknown`, or `other`.
- `industry` as nullable text.
- `source` constrained to `manual`, `imported`, `extracted`, or `unknown`.
- `created_at` and `updated_at` timestamps.

The table is support data for segmentation.
It does not replace `applications.company` and does not become the factual event timeline.

## Population Path

The first implementation should support manual or imported company metadata.

Extraction from email or job descriptions can come later, but extracted company metadata must be stored before metrics use it.

Unknown companies should be represented explicitly as `unknown` rather than omitted from the breakdown.

## Backend API And Repository Design

Add repository methods to upsert and read `company_profiles` by normalized company name.

Extend `MetricsBreakdownDimension` with `company_type` and `industry`.

For those dimensions, metrics queries should left join applications to `company_profiles` on normalized company name.

Rows without metadata should group under `unknown`.

Breakdown rows should continue to return `application_count`, `response_count`, `interview_count`, and `offer_count`.

Existing dashboard filters must compose with these new dimensions.

## Frontend Design

Extend the dashboard breakdown selector with `Company type` and `Industry` once the backend dimensions exist.

Add a Q-24 section if a dedicated presentation is clearer than relying only on the generic breakdown selector.

The section should show response and interview outcomes by company type or industry for the active route-backed filters.

Empty or unknown metadata should be visible as `Unknown` so the UI does not imply more precision than the data supports.

## Testing

Add backend repository and API tests for `company_type` and `industry` breakdowns.

Tests should verify unknown bucketing, response counts, interview counts, offer counts, and filter composition.

Add frontend tests that prove the dashboard can request and render company-type or industry breakdown rows.

Run backend `ruff`, focused `pytest`, backend `mypy`, and frontend `npm run check` for implementation PRs touching this path.

## Implementation Slices

1. Add the `company_profiles` schema, DTOs, and repository methods.
2. Add a local manual/import path for company profile rows.
3. Add `company_type` and `industry` metrics breakdown dimensions.
4. Add the Q-24 dashboard presentation and close JT-159.

## Open Decisions

Use `company_profiles` rather than adding nullable company-type fields directly to `applications`.
This keeps company metadata normalized and avoids copying the same company classification across many application rows.

Use `unknown` as a first-class bucket.
This keeps deterministic metrics honest when metadata has not been supplied yet.
