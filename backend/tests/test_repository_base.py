from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import pytest
from app.db import repositories
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

    def add_many(self, names: list[str]) -> None:
        self.execute_many(
            "INSERT INTO widgets (name) VALUES (?)",
            [(name,) for name in names],
        )

    def get_by_name(self, name: str) -> Widget | None:
        return self.fetch_one(
            "SELECT id, name FROM widgets WHERE name = ?",
            (name,),
        )

    def list_widgets(self) -> list[Widget]:
        return self.fetch_all("SELECT id, name FROM widgets ORDER BY id")

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


def test_repository_fetch_one_maps_single_row(
    repository: WidgetRepository,
) -> None:
    repository.add("alpha")

    assert repository.get_by_name("alpha") == Widget(id=1, name="alpha")


def test_repository_fetch_one_returns_none_when_no_row(
    repository: WidgetRepository,
) -> None:
    assert repository.get_by_name("missing") is None


def test_repository_fetch_all_maps_all_rows(
    repository: WidgetRepository,
) -> None:
    repository.add("alpha")
    repository.add("beta")

    assert repository.list_widgets() == [
        Widget(id=1, name="alpha"),
        Widget(id=2, name="beta"),
    ]


def test_repository_execute_many_runs_parameterized_bulk_statements(
    repository: WidgetRepository,
) -> None:
    repository.add_many(["alpha", "beta"])

    assert repository.list_widgets() == [
        Widget(id=1, name="alpha"),
        Widget(id=2, name="beta"),
    ]


def test_repository_package_exports_shared_sql_parameter_type() -> None:
    assert hasattr(repositories, "SqlParameters")


def test_repository_transaction_commits_successful_work(
    repository: WidgetRepository,
) -> None:
    with repository.transaction():
        repository.add("committed")

    assert repository.get_by_name("committed") == Widget(id=1, name="committed")


def test_repository_transaction_rolls_back_failed_work(
    repository: WidgetRepository,
) -> None:
    with pytest.raises(RuntimeError, match="force rollback"), repository.transaction():
        repository.add("rolled-back")
        raise RuntimeError("force rollback")

    assert repository.get_by_name("rolled-back") is None


def test_repository_transaction_rollback_keeps_prior_uncommitted_work(
    repository: WidgetRepository,
) -> None:
    repository.add("before-transaction")

    with pytest.raises(RuntimeError, match="force rollback"), repository.transaction():
        repository.add("inside-transaction")
        raise RuntimeError("force rollback")

    assert repository.get_by_name("before-transaction") == Widget(
        id=1,
        name="before-transaction",
    )
    assert repository.get_by_name("inside-transaction") is None


def test_repository_nested_transaction_rollback_keeps_outer_work(
    repository: WidgetRepository,
) -> None:
    with repository.transaction():
        repository.add("outer-before")

        with (
            pytest.raises(RuntimeError, match="force inner rollback"),
            repository.transaction(),
        ):
            repository.add("inner")
            raise RuntimeError("force inner rollback")

        repository.add("outer-after")

    assert repository.list_widgets() == [
        Widget(id=1, name="outer-before"),
        Widget(id=2, name="outer-after"),
    ]
