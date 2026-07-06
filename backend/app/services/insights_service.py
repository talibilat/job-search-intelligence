from __future__ import annotations

import hashlib
import json

from app.db.repositories import InsightRepository
from app.models import InsightInput
from app.models.records import InsightType


class InsightInputBuilder:
    """Build deterministic, cited input packages for narrative insight synthesis."""

    def __init__(self, insight_repository: InsightRepository) -> None:
        self._insight_repository = insight_repository

    def build(
        self,
        insight_type: InsightType,
        *,
        max_evidence_items: int = 100,
    ) -> InsightInput:
        if max_evidence_items < 1:
            msg = "max_evidence_items must be at least 1"
            raise ValueError(msg)

        insight_input = InsightInput(
            type=insight_type,
            facts=self._insight_repository.list_input_facts(),
            evidence=self._insight_repository.list_input_evidence(
                insight_type=insight_type,
                limit=max_evidence_items,
            ),
            inputs_hash="",
        )
        return insight_input.model_copy(
            update={"inputs_hash": _hash_insight_input(insight_input)},
        )


def _hash_insight_input(insight_input: InsightInput) -> str:
    payload = insight_input.model_dump(mode="json", exclude={"inputs_hash"})
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
