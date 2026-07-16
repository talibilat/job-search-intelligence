from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.sync import (
    EmailSyncConnectionResolver,
    EmailSyncStatusStore,
    get_email_sync_connection_resolver,
    get_sync_status_store,
)
from app.config import AppSettings, get_settings
from app.db.repositories.connection import EmailConnectionRepository
from app.db.repositories.email import EmailRepository
from app.db.repositories.pipeline_status import PipelineStatusRepository
from app.db.sqlite_url import sqlite_database_path
from app.models.pipeline import PipelineStatus
from app.services.pipeline_status import build_pipeline_status

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def get_readonly_pipeline_status_repository(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[PipelineStatusRepository]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield PipelineStatusRepository(connection)
    finally:
        connection.close()


@router.get(
    "/status",
    response_model=PipelineStatus,
    summary="Get Pipeline Status",
    description=(
        "Returns one deterministic overview of the local ingest, filter, classify, "
        "and aggregate pipeline plus the next action, without email content or secrets."
    ),
)
def pipeline_status(
    settings: Annotated[AppSettings, Depends(get_settings)],
    pipeline_status_repository: Annotated[
        PipelineStatusRepository,
        Depends(get_readonly_pipeline_status_repository),
    ],
    connection_resolver: Annotated[
        EmailSyncConnectionResolver,
        Depends(get_email_sync_connection_resolver),
    ],
    status_store: Annotated[EmailSyncStatusStore, Depends(get_sync_status_store)],
) -> PipelineStatus:
    connection = connection_resolver()
    if connection is None:
        connection = next(
            (
                item
                for item in EmailConnectionRepository(
                    pipeline_status_repository.connection
                ).list_connections_metadata()
                if item.account.provider is settings.email_provider
            ),
            None,
        )
    return build_pipeline_status(
        settings=settings,
        pipeline_status_repository=pipeline_status_repository,
        email_repository=EmailRepository(pipeline_status_repository.connection),
        connection=connection,
        sync_status=status_store.current_status(),
    )
