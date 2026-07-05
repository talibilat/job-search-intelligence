from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def test_golden_set_eval_reports_precision_and_recall(tmp_path: Path) -> None:
    assert importlib.util.find_spec("evals.run_eval") is not None

    from evals.run_eval import evaluate_golden_set

    fixture_path = tmp_path / "golden_set.jsonl"
    fixture_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "email_id": "email-1",
                        "expected_is_job_related": True,
                        "llm_response": {
                            "content": json.dumps(
                                {
                                    "is_job_related": True,
                                    "category": "application_confirmation",
                                    "confidence": 0.96,
                                }
                            ),
                            "model": "synthetic-eval",
                            "finish_reason": "stop",
                        },
                    }
                ),
                json.dumps(
                    {
                        "email_id": "email-2",
                        "expected_is_job_related": False,
                        "llm_response": {
                            "content": json.dumps(
                                {
                                    "is_job_related": False,
                                    "category": "other",
                                    "confidence": 0.91,
                                }
                            ),
                            "model": "synthetic-eval",
                            "finish_reason": "stop",
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    report = evaluate_golden_set(fixture_path)

    assert report.total == 2
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.passed is True
