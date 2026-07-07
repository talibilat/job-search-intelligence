import { useEffect, useState } from "react";

import {
  ApplicationStatus,
  getMetricsRatesMetricsRatesGet,
  getMetricsSummaryMetricsSummaryGet,
  listApplicationsApplicationsGet,
  type ApplicationRecord,
  type MetricRate,
  type MetricsSummaryResponse,
} from "../api";
import { ChartPanel } from "../components/charts";
import { Alert } from "../components/ui";

const liveApplicationStatuses = [
  ApplicationStatus.applied,
  ApplicationStatus.in_review,
  ApplicationStatus.assessment,
  ApplicationStatus.interview,
] as const;

type LiveApplicationsState = "loading" | "ready" | "error";
type ResponseRateLoadState = "loading" | "loaded" | "error";

const numberFormatter = new Intl.NumberFormat("en-US");

const filterPlaceholders = [
  "Status",
  "Date range",
  "Role",
  "Salary band",
  "Source",
  "Sponsorship",
  "Work mode",
] as const;

const metricPlaceholders = [] as const;

const percentageFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 1,
  style: "percent",
});

function liveApplicationsCountLabel(
  state: LiveApplicationsState,
  count: number,
) {
  if (state === "loading") {
    return "Loading";
  }
  if (state === "error") {
    return "Unavailable";
  }

  return count === 1 ? "1 live application" : `${count} live applications`;
}

function statusLabel(status: ApplicationRecord["current_status"]) {
  return status.replaceAll("_", " ");
}

function sortedUniqueApplications(applications: ApplicationRecord[]) {
  const uniqueApplications = new Map<string, ApplicationRecord>();

  for (const application of applications) {
    uniqueApplications.set(application.id, application);
  }

  return [...uniqueApplications.values()].sort((left, right) => {
    const activityOrder =
      Date.parse(left.last_activity_at) - Date.parse(right.last_activity_at);
    if (activityOrder !== 0 && !Number.isNaN(activityOrder)) {
      return activityOrder;
    }

    const activityTextOrder = left.last_activity_at.localeCompare(
      right.last_activity_at,
    );
    if (activityTextOrder !== 0) {
      return activityTextOrder;
    }

    const companyOrder = left.company.localeCompare(right.company);
    if (companyOrder !== 0) {
      return companyOrder;
    }

    return left.id.localeCompare(right.id);
  });
}

export function DashboardPage() {
  const [summary, setSummary] = useState<MetricsSummaryResponse | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(true);
  const [liveApplications, setLiveApplications] = useState<ApplicationRecord[]>(
    [],
  );
  const [liveApplicationsState, setLiveApplicationsState] =
    useState<LiveApplicationsState>("loading");
  const [responseRate, setResponseRate] = useState<MetricRate | null>(null);
  const [responseRateLoadState, setResponseRateLoadState] =
    useState<ResponseRateLoadState>("loading");

  useEffect(() => {
    let ignore = false;

    async function loadSummary() {
      setIsLoadingSummary(true);
      try {
        const response = await getMetricsSummaryMetricsSummaryGet();
        if (response.status === 200 && !ignore) {
          setSummary(response.data);
        }
      } catch {
        if (!ignore) {
          setSummary(null);
        }
      } finally {
        if (!ignore) {
          setIsLoadingSummary(false);
        }
      }
    }

    void loadSummary();

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    let isCancelled = false;

    async function loadLiveApplications() {
      setLiveApplicationsState("loading");

      try {
        const responses = await Promise.all(
          liveApplicationStatuses.map((status) =>
            listApplicationsApplicationsGet({ status }),
          ),
        );
        const nextApplications: ApplicationRecord[] = [];

        for (const response of responses) {
          if (response.status !== 200) {
            if (!isCancelled) {
              setLiveApplications([]);
              setLiveApplicationsState("error");
            }
            return;
          }

          nextApplications.push(...response.data);
        }

        if (!isCancelled) {
          setLiveApplications(sortedUniqueApplications(nextApplications));
          setLiveApplicationsState("ready");
        }
      } catch {
        if (!isCancelled) {
          setLiveApplications([]);
          setLiveApplicationsState("error");
        }
      }
    }

    void loadLiveApplications();

    return () => {
      isCancelled = true;
    };
  }, []);

  useEffect(() => {
    let isCancelled = false;

    async function loadResponseRate() {
      try {
        const response = await getMetricsRatesMetricsRatesGet();
        if (!isCancelled) {
          setResponseRate(response.data.overall_response_rate);
          setResponseRateLoadState("loaded");
        }
      } catch {
        if (!isCancelled) {
          setResponseRateLoadState("error");
        }
      }
    }

    void loadResponseRate();

    return () => {
      isCancelled = true;
    };
  }, []);

  const totalApplicationsValue = summaryMetricValue(
    isLoadingSummary,
    summary?.total_applications,
  );
  const distinctCompanyValue = summaryMetricValue(
    isLoadingSummary,
    summary?.distinct_company_count,
  );
  const interviewInvitationValue = summaryMetricValue(
    isLoadingSummary,
    summary?.interview_invitation_count,
  );
  const offersReceivedValue = summaryMetricValue(
    isLoadingSummary,
    summary?.offers_received,
  );

  return (
    <main
      aria-labelledby="dashboard-page-title"
      className="app-shell dashboard-shell"
    >
      <section
        className="dashboard-hero"
        aria-labelledby="dashboard-page-title"
      >
        <p className="eyebrow">Phase 3 deterministic dashboard</p>
        <h1 id="dashboard-page-title">Dashboard</h1>
        <p className="hero-copy">
          Q-01, Q-03, Q-07, Q-08, Q-10, and Q-11 now render from
          deterministic application and metrics endpoints, while remaining
          dashboard questions stay clearly marked as pending.
        </p>
      </section>

      <div className="dashboard-layout">
        <section
          aria-labelledby="dashboard-filters-title"
          className="dashboard-filter-panel"
        >
          <div>
            <p className="eyebrow">Route-backed controls</p>
            <h2 id="dashboard-filters-title">Dashboard filters</h2>
          </div>
          <p>
            Filter state will live in the URL query string so every
            deterministic metric uses the same scoped view.
          </p>
          <ul className="filter-placeholder-list">
            {filterPlaceholders.map((filter) => (
              <li key={filter}>{filter}</li>
            ))}
          </ul>
        </section>

        <section
          aria-labelledby="metrics-overview-title"
          className="dashboard-card"
        >
          <div>
            <p className="eyebrow">Deterministic source of truth</p>
            <h2 id="metrics-overview-title">Metrics overview</h2>
          </div>
          <div className="dashboard-metric-grid">
            <article className="metric-placeholder">
              <p className="metric-placeholder__label">Total applications</p>
              <p className="metric-placeholder__value">
                {totalApplicationsValue}
              </p>
              <p className="dashboard-card__meta">
                Q-01 reconciled from applications
              </p>
            </article>
            <article className="metric-placeholder">
              <p className="metric-placeholder__label">Distinct companies</p>
              <p className="metric-placeholder__value">
                {distinctCompanyValue}
              </p>
              <p className="dashboard-card__meta">
                Q-03 counted from normalized applications
              </p>
            </article>
            <article className="metric-placeholder">
              <h3 className="metric-placeholder__label">
                Interview invitations
              </h3>
              <p className="metric-placeholder__value">
                {interviewInvitationValue}
              </p>
              <p className="dashboard-card__meta">
                Q-07 - Counted from interview_scheduled events
              </p>
            </article>
            <article className="metric-placeholder">
              <h3 className="metric-placeholder__label">Offers received</h3>
              <p className="metric-placeholder__value">{offersReceivedValue}</p>
              <p className="dashboard-card__meta">
                Q-08 counted from offer events
              </p>
            </article>
            <article
              aria-label="Response rate metric"
              className="metric-placeholder"
            >
              <p className="metric-placeholder__label">Response rate</p>
              <p className="metric-placeholder__value">
                {formatResponseRateValue(responseRate, responseRateLoadState)}
              </p>
              <p className="dashboard-card__meta">
                {formatResponseRateMeta(responseRate, responseRateLoadState)}
              </p>
            </article>
            {metricPlaceholders.map((metric) => (
              <article className="metric-placeholder" key={metric.label}>
                <p className="metric-placeholder__label">{metric.label}</p>
                <p className="metric-placeholder__value">Pending</p>
                <p className="dashboard-card__meta">{metric.note}</p>
              </article>
            ))}
          </div>
        </section>
      </div>

      <section
        aria-labelledby="live-applications-title"
        className="dashboard-card dashboard-live-applications"
      >
        <div className="dashboard-live-applications__header">
          <div>
            <p className="eyebrow">Q-10</p>
            <h2 id="live-applications-title">
              Live applications awaiting response
            </h2>
            <p className="dashboard-card__meta">
              Active applications are pulled from deterministic application rows
              whose current status is applied, in review, assessment, or
              interview.
            </p>
          </div>
          <p className="dashboard-live-count" aria-live="polite" role="status">
            {liveApplicationsCountLabel(
              liveApplicationsState,
              liveApplications.length,
            )}
          </p>
        </div>

        {liveApplicationsState === "error" ? (
          <Alert tone="danger">
            Live applications are unavailable. Start the local backend and try
            again.
          </Alert>
        ) : liveApplicationsState === "loading" ? (
          <p className="dashboard-live-empty">Loading live applications.</p>
        ) : liveApplications.length > 0 ? (
          <ul className="dashboard-live-list">
            {liveApplications.map((application) => (
              <li className="dashboard-live-card" key={application.id}>
                <div>
                  <a
                    className="dashboard-live-card__company"
                    href={`/applications/${encodeURIComponent(application.id)}`}
                  >
                    {application.company}
                  </a>
                  <p className="dashboard-live-card__role">
                    {application.role_title}
                  </p>
                </div>
                <div className="dashboard-live-card__meta">
                  <span>{statusLabel(application.current_status)}</span>
                  <span>
                    Last activity{" "}
                    {new Date(application.last_activity_at).toLocaleDateString(
                      "en-US",
                      {
                        timeZone: "UTC",
                      },
                    )}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="dashboard-live-empty">
            No live applications are awaiting a reply right now.
          </p>
        )}
      </section>

      <ChartPanel
        description="Dashboard charts stay empty until broader deterministic metrics endpoints can supply reconciled series from the local SQLite database."
        emptyState={{
          title: "Dashboard metrics pending",
          description:
            "Broader deterministic metrics will appear here as additional metrics APIs are available.",
        }}
        title="Dashboard metrics shell"
      />
    </main>
  );
}

function summaryMetricValue(isLoading: boolean, value: number | undefined) {
  if (isLoading) {
    return "Loading";
  }
  if (value === undefined) {
    return "Unavailable";
  }
  return numberFormatter.format(value);
}


function formatResponseRateValue(
  metric: MetricRate | null,
  loadState: ResponseRateLoadState,
) {
  if (loadState === "error") {
    return "Unavailable";
  }
  if (loadState === "loading" || metric === null) {
    return "Loading";
  }
  if (metric.rate === null) {
    return "No data";
  }
  return percentageFormatter.format(metric.rate);
}


function formatResponseRateMeta(
  metric: MetricRate | null,
  loadState: ResponseRateLoadState,
) {
  if (loadState === "error") {
    return "Response rate is unavailable from the local backend";
  }
  if (loadState === "loading" || metric === null) {
    return "Loading deterministic numerator and denominator";
  }
  if (metric.denominator === 0) {
    return "0 applications in the denominator";
  }
  return `${numberFormatter.format(metric.numerator)} of ${numberFormatter.format(
    metric.denominator,
  )} applications have response evidence`;
}
