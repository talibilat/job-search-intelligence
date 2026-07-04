# Synthetic fixtures

Synthetic fixtures are private-data-free JSON files for backend tests and later dashboard smoke paths.
They model the same factual spine described in the PRD: emails, classifications, applications, and application events.

## Format

The canonical DTOs live in `backend/app/models/synthetic_fixture.py`.
Fixture files use `schema_version: "1"` and must set `contains_private_data` to `false`.

Each fixture has these top-level arrays:

- `emails` models future `raw_emails` rows with provider metadata and retained synthetic body text when needed.
- `classifications` models future `email_classifications` rows and references emails by `email_id`.
- `applications` models future `applications` rows used by deterministic metrics and aggregation tests.
- `events` models future `application_events` rows and references both `application_id` and `email_id`.

The DTOs reject unknown fields, duplicate IDs, private-data flags, and cross references to missing emails or applications.
Retained synthetic email body text is excluded from object repr output to preserve the same redaction habit used for real retained bodies.

## Sample

The initial sample fixture is `backend/tests/fixtures/synthetic/basic_job_search.json`.
It contains one application confirmation and one later rejection for the same synthetic application.
