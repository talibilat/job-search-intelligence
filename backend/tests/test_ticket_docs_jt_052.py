from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_jt_052_ticket_documentation_covers_llm_provider_setup() -> None:
    ticket_doc = REPO_ROOT / "docs" / "tickets" / "JT-052.md"

    content = ticket_doc.read_text(encoding="utf-8")

    assert "JT-052" in content
    assert "LLM Provider Setup Guide" in content
    assert "Azure OpenAI" in content
    assert "Ollama" in content
    assert "SecretStore" in content
    assert "classification_mode" in content
    assert "docs/llm-provider-setup.md" in content
