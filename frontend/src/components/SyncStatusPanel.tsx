import { useEffect, useState } from "react";

import {
  syncRecentEmailsSyncRecentEmailsGet,
  syncNowSyncPost,
  syncStatusSyncStatusGet,
  type EmailSyncOptions,
  type EmailSyncStatus,
  type RawEmailPreviewRecord,
} from "../api";
import { Alert, Button, DataTable, FormField, TextInput } from "./ui";
import type { DataTableColumn } from "./ui";

const numberFormatter = new Intl.NumberFormat("en-US");
const syncStatusPollIntervalMs = 5000;
const recentEmailPreviewLimit = 50;
type SyncLimitField =
  | "beforeDate"
  | "maxAgeDays"
  | "maxMessages"
  | "maxPages"
  | "sinceDate";
type SyncLimitErrors = Partial<Record<SyncLimitField, string>>;

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

function formatEmailTimestamp(value: string | null, label: string) {
  if (!value) {
    return `${label} pending`;
  }

  return `${label} ${dateFormatter.format(new Date(value))}`;
}

function emailRetentionLabel(email: RawEmailPreviewRecord) {
  return email.has_retained_body ? "retained body" : "metadata only";
}

function formatSubjectPresence(email: RawEmailPreviewRecord) {
  return email.subject_present ? "Subject captured" : "No subject";
}

function formatEmailDomains(domains: string[]) {
  return domains.length > 0 ? domains.join(", ") : "Unknown recipient";
}

function recentEmailRowKey(email: RawEmailPreviewRecord) {
  return [
    email.provider,
    email.ingested_at,
    email.sent_at,
    email.from_domain,
    email.subject_present ? "subject" : "no-subject",
    email.filter_outcome,
    email.filter_reason,
  ]
    .filter(Boolean)
    .join(":");
}

const recentEmailColumns: readonly DataTableColumn<RawEmailPreviewRecord>[] = [
  {
    header: "Subject",
    key: "subject_present",
    render: formatSubjectPresence,
  },
  {
    header: "From domain",
    key: "from_domain",
    render: (email) => email.from_domain ?? "Unknown sender",
  },
  {
    header: "To domains",
    key: "to_domains",
    render: (email) => formatEmailDomains(email.to_domains),
  },
  {
    header: "Sent",
    key: "sent_at",
    render: (email) => formatEmailTimestamp(email.sent_at, "Sent"),
  },
  {
    header: "Retention",
    key: "body_retention_state",
    render: emailRetentionLabel,
  },
  {
    header: "Filter",
    key: "filter_outcome",
    render: (email) => email.filter_outcome ?? "not evaluated",
  },
];

function SyncMetric({ label, value }: { label: string; value: string }) {
  return (
    <article className="sync-panel__metric">
      <p className="sync-panel__metric-value">{value}</p>
      <p className="sync-panel__metric-label">{label}</p>
    </article>
  );
}

function optionalPositiveInteger(value: string) {
  const trimmedValue = value.trim();
  if (!trimmedValue) {
    return null;
  }

  const parsedValue = Number.parseInt(trimmedValue, 10);
  return Number.isFinite(parsedValue) && parsedValue > 0
    ? parsedValue
    : null;
}

function validatePositiveInteger(value: string, label: string) {
  const trimmedValue = value.trim();
  if (!trimmedValue) {
    return null;
  }

  const parsedValue = Number.parseInt(trimmedValue, 10);
  if (!Number.isFinite(parsedValue) || parsedValue < 1) {
    return `${label} must be at least 1.`;
  }

  return null;
}

function buildSyncOptions({
  beforeDate,
  maxAgeDays,
  maxMessages,
  maxPages,
  sinceDate,
}: {
  beforeDate: string;
  maxAgeDays: string;
  maxMessages: string;
  maxPages: string;
  sinceDate: string;
}) {
  const errors: SyncLimitErrors = {};
  const maxMessagesError = validatePositiveInteger(maxMessages, "Email count");
  const maxAgeDaysError = validatePositiveInteger(maxAgeDays, "Max age");
  const maxPagesError = validatePositiveInteger(maxPages, "Max pages");

  if (maxMessagesError) {
    errors.maxMessages = maxMessagesError;
  }
  if (maxAgeDaysError) {
    errors.maxAgeDays = maxAgeDaysError;
  }
  if (maxPagesError) {
    errors.maxPages = maxPagesError;
  }
  if (sinceDate && beforeDate && sinceDate >= beforeDate) {
    errors.beforeDate = "Before date must be after since date.";
  }

  if (Object.keys(errors).length > 0) {
    return { errors, options: null };
  }

  return {
    errors,
    options: {
      before_date: beforeDate || null,
      max_age_days: optionalPositiveInteger(maxAgeDays),
      max_messages: optionalPositiveInteger(maxMessages),
      max_pages: optionalPositiveInteger(maxPages),
      since_date: sinceDate || null,
    } satisfies EmailSyncOptions,
  };
}

function progressLabel(status: EmailSyncStatus | null) {
  const progress = status?.progress ?? 0;
  const percentage = Math.round(progress * 100);
  if (status?.target_message_count) {
    return `${percentage}% of ${numberFormatter.format(status.target_message_count)} messages`;
  }

  if (status?.state === "running") {
    return "Sync in progress";
  }

  if (status?.state === "succeeded") {
    return "Sync complete";
  }

  return "Progress pending";
}

function optimisticRunningStatus(
  previousStatus: EmailSyncStatus | null,
  options: EmailSyncOptions,
): EmailSyncStatus {
  return {
    account_id: previousStatus?.account_id ?? null,
    finished_at: null,
    last_error: null,
    message_count: 0,
    mode: previousStatus?.mode ?? "full_backfill",
    page_count: 0,
    progress: 0,
    provider: previousStatus?.provider ?? null,
    raw_email_count: previousStatus?.raw_email_count ?? 0,
    recovered_from_expired_cursor: false,
    started_at: new Date().toISOString(),
    state: "running",
    target_message_count: options.max_messages ?? null,
  };
}

export function SyncStatusPanel() {
  const [status, setStatus] = useState<EmailSyncStatus | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [isStartingSync, setIsStartingSync] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [maxMessages, setMaxMessages] = useState("");
  const [sinceDate, setSinceDate] = useState("");
  const [beforeDate, setBeforeDate] = useState("");
  const [maxAgeDays, setMaxAgeDays] = useState("");
  const [maxPages, setMaxPages] = useState("");
  const [syncLimitErrors, setSyncLimitErrors] = useState<SyncLimitErrors>({});
  const [recentEmails, setRecentEmails] = useState<RawEmailPreviewRecord[]>([]);
  const [recentEmailsError, setRecentEmailsError] = useState<string | null>(
    null,
  );

  useEffect(() => {
    let ignore = false;

    async function loadRecentEmails() {
      try {
        const response = await syncRecentEmailsSyncRecentEmailsGet({
          limit: recentEmailPreviewLimit,
        });
        if (response.status !== 200) {
          if (!ignore) {
            setRecentEmailsError(
              apiErrorMessage(
                response.data,
                "Recent synced email metadata is unavailable.",
              ),
            );
          }
          return;
        }

        if (!ignore) {
          setRecentEmails(response.data);
          setRecentEmailsError(null);
        }
      } catch {
        if (!ignore) {
          setRecentEmailsError(
            "Recent synced email metadata is unavailable.",
          );
        }
      }
    }

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
        void loadRecentEmails();
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

    async function loadRecentEmails() {
      try {
        const response = await syncRecentEmailsSyncRecentEmailsGet({
          limit: recentEmailPreviewLimit,
        });
        if (response.status === 200 && !ignore) {
          setRecentEmails(response.data);
          setRecentEmailsError(null);
        }
      } catch {
        if (!ignore) {
          setRecentEmailsError(
            "Recent synced email metadata is unavailable.",
          );
        }
      }
    }

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
        void loadRecentEmails();
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
    const { errors, options } = buildSyncOptions({
      beforeDate,
      maxAgeDays,
      maxMessages,
      maxPages,
      sinceDate,
    });
    setSyncLimitErrors(errors);
    if (!options) {
      return;
    }

    setIsStartingSync(true);
    setErrorMessage(null);
    setStatus((currentStatus) => optimisticRunningStatus(currentStatus, options));

    try {
      const response = await syncNowSyncPost(options);
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
      try {
        const recentResponse = await syncRecentEmailsSyncRecentEmailsGet({
          limit: recentEmailPreviewLimit,
        });
        if (recentResponse.status === 200) {
          setRecentEmails(recentResponse.data);
          setRecentEmailsError(null);
        }
      } catch {
        setRecentEmailsError("Recent synced email metadata is unavailable.");
      }
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
  const syncButtonLabel =
    currentState === "running"
      ? "Sync running"
      : isStartingSync
        ? "Starting sync"
        : "Sync now";
  const progressValue = Math.round((status?.progress ?? 0) * 100);
  const showIndeterminateProgress =
    currentState === "running" &&
    (isStartingSync || status?.target_message_count == null);

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
        <div className="sync-panel__controls" aria-label="Sync extraction limits">
          <FormField
            error={syncLimitErrors.maxMessages}
            hint="Caps the number of metadata records extracted in this run."
            htmlFor="sync-max-messages"
            label="Email count"
          >
            <TextInput
              inputMode="numeric"
              min={1}
              onChange={(event) => {
                setMaxMessages(event.target.value);
                setSyncLimitErrors((currentErrors) => ({
                  ...currentErrors,
                  maxMessages: undefined,
                }));
              }}
              placeholder="500"
              type="number"
              value={maxMessages}
            />
          </FormField>
          <FormField
            hint="Only list messages on or after this date."
            htmlFor="sync-since-date"
            label="Since date"
          >
            <TextInput
              onChange={(event) => {
                setSinceDate(event.target.value);
                setSyncLimitErrors((currentErrors) => ({
                  ...currentErrors,
                  beforeDate: undefined,
                }));
              }}
              type="date"
              value={sinceDate}
            />
          </FormField>
          <FormField
            error={syncLimitErrors.beforeDate}
            hint="Stop before this date."
            htmlFor="sync-before-date"
            label="Before date"
          >
            <TextInput
              onChange={(event) => {
                setBeforeDate(event.target.value);
                setSyncLimitErrors((currentErrors) => ({
                  ...currentErrors,
                  beforeDate: undefined,
                }));
              }}
              type="date"
              value={beforeDate}
            />
          </FormField>
          <FormField
            error={syncLimitErrors.maxAgeDays}
            hint="Restricts extraction to recent messages."
            htmlFor="sync-max-age-days"
            label="Max age"
          >
            <TextInput
              inputMode="numeric"
              min={1}
              onChange={(event) => {
                setMaxAgeDays(event.target.value);
                setSyncLimitErrors((currentErrors) => ({
                  ...currentErrors,
                  maxAgeDays: undefined,
                }));
              }}
              placeholder="90"
              type="number"
              value={maxAgeDays}
            />
          </FormField>
          <FormField
            error={syncLimitErrors.maxPages}
            hint="Limits provider pagination for quick trial runs."
            htmlFor="sync-max-pages"
            label="Max pages"
          >
            <TextInput
              inputMode="numeric"
              min={1}
              onChange={(event) => {
                setMaxPages(event.target.value);
                setSyncLimitErrors((currentErrors) => ({
                  ...currentErrors,
                  maxPages: undefined,
                }));
              }}
              placeholder="3"
              type="number"
              value={maxPages}
            />
          </FormField>
        </div>
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

            <div className="sync-panel__progress-block">
              <div className="sync-panel__progress-meta">
                <p>{progressLabel(status)}</p>
                <p>{numberFormatter.format(progressValue)}%</p>
              </div>
              <div
                aria-label="Sync progress"
                aria-valuemax={100}
                aria-valuemin={0}
                aria-valuenow={showIndeterminateProgress ? undefined : progressValue}
                className={[
                  "sync-panel__progress",
                  showIndeterminateProgress
                    ? "sync-panel__progress--indeterminate"
                    : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                role="progressbar"
              >
                <span style={{ width: `${progressValue}%` }} />
              </div>
            </div>

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

            <section
              aria-labelledby="sync-recent-emails-title"
              className="sync-panel__recent"
            >
              <div className="sync-panel__recent-header">
                <div>
                  <p className="eyebrow">Stored email metadata</p>
                  <h3 id="sync-recent-emails-title">Recently synced emails</h3>
                </div>
                <p>
                  Sanitized metadata from raw_emails. Body text, snippets, and
                  provider message identifiers stay hidden.
                </p>
              </div>

              {recentEmails.length > 0 ? (
                <div
                  aria-label="Recently synced email metadata"
                  className="sync-panel__recent-scroll"
                  role="region"
                >
                  <DataTable
                    caption="Recently synced email metadata"
                    columns={recentEmailColumns}
                    rowKey={recentEmailRowKey}
                    rows={recentEmails}
                  />
                </div>
              ) : (
                <p className="sync-panel__recent-empty">
                  No synced email metadata is stored yet.
                </p>
              )}

              {recentEmailsError ? (
                <Alert title="Recent email metadata unavailable" tone="warning">
                  <p>{recentEmailsError}</p>
                </Alert>
              ) : null}
            </section>
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
