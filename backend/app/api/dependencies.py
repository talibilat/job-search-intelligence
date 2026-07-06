from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends

from app.api.errors import ApiError, ApiErrorCode
from app.config import AppSettings, LLMProviderName, get_settings
from app.db.repositories.classification_run import ClassificationRunRepository
from app.db.repositories.connection import EmailConnectionRepository
from app.db.repositories.email import EmailRepository
from app.db.sqlite_url import sqlite_database_path
from app.providers.llm import LLMProvider, LLMProviderUnavailableError, OllamaLLMProvider
from app.services.structured_extraction import StructuredExtractionService


def get_email_connection_repository(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[EmailConnectionRepository]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        yield EmailConnectionRepository(connection)
    finally:
        connection.close()


def get_llm_provider(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> LLMProvider:
    if settings.llm_provider is LLMProviderName.OLLAMA:
        try:
            return OllamaLLMProvider(settings=settings)
        except LLMProviderUnavailableError as error:
            raise ApiError(
                status_code=400,
                code=ApiErrorCode.BAD_REQUEST,
                message=error.public_message,
            ) from error

    raise ApiError(
        status_code=503,
        code=ApiErrorCode.SERVICE_UNAVAILABLE,
        message="Selected LLM provider is unavailable.",
    )


def get_writable_email_repository(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[EmailRepository]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        yield EmailRepository(connection)
    finally:
        connection.close()


def get_classification_run_repository(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[ClassificationRunRepository]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        yield ClassificationRunRepository(connection)
    finally:
        connection.close()


def get_structured_extraction_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_repository: Annotated[
        EmailRepository,
        Depends(get_writable_email_repository),
    ],
    classification_run_repository: Annotated[
        ClassificationRunRepository,
        Depends(get_classification_run_repository),
    ],
    llm_provider: Annotated[
        LLMProvider,
        Depends(get_llm_provider),
    ],
) -> StructuredExtractionService:
    return StructuredExtractionService(
        settings=settings,
        email_repository=email_repository,
        classification_run_repository=classification_run_repository,
        llm_provider=llm_provider,
    )


def get_readonly_email_repository(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[EmailRepository]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield EmailRepository(connection)
    finally:
        connection.close()
