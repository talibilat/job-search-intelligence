from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

CommaSeparatedTuple = Annotated[tuple[str, ...], NoDecode]
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
LOCAL_SQLITE_SCHEMES = {"sqlite", "sqlite+aiosqlite"}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = REPOSITORY_ROOT / "jobtracker.sqlite3"
DEFAULT_DATABASE_URL = f"sqlite+aiosqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"


def normalize_azure_openai_endpoint(endpoint: str) -> str:
    """Accept a pasted Azure operation URL but use its resource endpoint only."""

    value = endpoint.strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Azure OpenAI endpoint must be an absolute HTTPS resource URL.")
    return f"{parsed.scheme}://{parsed.netloc}"


class RuntimeEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SecretStoreBackend(StrEnum):
    KEYRING = "keyring"
    FERNET = "fernet"


class EmailProviderName(StrEnum):
    GMAIL = "gmail"


class LLMProviderName(StrEnum):
    AZURE_OPENAI = "azure_openai"
    OLLAMA = "ollama"


class ClassificationMode(StrEnum):
    HYBRID = "hybrid"
    LLM = "llm"
    LOCAL = "local"


class AppSettings(BaseSettings):
    """Typed operational settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="JOBTRACKER_",
        extra="ignore",
    )

    env: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: CommaSeparatedTuple = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    frontend_url: str = "http://127.0.0.1:5173"
    log_level: LogLevel = LogLevel.INFO

    data_dir: Path = Path("./.jobtracker")
    database_url: str = DEFAULT_DATABASE_URL
    sqlite_vec_extension_path: Path | None = None

    secret_store_backend: SecretStoreBackend = SecretStoreBackend.KEYRING
    fernet_key_file: Path = Path("./.jobtracker/fernet.key")

    email_provider: EmailProviderName = EmailProviderName.GMAIL
    llm_provider: LLMProviderName = LLMProviderName.OLLAMA
    classification_mode: ClassificationMode = ClassificationMode.LOCAL

    gmail_client_config_file: Path = Path("~/.config/jobtracker/google-oauth-client.json")
    gmail_scopes: CommaSeparatedTuple = (GMAIL_READONLY_SCOPE,)
    sync_on_open: bool = True
    sync_interval_seconds: int = Field(default=900, ge=1)
    gmail_page_size: int = Field(default=500, ge=1)
    backfill_batch_size: int = Field(default=1000, ge=1)
    retain_debug_email_bodies: bool = False

    classification_batch_size: int = Field(default=25, ge=1)
    classification_concurrency: int = Field(default=5, ge=1, le=25)
    processing_max_candidates_per_run: int = Field(default=500, ge=1, le=10_000)
    classification_prompt_version: str = Field(default="v2", min_length=1)
    classification_estimate_chars_per_unit: int = Field(default=4, ge=1)
    classification_estimate_prompt_overhead_units: int = Field(default=300, ge=0)
    classification_estimate_completion_units_per_candidate: int = Field(default=500, ge=0)
    classification_input_cost_per_1k_units_usd: float = Field(default=0.0, ge=0)
    classification_output_cost_per_1k_units_usd: float = Field(default=0.0, ge=0)
    insight_estimate_chars_per_unit: int = Field(default=4, ge=1)
    insight_input_cost_per_1k_units_usd: float = Field(default=0.0, ge=0)
    insight_output_cost_per_1k_units_usd: float = Field(default=0.0, ge=0)
    chat_index_max_emails: int = Field(default=1000, ge=1, le=100_000)
    llm_timeout_seconds: int = Field(default=60, ge=1)
    llm_max_retries: int = Field(default=2, ge=0)

    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = Field(default="2024-06-01", min_length=1)
    azure_openai_chat_deployment: str = ""
    azure_openai_embedding_deployment: str = ""

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = Field(default="llama3.1", min_length=1)
    ollama_embedding_model: str = Field(default="nomic-embed-text", min_length=1)

    ghost_threshold_days: int = Field(default=30, ge=1)
    follow_up_threshold_days: int = Field(default=7, ge=1)

    def __init__(self, *, _env_file: str | Path | None = ".env", **values: Any) -> None:
        super().__init__(_env_file=_env_file, **values)

    @classmethod
    def env_var_names(cls) -> set[str]:
        return {f"JOBTRACKER_{field_name.upper()}" for field_name in cls.model_fields}

    @field_validator("cors_origins", "gmail_scopes", mode="before")
    @classmethod
    def parse_comma_separated_tuple(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())

        if isinstance(value, list | tuple | set):
            return tuple(str(part).strip() for part in value if str(part).strip())

        return value

    @field_validator("database_url")
    @classmethod
    def validate_local_sqlite_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in LOCAL_SQLITE_SCHEMES
            or parsed.netloc
            or parsed.path in {"", "/", "/:memory:"}
        ):
            raise ValueError("database_url must use a file-backed local SQLite URL")

        return value

    @field_validator("gmail_scopes")
    @classmethod
    def validate_gmail_readonly_scope(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != (GMAIL_READONLY_SCOPE,):
            raise ValueError("gmail_scopes must only include gmail.readonly in v1")

        return value

    @field_validator("sqlite_vec_extension_path", mode="before")
    @classmethod
    def parse_optional_path(cls, value: object) -> object:
        if value == "":
            return None

        return value

    @field_validator(
        "data_dir",
        "fernet_key_file",
        "gmail_client_config_file",
        "sqlite_vec_extension_path",
    )
    @classmethod
    def expand_user_paths(cls, value: Path | None) -> Path | None:
        if value is None:
            return None

        return value.expanduser()


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
