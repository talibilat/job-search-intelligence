import { useEffect, useId, useState } from "react";

import {
  classificationEstimateClassificationEstimateGet,
  classificationReprocessingPlanClassificationReprocessingPlanGet,
  classificationRunClassificationRunPost,
  pipelineStatusPipelineStatusGet,
  type ClassificationPreRunEstimate,
  type ClassificationReprocessingPlan,
  type ClassificationRunResponse,
  type PipelineStatus,
} from "../api";
import { Alert, Button } from "./ui";

const numberFormatter = new Intl.NumberFormat("en-US");
const pipelinePollIntervalMs = 10000;

interface NextActionCopy {
  title: string;
  tone: "danger" | "info" | "success" | "warning";
}

interface StageInfo {
  dataSource: string;
  dataTable: string;
  howItWorks: string;
  missingData: string;
}

const nextActionCopy: Record<PipelineStatus["next_action"], NextActionCopy> = {
  connect_gmail: { title: "Connect Gmail to start", tone: "warning" },
  continue_backfill: {
    title: "Historical backfill is still in progress",
    tone: "info",
  },
  inspect_error: { title: "The last sync run failed", tone: "danger" },
  review_dashboard: { title: "Pipeline is up to date", tone: "success" },
  run_classification: {
    title: "Candidates are waiting for classification",
    tone: "warning",
  },
  run_sync: { title: "Run your first sync", tone: "warning" },
  wait_for_sync: { title: "Sync is running", tone: "info" },
};

function StageCount({
  definition,
  info,
  label,
  value,
}: {
  definition: string;
  info?: StageInfo;
  label: string;
  value: string;
}) {
  return (
    <article className="pipeline-panel__stage">
      <p className="pipeline-panel__stage-value">{value}</p>
      <div className="pipeline-panel__stage-heading">
        <p className="pipeline-panel__stage-label">{label}</p>
        {info ? <StageCountInfo info={info} label={label} /> : null}
      </div>
      <p className="pipeline-panel__stage-definition">{definition}</p>
    </article>
  );
}

function StageCountInfo({ info, label }: { info: StageInfo; label: string }) {
  const infoId = useId();
  const [isInfoPinned, setIsInfoPinned] = useState(false);
  const [isInfoPreviewed, setIsInfoPreviewed] = useState(false);
  const [isInfoDismissed, setIsInfoDismissed] = useState(false);
  const isInfoOpen = isInfoPinned || (isInfoPreviewed && !isInfoDismissed);

  return (
    <div className="pipeline-panel__stage-info">
      <Button
        aria-controls={infoId}
        aria-expanded={isInfoOpen}
        aria-label={`About ${label}`}
        className="pipeline-panel__stage-info-button"
        onBlur={() => {
          setIsInfoPreviewed(false);
          setIsInfoDismissed(false);
        }}
        onClick={() => {
          if (isInfoOpen) {
            setIsInfoPinned(false);
            setIsInfoPreviewed(false);
            setIsInfoDismissed(true);
            return;
          }

          setIsInfoPinned(true);
          setIsInfoDismissed(false);
        }}
        onFocus={() => {
          setIsInfoPreviewed(true);
          setIsInfoDismissed(false);
        }}
        onMouseEnter={() => {
          setIsInfoPreviewed(true);
          setIsInfoDismissed(false);
        }}
        onMouseLeave={() => {
          setIsInfoPreviewed(false);
          setIsInfoDismissed(false);
        }}
        variant="ghost"
      >
        i
      </Button>
      {isInfoOpen ? (
        <div className="pipeline-panel__stage-info-panel" id={infoId}>
          <p>{info.howItWorks}</p>
          <dl>
            <div>
              <dt>Data source</dt>
              <dd>Data source: {info.dataSource}</dd>
            </div>
            <div>
              <dt>Table</dt>
              <dd>Table: {info.dataTable}</dd>
            </div>
            <div>
              <dt>If values are zero or missing</dt>
              <dd>{info.missingData}</dd>
            </div>
          </dl>
        </div>
      ) : null}
    </div>
  );
}

function classificationResultSummary(result: ClassificationRunResponse) {
  const classified = numberFormatter.format(result.classified_count);
  const applications = numberFormatter.format(result.applications_upserted ?? 0);
  const events = numberFormatter.format(result.events_upserted ?? 0);
  const malformed =
    result.malformed_count > 0
      ? ` ${numberFormatter.format(result.malformed_count)} responses were malformed and quarantined.`
      : "";
  return (
    `Classified ${classified} candidate emails, upserted ${applications} ` +
    `applications and ${events} timeline events.${malformed}`
  );
}

function formatEstimatedCost(estimate: ClassificationPreRunEstimate) {
  if (!estimate.cost_estimate_available || estimate.estimated_cost_usd == null) {
    return "Cost estimate unavailable";
  }

  return `Estimated cost $${estimate.estimated_cost_usd.toFixed(2)} ${estimate.currency ?? "USD"}`;
}

function pluralizeCount(
  value: number,
  singular: string,
  plural = `${singular}s`,
) {
  return `${numberFormatter.format(value)} ${value === 1 ? singular : plural}`;
}

export function PipelineActivityPanel() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isClassifying, setIsClassifying] = useState(false);
  const [classificationMessage, setClassificationMessage] = useState<
    string | null
  >(null);
  const [classificationError, setClassificationError] = useState<
    string | null
  >(null);
  const [classificationEstimate, setClassificationEstimate] =
    useState<ClassificationPreRunEstimate | null>(null);
  const [classificationPlan, setClassificationPlan] =
    useState<ClassificationReprocessingPlan | null>(null);
  const [classificationReadinessError, setClassificationReadinessError] =
    useState<string | null>(null);

  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let ignore = false;

    async function loadStatus() {
      try {
        const response = await pipelineStatusPipelineStatusGet();
        if (ignore) {
          return;
        }
        if (response.status === 200) {
          setStatus(response.data);
          setLoadError(null);
        } else {
          setLoadError(
            "Pipeline status is unavailable. Start the local backend to see it.",
          );
        }
      } catch {
        if (!ignore) {
          setLoadError(
            "Pipeline status is unavailable. Start the local backend to see it.",
          );
        }
      }
    }

    async function loadClassificationReadiness() {
      try {
        const [estimateResponse, planResponse] = await Promise.all([
          classificationEstimateClassificationEstimateGet(),
          classificationReprocessingPlanClassificationReprocessingPlanGet(),
        ]);
        if (ignore) {
          return;
        }

        if (estimateResponse.status === 200 && planResponse.status === 200) {
          setClassificationEstimate(estimateResponse.data);
          setClassificationPlan(planResponse.data);
          setClassificationReadinessError(null);
          return;
        }

        setClassificationReadinessError(
          "Classification readiness is unavailable. Start the local backend and configure an LLM provider to see estimates.",
        );
      } catch {
        if (!ignore) {
          setClassificationReadinessError(
            "Classification readiness is unavailable. Start the local backend and configure an LLM provider to see estimates.",
          );
        }
      }
    }

    void loadStatus();
    void loadClassificationReadiness();
    const intervalId = window.setInterval(() => {
      void loadStatus();
      void loadClassificationReadiness();
    }, pipelinePollIntervalMs);
    return () => {
      ignore = true;
      window.clearInterval(intervalId);
    };
  }, [refreshToken]);

  async function handleRunClassification() {
    setIsClassifying(true);
    setClassificationError(null);
    setClassificationMessage(null);
    try {
      const response = await classificationRunClassificationRunPost();
      if (response.status === 200) {
        setClassificationMessage(classificationResultSummary(response.data));
      } else {
        setClassificationError(
          "Classification could not run. Check the configured LLM provider on the Setup page.",
        );
      }
    } catch {
      setClassificationError(
        "Classification could not run. Check the configured LLM provider on the Setup page.",
      );
    } finally {
      setIsClassifying(false);
      setRefreshToken((token) => token + 1);
    }
  }

  if (loadError) {
    return (
      <section aria-labelledby="pipeline-title" className="status-card pipeline-panel">
        <p className="eyebrow">Backend activity</p>
        <h2 id="pipeline-title">Pipeline status</h2>
        <Alert title="Pipeline status unavailable" tone="danger">
          <p>{loadError}</p>
        </Alert>
      </section>
    );
  }

  if (!status) {
    return (
      <section aria-labelledby="pipeline-title" className="status-card pipeline-panel">
        <p className="eyebrow">Backend activity</p>
        <h2 id="pipeline-title">Pipeline status</h2>
        <p>Loading deterministic pipeline counts from the local database.</p>
      </section>
    );
  }

  const actionCopy = nextActionCopy[status.next_action];
  const counts = status.counts;
  const backfillLabel =
    status.backfill_state === "completed"
      ? "Backfill complete"
      : status.backfill_state === "not_started"
        ? "Backfill not started"
        : status.backfill_state === "failed"
          ? "Backfill failed"
          : "Backfill in progress";

  return (
    <section aria-labelledby="pipeline-title" className="status-card pipeline-panel">
      <div className="pipeline-panel__header">
        <div>
          <p className="eyebrow">Backend activity</p>
          <h2 id="pipeline-title">Pipeline status</h2>
        </div>
        <p>
          Every number below is a deterministic count from the local SQLite
          database. Email bodies and secrets never appear here.
        </p>
      </div>

      <div className="pipeline-panel__connection" aria-label="Gmail connection">
        {status.gmail_connected ? (
          <p>
            <strong>Gmail connected:</strong>{" "}
            {status.account_display ?? "account configured"}
          </p>
        ) : (
          <p>
            <strong>Gmail is not connected.</strong>{" "}
            <a href="/setup">Connect it on the Setup page</a> to start syncing.
          </p>
        )}
        <p>
          {backfillLabel} -{" "}
          {numberFormatter.format(status.backfill_pages_processed)} pages and{" "}
          {numberFormatter.format(status.backfill_messages_processed)} provider
          messages processed.{" "}
          {status.incremental_sync_ready
            ? "Incremental sync is active: each sync now fetches only new mail."
            : "Incremental sync starts after the one-time backfill finishes; until then each sync continues the historical walk from newest toward oldest mail."}
        </p>
      </div>

      <Alert role="status" title={actionCopy.title} tone={actionCopy.tone}>
        <p>{status.next_action_reason}</p>
        {status.next_action === "run_classification" ? (
          <Button
            disabled={isClassifying}
            onClick={() => {
              void handleRunClassification();
            }}
          >
            {isClassifying ? "Classifying" : "Run classification"}
          </Button>
        ) : null}
        {status.next_action === "review_dashboard" ? (
          <p>
            <a href="/dashboard">Open the dashboard</a> to see deterministic
            metrics.
          </p>
        ) : null}
      </Alert>

      {classificationMessage ? (
        <Alert title="Classification finished" tone="success">
          <p>{classificationMessage}</p>
        </Alert>
      ) : null}
      {classificationError ? (
        <Alert title="Classification failed" tone="danger">
          <p>{classificationError}</p>
        </Alert>
      ) : null}
      {status.last_error ? (
        <Alert title="Last pipeline error" tone="danger">
          <p>{status.last_error}</p>
        </Alert>
      ) : null}

      <section
        aria-label="Classification readiness"
        className="pipeline-panel__classification-readiness"
      >
        <div>
          <p className="eyebrow">Classification</p>
          <h3>Classification readiness</h3>
        </div>
        {classificationEstimate && classificationPlan ? (
          <div className="pipeline-panel__readiness-grid">
            <article>
              <p className="pipeline-panel__readiness-value">
                {pluralizeCount(
                  classificationPlan.retained_candidate_count,
                  "retained candidate",
                )}
              </p>
              <div className="pipeline-panel__stage-heading">
                <p className="pipeline-panel__readiness-label">
                  Retained classification candidates
                </p>
                <StageCountInfo
                  info={{
                    dataSource: "GET /classification/reprocessing-plan",
                    dataTable: "raw_emails",
                    howItWorks:
                      "Counts retained Gmail candidate bodies that are eligible for the configured classifier before any LLM call runs.",
                    missingData:
                      "Run Gmail sync from this page after connecting Gmail on Setup. If retained candidates are zero, sync has not retained any job-search email bodies for classification yet.",
                  }}
                  label="Retained classification candidates"
                />
              </div>
              <p className="pipeline-panel__readiness-definition">
                Retained bodies eligible for the configured classifier.
              </p>
            </article>
            <article>
              <p className="pipeline-panel__readiness-value">
                {`${numberFormatter.format(classificationPlan.reprocess_count)} need classification`}
              </p>
              <div className="pipeline-panel__stage-heading">
                <p className="pipeline-panel__readiness-label">
                  Classification work waiting
                </p>
                <StageCountInfo
                  info={{
                    dataSource: "GET /classification/reprocessing-plan",
                    dataTable: "email_classifications",
                    howItWorks:
                      "Counts retained candidates that are unclassified or stale for the currently configured model or prompt before a classification run starts.",
                    missingData:
                      "Run classification from this page. If the value is zero, all retained candidates are already classified for the target model and prompt, or sync has not retained candidate bodies yet.",
                  }}
                  label="Classification work waiting"
                />
              </div>
              <p>
                {pluralizeCount(
                  classificationPlan.unclassified_count,
                  "unclassified candidate",
                )}{" "}
                and{" "}
                {pluralizeCount(
                  classificationPlan.stale_prompt_version_count,
                  "stale prompt",
                )}
                .
              </p>
            </article>
            <article>
              <p className="pipeline-panel__readiness-value">
                {pluralizeCount(
                  classificationPlan.stale_model_count,
                  "stale model",
                )}
              </p>
              <div className="pipeline-panel__stage-heading">
                <p className="pipeline-panel__readiness-label">
                  Classification freshness
                </p>
                <StageCountInfo
                  info={{
                    dataSource: "GET /classification/reprocessing-plan",
                    dataTable: "email_classifications",
                    howItWorks:
                      "Compares retained candidates against the configured target model and prompt so stale rows can be reclassified while current rows are skipped.",
                    missingData:
                      "Run classification from this page when stale model or stale prompt counts are non-zero. If every candidate is up to date, this card should show skipped candidates instead of queued work.",
                  }}
                  label="Classification freshness"
                />
              </div>
              <p>
                {pluralizeCount(
                  classificationPlan.up_to_date_count,
                  "up-to-date candidate",
                )}{" "}
                will be skipped.
              </p>
            </article>
            <article>
              <p>
                {`${numberFormatter.format(classificationEstimate.estimated_total_tokens)} estimated tokens`}
              </p>
              <p>{formatEstimatedCost(classificationEstimate)}</p>
            </article>
          </div>
        ) : classificationReadinessError ? (
          <Alert title="Classification readiness unavailable" tone="warning">
            <p>{classificationReadinessError}</p>
          </Alert>
        ) : (
          <p>Loading classification estimate and reprocessing status.</p>
        )}
        {classificationEstimate ? (
          <p className="pipeline-panel__note">
            {`Model ${classificationEstimate.model}, prompt ${classificationEstimate.prompt_version}`}
          </p>
        ) : null}
      </section>

      <div className="pipeline-panel__stages" aria-label="Pipeline stage counts">
        <StageCount
          definition="Gmail metadata rows stored locally (no body text by default)."
          info={{
            dataSource: "GET /pipeline/status",
            dataTable: "raw_emails",
            howItWorks:
              "Counts Gmail metadata rows stored in local SQLite after sync, without exposing provider cursors, secrets, or private email body text.",
            missingData:
              "Run Gmail sync from this page after connecting Gmail on Setup. If the count is zero, the mailbox metadata backfill has not stored any rows yet.",
          }}
          label="Raw emails"
          value={numberFormatter.format(counts.raw_email_count)}
        />
        <StageCount
          definition="Heuristic job-search filter decisions: kept vs skipped."
          info={{
            dataSource: "GET /pipeline/status",
            dataTable: "email_filter_decisions",
            howItWorks:
              "Counts public-safe heuristic audit decisions created during sync: candidate messages kept for later stages and rejected messages skipped before classification.",
            missingData:
              "Run Gmail sync after connecting Gmail on Setup. If both kept and skipped are zero, the broad job-search filter has not evaluated any synced metadata yet.",
          }}
          label="Filter decisions"
          value={`${numberFormatter.format(counts.filter_candidate_count)} kept / ${numberFormatter.format(counts.filter_rejected_count)} skipped`}
        />
        <StageCount
          definition="Likely job emails whose body text is kept locally for classification."
          info={{
            dataSource: "GET /pipeline/status",
            dataTable: "raw_emails",
            howItWorks:
              "Counts raw email rows whose body_retention_state shows selected job-search candidate bodies are retained locally for classification, while metadata-only rows keep private body text out of this stage.",
            missingData:
              "Run Gmail sync after connecting Gmail on Setup. If this count is zero while filter candidates exist, retained body fetching has not completed or the provider could not fetch selected candidate bodies.",
          }}
          label="Retained bodies"
          value={numberFormatter.format(counts.retained_body_count)}
        />
        <StageCount
          definition="Retained candidates the model has categorized (job-related shown)."
          info={{
            dataSource: "GET /pipeline/status",
            dataTable: "email_classifications",
            howItWorks:
              "Counts accepted classification rows produced from retained candidate emails, with the job-related subset shown separately so you can see how much synced evidence reached model classification.",
            missingData:
              "Run classification from this page after sync has retained candidate bodies. If this count is zero while retained bodies exist, the classification run has not completed or the configured LLM provider needs attention on Setup.",
          }}
          label="Classified"
          value={`${numberFormatter.format(counts.classified_email_count)} (${numberFormatter.format(counts.job_related_email_count)} job-related)`}
        />
        <StageCount
          definition="Job applications reconstructed from classified email, with timeline events."
          info={{
            dataSource: "GET /pipeline/status",
            dataTable: "applications, application_events",
            howItWorks:
              "Counts reconstructed application records and their deterministic timeline events created by aggregation after accepted job-related classifications are stored.",
            missingData:
              "Run classification after sync has retained candidate bodies. If applications are zero while classified job-related emails exist, aggregation has not created application timeline records yet or classified emails did not contain application evidence.",
          }}
          label="Applications"
          value={`${numberFormatter.format(counts.application_count)} (${numberFormatter.format(counts.application_event_count)} events)`}
        />
      </div>

      {status.unclassified_retained_count > 0 &&
      status.next_action !== "run_classification" ? (
        <p className="pipeline-panel__note">
          {numberFormatter.format(status.unclassified_retained_count)} retained
          candidate emails are waiting for classification.
        </p>
      ) : null}
    </section>
  );
}
