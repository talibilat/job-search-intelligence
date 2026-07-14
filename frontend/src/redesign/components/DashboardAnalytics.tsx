import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import {
  MetricsBreakdownDimension,
  getMetricsBreakdownMetricsBreakdownGet,
  getMetricsDiagnosticsMetricsDiagnosticsGet,
  getMetricsResponseRateTrendMetricsResponseRateTrendGet,
  getMetricsTimeseriesMetricsTimeseriesGet,
  getResponseSilenceMetricMetricsResponseSilenceGet,
  type DiagnosticSegmentComparison,
  type MetricBreakdownRow,
  type MetricsBreakdownDimension as BreakdownDimension,
  type MetricsDiagnosticsResponse,
  type MetricsResponseRateTrendResponse,
  type MetricsTimeseriesResponse,
  type ResponseSilenceMetric,
} from "../../api";
import { apiParamsFromFilters, titleize, type DashboardFilters } from "../dashboardFilters";

interface DashboardAnalyticsProps {
  filters: DashboardFilters;
  publishable: boolean;
  reloadKey: number;
}

const dimensions = Object.values(MetricsBreakdownDimension);
const percent = (value: number | null | undefined) => value == null ? "Not available" : `${(value * 100).toFixed(1)}%`;
const segment = (value: DiagnosticSegmentComparison | null | undefined, metric: "interview_rate" | "response_rate" | "response_rate_lift" = "response_rate") =>
  value ? `${titleize(value.value)} (${titleize(value.dimension)}), ${metric === "response_rate_lift" ? `${((value[metric] ?? 0) * 100).toFixed(1)} pp lift` : percent(value[metric])}` : "Not enough data";

function BreakdownTable({ dimension, rows }: { dimension: BreakdownDimension; rows: MetricBreakdownRow[] }) {
  return (
    <article className="rd-analytics-card">
      <h3>{titleize(dimension)}</h3>
      {rows.length === 0 ? <p>Not enough populated application data.</p> : (
        <div className="rd-table-scroll"><table><thead><tr><th>Segment</th><th>Apps</th><th>Response</th><th>Interview</th><th>Offer</th></tr></thead><tbody>
          {rows.map((row) => <tr key={row.value}><td>{titleize(row.value)}</td><td>{row.application_count}</td><td>{percent(row.response_rate)}</td><td>{percent(row.interview_rate)}</td><td>{percent(row.offer_rate)}</td></tr>)}
        </tbody></table></div>
      )}
    </article>
  );
}

export function DashboardAnalytics({ filters, publishable, reloadKey }: DashboardAnalyticsProps) {
  const [timeseries, setTimeseries] = useState<MetricsTimeseriesResponse | null>(null);
  const [trend, setTrend] = useState<MetricsResponseRateTrendResponse | null>(null);
  const [silence, setSilence] = useState<ResponseSilenceMetric | null>(null);
  const [diagnostics, setDiagnostics] = useState<MetricsDiagnosticsResponse | null>(null);
  const [breakdowns, setBreakdowns] = useState<Partial<Record<BreakdownDimension, MetricBreakdownRow[]>>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      if (!publishable) {
        setLoading(false);
        return;
      }
      const params = apiParamsFromFilters(filters);
      try {
        const [volumeResponse, trendResponse, silenceResponse, diagnosticsResponse, ...breakdownResponses] = await Promise.all([
          getMetricsTimeseriesMetricsTimeseriesGet(params),
          getMetricsResponseRateTrendMetricsResponseRateTrendGet(params),
          getResponseSilenceMetricMetricsResponseSilenceGet(params),
          getMetricsDiagnosticsMetricsDiagnosticsGet(params),
          ...dimensions.map((dimension) => getMetricsBreakdownMetricsBreakdownGet({ ...params, dimension })),
        ]);
        if (cancelled) return;
        if (volumeResponse.status !== 200 || trendResponse.status !== 200 || silenceResponse.status !== 200 || diagnosticsResponse.status !== 200 || breakdownResponses.some((response) => response.status !== 200)) {
          throw new Error("One or more deterministic analytics endpoints failed.");
        }
        setTimeseries(volumeResponse.data);
        setTrend(trendResponse.data);
        setSilence(silenceResponse.data);
        setDiagnostics(diagnosticsResponse.data);
        setBreakdowns(Object.fromEntries(dimensions.map((dimension, index) => [dimension, breakdownResponses[index].status === 200 ? breakdownResponses[index].data.rows : []])));
      } catch {
        if (!cancelled) setError("Complete analytics could not be loaded from the local backend.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [filters, publishable, reloadKey]);

  if (loading) return <p role="status" className="rd-muted">Loading trends, breakdowns, and diagnostics...</p>;
  if (error) return <p role="status" className="rd-error">{error}</p>;
  if (!publishable) return <section className="rd-incomplete"><h2>Analytics will unlock after processing</h2><p>Trends, segmentation, and diagnostics are available, but they are withheld until the current email pipeline reaches dashboard review.</p></section>;

  const diagnosticRows = diagnostics ? [
    ["Q-32", "Successful applications share", diagnostics.successful_application_segments.map((item) => segment(item, "interview_rate")).join("; ") || "Not enough data"],
    ["Q-33", "Rejected or ghosted applications share", diagnostics.negative_outcome_segments.map((item) => segment(item)).join("; ") || "Not enough data"],
    ["Q-34", "Strongest response correlate", segment(diagnostics.strongest_response_correlate, "response_rate_lift")],
    ["Q-35", "Wasted-effort segments", diagnostics.wasted_effort_segments.map((item) => segment(item)).join("; ") || "Not enough data"],
    ["Q-36", "Best ROI source", segment(diagnostics.best_roi_source, "interview_rate")],
    ["Q-37", "Sponsorship response impact", segment(diagnostics.sponsorship_response_impact, "response_rate_lift")],
    ["Q-38", "Skills that sell", diagnostics.selling_skill_segments.map((item) => segment(item, "interview_rate")).join("; ") || "Not enough data"],
    ["Q-38", "Dead-weight skills", diagnostics.dead_weight_skill_segments.map((item) => segment(item, "interview_rate")).join("; ") || "Not enough data"],
    ["Q-39", "Adjacent role suggestions", diagnostics.adjacent_role_suggestions.map((item) => segment(item, "interview_rate")).join("; ") || "Not enough data"],
  ] : [];

  return (
    <section aria-labelledby="complete-analytics-title" className="rd-analytics">
      <div><span className="rd-eyebrow">Deterministic answers</span><h2 id="complete-analytics-title">Trends, silence, and segmentation</h2><p>Every value below comes from the filtered applications table and event timeline.</p></div>
      <div className="rd-chart-grid">
        <article className="rd-analytics-card"><h3>Application volume</h3>{timeseries?.points.length ? <ResponsiveContainer height={220} width="100%"><LineChart data={timeseries.points}><CartesianGrid stroke="#E9E7DF"/><XAxis dataKey="period_start"/><YAxis allowDecimals={false}/><Tooltip/><Line dataKey="application_count" stroke="#1E5136" strokeWidth={3}/></LineChart></ResponsiveContainer> : <p>No application volume in this filter.</p>}</article>
        <article className="rd-analytics-card"><h3>Response rate trend</h3>{trend?.points.length ? <ResponsiveContainer height={220} width="100%"><LineChart data={trend.points.map((point) => ({ ...point, response_rate: point.response_rate == null ? null : point.response_rate * 100 }))}><CartesianGrid stroke="#E9E7DF"/><XAxis dataKey="period_start"/><YAxis unit="%"/><Tooltip/><Line dataKey="response_rate" stroke="#6C5FC7" strokeWidth={3}/></LineChart></ResponsiveContainer> : <p>No response-rate trend in this filter.</p>}</article>
        <article className="rd-analytics-card"><h3>Response versus silence</h3>{silence ? <ResponsiveContainer height={220} width="100%"><BarChart data={[{ label: "Human response", count: silence.human_response_count }, { label: "Silence", count: silence.silent_count }]}><CartesianGrid stroke="#E9E7DF"/><XAxis dataKey="label"/><YAxis allowDecimals={false}/><Tooltip/><Bar dataKey="count" fill="#1E5136" radius={[6,6,0,0]}/></BarChart></ResponsiveContainer> : <p>Not enough response evidence.</p>}</article>
      </div>
      <div><span className="rd-eyebrow">Tier 3</span><h2>Complete breakdowns</h2></div>
      <div className="rd-breakdown-grid">{dimensions.map((dimension) => <BreakdownTable dimension={dimension} key={dimension} rows={breakdowns[dimension] ?? []} />)}</div>
      <div><span className="rd-eyebrow">Phase 3.5</span><h2>Diagnostics</h2></div>
      <div className="rd-diagnostic-grid">{diagnosticRows.map(([question, label, value], index) => <article className="rd-analytics-card" key={`${question}-${index}`}><span className="rd-eyebrow">{question}</span><h3>{label}</h3><p>{value}</p></article>)}</div>
    </section>
  );
}
