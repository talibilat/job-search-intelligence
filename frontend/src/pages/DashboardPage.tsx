import { useEffect, useState, type FormEvent } from "react";

import {
  ApplicationSource,
  ApplicationStatus,
  SponsorshipStatus,
  WorkMode,
  getMetricsRatesMetricsRatesGet,
  getMetricsSummaryMetricsSummaryGet,
  listApplicationsApplicationsGet,
  type ApiErrorResponse,
  type ApplicationRecord,
  type ApplicationSource as ApplicationSourceValue,
  type ApplicationStatus as ApplicationStatusValue,
  type ListApplicationsApplicationsGetParams,
  type MetricRate,
  type MetricsSummaryResponse,
  type SponsorshipStatus as SponsorshipStatusValue,
  type WorkMode as WorkModeValue,
} from "../api";
import { ChartPanel } from "../components/charts";
import {
  Alert,
  Button,
  DataTable,
  FormField,
  TextInput,
} from "../components/ui";

type LoadState = "loading" | "loaded" | "error";
type LiveApplicationsState = "loading" | "ready" | "error";
type ResponseRateLoadState = "loading" | "loaded" | "error";

interface DashboardFilters {
  firstSeenFrom: string;
  firstSeenTo: string;
  role: string;
  salaryMax: string;
  salaryMin: string;
  source: ApplicationSourceValue | "";
  sponsorship: SponsorshipStatusValue | "";
  status: ApplicationStatusValue | "";
  workMode: WorkModeValue | "";
}

const emptyFilters: DashboardFilters = {
  firstSeenFrom: "",
  firstSeenTo: "",
  role: "",
  salaryMax: "",
  salaryMin: "",
  source: "",
  sponsorship: "",
  status: "",
  workMode: "",
};

const liveApplicationStatuses = [
  ApplicationStatus.applied,
  ApplicationStatus.in_review,
  ApplicationStatus.assessment,
  ApplicationStatus.interview,
] as const;

const metricPlaceholders: readonly { label: string; note: string }[] = [];

const statusOptions = Object.values(ApplicationStatus);
const sourceOptions = Object.values(ApplicationSource);
const sponsorshipOptions = Object.values(SponsorshipStatus);
const workModeOptions = Object.values(WorkMode);
const numberFormatter = new Intl.NumberFormat("en-US");
const percentageFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 1,
  style: "percent",
});

function titleize(value: string) {
  return value
    .split("_")
    .map((part, index) =>
      index === 0 ? `${part.charAt(0).toUpperCase()}${part.slice(1)}` : part,
    )
    .join(" ");
}

function filterValue<TValue extends string>(
  params: URLSearchParams,
  key: string,
  allowedValues: readonly TValue[],
) {
  const value = params.get(key);
  return value && allowedValues.includes(value as TValue)
    ? (value as TValue)
    : "";
}

function numericFilterText(value: string | null) {
  const trimmed = value?.trim() ?? "";
  if (trimmed.length === 0) {
    return "";
  }

  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? trimmed : "";
}

function filtersFromSearch(search: string): DashboardFilters {
  const params = new URLSearchParams(search);

  return {
    firstSeenFrom: params.get("first_seen_from") ?? "",
    firstSeenTo: params.get("first_seen_to") ?? "",
    role: params.get("role") ?? "",
    salaryMax: numericFilterText(params.get("salary_max")),
    salaryMin: numericFilterText(params.get("salary_min")),
    source: filterValue(params, "source", sourceOptions),
    sponsorship: filterValue(params, "sponsorship", sponsorshipOptions),
    status: filterValue(params, "status", statusOptions),
    workMode: filterValue(params, "work_mode", workModeOptions),
  };
}

function canonicalFilters(filters: DashboardFilters): DashboardFilters {
  return {
    ...filters,
    salaryMax: numericFilterText(filters.salaryMax),
    salaryMin: numericFilterText(filters.salaryMin),
  };
}

function optionalText(value: string) {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function optionalNumber(value: string) {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return undefined;
  }

  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function queryParamsFromFilters(
  filters: DashboardFilters,
): ListApplicationsApplicationsGetParams {
  return {
    first_seen_from: optionalText(filters.firstSeenFrom),
    first_seen_to: optionalText(filters.firstSeenTo),
    role: optionalText(filters.role),
    salary_max: optionalNumber(filters.salaryMax),
    salary_min: optionalNumber(filters.salaryMin),
    source: filters.source || undefined,
    sponsorship: filters.sponsorship || undefined,
    status: filters.status || undefined,
    work_mode: filters.workMode || undefined,
  };
}

function queryStringFromFilters(filters: DashboardFilters) {
  const params = new URLSearchParams();
  const apiParams = queryParamsFromFilters(filters);

  for (const [key, value] of Object.entries(apiParams)) {
    if (value !== undefined) {
      params.set(key, String(value));
    }
  }

  const query = params.toString();
  return query.length > 0 ? `?${query}` : "";
}

function replaceUrlWithFilters(filters: DashboardFilters) {
  const nextPath = `${window.location.pathname}${queryStringFromFilters(filters)}`;
  const currentPath = `${window.location.pathname}${window.location.search}`;
  if (nextPath !== currentPath) {
    window.history.replaceState({}, "", nextPath);
  }
}

function publicError(data: unknown, fallback: string) {
  if (
    typeof data === "object" &&
    data !== null &&
    "error" in data &&
    typeof (data as ApiErrorResponse).error?.message === "string"
  ) {
    return (data as ApiErrorResponse).error.message;
  }

  return fallback;
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

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    timeZone: "UTC",
    timeZoneName: "short",
    year: "numeric",
  }).format(new Date(value));
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

const applicationStatusColumns = [
  {
    key: "company",
    header: "Company",
    render: (row: ApplicationRecord) => (
      <a href={`/applications/${encodeURIComponent(row.id)}`}>{row.company}</a>
    ),
  },
  { key: "role_title", header: "Role" },
  {
    key: "current_status",
    header: "Status",
    render: (row: ApplicationRecord) => (
      <span className={`status-badge status-badge--${row.current_status}`}>
        {titleize(row.current_status)}
      </span>
    ),
  },
  {
    key: "first_seen_at",
    header: "First seen",
    render: (row: ApplicationRecord) => formatDateTime(row.first_seen_at),
  },
  {
    key: "last_activity_at",
    header: "Last activity",
    render: (row: ApplicationRecord) => formatDateTime(row.last_activity_at),
  },
  {
    key: "source",
    header: "Source",
    render: (row: ApplicationRecord) => titleize(row.source),
  },
] as const;

export function DashboardPage() {
  const [summary, setSummary] = useState<MetricsSummaryResponse | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(true);
  const [liveApplications, setLiveApplications] = useState<ApplicationRecord[]>(
    [],
  );
  const [liveApplicationsState, setLiveApplicationsState] =
    useState<LiveApplicationsState>("loading");
  const [responseRate, setResponseRate] = useState<MetricRate | null>(null);
  const [rejectionRate, setRejectionRate] = useState<MetricRate | null>(null);
  const [ghostRate, setGhostRate] = useState<MetricRate | null>(null);
  const [responseRateLoadState, setResponseRateLoadState] =
    useState<ResponseRateLoadState>("loading");
  const [filters, setFilters] = useState<DashboardFilters>(() =>
    filtersFromSearch(window.location.search),
  );
  const [appliedFilters, setAppliedFilters] =
    useState<DashboardFilters>(filters);
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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

    async function loadApplications() {
      setLoadState("loading");
      setErrorMessage(null);
      setApplications([]);

      const response = await listApplicationsApplicationsGet(
        queryParamsFromFilters(appliedFilters),
      );

      if (isCancelled) {
        return;
      }

      if (response.status !== 200) {
        setApplications([]);
        setErrorMessage(
          publicError(response.data, "Application statuses are unavailable."),
        );
        setLoadState("error");
        return;
      }

      setApplications(response.data);
      setLoadState("loaded");
    }

    void loadApplications().catch(() => {
      if (!isCancelled) {
        setApplications([]);
        setErrorMessage(
          "Application statuses are unavailable. Start the local backend to load Q-09.",
        );
        setLoadState("error");
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [appliedFilters]);

  useEffect(() => {
    replaceUrlWithFilters(appliedFilters);

    function handlePopState() {
      const nextFilters = filtersFromSearch(window.location.search);
      replaceUrlWithFilters(nextFilters);
      setFilters(nextFilters);
      setAppliedFilters(nextFilters);
    }

    window.addEventListener("popstate", handlePopState);
    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, [appliedFilters]);

  useEffect(() => {
    let isCancelled = false;

    async function loadResponseRate() {
      try {
        const response = await getMetricsRatesMetricsRatesGet();
        if (!isCancelled) {
          setResponseRate(response.data.overall_response_rate);
          setRejectionRate(response.data.rejection_rate);
          setGhostRate(response.data.ghost_rate);
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

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextFilters = canonicalFilters(filters);
    const nextQuery = queryStringFromFilters(nextFilters);
    window.history.pushState({}, "", `${window.location.pathname}${nextQuery}`);
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
  }

  function clearFilters() {
    window.history.pushState({}, "", window.location.pathname);
    setFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
  }

  const shownStatusCount = new Set(
    applications.map((application) => application.current_status),
  ).size;
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
          Q-01, Q-03, Q-07, Q-08, Q-09, Q-10, Q-11, Q-12, and Q-13 now render
          from deterministic application and metrics endpoints, while remaining
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
            Filter state lives in the URL query string and is passed directly to
            the deterministic applications API.
          </p>
          <form className="dashboard-filter-form" onSubmit={handleSubmit}>
            <div className="dashboard-filter-grid">
              <FormField htmlFor="dashboard-status" label="Status">
                <select
                  className="ui-input"
                  id="dashboard-status"
                  onChange={(event) =>
                    setFilters({
                      ...filters,
                      status: event.target.value as ApplicationStatusValue | "",
                    })
                  }
                  value={filters.status}
                >
                  <option value="">All statuses</option>
                  {statusOptions.map((status) => (
                    <option key={status} value={status}>
                      {titleize(status)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField htmlFor="dashboard-role" label="Role">
                <TextInput
                  id="dashboard-role"
                  onChange={(event) =>
                    setFilters({ ...filters, role: event.target.value })
                  }
                  placeholder="Backend"
                  value={filters.role}
                />
              </FormField>
              <FormField htmlFor="dashboard-source" label="Source">
                <select
                  className="ui-input"
                  id="dashboard-source"
                  onChange={(event) =>
                    setFilters({
                      ...filters,
                      source: event.target.value as ApplicationSourceValue | "",
                    })
                  }
                  value={filters.source}
                >
                  <option value="">All sources</option>
                  {sourceOptions.map((source) => (
                    <option key={source} value={source}>
                      {titleize(source)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField htmlFor="dashboard-sponsorship" label="Sponsorship">
                <select
                  className="ui-input"
                  id="dashboard-sponsorship"
                  onChange={(event) =>
                    setFilters({
                      ...filters,
                      sponsorship: event.target.value as
                        SponsorshipStatusValue | "",
                    })
                  }
                  value={filters.sponsorship}
                >
                  <option value="">All sponsorship</option>
                  {sponsorshipOptions.map((sponsorship) => (
                    <option key={sponsorship} value={sponsorship}>
                      {titleize(sponsorship)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField htmlFor="dashboard-work-mode" label="Work mode">
                <select
                  className="ui-input"
                  id="dashboard-work-mode"
                  onChange={(event) =>
                    setFilters({
                      ...filters,
                      workMode: event.target.value as WorkModeValue | "",
                    })
                  }
                  value={filters.workMode}
                >
                  <option value="">All work modes</option>
                  {workModeOptions.map((workMode) => (
                    <option key={workMode} value={workMode}>
                      {titleize(workMode)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField
                htmlFor="dashboard-first-seen-from"
                label="First seen from"
              >
                <TextInput
                  id="dashboard-first-seen-from"
                  onChange={(event) =>
                    setFilters({
                      ...filters,
                      firstSeenFrom: event.target.value,
                    })
                  }
                  placeholder="2026-07-01T00:00:00Z"
                  value={filters.firstSeenFrom}
                />
              </FormField>
              <FormField
                htmlFor="dashboard-first-seen-to"
                label="First seen to"
              >
                <TextInput
                  id="dashboard-first-seen-to"
                  onChange={(event) =>
                    setFilters({ ...filters, firstSeenTo: event.target.value })
                  }
                  placeholder="2026-07-31T23:59:59Z"
                  value={filters.firstSeenTo}
                />
              </FormField>
              <FormField htmlFor="dashboard-salary-min" label="Salary min">
                <TextInput
                  id="dashboard-salary-min"
                  inputMode="numeric"
                  onChange={(event) =>
                    setFilters({ ...filters, salaryMin: event.target.value })
                  }
                  placeholder="120000"
                  value={filters.salaryMin}
                />
              </FormField>
              <FormField htmlFor="dashboard-salary-max" label="Salary max">
                <TextInput
                  id="dashboard-salary-max"
                  inputMode="numeric"
                  onChange={(event) =>
                    setFilters({ ...filters, salaryMax: event.target.value })
                  }
                  placeholder="180000"
                  value={filters.salaryMax}
                />
              </FormField>
            </div>
            <div className="dashboard-filter-actions">
              <Button type="submit">Apply filters</Button>
              <Button onClick={clearFilters} type="button" variant="secondary">
                Clear filters
              </Button>
            </div>
          </form>
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
            <article className="metric-placeholder">
              <p className="metric-placeholder__label">Applications shown</p>
              <p className="metric-placeholder__value">{applications.length}</p>
              <p className="dashboard-card__meta">Returned by /applications</p>
            </article>
            <article className="metric-placeholder">
              <p className="metric-placeholder__label">Statuses in view</p>
              <p className="metric-placeholder__value">{shownStatusCount}</p>
              <p className="dashboard-card__meta">
                Derived from current_status
              </p>
            </article>
            <article className="metric-placeholder">
              <p className="metric-placeholder__label">Answer</p>
              <p className="metric-placeholder__value">Q-09</p>
              <p className="dashboard-card__meta">
                Per-application status table
              </p>
            </article>
            <article
              aria-label="Response rate metric"
              className="metric-placeholder"
            >
              <p className="metric-placeholder__label">Response rate</p>
              <p className="metric-placeholder__value">
                {formatRateValue(responseRate, responseRateLoadState)}
              </p>
              <p className="dashboard-card__meta">
                {formatResponseRateMeta(responseRate, responseRateLoadState)}
              </p>
            </article>
            <article
              aria-label="Rejection rate metric"
              className="metric-placeholder"
            >
              <p className="metric-placeholder__label">Rejection rate</p>
              <p className="metric-placeholder__value">
                {formatRateValue(rejectionRate, responseRateLoadState)}
              </p>
              <p className="dashboard-card__meta">
                {formatRejectionRateMeta(rejectionRate, responseRateLoadState)}
              </p>
            </article>
            <article aria-label="Ghost rate metric" className="metric-placeholder">
              <p className="metric-placeholder__label">Ghost rate</p>
              <p className="metric-placeholder__value">
                {formatRateValue(ghostRate, responseRateLoadState)}
              </p>
              <p className="dashboard-card__meta">
                {formatGhostRateMeta(ghostRate, responseRateLoadState)}
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
        className="dashboard-card status-table-card"
        aria-labelledby="status-table-title"
      >
        <div>
          <p className="eyebrow">Applications table</p>
          <h2 id="status-table-title">Current status of every application</h2>
        </div>
        {loadState === "loading" ? (
          <p className="dashboard-card__meta">Loading applications...</p>
        ) : null}
        {errorMessage ? (
          <Alert title="Application statuses unavailable" tone="danger">
            <p>{errorMessage}</p>
          </Alert>
        ) : null}
        <DataTable
          caption="Application current statuses"
          columns={applicationStatusColumns}
          emptyMessage={
            loadState === "loaded"
              ? "No applications match these filters."
              : "No application statuses loaded yet."
          }
          rowKey={(row) => row.id}
          rows={applications}
        />
      </section>

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

function formatRateValue(
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

function formatRejectionRateMeta(
  metric: MetricRate | null,
  loadState: ResponseRateLoadState,
) {
  if (loadState === "error") {
    return "Rejection rate is unavailable from the local backend";
  }
  if (loadState === "loading" || metric === null) {
    return "Loading deterministic numerator and denominator";
  }
  if (metric.denominator === 0) {
    return "0 applications in the denominator";
  }
  const applicationLabel =
    metric.denominator === 1 ? "application is" : "applications are";
  return `${numberFormatter.format(metric.numerator)} of ${numberFormatter.format(
    metric.denominator,
  )} ${applicationLabel} rejected`;
}

function formatGhostRateMeta(
  metric: MetricRate | null,
  loadState: ResponseRateLoadState,
) {
  if (loadState === "error") {
    return "Ghost rate is unavailable from the local backend";
  }
  if (loadState === "loading" || metric === null) {
    return "Loading deterministic numerator and denominator";
  }
  if (metric.denominator === 0) {
    return "0 applications in the denominator";
  }
  return `${numberFormatter.format(metric.numerator)} of ${numberFormatter.format(
    metric.denominator,
  )} applications are ghosted or silent past threshold`;
}
