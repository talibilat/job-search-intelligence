# Pipeline Diagnostic

The offline pipeline diagnostic reproduces the path from synced email records to deterministic dashboard metrics without Gmail access, network access, credentials, or a real LLM call.
It uses the private-data-free fixture at `backend/tests/fixtures/synthetic/diagnostic_job_search.json`, a deterministic fake LLM provider, and a temporary migrated SQLite database.

## Run

From `backend/`, run:

```bash
uv run python -m scripts.run_pipeline_diagnostic
```

The command exits with status `0` and prints a JSON report when every stage reconciles.
The report includes counts for raw emails, retained filter candidates, classifications, applications, events, rejections, and deterministic summary metrics.

If a stage fails, the command exits with status `1` and prints the failing stage to standard error, for example:

```text
FAIL stage=applications: expected 5 rows, got 0
```

The diagnostic never reads local Gmail data or `.env`, never calls a remote provider, and deletes its temporary database when complete.

## Focused Tests

From `backend/`, run:

```bash
uv run pytest tests/test_pipeline_diagnostic.py tests/test_classification_run_api.py tests/test_metrics_summary_api.py tests/test_metrics_rates_api.py
```
