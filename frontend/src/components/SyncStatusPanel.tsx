import { useEffect, useState } from "react";

import {
  syncNowSyncPost,
  syncStatusSyncStatusGet,
  type EmailSyncStatus,
} from "../api";
import { Alert, Button } from "./ui";

const numberFormatter = new Intl.NumberFormat("en-US");
const syncStatusPollIntervalMs = 5000;

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  month: "short",
  timeZone: "UTC",
  timeZoneName: "short",
  year: "numeric",
});

const stateCopy: Record<
  EmailSyncStatus["state"],
  {
    description: string;
    title: string;
    tone: "danger" | "info" | "success" | "warning";
  }
> = {
  failed: {
    description: "The last manual sync stopped before finishing.",
    title: "Last sync failed",
    tone: "danger",
  },
  idle: {
    description: "No manual sync has reported progress yet.",
    title: "No sync run yet",
    tone: "warning",
  },
  running: {
    description: "A manual sync is currently updating local Gmail metadata.",
    title: "Sync is running",
    tone: "info",
  },
  succeeded: {
    description: "The most recent manual sync completed successfully.",
    title: "Last sync succeeded",
    tone: "success",
  },
};

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

function formatCount(value: number | undefined, label: string) {
  if (value == null) {
    return `Pending ${label}`;
  }

  return `${numberFormatter.format(value ?? 0)} ${label}`;
}

function formatSyncMode(status: EmailSyncStatus) {
  if (status.mode === "full_backfill") {
    return "Full backfill";
  }

  if (status.mode === "incremental") {
    return "Incremental";
  }

  return "Mode pending";
}

function formatTimestamp(status: EmailSyncStatus) {
  if (status.finished_at) {
    return `Finished ${dateFormatter.format(new Date(status.finished_at))}`;
  }

  if (status.started_at) {
    return `Started ${dateFormatter.format(new Date(status.started_at))}`;
  }

  return "No last run recorded";
}

function providerLabel(status: EmailSyncStatus) {
  if (status.provider === "gmail") {
    return "Gmail";
  }

  return "Provider pending";
}

function SyncMetric({ label, value }: { label: string; value: string }) {
  return (
    <article className="sync-panel__metric">
      <p className="sync-panel__metric-value">{value}</p>
      <p className="sync-panel__metric-label">{label}</p>
    </article>
  );
}

export function SyncStatusPanel() {
  const [status, setStatus] = useState<EmailSyncStatus | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [isStartingSync, setIsStartingSync] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;

    async function loadStatus() {
      setIsLoadingStatus(true);
      try {
        const response = await syncStatusSyncStatusGet();
        if (response.status !== 200) {
          if (!ignore) {
            setErrorMessage(
              apiErrorMessage(
                response.data,
                "Sync status is unavailable. Start the local backend to see progress.",
              ),
            );
          }
          return;
        }

        if (!ignore) {
          setStatus(response.data);
          setErrorMessage(null);
        }
      } catch {
        if (!ignore) {
          setErrorMessage(
            "Sync status is unavailable. Start the local backend to see progress.",
          );
        }
      } finally {
        if (!ignore) {
          setIsLoadingStatus(false);
        }
      }
    }

    void loadStatus();

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (status?.state !== "running" && !isStartingSync) {
      return;
    }

    let ignore = false;

    async function refreshStatus() {
      try {
        const response = await syncStatusSyncStatusGet();
        if (response.status !== 200) {
          if (!ignore) {
            setErrorMessage(
              apiErrorMessage(
                response.data,
                "Sync status is unavailable. Start the local backend to see progress.",
              ),
            );
          }
          return;
        }

        if (!ignore) {
          setStatus(response.data);
          setErrorMessage(null);
        }
      } catch {
        if (!ignore) {
          setErrorMessage(
            "Sync status is unavailable. Start the local backend to see progress.",
          );
        }
      }
    }

    const intervalId = window.setInterval(() => {
      void refreshStatus();
    }, syncStatusPollIntervalMs);

    return () => {
      ignore = true;
      window.clearInterval(intervalId);
    };
  }, [isStartingSync, status?.state]);

  async function handleSyncNow() {
    setIsStartingSync(true);
    setErrorMessage(null);

    try {
      const response = await syncNowSyncPost();
      if (response.status !== 200) {
        setErrorMessage(
          apiErrorMessage(
            response.data,
            "Sync could not start. Check Gmail setup and try again.",
          ),
        );
        return;
      }

      setStatus(response.data);
    } catch {
      setErrorMessage(
        "Sync could not start. Check that the local backend is running.",
      );
    } finally {
      setIsStartingSync(false);
    }
  }

  const currentState = status?.state ?? "idle";
  const copy = stateCopy[currentState];
  const showSyncDetails = status !== null || errorMessage === null;
  const syncButtonDisabled =
    isLoadingStatus || isStartingSync || currentState === "running";
  const syncButtonLabel = isStartingSync
    ? "Starting sync"
    : currentState === "running"
      ? "Sync running"
      : "Sync now";

  return (
    <section className="status-card sync-panel" aria-labelledby="sync-title">
      <div className="sync-panel__header">
        <div>
          <p className="eyebrow">Sync status</p>
          <h2 id="sync-title">Gmail sync progress</h2>
        </div>
        <p>
          Track manual Gmail sync state, progress counts, and the most recent
          run without exposing provider cursors or email content.
        </p>
        <div className="sync-panel__actions">
          <Button
            disabled={syncButtonDisabled}
            onClick={() => {
              void handleSyncNow();
            }}
          >
            {syncButtonLabel}
          </Button>
        </div>
      </div>

      <div className="sync-panel__body" aria-live="polite">
        {showSyncDetails ? (
          <>
            <Alert role="status" title={copy.title} tone={copy.tone}>
              <p>{copy.description}</p>
            </Alert>

            <div
              className="sync-panel__metrics"
              aria-label="Sync progress counts"
            >
              <SyncMetric
                label="Stored in raw_emails"
                value={formatCount(status?.raw_email_count, "raw emails")}
              />
              <SyncMetric
                label="Provider messages"
                value={formatCount(status?.message_count, "messages")}
              />
              <SyncMetric
                label="Pages processed"
                value={formatCount(status?.page_count, "pages")}
              />
            </div>

            <div className="sync-panel__meta-grid">
              <p>{formatTimestamp(status ?? { state: "idle" })}</p>
              <p>{providerLabel(status ?? { state: "idle" })}</p>
              <p>{formatSyncMode(status ?? { state: "idle" })}</p>
              <p>{status?.account_id ?? "Account pending"}</p>
            </div>

            {status?.recovered_from_expired_cursor ? (
              <p className="sync-panel__badge">Recovered expired cursor</p>
            ) : null}

            {status?.last_error ? (
              <Alert title="Last sync error" tone="danger">
                <p>{status.last_error}</p>
              </Alert>
            ) : null}
          </>
        ) : null}

        {errorMessage ? (
          <Alert title="Sync status unavailable" tone="danger">
            <p>{errorMessage}</p>
          </Alert>
        ) : null}
      </div>
    </section>
  );
}
