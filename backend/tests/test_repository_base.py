from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import pytest

from app.db.repositories.base import BaseRepository


@dataclass(frozen=True)
class Widget:
    id: int
    name: str


class WidgetRepository(BaseRepository[Widget]):
    def create_table(self) -> None:
        self.execute(
            """
            CREATE TABLE widgets (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
            """,
        )

    def add(self, name: str) -> None:
        self.execute("INSERT INTO widgets (name) VALUES (?)", (name,))

    def get_by_name(self, name: str) -> Widget | None:
        row = self.execute(
            "SELECT id, name FROM widgets WHERE name = ?",
            (name,),
        ).fetchone()
        if row is None:
            return None
        return self.map_row(row)

    def map_row(self, row: sqlite3.Row) -> Widget:
        return Widget(id=row["id"], name=row["name"])


@pytest.fixture
def repository() -> WidgetRepository:
    connection = sqlite3.connect(":memory:")
    repo = WidgetRepository(connection)
    repo.create_table()
    connection.commit()
    return repo


def test_repository_maps_sqlite_rows_to_typed_objects(
    repository: WidgetRepository,
) -> None:
    repository.add("alpha")

    assert repository.get_by_name("alpha") == Widget(id=1, name="alpha")


def test_repository_transaction_commits_successful_work(
    repository: WidgetRepository,
) -> None:
    with repository.transaction():
        repository.add("committed")

    assert repository.get_by_name("committed") == Widget(id=1, name="committed")


def test_repository_transaction_rolls_back_failed_work(
    repository: WidgetRepository,
) -> None:
    with pytest.raises(RuntimeError, match="force rollback"):
        with repository.transaction():
            repository.add("rolled-back")
            raise RuntimeError("force rollback")

    assert repository.get_by_name("rolled-back") is None


def test_repository_transaction_rollback_keeps_prior_uncommitted_work(
    repository: WidgetRepository,
) -> None:
    repository.add("before-transaction")

    with pytest.raises(RuntimeError, match="force rollback"):
        with repository.transaction():
            repository.add("inside-transaction")
            raise RuntimeError("force rollback")

    assert repository.get_by_name("before-transaction") == Widget(
        id=1,
        name="before-transaction",
    )
    assert repository.get_by_name("inside-transaction") is None
