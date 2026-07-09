from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_jt_054_ticket_documentation_covers_playwright_smoke_harness() -> None:
    ticket_doc = REPO_ROOT / "docs" / "tickets" / "JT-054.md"

    content = ticket_doc.read_text(encoding="utf-8")

    assert "JT-054" in content
    assert "Playwright" in content
    assert "frontend/playwright.config.ts" in content
    assert "frontend/tests/smoke/phase0-shell.pw.ts" in content
    assert "npm run test:smoke" in content
    assert "setup" in content
    assert "sync" in content
    assert "dashboard" in content
