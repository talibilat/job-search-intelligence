from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_jt_051_ticket_documentation_covers_google_oauth_setup() -> None:
    ticket_doc = REPO_ROOT / "docs" / "tickets" / "JT-051.md"

    content = ticket_doc.read_text(encoding="utf-8")

    assert "JT-051" in content
    assert "Google OAuth Setup Guide" in content
    assert "user-created" in content
    assert "Desktop" in content
    assert "gmail.readonly" in content
    assert "SecretStore" in content
    assert "docs/google-oauth-setup.md" in content
