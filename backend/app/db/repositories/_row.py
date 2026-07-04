from __future__ import annotations

import sqlite3
from typing import cast


def row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    keys = row.keys()
    return {key: cast(object, row[key]) for key in keys}
