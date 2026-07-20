from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from app.config import AppSettings
from app.db.repositories._row import row_to_dict
from app.db.repositories.base import BaseRepository
from app.models.provider_config import ProviderConfigurationRecord


class ProviderConfigurationRepository(BaseRepository[ProviderConfigurationRecord]):
    """Read and replace the one local non-secret provider configuration row."""

    def fetch(self) -> ProviderConfigurationRecord | None:
        try:
            return self.fetch_one(
                """
                SELECT email_provider, llm_provider, classification_mode,
                       sync_on_open, sync_interval_seconds,
                       azure_openai_endpoint, azure_openai_api_version,
                       azure_openai_chat_deployment,
                       azure_openai_embedding_deployment,
                       ollama_base_url, ollama_chat_model,
                       ollama_embedding_model, web_search_enabled,
                       web_search_provider, tavily_base_url,
                       web_search_max_results, web_search_timeout_seconds,
                       updated_at
                FROM provider_configuration WHERE singleton_id = 1
                """
            )
        except sqlite3.OperationalError as error:
            if "no such table: provider_configuration" in str(error):
                return None
            if "no such column" in str(error) and any(
                column_name in str(error)
                for column_name in (
                    "web_search_enabled",
                    "web_search_provider",
                    "tavily_base_url",
                    "web_search_max_results",
                    "web_search_timeout_seconds",
                )
            ):
                return self._fetch_pre_tavily_record()
            raise

    def _fetch_pre_tavily_record(self) -> ProviderConfigurationRecord | None:
        row = self.execute(
            """
            SELECT email_provider, llm_provider, classification_mode,
                   sync_on_open, sync_interval_seconds,
                   azure_openai_endpoint, azure_openai_api_version,
                   azure_openai_chat_deployment,
                   azure_openai_embedding_deployment,
                   ollama_base_url, ollama_chat_model,
                   ollama_embedding_model, updated_at
            FROM provider_configuration WHERE singleton_id = 1
            """
        ).fetchone()
        if row is None:
            return None
        values = row_to_dict(row)
        values.update(
            web_search_enabled=False,
            web_search_provider="tavily",
            tavily_base_url="https://api.tavily.com",
            web_search_max_results=5,
            web_search_timeout_seconds=10,
        )
        return ProviderConfigurationRecord.model_validate(values)

    def save(self, settings: AppSettings) -> ProviderConfigurationRecord:
        updated_at = datetime.now(UTC)
        self.execute(
            """
            INSERT INTO provider_configuration (
                singleton_id, email_provider, llm_provider, classification_mode,
                sync_on_open, sync_interval_seconds, azure_openai_endpoint,
                azure_openai_api_version, azure_openai_chat_deployment,
                azure_openai_embedding_deployment, ollama_base_url,
                ollama_chat_model, ollama_embedding_model, updated_at,
                web_search_enabled, web_search_provider, tavily_base_url,
                web_search_max_results, web_search_timeout_seconds
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(singleton_id) DO UPDATE SET
                email_provider = excluded.email_provider,
                llm_provider = excluded.llm_provider,
                classification_mode = excluded.classification_mode,
                sync_on_open = excluded.sync_on_open,
                sync_interval_seconds = excluded.sync_interval_seconds,
                azure_openai_endpoint = excluded.azure_openai_endpoint,
                azure_openai_api_version = excluded.azure_openai_api_version,
                azure_openai_chat_deployment = excluded.azure_openai_chat_deployment,
                azure_openai_embedding_deployment = excluded.azure_openai_embedding_deployment,
                ollama_base_url = excluded.ollama_base_url,
                ollama_chat_model = excluded.ollama_chat_model,
                ollama_embedding_model = excluded.ollama_embedding_model,
                web_search_enabled = excluded.web_search_enabled,
                web_search_provider = excluded.web_search_provider,
                tavily_base_url = excluded.tavily_base_url,
                web_search_max_results = excluded.web_search_max_results,
                web_search_timeout_seconds = excluded.web_search_timeout_seconds,
                updated_at = excluded.updated_at
            """,
            (
                settings.email_provider.value,
                settings.llm_provider.value,
                settings.classification_mode.value,
                int(settings.sync_on_open),
                settings.sync_interval_seconds,
                settings.azure_openai_endpoint,
                settings.azure_openai_api_version,
                settings.azure_openai_chat_deployment,
                settings.azure_openai_embedding_deployment,
                settings.ollama_base_url,
                settings.ollama_chat_model,
                settings.ollama_embedding_model,
                updated_at.isoformat(),
                int(settings.web_search_enabled),
                settings.web_search_provider.value,
                settings.tavily_base_url,
                settings.web_search_max_results,
                settings.web_search_timeout_seconds,
            ),
        )
        self.connection.commit()
        record = self.fetch()
        if record is None:
            raise RuntimeError("provider configuration could not be read back")
        return record

    def map_row(self, row: sqlite3.Row) -> ProviderConfigurationRecord:
        return ProviderConfigurationRecord.model_validate(row_to_dict(row))
