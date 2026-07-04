import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "frontend-ci.yml"
FRONTEND_PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
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


def test_frontend_check_generates_openapi_through_backend_uv() -> None:
    package_json = json.loads(FRONTEND_PACKAGE_JSON.read_text(encoding="utf-8"))
    scripts = package_json["scripts"]

    assert scripts["generate:openapi"] == (
        "cd ../backend && uv run python -m scripts.generate_openapi"
    )
    assert scripts["generate:api"].startswith("npm run generate:openapi && ")
    assert scripts["check:api"].startswith("npm run generate:api && ")
    assert scripts["check"].startswith("npm run check:api && ")


def test_frontend_ci_installs_backend_dependencies_for_openapi_generation() -> None:
    workflow = FRONTEND_CI_WORKFLOW.read_text(encoding="utf-8")

    assert "uses: astral-sh/setup-uv@v5" in workflow
    assert "uses: actions/setup-python@v5" in workflow
    assert (
        "- name: Install backend dependencies\n"
        "        working-directory: backend\n"
        "        run: uv sync --dev --locked"
    ) in workflow
