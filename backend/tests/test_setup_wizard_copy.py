from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COPY_PATH = REPO_ROOT / "frontend" / "src" / "setupWizardCopy.ts"


def test_setup_wizard_copy_covers_required_first_run_choices() -> None:
    copy = COPY_PATH.read_text(encoding="utf-8")

    assert "Choose your LLM provider" in copy
    assert "Azure OpenAI" in copy
    assert "Ollama" in copy
    assert "Pick a classification mode" in copy
    assert "hybrid" in copy
    assert "llm" in copy
    assert "local" in copy
    assert "Connect Gmail read-only" in copy
    assert "gmail.readonly" in copy
    assert "Confirm privacy boundaries" in copy
    assert "No shared credentials" in copy
    assert "SecretStore" in copy
