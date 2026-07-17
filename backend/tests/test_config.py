from __future__ import annotations

from pathlib import Path

import pytest
from app.config import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_DATABASE_URL,
    AppSettings,
    ClassificationMode,
    EmailProviderName,
    LLMProviderName,
    RuntimeEnvironment,
    SecretStoreBackend,
)
from pydantic import ValidationError


def clear_jobtracker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in AppSettings.env_var_names():
        monkeypatch.delenv(env_name, raising=False)


def parse_env_example() -> set[str]:
    backend_root = Path(__file__).resolve().parents[1]
    env_names: set[str] = set()

    for raw_line in (backend_root / ".env.example").read_text().splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            env_names.add(line.split("=", 1)[0])

    return env_names


def test_settings_defaults_match_phase_zero_config_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)

    settings = AppSettings(_env_file=None)

    assert settings.env is RuntimeEnvironment.DEVELOPMENT
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.cors_origins == (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    assert settings.data_dir == Path("./.jobtracker")
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert Path(__file__).resolve().parents[2] / "jobtracker.sqlite3" == DEFAULT_DATABASE_PATH
    assert settings.sqlite_vec_extension_path is None
    assert settings.secret_store_backend is SecretStoreBackend.KEYRING
    assert settings.email_provider is EmailProviderName.GMAIL
    assert settings.llm_provider is LLMProviderName.OLLAMA
    assert settings.classification_mode is ClassificationMode.LOCAL
    assert settings.classification_estimate_chars_per_unit == 4
    assert settings.classification_estimate_prompt_overhead_units == 300
    assert settings.classification_estimate_completion_units_per_candidate == 500
    assert settings.classification_input_cost_per_1k_units_usd == 0.0
    assert settings.classification_output_cost_per_1k_units_usd == 0.0
    assert settings.gmail_scopes == ("https://www.googleapis.com/auth/gmail.readonly",)
    assert settings.gmail_client_config_file == (
        Path.home() / ".config/jobtracker/google-oauth-client.json"
    )
    assert settings.sync_on_open is True
    assert settings.ghost_threshold_days == 30
    assert settings.follow_up_threshold_days == 7


def test_settings_load_env_file_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "JOBTRACKER_ENV=test",
                "JOBTRACKER_API_HOST=0.0.0.0",
                "JOBTRACKER_API_PORT=8123",
                "JOBTRACKER_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000",
                "JOBTRACKER_SECRET_STORE_BACKEND=fernet",
                "JOBTRACKER_LLM_PROVIDER=azure_openai",
                "JOBTRACKER_CLASSIFICATION_MODE=hybrid",
                "JOBTRACKER_CLASSIFICATION_ESTIMATE_CHARS_PER_UNIT=3",
                "JOBTRACKER_CLASSIFICATION_ESTIMATE_PROMPT_OVERHEAD_UNITS=250",
                "JOBTRACKER_CLASSIFICATION_ESTIMATE_COMPLETION_UNITS_PER_CANDIDATE=450",
                "JOBTRACKER_CLASSIFICATION_INPUT_COST_PER_1K_UNITS_USD=0.0025",
                "JOBTRACKER_CLASSIFICATION_OUTPUT_COST_PER_1K_UNITS_USD=0.01",
                "JOBTRACKER_SYNC_ON_OPEN=false",
                "JOBTRACKER_GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly",
                "JOBTRACKER_SQLITE_VEC_EXTENSION_PATH=/usr/local/lib/sqlite_vec.dylib",
                "JOBTRACKER_GHOST_THRESHOLD_DAYS=45",
                "JOBTRACKER_FOLLOW_UP_THRESHOLD_DAYS=10",
            ]
        )
    )

    settings = AppSettings(_env_file=env_file)

    assert settings.env is RuntimeEnvironment.TEST
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8123
    assert settings.cors_origins == (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
    assert settings.secret_store_backend is SecretStoreBackend.FERNET
    assert settings.llm_provider is LLMProviderName.AZURE_OPENAI
    assert settings.classification_mode is ClassificationMode.HYBRID
    assert settings.classification_estimate_chars_per_unit == 3
    assert settings.classification_estimate_prompt_overhead_units == 250
    assert settings.classification_estimate_completion_units_per_candidate == 450
    assert settings.classification_input_cost_per_1k_units_usd == 0.0025
    assert settings.classification_output_cost_per_1k_units_usd == 0.01
    assert settings.sync_on_open is False
    assert settings.gmail_scopes == ("https://www.googleapis.com/auth/gmail.readonly",)
    assert settings.sqlite_vec_extension_path == Path("/usr/local/lib/sqlite_vec.dylib")
    assert settings.ghost_threshold_days == 45
    assert settings.follow_up_threshold_days == 10


def test_settings_reject_invalid_enum_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("JOBTRACKER_CLASSIFICATION_MODE=autopilot\n")

    with pytest.raises(ValidationError):
        AppSettings(_env_file=env_file)


def test_settings_reject_non_sqlite_database_urls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("JOBTRACKER_DATABASE_URL=postgresql://db.example.com/jobtracker\n")

    with pytest.raises(ValidationError):
        AppSettings(_env_file=env_file)


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite+aiosqlite:///:memory:",
    ],
)
def test_settings_reject_in_memory_sqlite_database_urls(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(f"JOBTRACKER_DATABASE_URL={database_url}\n")

    with pytest.raises(ValidationError):
        AppSettings(_env_file=env_file)


def test_settings_reject_broader_gmail_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "JOBTRACKER_GMAIL_SCOPES="
        "https://www.googleapis.com/auth/gmail.readonly,"
        "https://www.googleapis.com/auth/gmail.modify\n"
    )

    with pytest.raises(ValidationError):
        AppSettings(_env_file=env_file)


def test_env_example_keys_are_backed_by_settings_fields() -> None:
    assert AppSettings.env_var_names() == parse_env_example()


def test_settings_ignore_secret_like_unknown_env_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_jobtracker_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("JOBTRACKER_AZURE_OPENAI_API_KEY=super-secret-api-key\n")

    settings = AppSettings(_env_file=env_file)

    assert "super-secret-api-key" not in repr(settings)
    assert "super-secret-api-key" not in str(settings.model_dump())
