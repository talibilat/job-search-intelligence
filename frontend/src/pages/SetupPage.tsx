import { useEffect, useState } from "react";

import {
  gmailAuthUrlAuthGmailGet,
  setupStatusSetupStatusGet,
  type EmailAuthorizationStartResult,
  type SetupStatusResponse,
} from "../api";
import { Alert, Button } from "../components/ui";
import { setupWizardSections } from "../setupWizardCopy";
import "./SetupPage.css";

const setupSteps = [
  {
    title: "Choose provider",
    body: "Select Azure OpenAI or Ollama without storing secret values in the browser shell.",
  },
  {
    title: "Classification mode",
    body: "Confirm hybrid, llm, or local mode before any future inbox classification run.",
  },
  {
    title: "Connect Gmail",
    body: "Prepare for a user-owned Google OAuth client with gmail.readonly scope only.",
  },
  {
    title: "Ready state",
    body: "Keep setup incomplete until provider choices and Gmail authorization are explicitly accepted.",
  },
] as const;

function apiErrorMessage(data: unknown, fallback: string) {
  if (
    typeof data === "object" &&
    data !== null &&
    "error" in data &&
    typeof data.error === "object" &&
    data.error !== null &&
    "message" in data.error &&
    typeof data.error.message === "string"
  ) {
    return data.error.message;
  }

  return fallback;
}

export function SetupPage() {
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(
    null,
  );
  const [authorization, setAuthorization] =
    useState<EmailAuthorizationStartResult | null>(null);
  const [isCheckingStatus, setIsCheckingStatus] = useState(true);
  const [isStartingAuth, setIsStartingAuth] = useState(false);
  const [gmailAuthError, setGmailAuthError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;

    async function loadSetupStatus() {
      setIsCheckingStatus(true);
      try {
        const response = await setupStatusSetupStatusGet();
        if (!ignore) {
          setSetupStatus(response.data);
        }
      } catch {
        if (!ignore) {
          setGmailAuthError(
            "Setup status is unavailable. Start the local backend before connecting Gmail.",
          );
        }
      } finally {
        if (!ignore) {
          setIsCheckingStatus(false);
        }
      }
    }

    void loadSetupStatus();

    return () => {
      ignore = true;
    };
  }, []);

  const gmailConnected = setupStatus?.gmail_connected ?? false;
  const authButtonLabel = isCheckingStatus
    ? "Checking Gmail status"
    : gmailConnected
      ? "Gmail connected"
      : isStartingAuth
        ? "Preparing Gmail OAuth"
        : "Start Gmail OAuth";

  async function handleStartGmailAuth() {
    setIsStartingAuth(true);
    setAuthorization(null);
    setGmailAuthError(null);

    try {
      const response = await gmailAuthUrlAuthGmailGet();
      if (response.status !== 200) {
        setGmailAuthError(
          apiErrorMessage(
            response.data,
            "Gmail authorization could not start. Check the OAuth client JSON path.",
          ),
        );
        return;
      }

      setAuthorization(response.data);
    } catch {
      setGmailAuthError(
        "Gmail authorization could not start. Check that the local backend is running.",
      );
    } finally {
      setIsStartingAuth(false);
    }
  }

  return (
    <main className="app-shell setup-page">
      <section className="setup-hero" aria-labelledby="setup-page-title">
        <p className="eyebrow">First-run setup</p>
        <h1 id="setup-page-title">Set up JobTracker locally</h1>
        <p className="hero-copy">
          Configure provider choices, classification mode, and Gmail
          authorization boundaries before the app reaches a ready state.
        </p>
        <div className="setup-actions" aria-label="Setup actions">
          <Button disabled>Save setup choices</Button>
          <Button
            disabled={isCheckingStatus || gmailConnected || isStartingAuth}
            onClick={() => {
              void handleStartGmailAuth();
            }}
            variant="secondary"
          >
            {authButtonLabel}
          </Button>
        </div>
      </section>

      <section className="setup-layout" aria-labelledby="setup-checklist-title">
        <div className="setup-checklist-card">
          <p className="eyebrow">Phase 0 shell</p>
          <h2 id="setup-checklist-title">Setup checklist</h2>
          <p>
            This shell makes the required first-run choices visible while later
            tickets wire the real persistence, secret store, and OAuth flows.
          </p>
          <ol className="setup-checklist">
            {setupSteps.map((step, index) => (
              <li key={step.title}>
                <span aria-hidden="true">{index + 1}</span>
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>

        <aside
          className="setup-privacy-card"
          aria-labelledby="setup-privacy-title"
        >
          <p className="eyebrow">Privacy boundary</p>
          <h2 id="setup-privacy-title">No secrets in this page shell</h2>
          <p>
            Secret material stays behind SecretStore-owned backend boundaries.
            This UI only names the choices the setup API shell will validate.
          </p>
        </aside>

        <section
          className="setup-gmail-card"
          aria-labelledby="setup-gmail-title"
        >
          <p className="eyebrow">Gmail auth</p>
          <h2 id="setup-gmail-title">Gmail callback status</h2>
          {gmailConnected ? (
            <Alert role="status" title="Gmail callback complete" tone="success">
              <p>
                A non-secret Gmail connection is stored locally. OAuth token
                material remains behind SecretStore and is never returned to the
                setup page.
              </p>
            </Alert>
          ) : (
            <Alert
              role="status"
              title={
                authorization
                  ? "Ready to authorize read-only Gmail access"
                  : "Waiting for Gmail callback"
              }
              tone={authorization ? "info" : "warning"}
            >
              <p>
                Start the backend-built OAuth flow, approve only the read-only
                Gmail scope, then return here after the backend callback stores
                connection metadata.
              </p>
            </Alert>
          )}

          {authorization ? (
            <div className="setup-oauth-result">
              <a
                className="setup-oauth-link"
                href={authorization.authorization_url}
              >
                Continue to Google
              </a>
              <p>
                Requested scope: {authorization.requested_scopes.join(", ")}
              </p>
            </div>
          ) : null}

          {gmailAuthError ? (
            <Alert title="Gmail auth failed" tone="danger">
              <p>{gmailAuthError}</p>
            </Alert>
          ) : null}
        </section>
      </section>

      <section
        className="wizard-copy"
        id="setup-choices"
        aria-labelledby="setup-choices-title"
      >
        <div className="section-heading">
          <p className="eyebrow">Required choices</p>
          <h2 id="setup-choices-title">
            The wizard must make each privacy and provider choice explicit.
          </h2>
          <p>
            These cards keep setup aligned with FR-0 and FR-6 without
            implementing later provider auth or secret persistence work.
          </p>
        </div>

        <div className="wizard-grid">
          {setupWizardSections.map((section) => (
            <article className="wizard-card" key={section.title}>
              <h3>{section.title}</h3>
              <p>{section.body}</p>
              <ul>
                {section.options.map((option) => (
                  <li key={option.label}>
                    <strong>{option.label}</strong>
                    <span>{option.body}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
