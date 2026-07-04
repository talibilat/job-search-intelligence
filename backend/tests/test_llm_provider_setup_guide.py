from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE_PATH = REPO_ROOT / "docs" / "llm-provider-setup.md"


def test_llm_provider_setup_guide_covers_phase_zero_provider_paths() -> None:
    guide = GUIDE_PATH.read_text(encoding="utf-8")

    assert "# LLM Provider Setup Guide" in guide
    assert "## Azure OpenAI" in guide
    assert "## Ollama" in guide
    assert "classification_mode" in guide
    assert "every ingested email" in guide
    assert "SecretStore" in guide
    assert "JOBTRACKER_SECRET_STORE_BACKEND=keyring" in guide
    assert "JOBTRACKER_SECRET_STORE_BACKEND=fernet" in guide
    assert "JOBTRACKER_FERNET_KEY_FILE" in guide
    assert "No shared or bundled credentials" in guide
