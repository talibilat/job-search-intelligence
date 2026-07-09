from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_jt_055_ticket_documentation_covers_gmail_auth_url_endpoint() -> None:
    ticket_doc = REPO_ROOT / "docs" / "tickets" / "JT-055.md"

    content = ticket_doc.read_text(encoding="utf-8")

    assert "JT-055" in content
    assert "GET /auth/gmail" in content
    assert "gmail.readonly" in content
    assert "backend/app/api/auth.py" in content
    assert "backend/app/services/gmail_auth.py" in content
    assert "backend/app/providers/email/gmail.py" in content
    assert "backend/tests/test_gmail_auth_api.py" in content
    assert "client secret" in content
