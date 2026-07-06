from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def test_filter_golden_set_eval_reports_precision_and_recall(tmp_path: Path) -> None:
    assert importlib.util.find_spec("evals.run_eval") is not None

    from evals.run_eval import evaluate_filter_golden_set

    fixture_path = tmp_path / "golden_set.jsonl"
    fixture_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": "1",
                        "case_id": "positive-001",
                        "contains_private_data": False,
                        "email": {
                            "provider": "gmail",
                            "from_addr": "recruiter@acme.example",
                            "subject": "Backend engineer role",
                            "body_text": "I found your profile and think you'd be a great fit.",
                        },
                        "expected": {
                            "is_job_related": True,
                            "category": "recruiter_outreach",
                        },
                        "rationale": "Recruiter outreach with role keyword.",
                        "expected_to_pass_filter": True,
                    }
                ),
                json.dumps(
                    {
                        "schema_version": "1",
                        "case_id": "negative-001",
                        "contains_private_data": False,
                        "email": {
                            "provider": "gmail",
                            "from_addr": "receipts@shop.example",
                            "subject": "Your order receipt",
                            "body_text": "Thanks for your purchase.",
                        },
                        "expected": {
                            "is_job_related": False,
                            "category": "other",
                        },
                        "rationale": "Non-job email.",
                        "expected_to_pass_filter": False,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    report = evaluate_filter_golden_set(fixture_path)

    assert report.total == 2
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.passed is True


def test_filter_golden_set_rejects_surprising_positive(tmp_path: Path) -> None:
    """An entry expected to pass filter but lacking signals should cause a false negative."""
    assert importlib.util.find_spec("evals.run_eval") is not None

    from evals.run_eval import evaluate_filter_golden_set

    fixture_path = tmp_path / "golden_set.jsonl"
    fixture_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "case_id": "positive-miss-001",
                "contains_private_data": False,
                "email": {
                    "provider": "gmail",
                    "from_addr": "random@unknown.example",
                    "subject": "A completely unrelated subject",
                    "body_text": "This is not about job search at all.",
                },
                "expected": {
                    "is_job_related": True,
                    "category": "other",
                },
                "rationale": "Expected to pass but has no heuristic signals.",
                "expected_to_pass_filter": True,
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_filter_golden_set(fixture_path)

    assert report.total == 1
    assert report.true_positives == 0
    assert report.false_negatives == 1
    assert report.precision == 0.0
    assert report.recall == 0.0
    assert report.passed is False
