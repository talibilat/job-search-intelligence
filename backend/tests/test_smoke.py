from pathlib import Path

import pytest


@pytest.mark.smoke
def test_backend_scaffold_is_available() -> None:
    backend_root = Path(__file__).resolve().parents[1]

    assert (backend_root / "app").is_dir()
    assert (backend_root / "tests").is_dir()
