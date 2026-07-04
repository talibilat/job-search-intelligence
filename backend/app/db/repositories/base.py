from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Generic, TypeVar

MappedRowT = TypeVar("MappedRowT")
SqlParameters = Sequence[object] | Mapping[str, object]


class BaseRepository(ABC, Generic[MappedRowT]):
    """Shared SQLite repository conventions for transactions and row mapping."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def execute(
        self,
        sql: str,
        parameters: SqlParameters = (),
    ) -> sqlite3.Cursor:
        return self._connection.execute(sql, parameters)

    def fetch_one(
        self,
        sql: str,
        parameters: SqlParameters = (),
    ) -> MappedRowT | None:
        row = self.execute(sql, parameters).fetchone()
        if row is None:
            return None
        return self.map_row(row)

    def fetch_all(
        self,
        sql: str,
        parameters: SqlParameters = (),
    ) -> list[MappedRowT]:
        return [self.map_row(row) for row in self.execute(sql, parameters).fetchall()]

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self._connection.execute("SAVEPOINT repository_transaction")
        try:
            yield
        except Exception:
            self._connection.execute("ROLLBACK TO SAVEPOINT repository_transaction")
            self._connection.execute("RELEASE SAVEPOINT repository_transaction")
            raise
        self._connection.execute("RELEASE SAVEPOINT repository_transaction")

    @abstractmethod
    def map_row(self, row: sqlite3.Row) -> MappedRowT:
        """Map a SQLite row into the repository's typed domain object."""
