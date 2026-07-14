import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";

import {
  checkLlmProviderHealthConfigProvidersLlmHealthPost,
  classificationEstimateClassificationEstimateGet,
  disconnectEmailConnectionAuthConnectionsProviderAccountIdDelete,
  gmailAuthUrlAuthGmailGet,
  loadProviderConfig as getProviderConfigConfigProvidersGet,
  updateProviderConfig as updateProviderConfigConfigProvidersPut,
  wipeDataLocalDataWipePost,
  type ClassificationPreRunEstimate,
  type ClassificationMode,
  type EmailConnection,
  type LLMProviderHealthCheckResponse,
  type ProviderConfigResponse,
  type ProviderConfigUpdateRequest,
  type SyncLocalStats,
} from "../../api";
import { publicApiError } from "../apiError";
import { ProviderSetup } from "../../components/ProviderSetup";
import type { RequestLoadState } from "../RedesignApp";
import { formatCount, logoStyle } from "../theme";

interface SettingsPageProps {
  connections: EmailConnection[];
  connectionsError: string | null;
  connectionsLoadState: RequestLoadState;
  onChanged: () => void;
  onRetryConnections: () => Promise<void>;
  syncStats: SyncLocalStats | null;
}

const PROVIDERS = [
  { name: "Gmail", hue: 25, supported: true },
  { name: "Outlook", hue: 240, supported: false },
  { name: "Yahoo", hue: 300, supported: false },
  { name: "iCloud", hue: 210, supported: false },
  { name: "Other (IMAP)", hue: 120, supported: false },
];

type AutoSyncKey = "30min" | "hour" | "manual";
type AutoSyncValue = AutoSyncKey | `interval:${number}`;
type ConfigLoadState = "error" | "loading" | "ready";
type NonLlmClassificationMode = Exclude<ClassificationMode, "llm">;

function autoSyncValueFor(config: ProviderConfigResponse | null): AutoSyncValue {
  if (!config) {
    return "manual";
  }
  if (!config.settings.sync_on_open) {
    return "manual";
  }
  if (config.settings.sync_interval_seconds === 1800) {
    return "30min";
  }
  if (config.settings.sync_interval_seconds === 3600) {
    return "hour";
  }
  return `interval:${config.settings.sync_interval_seconds}`;
}

function intervalLabel(seconds: number): string {
  if (seconds % 60 === 0) {
    return `Every ${seconds / 60} minutes`;
  }
  return `Every ${seconds} seconds`;
}

export function SettingsPage({
  connections,
  connectionsError,
  connectionsLoadState,
  onChanged,
  onRetryConnections,
}: SettingsPageProps) {
  const [addOpen, setAddOpen] = useState(false);
  const [providerNote, setProviderNote] = useState<string | null>(null);
  const [config, setConfig] = useState<ProviderConfigResponse | null>(null);
  const [configLoadState, setConfigLoadState] = useState<ConfigLoadState>("loading");
  const [configError, setConfigError] = useState<string | null>(null);
  const [configPending, setConfigPending] = useState(false);
  const [providerHealth, setProviderHealth] = useState<LLMProviderHealthCheckResponse | null>(null);
  const [providerHealthPending, setProviderHealthPending] = useState(false);
  const [providerHealthError, setProviderHealthError] = useState<string | null>(null);
  const [estimate, setEstimate] = useState<ClassificationPreRunEstimate | null>(null);
  const [gmailAuthError, setGmailAuthError] = useState<string | null>(null);
  const [gmailAuthPending, setGmailAuthPending] = useState(false);
  const [wipeStage, setWipeStage] = useState(0);
  const [disconnectPending, setDisconnectPending] = useState<string | null>(null);
  const [wipePending, setWipePending] = useState(false);
  const [disconnectError, setDisconnectError] = useState<string | null>(null);
  const [disconnectSuccess, setDisconnectSuccess] = useState<string | null>(null);
  const [wipeError, setWipeError] = useState<string | null>(null);
  const [wipeSuccess, setWipeSuccess] = useState<string | null>(null);
  const configRequestPending = useRef(true);
  const confirmedNonLlmModes = useRef<Partial<Record<string, NonLlmClassificationMode>>>({});
  const wipeTimer = useRef<number | null>(null);

  const retryProviderConfig = async () => {
    if (configRequestPending.current || configLoadState !== "error") {
      return;
    }
    configRequestPending.current = true;
    setConfigLoadState("loading");
    setConfigError(null);
    try {
      const response = await getProviderConfigConfigProvidersGet();
      if (response.status === 200) {
        setConfig(response.data);
        if (response.data.selection.classification_mode !== "llm") {
          confirmedNonLlmModes.current[response.data.selection.llm_provider] =
            response.data.selection.classification_mode;
        }
        setConfigError(null);
        setConfigLoadState("ready");
        return;
      }
      setConfig(null);
      setConfigError(publicApiError({ response }, "Provider settings could not be loaded."));
      setConfigLoadState("error");
    } catch (error) {
      setConfig(null);
      setConfigError(
        publicApiError(error, "Provider settings could not be loaded. Check the local backend."),
      );
      setConfigLoadState("error");
    } finally {
      configRequestPending.current = false;
    }
  };

  useEffect(() => {
    let cancelled = false;
    configRequestPending.current = true;
    const loadConfig = async () => {
      try {
        const response = await getProviderConfigConfigProvidersGet();
        if (cancelled) {
          return;
        }
        if (response.status === 200) {
          setConfig(response.data);
          if (response.data.selection.classification_mode !== "llm") {
            confirmedNonLlmModes.current[response.data.selection.llm_provider] =
              response.data.selection.classification_mode;
          }
          setConfigError(null);
          setConfigLoadState("ready");
          return;
        }
        setConfig(null);
        setConfigError(publicApiError({ response }, "Provider settings could not be loaded."));
        setConfigLoadState("error");
      } catch (error) {
        if (cancelled) {
          return;
        }
        setConfig(null);
        setConfigError(
          publicApiError(error, "Provider settings could not be loaded. Check the local backend."),
        );
        setConfigLoadState("error");
      } finally {
        if (!cancelled) {
          configRequestPending.current = false;
        }
      }
    };
    const loadEstimate = async () => {
      const estimateResponse = await classificationEstimateClassificationEstimateGet().catch(
        () => null,
      );
      if (cancelled) {
        return;
      }
      if (estimateResponse?.status === 200) {
        setEstimate(estimateResponse.data);
      }
    };
    void loadConfig();
    void loadEstimate();
    return () => {
      cancelled = true;
      configRequestPending.current = false;
    };
  }, []);

  useEffect(
    () => () => {
      if (wipeTimer.current !== null) {
        window.clearTimeout(wipeTimer.current);
      }
    },
    [],
  );

  const applyConfigUpdate = async (update: ProviderConfigUpdateRequest) => {
    if (configLoadState !== "ready" || config === null || configPending) {
      return;
    }
    setConfigPending(true);
    setConfigError(null);
    try {
      const response = await updateProviderConfigConfigProvidersPut(update);
      if (response.status !== 200) {
        setConfigError(publicApiError({ response }, "Settings could not be updated."));
        return;
      }
      setConfig(response.data);
      if (response.data.selection.classification_mode !== "llm") {
        confirmedNonLlmModes.current[response.data.selection.llm_provider] =
          response.data.selection.classification_mode;
      }
      if (update.llm_provider !== undefined && update.llm_provider !== null) {
        setProviderHealth(null);
        setProviderHealthError(null);
        setProviderHealthPending(true);
        const healthResponse = await checkLlmProviderHealthConfigProvidersLlmHealthPost().catch(
          (healthError: unknown) => ({ error: healthError }),
        );
        if ("status" in healthResponse && healthResponse.status === 200) {
          setProviderHealth(healthResponse.data);
        } else {
          setProviderHealthError(publicApiError("status" in healthResponse ? { response: healthResponse } : healthResponse.error, "Provider availability could not be checked."));
        }
        setProviderHealthPending(false);
      }
      const estimateResponse = await classificationEstimateClassificationEstimateGet().catch(() => null);
      if (estimateResponse?.status === 200) {
        setEstimate(estimateResponse.data);
      }
    } catch (error) {
      setConfigError(publicApiError(error, "Settings could not be updated. Check the local backend."));
    } finally {
      setProviderHealthPending(false);
      setConfigPending(false);
    }
  };

  const onPickProvider = async (provider: (typeof PROVIDERS)[number]) => {
    if (provider.supported) {
      if (gmailAuthPending) {
        return;
      }
      setGmailAuthPending(true);
      setGmailAuthError(null);
      try {
        const response = await gmailAuthUrlAuthGmailGet();
        if (response.status !== 200) {
          setGmailAuthError(
            publicApiError(
              { response },
              "Gmail authorization could not start. Check your OAuth configuration.",
            ),
          );
          return;
        }
        window.location.assign(response.data.authorization_url);
      } catch (error) {
        setGmailAuthError(
          publicApiError(error, "Gmail authorization could not start. Check the local backend."),
        );
      } finally {
        setGmailAuthPending(false);
      }
      return;
    }
    setProviderNote(`${provider.name} is coming later — only Gmail is supported in this version.`);
  };

  const onDisconnect = async (connection: EmailConnection) => {
    const key = `${connection.account.provider}:${connection.account.account_id}`;
    if (disconnectPending !== null) return;
    setDisconnectPending(key);
    setDisconnectError(null);
    setDisconnectSuccess(null);
    try {
      const response = await disconnectEmailConnectionAuthConnectionsProviderAccountIdDelete(
        connection.account.provider,
        connection.account.account_id,
      );
      if (response.status !== 200) {
        setDisconnectError(publicApiError({ response }, "Inbox could not be disconnected."));
        return;
      }
      setDisconnectSuccess("Inbox disconnected successfully.");
      onChanged();
    } catch (disconnectError) {
      setDisconnectError(publicApiError(disconnectError, "Inbox could not be disconnected. Check the local backend."));
    } finally {
      setDisconnectPending(null);
    }
  };

  const onAutoSyncChange = (key: AutoSyncKey) => {
    if (key === "manual") {
      void applyConfigUpdate({ sync_on_open: false });
      return;
    }
    void applyConfigUpdate({
      sync_interval_seconds: key === "30min" ? 1800 : 3600,
      sync_on_open: true,
    });
  };

  const onWipeClick = async () => {
    if (wipePending) return;
    if (wipeStage === 0) {
      setWipeStage(1);
      wipeTimer.current = window.setTimeout(() => setWipeStage(0), 4000);
      return;
    }
    if (wipeTimer.current !== null) {
      window.clearTimeout(wipeTimer.current);
      wipeTimer.current = null;
    }
    setWipeStage(0);
    setWipePending(true);
    setWipeError(null);
    setWipeSuccess(null);
    try {
      const response = await wipeDataLocalDataWipePost({ confirmation: "wipe-local-data" });
      if (response.status !== 200) {
        setWipeError(publicApiError({ response }, "Local data could not be deleted."));
        return;
      }
      setWipeSuccess("Local data deleted successfully.");
      onChanged();
    } catch (wipeError) {
      setWipeError(publicApiError(wipeError, "Local data could not be deleted. Check the local backend."));
    } finally {
      setWipePending(false);
    }
  };

  const selectedLlm = config?.selection.llm_provider;
  const localSelected = selectedLlm === "ollama";
  const cloudSelected = selectedLlm === "azure_openai";
  const configControlsDisabled = configLoadState !== "ready" || configPending;
  const prefilterOn = config ? config.selection.classification_mode !== "llm" : false;
  const recommendedNonLlmMode: NonLlmClassificationMode =
    config?.recommended_classification_mode !== "llm"
      ? (config?.recommended_classification_mode ?? "hybrid")
      : selectedLlm === "ollama"
        ? "local"
        : "hybrid";
  const customIntervalSeconds =
    config?.settings.sync_on_open && ![1800, 3600].includes(config.settings.sync_interval_seconds)
      ? config.settings.sync_interval_seconds
      : null;

  const onTogglePrefilter = () => {
    if (!config || !selectedLlm) {
      return;
    }
    const restoreMode = confirmedNonLlmModes.current[selectedLlm] ?? recommendedNonLlmMode;
    void applyConfigUpdate({
      classification_mode: prefilterOn ? "llm" : restoreMode,
    });
  };

  const engineOptionStyle = (on: boolean): CSSProperties => ({
    display: "block",
    textAlign: "left",
    padding: "14px 16px",
    borderRadius: "12px",
    cursor: "pointer",
    border: on ? "1.5px solid #1E5136" : "1px solid #E4E2DA",
    background: on ? "#F3F8F4" : "#FAFAF7",
    width: "100%",
  });

  const scanCost = (() => {
    if (!estimate) {
      return "—";
    }
    const emails = `${formatCount(estimate.candidate_count)} emails`;
    if (estimate.estimated_cost_usd === null || estimate.estimated_cost_usd === undefined) {
      return estimate.cost_estimate_available ? `free (${emails})` : `unavailable (${emails})`;
    }
    return `$${estimate.estimated_cost_usd.toFixed(2)} (${emails})`;
  })();

  return (
    <section
      style={{
        maxWidth: "720px",
        margin: "0 auto",
        padding: "28px 32px 60px",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
      }}
    >
      <div>
        <h1 style={{ margin: 0, fontSize: "22px", fontWeight: 700, letterSpacing: "-0.02em" }}>
          Settings
        </h1>
        <p style={{ margin: "6px 0 0", color: "#666D66", fontSize: "13.5px" }}>
          Everything runs on your computer. Your emails never leave this machine unless you choose
          a cloud AI.
        </p>
      </div>

      {config ? (
        <ProviderSetup
          autoLoad={false}
          checkReadinessOnMount
          initialConfig={config}
          key={`${config.selection.llm_provider}:${config.selection.classification_mode}`}
        />
      ) : null}

      <div
        style={{
          padding: "20px 22px",
          border: "1px solid #E4E2DA",
          borderRadius: "16px",
          background: "#fff",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "15px", fontWeight: 700 }}>Connected inboxes</h2>
        <p style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>
          Read-only access on every provider. JobTracker can never send, delete, or change your
          mail.
        </p>
        {connectionsLoadState === "loading" ? (
          <div role="status" style={{ fontSize: "12px", color: "#9A9F96" }}>Loading connected inboxes…</div>
        ) : null}
        {connectionsLoadState === "error" ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "6px" }}>
            <div role="alert" style={{ fontSize: "12px", color: "#96403C" }}>{connectionsError}</div>
            <button aria-label="Retry inbox connections" onClick={() => void onRetryConnections()} style={{ padding: "7px 14px", border: "1px dashed #C9C6BA", borderRadius: "999px", background: "none", color: "#4A5049", cursor: "pointer", fontSize: "12px", fontWeight: 600 }} type="button">Retry</button>
          </div>
        ) : null}
        {connectionsLoadState === "ready" && connections.length === 0 ? (
          <div style={{ fontSize: "12px", color: "#9A9F96" }}>No connected inboxes yet.</div>
        ) : null}
        {connectionsLoadState === "ready" ? connections.map((connection) => {
          const providerName =
            connection.account.provider === "gmail" ? "Gmail" : connection.account.provider;
          const email = connection.display_email?.address ?? connection.account.account_id;
          return (
            <div
              key={`${connection.account.provider}-${connection.account.account_id}`}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "12px",
                padding: "12px 14px",
                border: "1px solid #D4E2D6",
                borderRadius: "12px",
                background: "#E7EFE8",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span style={logoStyle(providerName)}>{providerName[0]}</span>
                <div>
                  <div style={{ fontSize: "13.5px", fontWeight: 600, color: "#1E5136" }}>
                    {providerName} · {email}
                  </div>
                  <div style={{ fontSize: "12px", color: "#66886F" }}>
                    Stored connection
                    {connection.reauth_required ? " · reconnect needed" : ""}
                  </div>
                </div>
              </div>
              <button
                disabled={disconnectPending !== null}
                onClick={() => void onDisconnect(connection)}
                style={{
                  padding: "7px 14px",
                  border: "1px solid #C2D6C6",
                  borderRadius: "999px",
                  background: "#fff",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "#1E5136",
                  cursor: "pointer",
                }}
                type="button"
              >
                {disconnectPending === `${connection.account.provider}:${connection.account.account_id}` ? "Disconnecting…" : "Disconnect"}
              </button>
            </div>
          );
        }) : null}
        {disconnectError ? <div role="alert" style={{ fontSize: "12px", color: "#96403C" }}>{disconnectError}</div> : null}
        {disconnectSuccess ? <div role="status" style={{ fontSize: "12px", color: "#1E5136" }}>{disconnectSuccess}</div> : null}
        {addOpen ? (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(5,minmax(0,1fr))",
              gap: "8px",
            }}
          >
            {PROVIDERS.map((provider) => (
              <button
                className="rd-hover-green-border-white"
                disabled={provider.supported && gmailAuthPending}
                key={provider.name}
                onClick={() => void onPickProvider(provider)}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "6px",
                  padding: "12px 6px",
                  border: "1px solid #E4E2DA",
                  borderRadius: "12px",
                  background: "#FAFAF7",
                  cursor: "pointer",
                }}
                type="button"
              >
                <span
                  style={{
                    ...logoStyle(provider.name),
                    background: `oklch(0.93 0.03 ${provider.hue})`,
                    color: `oklch(0.4 0.08 ${provider.hue})`,
                  }}
                >
                  {provider.name[0]}
                </span>
                <span style={{ fontSize: "11.5px", fontWeight: 600, color: "#4A5049" }}>
                  {provider.name}
                </span>
              </button>
            ))}
          </div>
        ) : null}
        {providerNote ? (
          <div style={{ fontSize: "12px", color: "#8A6A14" }}>{providerNote}</div>
        ) : null}
        {gmailAuthError ? (
          <div role="alert" style={{ fontSize: "12px", color: "#96403C" }}>
            {gmailAuthError}
          </div>
        ) : null}
        <button
          className="rd-hover-green-border-text"
          onClick={() => {
            setAddOpen((value) => !value);
            setProviderNote(null);
          }}
          style={{
            alignSelf: "flex-start",
            padding: "8px 16px",
            border: "1px dashed #C9C6BA",
            borderRadius: "999px",
            background: "none",
            fontSize: "12.5px",
            fontWeight: 600,
            color: "#4A5049",
            cursor: "pointer",
          }}
          type="button"
        >
          {addOpen ? "Cancel" : "+ Add another inbox"}
        </button>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: "13px",
            color: "#4A5049",
            borderTop: "1px solid #F0EEE7",
            paddingTop: "12px",
          }}
        >
          <span>Check for new email automatically</span>
          <select
            aria-label="Auto-sync interval"
            disabled={configControlsDisabled}
            onChange={(event) => {
              if (["30min", "hour", "manual"].includes(event.target.value)) {
                onAutoSyncChange(event.target.value as AutoSyncKey);
              }
            }}
            style={{
              padding: "6px 10px",
              border: "1px solid #E4E2DA",
              borderRadius: "8px",
              background: "#FAFAF7",
              fontSize: "12.5px",
            }}
            value={configLoadState === "ready" && config ? autoSyncValueFor(config) : ""}
          >
            <option disabled value="">
              {configLoadState === "loading" ? "Loading..." : "Unavailable"}
            </option>
            <option value="30min">Every 30 minutes</option>
            <option value="hour">Every hour</option>
            <option value="manual">Only when I click Sync</option>
            {customIntervalSeconds !== null ? (
              <option value={`interval:${customIntervalSeconds}`}>
                {intervalLabel(customIntervalSeconds)}
              </option>
            ) : null}
          </select>
        </div>
      </div>

      <div
        style={{
          padding: "20px 22px",
          border: "1px solid #E4E2DA",
          borderRadius: "16px",
          background: "#fff",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "15px", fontWeight: 700 }}>AI engine</h2>
        <p style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>
          Which AI reads your job-search emails and writes your insights.
        </p>
        <button
          disabled={configControlsDisabled}
          onClick={() => void applyConfigUpdate({ llm_provider: "ollama" })}
          style={engineOptionStyle(localSelected)}
          type="button"
        >
          <span style={{ fontWeight: 700, fontSize: "13.5px", display: "block" }}>
            On this computer{" "}
            <span style={{ fontWeight: 600, color: "#1E5136", fontSize: "11px" }}>
              · Most private
            </span>
          </span>
          <span style={{ fontSize: "12.5px", color: "#666D66" }}>
            Uses a local model. Nothing ever leaves your machine. Slower, free.
          </span>
        </button>
        <button
          disabled={configControlsDisabled}
          onClick={() => void applyConfigUpdate({ llm_provider: "azure_openai" })}
          style={engineOptionStyle(cloudSelected)}
          type="button"
        >
          <span style={{ fontWeight: 700, fontSize: "13.5px", display: "block" }}>
            Cloud AI (your own account)
          </span>
          <span style={{ fontSize: "12.5px", color: "#666D66" }}>
            Faster and smarter. Only job-related emails are sent, using your own API key.
          </span>
        </button>
        <div
          style={{
            fontSize: "12.5px",
            color: "#4A5049",
            background: "#F7F6F2",
            borderRadius: "10px",
            padding: "10px 12px",
          }}
        >
          {configLoadState === "loading"
            ? "Loading provider settings..."
            : configLoadState === "error"
              ? "Provider selection is unavailable until settings load successfully."
              : localSelected
                ? "Currently using: a local model on this computer. Your emails are never uploaded anywhere."
                : "Currently using: your own cloud AI account. Only emails already identified as job-related are sent — never your whole inbox."}
          {providerHealthPending ? (
            <div style={{ marginTop: "5px", color: "#666D66" }}>Checking provider availability...</div>
          ) : providerHealth ? (
            <div
              style={{
                marginTop: "5px",
                color: providerHealth.status === "available" ? "#1E5136" : "#96403C",
                fontWeight: 600,
              }}
            >
              {providerHealth.provider_name} {providerHealth.status}
            </div>
          ) : null}
          {providerHealthError ? (
            <div role="alert" style={{ marginTop: "5px", color: "#96403C", fontWeight: 600 }}>{providerHealthError}</div>
          ) : null}
        </div>
        {configError ? (
          <>
            <div role="alert" style={{ fontSize: "12px", color: "#96403C" }}>
              {configError}
            </div>
            {configLoadState === "error" ? (
              <button
                aria-label="Retry provider settings"
                onClick={() => void retryProviderConfig()}
                style={{
                  alignSelf: "flex-start",
                  padding: "8px 16px",
                  border: "1px dashed #C9C6BA",
                  borderRadius: "999px",
                  background: "none",
                  fontSize: "12.5px",
                  fontWeight: 600,
                  color: "#4A5049",
                  cursor: "pointer",
                }}
                type="button"
              >
                Retry
              </button>
            ) : null}
          </>
        ) : null}
      </div>

      <div
        style={{
          padding: "20px 22px",
          border: "1px solid #E4E2DA",
          borderRadius: "16px",
          background: "#fff",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "15px", fontWeight: 700 }}>Cost control</h2>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: "13px",
            color: "#4A5049",
          }}
        >
          <span>
            Pre-filter emails before sending to AI{" "}
            <span style={{ color: "#9A9F96" }}>(recommended — cuts cost ~90%)</span>
          </span>
          <button
            aria-checked={prefilterOn}
            aria-label="Toggle pre-filtering"
            disabled={configControlsDisabled}
            role="switch"
            onClick={onTogglePrefilter}
            style={{
              width: "40px",
              height: "23px",
              borderRadius: "999px",
              border: "none",
              cursor: "pointer",
              position: "relative",
              background: prefilterOn ? "#1E5136" : "#D8D6CC",
              transition: "background 0.15s",
            }}
            type="button"
          >
            <span
              style={{
                position: "absolute",
                top: "2.5px",
                left: prefilterOn ? "19px" : "3px",
                width: "18px",
                height: "18px",
                borderRadius: "50%",
                background: "#fff",
                transition: "left 0.15s",
                display: "block",
              }}
            />
          </button>
        </div>
        <div style={{ fontSize: "12px", color: "#9A9F96" }}>
          Estimated cost of your next full scan:{" "}
          <strong style={{ color: "#1B201C" }}>{scanCost}</strong>
        </div>
      </div>

      <div
        style={{
          padding: "20px 22px",
          border: "1px solid #EBD9D6",
          borderRadius: "16px",
          background: "#FDF9F8",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "15px", fontWeight: 700, color: "#96403C" }}>
          Delete everything
        </h2>
        <p style={{ margin: 0, fontSize: "12.5px", color: "#8A6560" }}>
          Wipes all local data: synced email, applications, insights, and stored keys. Your actual
          Gmail is untouched.
        </p>
        <button
          disabled={wipePending}
          onClick={() => void onWipeClick()}
          style={{
            alignSelf: "flex-start",
            padding: "8px 16px",
            borderRadius: "999px",
            cursor: "pointer",
            fontSize: "12.5px",
            fontWeight: 600,
            border: "1px solid #DBA9A4",
            background: wipeStage === 0 ? "#fff" : "#96403C",
            color: wipeStage === 0 ? "#96403C" : "#fff",
          }}
          type="button"
        >
          {wipePending
            ? "Deleting local data…"
            : wipeStage === 0
            ? "Delete all local data…"
            : "Click again to confirm - this can't be undone"}
        </button>
        {wipeError ? <div role="alert" style={{ fontSize: "12px", color: "#96403C" }}>{wipeError}</div> : null}
        {wipeSuccess ? <div role="status" style={{ fontSize: "12px", color: "#1E5136" }}>{wipeSuccess}</div> : null}
      </div>
    </section>
  );
}
