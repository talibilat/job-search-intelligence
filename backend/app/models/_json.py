from __future__ import annotations

import json
from typing import cast


def parse_json_column(value: object) -> object:
    if isinstance(value, str):
        return cast(object, json.loads(value))
    return value
