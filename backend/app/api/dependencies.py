from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends

from app.agent.tools import SemanticSearchTool, StructuredQueryTool
from app.api.errors import ApiError, ApiErrorCode
from app.config import AppSettings, LLMProviderName, get_settings
from app.db.engine import load_sqlite_vec_sync, verify_sqlite_vec
from app.db.repositories import (
    ApplicationRepository,
    ChatRepository,
    CorrectionConflictRepository,
    CorrectionRepository,
    EmailChunkRepository,
    EventRepository,
    InsightRepository,
    MetricsRepository,
    ProviderConfigurationRepository,
)
from app.db.repositories.classification_run import ClassificationRunRepository
from app.db.repositories.connection import EmailConnectionRepository
from app.db.repositories.email import EmailRepository
from app.db.sqlite_url import sqlite_database_path
from app.providers import provider_registry
from app.providers.llm import LLMProvider, LLMProviderUnavailableError, OllamaLLMProvider
from app.providers.llm.azure_openai import AzureOpenAIProvider
from app.security import SecretRef, SecretStore, create_secret_store
from app.services.aggregation import AggregationService
from app.services.application_corrections import ApplicationCorrectionService
from app.services.applications import (
    ApplicationCorrectionConflictService,
    ApplicationCorrectionHistoryService,
    ApplicationDetailService,
    ApplicationEventsService,
)
from app.services.chat_history import ChatHistoryService
from app.services.chat_index import ChatIndexService
from app.services.chat_service import ChatService
from app.services.diagnostics import DiagnosticsService
from app.services.ghost_inference import GhostInferenceService
from app.services.insights_service import InsightGenerationService, InsightReadService
from app.services.manual_edit import ManualApplicationEditService
from app.services.manual_merge import ManualApplicationMergeService
from app.services.metrics import (
    MetricsBreakdownService,
    MetricsFunnelService,
    MetricsRatesService,
    MetricsResponseRateTrendService,
    MetricsSummaryService,
    MetricsTimeseriesService,
)
from app.services.processing import ProcessingOrchestrationService
from app.services.readiness import ProviderReadinessService
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


def get_provider_configuration_repository(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[ProviderConfigurationRepository]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        yield ProviderConfigurationRepository(connection)
    finally:
        connection.close()


def get_email_connection_secret_refs(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> list[SecretRef]:
    """Read connection credential refs and close SQLite before destructive work."""

    database_path = sqlite_database_path(settings.database_url)
    if not database_path.is_file():
        return []
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        repository = EmailConnectionRepository(connection)
        return [item.credential_ref for item in repository.list_connections_metadata()]
    finally:
        connection.close()


def get_llm_secret_store(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> SecretStore:
    return create_secret_store(settings)


def get_llm_provider(
    settings: Annotated[AppSettings, Depends(get_settings)],
    secret_store: Annotated[SecretStore, Depends(get_llm_secret_store)],
) -> LLMProvider:
    if settings.llm_provider is LLMProviderName.AZURE_OPENAI:
        return AzureOpenAIProvider(settings=settings, secret_store=secret_store)

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
        code=ApiErrorCode.LLM_PROVIDER_UNAVAILABLE,
        message="The selected LLM provider is unavailable.",
    )


def get_provider_readiness_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
    connection_repository: Annotated[
        EmailConnectionRepository,
        Depends(get_email_connection_repository),
    ],
    secret_store: Annotated[SecretStore, Depends(get_llm_secret_store)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> ProviderReadinessService:
    return ProviderReadinessService(
        settings=settings,
        registry=provider_registry,
        connection_reader=connection_repository,
        secret_store=secret_store,
        llm_provider=llm_provider,
    )


def get_insight_repository(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[InsightRepository]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        yield InsightRepository(connection)
    finally:
        connection.close()


def get_chat_history_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[ChatHistoryService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield ChatHistoryService(ChatRepository(connection))
    finally:
        connection.close()


def get_chat_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> Iterator[ChatService]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    load_sqlite_vec_sync(connection, settings.sqlite_vec_extension_path)
    verify_sqlite_vec(connection)
    try:
        email_repository = EmailRepository(connection)
        chunk_repository = EmailChunkRepository(connection)
        embedding_model = (
            settings.azure_openai_embedding_deployment
            if settings.llm_provider is LLMProviderName.AZURE_OPENAI
            else settings.ollama_embedding_model
        )
        yield ChatService(
            history_repository=ChatRepository(connection),
            index_service=ChatIndexService(
                email_repository=email_repository,
                chunk_repository=chunk_repository,
                llm_provider=llm_provider,
                embedding_model=embedding_model,
                max_emails=settings.chat_index_max_emails,
            ),
            structured_query=StructuredQueryTool(
                metrics_repository=MetricsRepository(connection),
                application_reader=ApplicationRepository(connection),
                ghost_threshold_days=settings.ghost_threshold_days,
            ),
            semantic_search=SemanticSearchTool(
                repository=chunk_repository,
                llm_provider=llm_provider,
                embedding_model=embedding_model,
            ),
        )
    finally:
        connection.close()


def get_insight_generation_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
    insight_repository: Annotated[
        InsightRepository,
        Depends(get_insight_repository),
    ],
    llm_provider: Annotated[
        LLMProvider,
        Depends(get_llm_provider),
    ],
) -> InsightGenerationService:
    return InsightGenerationService(
        settings=settings,
        insight_repository=insight_repository,
        llm_provider=llm_provider,
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


def get_aggregation_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[AggregationService]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        yield AggregationService(
            application_repository=ApplicationRepository(connection),
            event_repository=EventRepository(connection),
            email_repository=EmailRepository(connection),
            correction_conflict_repository=CorrectionConflictRepository(connection),
        )
    finally:
        connection.close()


def get_readonly_application_repository(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[ApplicationRepository]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield ApplicationRepository(connection)
    finally:
        connection.close()


def get_application_detail_service(
    application_repository: Annotated[
        ApplicationRepository,
        Depends(get_readonly_application_repository),
    ],
) -> ApplicationDetailService:
    return ApplicationDetailService(application_repository)


def get_application_events_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[ApplicationEventsService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield ApplicationEventsService(
            application_repository=ApplicationRepository(connection),
            event_repository=EventRepository(connection),
        )
    finally:
        connection.close()


def get_application_correction_conflict_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[ApplicationCorrectionConflictService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield ApplicationCorrectionConflictService(
            application_repository=ApplicationRepository(connection),
            conflict_repository=CorrectionConflictRepository(connection),
        )
    finally:
        connection.close()


def get_ghost_inference_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[GhostInferenceService]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield GhostInferenceService(
            application_repository=ApplicationRepository(connection),
            event_repository=EventRepository(connection),
            threshold_days=settings.ghost_threshold_days,
        )
    finally:
        connection.close()


def get_processing_orchestration_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
    email_repository: Annotated[EmailRepository, Depends(get_writable_email_repository)],
    extraction_service: Annotated[
        StructuredExtractionService,
        Depends(get_structured_extraction_service),
    ],
    aggregation_service: Annotated[AggregationService, Depends(get_aggregation_service)],
    ghost_inference_service: Annotated[
        GhostInferenceService,
        Depends(get_ghost_inference_service),
    ],
) -> ProcessingOrchestrationService:
    return ProcessingOrchestrationService(
        settings=settings,
        email_repository=email_repository,
        extraction_service=extraction_service,
        aggregation_service=aggregation_service,
        ghost_inference_service=ghost_inference_service,
    )


def get_metrics_summary_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[MetricsSummaryService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield MetricsSummaryService(
            metrics_repository=MetricsRepository(connection),
            ghost_threshold_days=settings.ghost_threshold_days,
        )
    finally:
        connection.close()


def get_metrics_rates_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[MetricsRatesService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield MetricsRatesService(
            metrics_repository=MetricsRepository(connection),
            ghost_threshold_days=settings.ghost_threshold_days,
        )
    finally:
        connection.close()


def get_metrics_timeseries_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[MetricsTimeseriesService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield MetricsTimeseriesService(metrics_repository=MetricsRepository(connection))
    finally:
        connection.close()


def get_metrics_response_rate_trend_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[MetricsResponseRateTrendService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield MetricsResponseRateTrendService(metrics_repository=MetricsRepository(connection))
    finally:
        connection.close()


def get_metrics_funnel_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[MetricsFunnelService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield MetricsFunnelService(metrics_repository=MetricsRepository(connection))
    finally:
        connection.close()


def get_metrics_breakdown_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[MetricsBreakdownService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield MetricsBreakdownService(metrics_repository=MetricsRepository(connection))
    finally:
        connection.close()


def get_metrics_diagnostics_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[DiagnosticsService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield DiagnosticsService(metrics_repository=MetricsRepository(connection))
    finally:
        connection.close()


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


def get_manual_merge_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[ManualApplicationMergeService]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield ManualApplicationMergeService(
            application_repository=ApplicationRepository(connection),
            event_repository=EventRepository(connection),
            correction_repository=CorrectionRepository(connection),
        )
    finally:
        connection.close()


def get_manual_edit_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[ManualApplicationEditService]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        yield ManualApplicationEditService(
            application_repository=ApplicationRepository(connection),
            event_repository=EventRepository(connection),
            correction_repository=CorrectionRepository(connection),
        )
    finally:
        connection.close()


def get_application_correction_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[ApplicationCorrectionService]:
    database_path = sqlite_database_path(settings.database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield ApplicationCorrectionService(
            application_repository=ApplicationRepository(connection),
            event_repository=EventRepository(connection),
            correction_repository=CorrectionRepository(connection),
        )
    finally:
        connection.close()


def get_application_correction_history_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[ApplicationCorrectionHistoryService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield ApplicationCorrectionHistoryService(
            application_repository=ApplicationRepository(connection),
            correction_repository=CorrectionRepository(connection),
        )
    finally:
        connection.close()


def get_insight_read_service(
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> Iterator[InsightReadService]:
    database_path = sqlite_database_path(settings.database_url)
    connection_target = str(database_path) if database_path.exists() else ":memory:"
    connection = sqlite3.connect(connection_target, check_same_thread=False)
    try:
        yield InsightReadService(
            settings=settings,
            insight_repository=InsightRepository(connection),
        )
    finally:
        connection.close()
