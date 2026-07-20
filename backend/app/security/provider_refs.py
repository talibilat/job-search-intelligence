from app.security.secret_store import SecretKind, SecretRef

AZURE_OPENAI_API_KEY_REF = SecretRef(
    kind=SecretKind.LLM_API_KEY,
    provider="azure_openai",
    name="api_key",
)
GMAIL_OAUTH_CLIENT_REF = SecretRef(
    kind=SecretKind.OAUTH_CLIENT,
    provider="gmail",
    name="desktop_client_json",
)
TAVILY_API_KEY_REF = SecretRef(
    kind=SecretKind.WEB_SEARCH_API_KEY,
    provider="tavily",
    name="api_key",
)
