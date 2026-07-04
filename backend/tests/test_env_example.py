from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke


EXPECTED_ENV_KEYS = {
    "JOBTRACKER_ENV",
    "JOBTRACKER_API_HOST",
    "JOBTRACKER_API_PORT",
    "JOBTRACKER_CORS_ORIGINS",
    "JOBTRACKER_LOG_LEVEL",
    "JOBTRACKER_DATA_DIR",
    "JOBTRACKER_DATABASE_URL",
    "JOBTRACKER_SQLITE_VEC_EXTENSION_PATH",
    "JOBTRACKER_SECRET_STORE_BACKEND",
    "JOBTRACKER_FERNET_KEY_FILE",
    "JOBTRACKER_EMAIL_PROVIDER",
    "JOBTRACKER_LLM_PROVIDER",
    "JOBTRACKER_CLASSIFICATION_MODE",
    "JOBTRACKER_GMAIL_CLIENT_CONFIG_FILE",
    "JOBTRACKER_GMAIL_SCOPES",
    "JOBTRACKER_SYNC_ON_OPEN",
    "JOBTRACKER_SYNC_INTERVAL_SECONDS",
    "JOBTRACKER_GMAIL_PAGE_SIZE",
    "JOBTRACKER_BACKFILL_BATCH_SIZE",
    "JOBTRACKER_RETAIN_DEBUG_EMAIL_BODIES",
    "JOBTRACKER_CLASSIFICATION_BATCH_SIZE",
    "JOBTRACKER_CLASSIFICATION_PROMPT_VERSION",
    "JOBTRACKER_LLM_TIMEOUT_SECONDS",
    "JOBTRACKER_LLM_MAX_RETRIES",
    "JOBTRACKER_AZURE_OPENAI_ENDPOINT",
    "JOBTRACKER_AZURE_OPENAI_API_VERSION",
    "JOBTRACKER_AZURE_OPENAI_CHAT_DEPLOYMENT",
    "JOBTRACKER_AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    "JOBTRACKER_OLLAMA_BASE_URL",
    "JOBTRACKER_OLLAMA_CHAT_MODEL",
    "JOBTRACKER_OLLAMA_EMBEDDING_MODEL",
    "JOBTRACKER_GHOST_THRESHOLD_DAYS",
}


def parse_env_example(env_example_path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}

    for line_number, raw_line in enumerate(env_example_path.read_text().splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        assert "=" in line, f"line {line_number} must be KEY=value"
        key, value = line.split("=", 1)
        assert key.startswith("JOBTRACKER_"), f"line {line_number} uses an unexpected key prefix"
        assert key not in parsed, f"line {line_number} duplicates {key}"
        parsed[key] = value

    return parsed


def env_example_path() -> Path:
    backend_root = Path(__file__).resolve().parents[1]
    return backend_root / ".env.example"


def load_env_example() -> dict[str, str]:
    return parse_env_example(env_example_path())


def load_env_example_text() -> str:
    return env_example_path().read_text()


def readme_path() -> Path:
    return Path(__file__).resolve().parents[2] / "README.md"


def test_env_example_documents_expected_v1_settings() -> None:
    env_values = load_env_example()

    assert set(env_values) == EXPECTED_ENV_KEYS
    assert env_values["JOBTRACKER_GMAIL_SCOPES"] == "https://www.googleapis.com/auth/gmail.readonly"
    assert env_values["JOBTRACKER_CLASSIFICATION_MODE"] in {"hybrid", "llm", "local"}
    assert env_values["JOBTRACKER_SECRET_STORE_BACKEND"] in {"keyring", "fernet"}


def test_env_example_does_not_include_secret_values() -> None:
    env_values = load_env_example()

    secret_like_names = (
        "API_KEY",
        "CLIENT_SECRET",
        "PASSWORD",
        "TOKEN",
        "ACCESS_KEY",
    )

    assert not [key for key in env_values if any(name in key for name in secret_like_names)]
    assert all("<" not in value and ">" not in value for value in env_values.values())


def test_env_example_does_not_document_later_provider_settings() -> None:
    env_values = load_env_example()

    assert not [key for key in env_values if key.startswith("JOBTRACKER_OPENAI_")]
    assert not [key for key in env_values if key.startswith("JOBTRACKER_ANTHROPIC_")]


def test_env_example_keeps_oauth_client_config_outside_repo() -> None:
    env_values = load_env_example()

    assert not env_values["JOBTRACKER_GMAIL_CLIENT_CONFIG_FILE"].startswith("./")


def test_env_example_documents_allowed_setting_values() -> None:
    env_text = load_env_example_text()

    assert "JOBTRACKER_SECRET_STORE_BACKEND allowed values: keyring, fernet" in env_text
    assert "JOBTRACKER_EMAIL_PROVIDER allowed values: gmail" in env_text
    assert "JOBTRACKER_LLM_PROVIDER allowed values: azure_openai, ollama" in env_text
    assert "JOBTRACKER_CLASSIFICATION_MODE allowed values: hybrid, llm, local" in env_text


def test_wipe_data_marker_contract_is_documented() -> None:
    env_text = load_env_example_text()
    readme_text = readme_path().read_text()

    assert ".jobtracker-data" in env_text
    assert ".jobtracker-data" in readme_text
    assert ".jobtracker" in env_text
    assert ".jobtracker" in readme_text
