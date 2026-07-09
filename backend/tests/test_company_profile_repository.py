from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.db.repositories import CompanyProfileRepository

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_company_profile_repository_upserts_and_reads_profiles(tmp_path: Path) -> None:
    database_path = migrated_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        repository = CompanyProfileRepository(connection)

        repository.upsert_profile(
            normalized_company="example labs",
            display_company="Example Labs",
            company_type="startup",
            industry="Developer tools",
            source="manual",
            updated_at="2026-07-09T12:00:00+00:00",
        )
        repository.upsert_profile(
            normalized_company="example labs",
            display_company="Example Labs",
            company_type="enterprise",
            industry="Cloud infrastructure",
            source="imported",
            updated_at="2026-07-09T13:00:00+00:00",
        )

        profile = repository.get_profile("example labs")

    assert profile is not None
    assert profile.normalized_company == "example labs"
    assert profile.display_company == "Example Labs"
    assert profile.company_type == "enterprise"
    assert profile.industry == "Cloud infrastructure"
    assert profile.source == "imported"


def migrated_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "jobtracker.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path
