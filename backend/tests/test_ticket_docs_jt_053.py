from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_jt_053_ticket_documentation_covers_setup_wizard_copy() -> None:
    ticket_doc = REPO_ROOT / "docs" / "tickets" / "JT-053.md"

    content = ticket_doc.read_text(encoding="utf-8")

    assert "JT-053" in content
    assert "setup wizard copy" in content
    assert "frontend/src/setupWizardCopy.ts" in content
    assert "frontend/src/pages/SetupPage.tsx" in content
    assert "Azure OpenAI" in content
    assert "Ollama" in content
    assert "gmail.readonly" in content
    assert "SecretStore" in content
