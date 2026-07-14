import { useEffect, useState } from "react";

import {
  gmailAuthUrlAuthGmailGet,
  loadProviderConfig,
  loadProviderReadiness,
  loadSetupStatus,
  saveInitialSetup,
  updateProviderConfig,
  type ClassificationMode,
  type LLMProviderName,
  type ProviderConfigResponse,
  type ProviderConfigUpdateRequest,
  type ProviderReadinessResponse,
  type SetupSubmitRequest,
} from "../api";

interface ProviderSetupProps {
  autoLoad?: boolean;
  checkReadinessOnMount?: boolean;
  firstRun?: boolean;
  initialConfig?: ProviderConfigResponse;
}

const stateLabel = {
  missing_config: "Needs configuration",
  missing_credential: "Needs credential",
  not_implemented: "Not implemented",
  ready: "Ready",
  reauth_required: "Reconnect required",
  unavailable: "Unavailable",
} as const;

export function ProviderSetup({
  autoLoad = true,
  checkReadinessOnMount = false,
  firstRun = false,
  initialConfig,
}: ProviderSetupProps) {
  const [config, setConfig] = useState<ProviderConfigResponse | null>(initialConfig ?? null);
  const [readiness, setReadiness] = useState<ProviderReadinessResponse | null>(null);
  const [llmProvider, setLlmProvider] = useState<LLMProviderName>(
    initialConfig?.selection.llm_provider ?? "ollama",
  );
  const [classificationMode, setClassificationMode] =
    useState<ClassificationMode>(initialConfig?.selection.classification_mode ?? "local");
  const [gmailJson, setGmailJson] = useState("");
  const [azureKey, setAzureKey] = useState("");
  const [azureEndpoint, setAzureEndpoint] = useState(
    initialConfig?.settings.azure_openai_endpoint ?? "",
  );
  const [azureApiVersion, setAzureApiVersion] = useState(
    initialConfig?.settings.azure_openai_api_version ?? "2024-06-01",
  );
  const [azureChat, setAzureChat] = useState(
    initialConfig?.settings.azure_openai_chat_deployment ?? "",
  );
  const [azureEmbedding, setAzureEmbedding] = useState(
    initialConfig?.settings.azure_openai_embedding_deployment ?? "",
  );
  const [ollamaUrl, setOllamaUrl] = useState(
    initialConfig?.settings.ollama_base_url ?? "http://127.0.0.1:11434",
  );
  const [ollamaChat, setOllamaChat] = useState(
    initialConfig?.settings.ollama_chat_model ?? "llama3.1",
  );
  const [ollamaEmbedding, setOllamaEmbedding] = useState(
    initialConfig?.settings.ollama_embedding_model ?? "nomic-embed-text",
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [authorizationUrl, setAuthorizationUrl] = useState<string | null>(null);
  const [gmailConnected, setGmailConnected] = useState(false);

  const applyLoaded = (
    configResponse: Awaited<ReturnType<typeof loadProviderConfig>>,
    readinessResponse: Awaited<ReturnType<typeof loadProviderReadiness>>,
  ) => {
    if (configResponse.status !== 200 || readinessResponse.status !== 200) {
      throw new Error("Provider setup could not be loaded.");
    }
    const next = configResponse.data;
    setConfig(next);
    setReadiness(readinessResponse.data);
    setLlmProvider(next.selection.llm_provider);
    setClassificationMode(next.selection.classification_mode);
    setAzureEndpoint(next.settings.azure_openai_endpoint);
    setAzureApiVersion(next.settings.azure_openai_api_version);
    setAzureChat(next.settings.azure_openai_chat_deployment);
    setAzureEmbedding(next.settings.azure_openai_embedding_deployment);
    setOllamaUrl(next.settings.ollama_base_url);
    setOllamaChat(next.settings.ollama_chat_model);
    setOllamaEmbedding(next.settings.ollama_embedding_model);
  };

  const refresh = async () => {
    const responses = await Promise.all([
      loadProviderConfig(),
      loadProviderReadiness(),
    ]);
    applyLoaded(...responses);
  };

  useEffect(() => {
    if (!autoLoad) {
      if (checkReadinessOnMount) {
        void loadProviderReadiness()
          .then((response) => {
            if (response.status === 200) setReadiness(response.data);
          })
          .catch(() => undefined);
      }
      return;
    }
    let cancelled = false;
    if (firstRun) {
      void loadSetupStatus()
        .then((response) => {
          if (cancelled || response.status !== 200) return;
          const status = response.data;
          setLlmProvider(status.llm_provider);
          setClassificationMode(status.recommended_classification_mode);
          setReadiness(status.readiness);
          setGmailConnected(status.gmail_connected);
          setConfig(defaultConfig(status.llm_provider, status.classification_mode));
        })
        .catch(() => {
          if (!cancelled) {
            setError("Setup status unavailable. Start the local backend and retry.");
          }
        });
      return () => {
        cancelled = true;
      };
    }
    void Promise.all([loadProviderConfig(), loadProviderReadiness()])
      .then((responses) => {
        if (!cancelled) applyLoaded(...responses);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Provider setup is unavailable. Start the local backend and retry.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [autoLoad, checkReadinessOnMount, firstRun]);

  const save = async () => {
    setPending(true);
    setError(null);
    setMessage(null);
    const request: SetupSubmitRequest = {
      classification_mode: classificationMode,
      email_provider: "gmail",
      llm_provider: llmProvider,
      ...(gmailJson ? { gmail_oauth_client_json: gmailJson } : {}),
      ...(llmProvider === "azure_openai"
        ? {
            azure_openai_api_key: azureKey || undefined,
            azure_openai_api_version: azureApiVersion,
            azure_openai_chat_deployment: azureChat,
            azure_openai_embedding_deployment: azureEmbedding,
            azure_openai_endpoint: azureEndpoint,
          }
        : firstRun
          ? {}
          : {
            ollama_base_url: ollamaUrl,
            ollama_chat_model: ollamaChat,
            ollama_embedding_model: ollamaEmbedding,
          }),
    };
    try {
      const response = firstRun
        ? await saveInitialSetup(request)
        : await updateProviderConfig(request satisfies ProviderConfigUpdateRequest);
      if (response.status !== 200) {
        throw new Error(apiMessage(response.data, "Provider setup could not be saved."));
      }
      setGmailJson("");
      setAzureKey("");
      setMessage(firstRun ? "Setup choices saved" : "Provider setup saved securely.");
      if (firstRun) {
        if ("readiness" in response.data) setReadiness(response.data.readiness);
      } else {
        await refresh();
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Provider setup could not be saved. Check the entered values.",
      );
    } finally {
      setPending(false);
    }
  };

  const connectGmail = async () => {
    setPending(true);
    setError(null);
    try {
      const response = await gmailAuthUrlAuthGmailGet();
      if (response.status !== 200) {
        throw new Error(apiMessage(response.data, "Gmail authorization could not start."));
      }
      if (firstRun) {
        setAuthorizationUrl(response.data.authorization_url);
        setPending(false);
      } else {
        window.location.assign(response.data.authorization_url);
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Gmail authorization could not start. Save OAuth client JSON first.",
      );
      setPending(false);
    }
  };

  return (
    <section aria-labelledby="provider-setup-title" style={cardStyle}>
      <div>
        <p style={eyebrowStyle}>Local provider setup</p>
        <h2 id="provider-setup-title" style={{ fontSize: "17px", margin: 0 }}>
          Credentials and readiness
        </h2>
        <p style={helpStyle}>
          Credentials are write-only and encrypted through the local SecretStore. Saved values are
          never returned to this page.
        </p>
      </div>

      <label style={fieldStyle}>
        <span>AI provider</span>
        <select
          aria-label="AI provider"
          onChange={(event) => {
            const provider = event.target.value as LLMProviderName;
            setLlmProvider(provider);
            setClassificationMode(provider === "ollama" ? "local" : "hybrid");
          }}
          value={llmProvider}
        >
          <option value="ollama">Ollama (local)</option>
          <option value="azure_openai">Azure OpenAI</option>
        </select>
      </label>

      <fieldset style={{ border: 0, margin: 0, padding: 0 }}>
        <legend style={{ fontSize: "12.5px", fontWeight: 600 }}>Classification mode</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", marginTop: "6px" }}>
          {(["hybrid", "llm", ...(llmProvider === "ollama" ? ["local"] : [])] as ClassificationMode[]).map(
            (mode) => (
              <label key={mode} style={{ fontSize: "12.5px" }}>
                <input
                  checked={classificationMode === mode}
                  name="classification-mode"
                  onChange={() => setClassificationMode(mode)}
                  type="radio"
                />{" "}
                {mode}
              </label>
            ),
          )}
        </div>
      </fieldset>

      {llmProvider === "azure_openai" ? (
        <div style={gridStyle}>
          <TextField label="Azure endpoint" onChange={setAzureEndpoint} value={azureEndpoint} />
          <TextField
            label="Azure API version"
            onChange={setAzureApiVersion}
            value={azureApiVersion}
          />
          <TextField label="Chat deployment" onChange={setAzureChat} value={azureChat} />
          <TextField
            label="Embedding deployment"
            onChange={setAzureEmbedding}
            value={azureEmbedding}
          />
          <TextField
            label="Azure API key"
            onChange={setAzureKey}
            placeholder="Leave blank to keep the stored key"
            type="password"
            value={azureKey}
          />
        </div>
      ) : (
        <div style={gridStyle}>
          <TextField label="Ollama URL" onChange={setOllamaUrl} value={ollamaUrl} />
          <TextField label="Chat model" onChange={setOllamaChat} value={ollamaChat} />
          <TextField
            label="Embedding model"
            onChange={setOllamaEmbedding}
            value={ollamaEmbedding}
          />
        </div>
      )}

      <label style={fieldStyle}>
        <span>Google Desktop OAuth client JSON</span>
        <textarea
          aria-label="Google Desktop OAuth client JSON"
          onChange={(event) => setGmailJson(event.target.value)}
          placeholder='Paste the downloaded JSON. Leave blank to keep the stored client.'
          rows={4}
          value={gmailJson}
        />
      </label>

      {readiness ? (
        <div aria-label="Provider readiness" style={readinessGridStyle}>
          <ReadinessItem label="Gmail sync" value={readiness.gmail_sync} />
          <ReadinessItem
            label="Classification"
            value={readiness.classification_generation}
          />
          <ReadinessItem label="Embeddings" value={readiness.embedding_generation} />
          <ReadinessItem label="Chat" value={readiness.chat_generation} />
        </div>
      ) : (
        <p style={helpStyle}>Readiness has not been checked yet. Recheck after saving changes.</p>
      )}

      {error ? (
        <p role="alert" style={errorStyle}>
          {firstRun && error.startsWith("Setup status unavailable")
            ? "Setup status unavailable"
            : error}
        </p>
      ) : null}
      {message ? <p role="status" style={successStyle}>{message}</p> : null}
      {gmailConnected || readiness?.gmail_sync.state === "ready" ? (
        <p role="status" style={successStyle}>Gmail callback complete</p>
      ) : null}
      {authorizationUrl ? (
        <div>
          <a href={authorizationUrl}>Continue to Google</a>
          <p style={helpStyle}>Requested scope: https://www.googleapis.com/auth/gmail.readonly</p>
        </div>
      ) : null}
      {firstRun && llmProvider === "azure_openai" ? (
        <p style={helpStyle}>Preselected from Azure OpenAI setup</p>
      ) : null}
      {firstRun && error?.startsWith("Setup status unavailable") ? (
        <p style={helpStyle}>
          Setup status is unavailable. Start the local backend before saving setup choices or
          connecting Gmail.
        </p>
      ) : null}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
        <button disabled={pending || !config} onClick={() => void save()} type="button">
          {pending ? "Saving..." : firstRun ? "Save setup choices" : "Save provider setup"}
        </button>
        <button
          disabled={pending || gmailConnected}
          onClick={() => void connectGmail()}
          type="button"
        >
          {gmailConnected ? "Gmail connected" : firstRun ? "Start Gmail OAuth" : "Connect Gmail"}
        </button>
        <button disabled={pending} onClick={() => void refresh()} type="button">
          Recheck readiness
        </button>
      </div>
    </section>
  );
}

function TextField({
  label,
  onChange,
  placeholder,
  type = "text",
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  value: string;
}) {
  return (
    <label style={fieldStyle}>
      <span>{label}</span>
      <input
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type={type}
        value={value}
      />
    </label>
  );
}

function ReadinessItem({
  label,
  value,
}: {
  label: string;
  value: ProviderReadinessResponse["gmail_sync"];
}) {
  return (
    <article style={{ borderTop: "2px solid #D4E2D6", paddingTop: "9px" }}>
      <strong style={{ display: "block", fontSize: "12px" }}>{label}</strong>
      <span style={{ color: value.state === "ready" ? "#1E5136" : "#8A6A14", fontSize: "12px" }}>
        {stateLabel[value.state]}
      </span>
      <p style={{ ...helpStyle, margin: "4px 0 0" }}>{value.message}</p>
      {value.action ? <p style={{ ...helpStyle, color: "#1B201C", margin: "4px 0 0" }}>{value.action}</p> : null}
    </article>
  );
}

function apiMessage(data: unknown, fallback: string) {
  if (typeof data !== "object" || data === null || !("error" in data)) return fallback;
  const body = data.error;
  if (typeof body !== "object" || body === null || !("message" in body)) return fallback;
  return typeof body.message === "string" ? body.message : fallback;
}

const cardStyle = {
  background: "#fff",
  border: "1px solid #E4E2DA",
  borderRadius: "16px",
  display: "flex",
  flexDirection: "column",
  gap: "14px",
  padding: "20px 22px",
} as const;
const eyebrowStyle = { color: "#66886F", fontSize: "11px", fontWeight: 700, margin: "0 0 5px", textTransform: "uppercase" } as const;
const helpStyle = { color: "#666D66", fontSize: "12.5px", lineHeight: 1.45 } as const;
const fieldStyle = { display: "flex", flexDirection: "column", fontSize: "12.5px", fontWeight: 600, gap: "5px" } as const;
const gridStyle = { display: "grid", gap: "10px", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))" } as const;
const readinessGridStyle = { display: "grid", gap: "12px", gridTemplateColumns: "repeat(auto-fit, minmax(135px, 1fr))" } as const;
const errorStyle = { color: "#96403C", fontSize: "12.5px", margin: 0 } as const;
const successStyle = { color: "#1E5136", fontSize: "12.5px", margin: 0 } as const;

function defaultConfig(
  provider: LLMProviderName,
  mode: ClassificationMode,
): ProviderConfigResponse {
  return {
    email_providers: [],
    llm_providers: [],
    recommended_classification_mode: provider === "ollama" ? "local" : "hybrid",
    selection: {
      classification_mode: mode,
      email_provider: "gmail",
      llm_provider: provider,
    },
    settings: {
      azure_openai_api_version: "2024-06-01",
      azure_openai_chat_deployment: "",
      azure_openai_embedding_deployment: "",
      azure_openai_endpoint: "",
      gmail_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      ollama_base_url: "http://127.0.0.1:11434",
      ollama_chat_model: "llama3.1",
      ollama_embedding_model: "nomic-embed-text",
      sync_interval_seconds: 900,
      sync_on_open: true,
    },
  };
}
