import { useEffect, useState } from "react";

import {
  syncNowSyncPost,
  syncStatusSyncStatusGet,
  type EmailSyncStatus,
} from "./api";
import { ChartPanel } from "./components/charts";
import { Alert, Button } from "./components/ui";
import Chat from "./pages/Chat";
import { DashboardPage } from "./pages/DashboardPage";
import { Insights } from "./pages/Insights";
import { SetupPage } from "./pages/SetupPage";

const phaseItems = [
  "Connect Gmail through a local-only setup flow",
  "Reconstruct applications from job-search email history",
  "Answer factual dashboard questions from deterministic data",
] as const;

const navigationItems = [
  { href: "/", label: "Overview" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/setup", label: "Setup" },
  { href: "/insights", label: "Insights" },
  { href: "/chat", label: "Chat" },
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

function formatLabel(value: string | null | undefined) {
  if (!value) {
    return "Not reported";
  }

  return value
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function formatCount(value: number | undefined, singular: string, plural: string) {
  const count = value ?? 0;
  return `${count} ${count === 1 ? singular : plural}`;
}

function syncStatusTitle(status: EmailSyncStatus | null) {
  if (!status) {
    return "Current sync state: Unknown";
  }

  if (status.state === "succeeded") {
    return "Last sync succeeded";
  }

  if (status.state === "failed") {
    return "Last sync failed";
  }

  if (status.state === "running") {
    return "Sync is running";
  }

  return `Current sync state: ${formatLabel(status.state)}`;
}

function SyncActionPanel() {
  const [syncStatus, setSyncStatus] = useState<EmailSyncStatus | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;

    async function loadSyncStatus() {
      setIsLoadingStatus(true);
      try {
        const response = await syncStatusSyncStatusGet();
        if (!ignore) {
          setSyncStatus(response.data);
        }
      } catch {
        if (!ignore) {
          setSyncError(
            "Sync status is unavailable. Start the local backend before syncing.",
          );
        }
      } finally {
        if (!ignore) {
          setIsLoadingStatus(false);
        }
      }
    }

    void loadSyncStatus();

    return () => {
      ignore = true;
    };
  }, []);

  async function handleSyncNow() {
    setIsSyncing(true);
    setSyncError(null);

    try {
      const response = await syncNowSyncPost();
      if (response.status !== 200) {
        setSyncError(
          apiErrorMessage(
            response.data,
            "Sync could not start. Check the local backend and Gmail setup.",
          ),
        );
        return;
      }

      setSyncStatus(response.data);
    } catch {
      setSyncError(
        "Sync could not start. Check that the local backend is running.",
      );
    } finally {
      setIsSyncing(false);
    }
  }

  const isRunning = syncStatus?.state === "running";
  const syncButtonLabel = isSyncing || isRunning ? "Syncing" : "Sync now";

  return (
    <div className="sync-action-panel">
      <div className="sync-status-summary" role="status" aria-live="polite">
        <p className="sync-status-summary__title">
          {isLoadingStatus ? "Loading sync status" : syncStatusTitle(syncStatus)}
        </p>
        <dl className="sync-metrics">
          <div>
            <dt>Mode</dt>
            <dd>{formatLabel(syncStatus?.mode)}</dd>
          </div>
          <div>
            <dt>Messages</dt>
            <dd>{formatCount(syncStatus?.message_count, "message", "messages")}</dd>
          </div>
          <div>
            <dt>Raw emails</dt>
            <dd>
              {formatCount(syncStatus?.raw_email_count, "raw email", "raw emails")}
            </dd>
          </div>
        </dl>
      </div>

      <div className="sync-actions">
        <Button
          disabled={isLoadingStatus || isSyncing || isRunning}
          onClick={() => {
            void handleSyncNow();
          }}
        >
          {syncButtonLabel}
        </Button>
        <p className="sync-actions__hint">
          Uses the local backend sync API. Gmail data stays in the local SQLite
          store and OAuth tokens stay behind SecretStore.
        </p>
      </div>

      {syncError ? (
        <Alert title="Sync could not start" tone="danger">
          <p>{syncError}</p>
        </Alert>
      ) : null}
    </div>
  );
}

function OverviewPage() {
  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">Phase 0 frontend shell</p>
        <h1 id="page-title">
          JobTracker turns your inbox into job-search intelligence.
        </h1>
        <p className="hero-copy">
          This local-first app will connect to Gmail, reconstruct applications,
          and keep every factual answer grounded in the application timeline.
        </p>
      </section>

      <section className="status-card" aria-labelledby="status-title">
        <div>
          <p className="eyebrow">Current milestone</p>
          <h2 id="status-title">Frontend foundation ready for Phase 0 pages</h2>
        </div>
        <ul>
          {phaseItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="status-card" aria-labelledby="sync-title">
        <div>
          <p className="eyebrow">Sync readiness</p>
          <h2 id="sync-title">Run a local Gmail sync on demand</h2>
        </div>
        <SyncActionPanel />
      </section>

      <ChartPanel
        description="A small accessible wrapper layer is ready for future deterministic dashboard charts, while Phase 0 avoids real dashboard metrics."
        emptyState={{
          title: "Dashboard data pending",
          description:
            "Future deterministic dashboard metrics will render here after the metrics API exists.",
        }}
        title="Chart foundation"
      />
    </main>
  );
}

function App() {
  const routePath = window.location.pathname.replace(/\/+$/, "") || "/";
  const currentPath = navigationItems.some((item) => item.href === routePath)
    ? routePath
    : "/";

  return (
    <>
      <nav className="app-nav" aria-label="Primary">
        <a className="app-nav__brand" href="/">
          JobTracker
        </a>
        <div className="app-nav__links">
          {navigationItems.map((item) => (
            <a
              aria-current={currentPath === item.href ? "page" : undefined}
              className="app-nav__link"
              href={item.href}
              key={item.href}
            >
              {item.label}
            </a>
          ))}
        </div>
      </nav>
      {currentPath === "/setup" ? (
        <SetupPage />
      ) : currentPath === "/dashboard" ? (
        <DashboardPage />
      ) : currentPath === "/insights" ? (
        <Insights />
      ) : currentPath === "/chat" ? (
        <Chat />
      ) : (
        <OverviewPage />
      )}
    </>
  );
}

export default App;
