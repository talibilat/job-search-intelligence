from __future__ import annotations

import subprocess
import sys


def test_classification_golden_eval_runs_and_reports_precision_recall() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "evals.run_eval"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "precision:" in result.stdout
    assert "recall:" in result.stdout
    assert "pass:" in result.stdout
