from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import AppSettings, get_settings
from app.db.repositories import EmailRepository
from app.db.sqlite_url import sqlite_database_path
from app.models import ClassificationPreRunEstimate
from app.services.classification_estimate import build_classification_pre_run_estimate

router = APIRouter(prefix="/classification", tags=["classification"])


def get_classification_email_repository(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[EmailRepository]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        yield EmailRepository(connection)
    finally:
        connection.close()


@router.get("/estimate", response_model=ClassificationPreRunEstimate)
def classification_estimate(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_repository: Annotated[
        EmailRepository,
        Depends(get_classification_email_repository),
    ],
) -> ClassificationPreRunEstimate:
    return build_classification_pre_run_estimate(
        settings=settings,
        email_repository=email_repository,
    )
