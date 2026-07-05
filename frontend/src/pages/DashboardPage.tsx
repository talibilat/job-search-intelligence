import { ChartPanel } from "../components/charts";

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
  return (
    <main aria-labelledby="dashboard-page-title" className="app-shell dashboard-shell">
      <section className="dashboard-hero" aria-labelledby="dashboard-page-title">
        <p className="eyebrow">Phase 0 dashboard shell</p>
        <h1 id="dashboard-page-title">Dashboard</h1>
        <p className="hero-copy">
          This route is ready for deterministic job-search metrics once the applications API and metrics endpoints exist.
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
            Filter state will live in the URL query string so every deterministic metric uses the same scoped view.
          </p>
          <ul className="filter-placeholder-list">
            {filterPlaceholders.map((filter) => (
              <li key={filter}>{filter}</li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="metrics-overview-title" className="dashboard-card">
          <div>
            <p className="eyebrow">Deterministic source of truth</p>
            <h2 id="metrics-overview-title">Metrics overview</h2>
          </div>
          <div className="dashboard-metric-grid">
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
