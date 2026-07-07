import { useEffect, useState } from "react";

import {
  getMetricsSummaryMetricsSummaryGet,
  type MetricsSummaryResponse,
} from "../api";
import { ChartPanel } from "../components/charts";

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

const metricPlaceholders = [
  {
    label: "Total applications",
    note: "Counted from applications",
  },
  {
    label: "Response rate",
    note: "Calculated deterministically",
  },
  {
    label: "Live applications",
    note: "Derived from event timeline",
  },
] as const;

export function DashboardPage() {
  const [summary, setSummary] = useState<MetricsSummaryResponse | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(true);

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

  const distinctCompanyValue = summaryMetricValue(
    isLoadingSummary,
    summary?.distinct_company_count,
  );
  const interviewInvitationValue = summaryMetricValue(
    isLoadingSummary,
    summary?.interview_invitation_count,
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
          Q-07 now reports interview invitations from the local application
          event timeline, while the remaining dashboard questions stay clearly
          marked as pending.
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
              <p className="metric-placeholder__label">Distinct companies</p>
              <p className="metric-placeholder__value">{distinctCompanyValue}</p>
              <p className="dashboard-card__meta">
                Q-03 counted from normalized applications
              </p>
            </article>
            <article className="metric-placeholder">
              <h3 className="metric-placeholder__label">Interview invitations</h3>
              <p className="metric-placeholder__value">{interviewInvitationValue}</p>
              <p className="dashboard-card__meta">
                Q-07 - Counted from interview_scheduled events
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

      <ChartPanel
        description="Dashboard charts stay empty until deterministic metrics endpoints can supply reconciled values from the local SQLite database."
        emptyState={{
          title: "Dashboard metrics pending",
          description:
            "Deterministic metrics will appear here after the metrics API is available.",
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
