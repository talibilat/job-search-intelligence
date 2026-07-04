# JT-032 Wipe Data Design

## Context

JT-032 adds a privacy path for clearing local JobTracker data and derived artifacts.
The work is Phase 0 groundwork and maps to `FR-6.3`, `FR-6`, `NFR-1`, `NFR-5`, and `NFR-8`.
The implementation must preserve the local-first model and the `applications` plus `application_events` invariant by deleting local data atomically instead of mutating application records piecemeal.

## Scope

The ticket will add a backend API endpoint for wiping local app data.
The endpoint is visible through OpenAPI and documented in the README.
The endpoint will use typed Pydantic request and response DTOs.
The route will stay thin and delegate filesystem behavior to a focused service.

The ticket will not add a frontend UI.
The ticket will not delete OS keyring secrets or external OAuth client JSON files.
The ticket will not add database migrations.
The ticket will not implement later Phase 1-5 data models.

## API Design

Add `POST /local-data/wipe`.
The request requires `confirmation` to exactly equal `wipe-local-data`.
This prevents accidental deletion from a casual HTTP call or generated client misuse.

The response returns a typed summary with three fields.
`status` is always `wiped` when the operation succeeds.
`deleted_paths` contains non-secret filesystem paths that were deleted.
`missing_paths` contains non-secret filesystem paths that were already absent.

The endpoint will return `422` for request validation failures.
The endpoint will return a typed `400` API error if resolved paths are unsafe wipe targets.

## Service Design

Add `backend/app/services/wipe_data.py`.
The service consumes `AppSettings` and computes deletion targets from `settings.data_dir` and `settings.database_url`.
The service deletes `settings.data_dir` recursively when it exists and is app-owned.
An app-owned data directory is either named `.jobtracker` or contains the `.jobtracker-data` marker file.
The service deletes the configured SQLite database file and SQLite sidecar files when the database path is outside `settings.data_dir`.
The sidecar files are `<database>-wal`, `<database>-shm`, and `<database>-journal`.
The service treats missing paths as already clean so the operation is idempotent.
The service preflights every target before deleting anything.
The service refuses unsafe targets such as the filesystem root, the user home directory, the repository root, the current working directory, current-working-directory parents, non-directory data-dir paths, external SQLite paths that are directories, and symlinks that would escape the app-owned data directory.

## Data Model Impact

No schema changes are required.
The operation clears the local SQLite file and derived artifacts rather than issuing row-level deletes.
This keeps the future `applications` and `application_events` invariant intact because all derived records are wiped together.

## Privacy And Security

The endpoint does not log secrets or email content.
The response only includes local filesystem paths derived from configured storage targets.
The wipe behavior remains local-first and never sends data to a network service.
External credential files and OS keyring entries are out of scope because concrete secret-store adapters are separate tickets.

## Verification

Add unit tests for the service behavior.
Add API tests for confirmation validation, OpenAPI visibility, and successful wipe behavior with temporary settings.
Run `uv run ruff format --check .` from `backend/`.
Run `uv run ruff check .` from `backend/`.
Run `uv run mypy` from `backend/`.
Run `uv run pytest` from `backend/`.
Run the `no-mistakes` skill after a local feature-branch commit because the tool validates committed history.
Resolve all reported issues before pushing or opening a pull request.

## Self Review

There are no placeholders or deferred implementation requirements in this design.
The design stays within JT-032 by adding only the local wipe-data API path, service behavior, docs, and tests.
The design does not conflict with the architecture spec because routes stay thin, business behavior lives in a service, and API boundaries use Pydantic DTOs.
