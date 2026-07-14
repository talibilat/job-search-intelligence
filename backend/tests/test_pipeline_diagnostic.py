from __future__ import annotations

import asyncio
import json
from pathlib import Path

from scripts.run_pipeline_diagnostic import (
    DEFAULT_FIXTURE_PATH,
    PipelineDiagnosticError,
    main,
    run_pipeline_diagnostic,
)


def test_pipeline_diagnostic_proves_email_to_metrics_path(tmp_path: Path) -> None:
    report = asyncio.run(
        run_pipeline_diagnostic(
            database_path=tmp_path / "jobtracker.sqlite3",
        )
    )

    assert report.status == "passed"
    assert [(stage.name, stage.count) for stage in report.stages] == [
        ("raw_emails", 10),
        ("retained_candidates", 9),
        ("classifications", 9),
        ("applications", 5),
        ("application_events", 10),
        ("rejections", 1),
    ]
    assert report.metrics.model_dump() == {
        "total_applications": 5,
        "rejected_applications": 1,
        "ghosted_applications": 1,
        "interview_invitations": 1,
        "offers_received": 1,
        "human_responses": 3,
        "silent_applications": 2,
    }


def test_pipeline_diagnostic_command_prints_report(capsys: object) -> None:
    assert main([]) == 0

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    report = json.loads(captured.out)
    assert report["status"] == "passed"
    assert report["metrics"]["rejected_applications"] == 1


def test_pipeline_diagnostic_identifies_failed_stage(
    tmp_path: Path,
    capsys: object,
) -> None:
    fixture = json.loads(DEFAULT_FIXTURE_PATH.read_text())
    fixture["classifications"] = fixture["classifications"][:-1]
    broken_fixture_path = tmp_path / "broken-fixture.json"
    broken_fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture", str(broken_fixture_path)]) == 1

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == ""
    assert "FAIL stage=retained_candidates" in captured.err


def test_pipeline_diagnostic_error_names_stage() -> None:
    error = PipelineDiagnosticError(stage="applications", detail="expected 5 rows, got 0")

    assert str(error) == ("pipeline diagnostic failed at applications: expected 5 rows, got 0")
