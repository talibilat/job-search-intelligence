# Synthetic fixtures

Synthetic fixtures are private-data-free JSON files for backend tests and later dashboard smoke paths.
They model the same factual spine described in the PRD: emails, classifications, applications, and application events.

## Format

The canonical DTOs live in `backend/app/models/synthetic_fixture.py`.
Fixture files use `schema_version: "1"` and must set `contains_private_data` to `false`.
The DTOs are exported from `backend/app/models/__init__.py` for tests and the SQLite fixture loader.

Each fixture has these top-level arrays:

- `emails` models `raw_emails` rows with provider metadata and retained synthetic body text when needed.
- `classifications` models `email_classifications` rows and references emails by `email_id`.
- `applications` models `applications` rows used by deterministic metrics and aggregation tests.
- `events` models `application_events` rows and references both `application_id` and `email_id`.

The DTO can default omitted arrays to empty tuples, but checked-in JSON fixtures should include all four arrays explicitly so fixture intent is obvious in review.

## Fields

Top-level fixture fields:

- `schema_version`: required, currently only `"1"`.
- `fixture_id`: required non-empty string.
- `description`: required non-empty string.
- `contains_private_data`: required, must be `false`.
- `emails`, `classifications`, `applications`, `events`: explicit arrays in checked-in JSON fixtures.

`emails` fields:

- `id`: required non-empty string.
- `provider`: required backend email provider enum value.
- `thread_id`, `from_addr`, `to_addr`, `subject`: optional non-empty strings.
- `sent_at`: optional timestamp.
- `body_text`: optional synthetic body text, excluded from DTO repr output.
- `body_retention_state`: optional, defaults to `metadata_only`.
  Current values are `metadata_only`, `retained`, and `debugging` through the shared backend raw-email retention enum.
  `metadata_only` rows must omit `body_text`; `retained` and `debugging` rows must include it.
- `labels`: optional string array, defaults to empty.
- `ingested_at`: required timestamp.

`classifications` fields:

- `email_id`: required non-empty string referencing an `emails[].id` value.
- `is_job_related`: required boolean.
- `category`: required classification category enum value.
- `confidence`: required number from `0` through `1`.
- `model`, `prompt_version`: required non-empty strings.
- `classified_at`: required timestamp.

`applications` fields:

- `id`, `company`, `role_title`: required non-empty strings.
- `source`: optional application source enum value, defaults to `other`.
- `first_seen_at`, `last_activity_at`, `created_at`, `updated_at`: required timestamps.
- `current_status`: required application status enum value.
- `salary_min`, `salary_max`: optional non-negative integers.
- `currency`: optional three-character string.
- `location`, `seniority`: optional non-empty strings.
- `work_mode`: optional work-mode enum value.
- `sponsorship`: optional sponsorship enum value, defaults to `unknown`.
- `tech_stack`: optional string array, defaults to empty.
- `manual_lock`: optional boolean, defaults to `false`.

`events` fields:

- `id`: required non-empty string.
- `application_id`: required non-empty string referencing an `applications[].id` value.
- `email_id`: required non-empty string referencing an `emails[].id` value.
- `event_type`: required event type enum value.
- `event_at`: required timestamp.
- `extract_note`: optional non-empty string.

All payload fields are strict: unknown fields are rejected at every level.
The file-level contract rejects duplicate email IDs, duplicate classification `email_id` values, duplicate application IDs, duplicate event IDs, private-data flags, and cross references to missing emails or applications.
Application salary ranges must be non-negative, and `salary_min` must be less than or equal to `salary_max` when both are present.
Retained synthetic email body text is excluded from object repr output to preserve the same redaction habit used for real retained bodies.
Synthetic fixtures share the backend raw-email retention enum, so obsolete values such as `omitted` are rejected.
Use `debugging` for synthetic emails whose retained body exists only to exercise debugging or reconciliation flows.

## Enumerations

Fixture enum values mirror the planned database contract:

- `body_retention_state`: `metadata_only`, `retained`, `debugging`
- `category`: `application_confirmation`, `rejection`, `interview_invite`, `recruiter_outreach`, `offer`, `assessment`, `follow_up`, `other`
- `source`: `linkedin`, `company_site`, `indeed`, `referral`, `other`
- `current_status`: `applied`, `in_review`, `assessment`, `interview`, `offer`, `rejected`, `ghosted`, `withdrawn`
- `work_mode`: `remote`, `hybrid`, `onsite`
- `sponsorship`: `offered`, `not_offered`, `unknown`
- `event_type`: `applied`, `response`, `assessment`, `interview_scheduled`, `feedback`, `rejection`, `offer`, `ghost_inferred`

`provider` uses the existing backend email provider enum, currently `gmail`.

## Sample

The initial sample fixture is `backend/tests/fixtures/synthetic/basic_job_search.json`.
It contains one application confirmation and one later rejection for the same synthetic application.

## Loader

`backend/app/db/repositories/synthetic_fixture.py` defines `SyntheticFixtureRepository`.
Use `SyntheticFixtureRepository(connection).load_file(path)` to validate a JSON fixture and load it into a caller-provided local SQLite connection.
Use `load_fixture(fixture)` when the caller already has a validated `SyntheticFixtureFile` instance.

The loader creates the four core fixture tables when they are missing:

- `raw_emails`
- `email_classifications`
- `applications`
- `application_events`

Rows are inserted with deterministic `INSERT OR REPLACE` behavior keyed by fixture IDs, so loading the same fixture twice does not duplicate rows.
The loader returns `SyntheticFixtureLoadResult` with the fixture ID and per-table counts.
It is for deterministic tests and smoke data only; it does not add API routes, production ingestion behavior, LLM behavior, telemetry, or real email data.

Validate the fixture contract from `backend/` with:

```bash
uv run pytest tests/test_synthetic_fixture_format.py -v
```

Validate the loader with:

```bash
uv run pytest tests/test_synthetic_fixture_loader.py -v
```
