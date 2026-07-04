import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "frontend-ci.yml"
FRONTEND_PACKAGE_LOCK = REPO_ROOT / "frontend" / "package-lock.json"


def test_frontend_package_lock_is_valid_json() -> None:
    json.loads(FRONTEND_PACKAGE_LOCK.read_text(encoding="utf-8"))


def test_frontend_ci_uses_nested_frontend_package_lockfile() -> None:
    workflow = FRONTEND_CI_WORKFLOW.read_text(encoding="utf-8")

    assert "cache-dependency-path: frontend/package-lock.json" in workflow
    assert (
        "- name: Install dependencies\n        working-directory: frontend\n        run: npm ci"
    ) in workflow
    assert (
        "- name: Check frontend\n        working-directory: frontend\n        run: npm run check"
    ) in workflow
