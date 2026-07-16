import { useEffect, useState } from "react";

import {
  getMetricsBreakdownMetricsBreakdownGet,
  getMetricsDiagnosticsMetricsDiagnosticsGet,
  type DiagnosticSegmentComparison,
  type MetricBreakdownRow,
  type MetricsDiagnosticsResponse,
  type MetricsFunnelResponse,
  type MetricsRatesResponse,
  type MetricsSummaryResponse,
  type MetricsTimeseriesResponse,
} from "../../../api";
import { publicApiError } from "../../apiError";
import { formatCount, formatHoursAsDuration, formatShortDate } from "../../theme";

interface VisualizedTabProps {
  funnel: MetricsFunnelResponse | null;
  rates: MetricsRatesResponse | null;
  summary: MetricsSummaryResponse | null;
  timeseries: MetricsTimeseriesResponse | null;
}

const FUNNEL_LABELS: Record<string, string> = {
  applied: "Applied",
  screen: "Screen",
  interview: "Interview",
  final: "Final",
  offer: "Offer",
};

function ratePercentLabel(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? "—" : `${Math.round(rate * 1_000) / 10}%`;
}

function safeFormatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : formatCount(value);
}

function BreakdownPanel({
  title,
  metricLabel,
  rows,
  loading,
  error,
  metric,
}: {
  title: string;
  metricLabel: string;
  rows: MetricBreakdownRow[];
  loading: boolean;
  error: string | null;
  metric: "response" | "interview";
}) {
  const maxCount = Math.max(...rows.map((row) => row.application_count), 1);
  return (
    <div style={{ padding: "18px 20px", border: "1px solid #E4E2DA", borderRadius: "14px", background: "#fff", boxShadow: "0 1px 2px rgba(20,25,20,0.04)" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "12px" }}>
        <h3 style={{ margin: 0, fontSize: "13.5px", fontWeight: 700 }}>{title}</h3>
        <span style={{ fontSize: "10.5px", fontWeight: 700, color: "#66886F", letterSpacing: "0.04em", textTransform: "uppercase" }}>
          {metricLabel}
        </span>
      </div>
      {loading ? <p style={{ margin: 0, fontSize: "12px", color: "#9A9F96" }}>Loading…</p> : null}
      {!loading && error ? <p role="alert" style={{ margin: 0, fontSize: "12px", color: "#96403C" }}>{error}</p> : null}
      {!loading && !error && rows.length === 0 ? (
        <p style={{ margin: 0, fontSize: "12px", color: "#9A9F96" }}>Not enough data yet.</p>
      ) : null}
      {!loading && !error && rows.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {rows.slice(0, 6).map((row) => {
            const rate = metric === "response" ? row.response_rate : row.interview_rate;
            return (
              <div key={row.value} style={{ display: "grid", gridTemplateColumns: "104px 1fr 66px", alignItems: "center", gap: "10px" }}>
                <span style={{ fontSize: "12px", color: "#4A5049", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {row.value}
                </span>
                <span style={{ height: "13px", borderRadius: "5px", background: "#EFEEE8", overflow: "hidden", display: "block" }}>
                  <span
                    style={{
                      display: "block",
                      height: "100%",
                      width: `${Math.max(4, (row.application_count / maxCount) * 100)}%`,
                      background: "#1E5136",
                      borderRadius: "5px",
                      opacity: 0.85,
                    }}
                  />
                </span>
                <span style={{ fontSize: "11.5px", color: "#666D66", textAlign: "right", whiteSpace: "nowrap" }}>
                  <strong style={{ color: "#1B201C" }}>{ratePercentLabel(rate)}</strong> · {formatCount(row.application_count)}
                </span>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function SegmentChipList({ segments, tone }: { segments: DiagnosticSegmentComparison[]; tone: "positive" | "negative" }) {
  const colors = tone === "positive" ? { bg: "#E3EFE6", fg: "#1E5136" } : { bg: "#F6E9E7", fg: "#96403C" };
  if (segments.length === 0) {
    return <p style={{ margin: 0, fontSize: "12px", color: "#9A9F96" }}>Not enough data yet.</p>;
  }
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
      {segments.slice(0, 8).map((segment) => {
        const rate = tone === "positive" ? segment.success_rate : segment.negative_rate;
        return (
          <span
            key={`${segment.dimension}-${segment.value}`}
            style={{ display: "inline-flex", alignItems: "center", gap: "6px", padding: "4px 10px", borderRadius: "999px", background: colors.bg, color: colors.fg, fontSize: "12px", fontWeight: 600 }}
          >
            {segment.value}
            <span style={{ opacity: 0.75, fontWeight: 400 }}>{ratePercentLabel(rate)}</span>
          </span>
        );
      })}
    </div>
  );
}

export function VisualizedTab({ funnel, rates, summary, timeseries }: VisualizedTabProps) {
  const [roleRows, setRoleRows] = useState<MetricBreakdownRow[]>([]);
  const [sourceRows, setSourceRows] = useState<MetricBreakdownRow[]>([]);
  const [techRows, setTechRows] = useState<MetricBreakdownRow[]>([]);
  const [salaryRows, setSalaryRows] = useState<MetricBreakdownRow[]>([]);
  const [breakdownLoading, setBreakdownLoading] = useState(true);
  const [breakdownError, setBreakdownError] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState<MetricsDiagnosticsResponse | null>(null);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(true);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setBreakdownLoading(true);
      setBreakdownError(null);
      setDiagnosticsLoading(true);
      setDiagnosticsError(null);
      const [roleResponse, sourceResponse, techResponse, salaryResponse, diagnosticsResponse] = await Promise.all([
        getMetricsBreakdownMetricsBreakdownGet({ dimension: "role" }).catch((error: unknown) => ({ error })),
        getMetricsBreakdownMetricsBreakdownGet({ dimension: "source" }).catch((error: unknown) => ({ error })),
        getMetricsBreakdownMetricsBreakdownGet({ dimension: "tech" }).catch((error: unknown) => ({ error })),
        getMetricsBreakdownMetricsBreakdownGet({ dimension: "salary" }).catch((error: unknown) => ({ error })),
        getMetricsDiagnosticsMetricsDiagnosticsGet().catch((error: unknown) => ({ error })),
      ]);
      if (cancelled) {
        return;
      }
      if ("status" in roleResponse && roleResponse.status === 200) {
        setRoleRows(roleResponse.data.rows);
      } else {
        setBreakdownError(publicApiError("status" in roleResponse ? { response: roleResponse } : roleResponse.error, "Breakdowns could not be loaded."));
      }
      if ("status" in sourceResponse && sourceResponse.status === 200) {
        setSourceRows(sourceResponse.data.rows);
      }
      if ("status" in techResponse && techResponse.status === 200) {
        setTechRows(techResponse.data.rows);
      }
      if ("status" in salaryResponse && salaryResponse.status === 200) {
        setSalaryRows(salaryResponse.data.rows);
      }
      setBreakdownLoading(false);
      if ("status" in diagnosticsResponse && diagnosticsResponse.status === 200) {
        setDiagnostics(diagnosticsResponse.data);
      } else {
        setDiagnostics(null);
        setDiagnosticsError(publicApiError("status" in diagnosticsResponse ? { response: diagnosticsResponse } : diagnosticsResponse.error, "Diagnostics could not be loaded."));
      }
      setDiagnosticsLoading(false);
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const kpis = summary
    ? [
        { label: "Applications", value: safeFormatCount(summary.total_applications), note: `${summary.live_applications ?? "—"} still active` },
        { label: "Companies", value: safeFormatCount(summary.distinct_company_count), note: "Distinct companies applied to" },
        { label: "Response rate", value: ratePercentLabel(rates?.overall_response_rate?.rate), note: "Of all applications" },
        { label: "Interview rate", value: ratePercentLabel(rates?.application_to_interview_rate?.rate), note: "Applied → interview" },
        { label: "Offers", value: safeFormatCount(summary.offers_received), note: "Offers received" },
      ]
    : [];

  const funnelStages = funnel?.stages ?? [];
  const firstStageCount = funnelStages[0]?.count ?? 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      <div>
        <h1 style={{ margin: 0, fontSize: "26px", fontWeight: 700, letterSpacing: "-0.02em" }}>
          Your search, visualized
        </h1>
        <p style={{ margin: "8px 0 0", color: "#666D66", fontSize: "14px", maxWidth: "680px" }}>
          The whole picture on one canvas — the funnel, where you convert, how fast, and what it all adds
          up to. Every panel is computed from your applications.
        </p>
      </div>

      {kpis.length > 0 ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5,minmax(0,1fr))", gap: "12px" }}>
          {kpis.map((kpi) => (
            <div key={kpi.label} style={{ padding: "16px 18px", border: "1px solid #E4E2DA", borderRadius: "14px", background: "#fff", boxShadow: "0 1px 2px rgba(20,25,20,0.04)" }}>
              <div style={{ fontSize: "12px", fontWeight: 600, color: "#666D66" }}>{kpi.label}</div>
              <div style={{ fontSize: "28px", fontWeight: 700, letterSpacing: "-0.03em", marginTop: "4px", fontVariantNumeric: "tabular-nums" }}>
                {kpi.value}
              </div>
              <div style={{ fontSize: "11.5px", color: "#9A9F96", marginTop: "2px" }}>{kpi.note}</div>
            </div>
          ))}
        </div>
      ) : null}

      <div style={{ padding: "24px", border: "1px solid #E4E2DA", borderRadius: "16px", background: "#fff", boxShadow: "0 1px 2px rgba(20,25,20,0.04)" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "18px" }}>
          <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Where everyone goes</h2>
        </div>
        {funnelStages.length === 0 ? (
          <p style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>No funnel activity yet.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            {funnelStages.map((stage) => (
              <div key={stage.stage} style={{ display: "grid", gridTemplateColumns: "120px 1fr 150px", alignItems: "center", gap: "14px" }}>
                <span style={{ fontSize: "13.5px", fontWeight: 600, color: "#1B201C" }}>{FUNNEL_LABELS[stage.stage] ?? stage.stage}</span>
                <span style={{ height: "34px", borderRadius: "8px", background: "#EFEEE8", overflow: "hidden", display: "flex", alignItems: "center" }}>
                  <span
                    style={{
                      display: "block",
                      height: "100%",
                      width: `${firstStageCount ? Math.max(4, (stage.count / firstStageCount) * 100) : 4}%`,
                      background: "#1E5136",
                      borderRadius: "8px",
                      opacity: 0.85,
                    }}
                  />
                </span>
                <span style={{ textAlign: "right" }}>
                  <span style={{ display: "block", fontSize: "18px", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{stage.count}</span>
                  <span style={{ display: "block", fontSize: "11px", color: "#9A9F96" }}>
                    {firstStageCount ? `${Math.round((stage.count / firstStageCount) * 1000) / 10}% of applied` : "—"}
                  </span>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
        <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Where you convert best</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "12px" }}>
          <BreakdownPanel error={breakdownError} loading={breakdownLoading} metric="response" metricLabel="Response rate" rows={roleRows} title="By role" />
          <BreakdownPanel error={breakdownError} loading={breakdownLoading} metric="response" metricLabel="Response rate" rows={sourceRows} title="By source" />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.1fr) minmax(0,1fr)", gap: "12px" }}>
        <BreakdownPanel error={breakdownError} loading={breakdownLoading} metric="interview" metricLabel="Interview rate" rows={techRows} title="Which skills sell" />
        <BreakdownPanel error={breakdownError} loading={breakdownLoading} metric="response" metricLabel="Response rate" rows={salaryRows} title="Salary bands you target" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: "12px" }}>
        <div style={{ padding: "18px 20px", border: "1px solid #E4E2DA", borderRadius: "14px", background: "#fff", boxShadow: "0 1px 2px rgba(20,25,20,0.04)" }}>
          <h3 style={{ margin: "0 0 12px", fontSize: "13.5px", fontWeight: 700 }}>How fast companies reply</h3>
          {summary ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: "12px", color: "#4A5049" }}>Time to first response</span>
                <strong style={{ fontSize: "13px" }}>{formatHoursAsDuration(summary.average_time_to_first_response?.average_hours)}</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: "12px", color: "#4A5049" }}>Time to rejection</span>
                <strong style={{ fontSize: "13px" }}>{formatHoursAsDuration(summary.average_time_to_rejection?.average_hours)}</strong>
              </div>
            </div>
          ) : (
            <p style={{ margin: 0, fontSize: "12px", color: "#9A9F96" }}>Loading…</p>
          )}
        </div>

        <div style={{ padding: "18px 20px", border: "1px solid #E4E2DA", borderRadius: "14px", background: "#fff", boxShadow: "0 1px 2px rgba(20,25,20,0.04)" }}>
          <h3 style={{ margin: "0 0 12px", fontSize: "13.5px", fontWeight: 700 }}>Momentum</h3>
          {timeseries && timeseries.points.length > 0 ? (
            (() => {
              const maxCount = Math.max(...timeseries.points.map((point) => point.application_count), 1);
              return (
                <div style={{ display: "grid", gridAutoFlow: "column", gridAutoColumns: "1fr", gap: "6px", alignItems: "end", minHeight: "72px" }}>
                  {timeseries.points.map((point) => (
                    <div key={point.period_start} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px", height: "100%" }}>
                      <div style={{ flex: 1, width: "100%", display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
                        <span style={{ width: "10px", height: `${Math.max(4, (point.application_count / maxCount) * 100)}%`, background: "#1E5136", borderRadius: "3px", display: "block" }} />
                      </div>
                      <span style={{ fontSize: "9px", color: "#9A9F96" }}>{formatShortDate(point.period_start)}</span>
                    </div>
                  ))}
                </div>
              );
            })()
          ) : (
            <p style={{ margin: 0, fontSize: "12px", color: "#9A9F96" }}>No application volume yet.</p>
          )}
        </div>
      </div>

      {summary?.personal_ghost_threshold ? (
        <div style={{ padding: "16px 18px", border: "1px solid #D9D2EE", borderRadius: "14px", background: "#F4F2FB", display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "12px", fontWeight: 700, color: "#4B3FA6" }}>Your personal ghost threshold</span>
          <span style={{ fontSize: "22px", fontWeight: 700, color: "#1B201C" }}>{summary.personal_ghost_threshold.threshold_days} days</span>
          <span style={{ fontSize: "12px", color: "#565073" }}>
            {summary.personal_ghost_threshold.threshold_source === "response_percentile"
              ? `Derived from your own response timing across ${summary.personal_ghost_threshold.response_sample_size} responses.`
              : "Using the configured fallback threshold — not enough response history yet to derive your own."}{" "}
            {summary.personal_ghost_threshold.silent_application_count} applications are currently silent past this threshold.
          </span>
        </div>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "12px" }}>
        <div style={{ padding: "18px 20px", border: "1px solid #E4E2DA", borderRadius: "14px", background: "#fff" }}>
          <h3 style={{ margin: "0 0 10px", fontSize: "13.5px", fontWeight: 700, color: "#1E5136" }}>What your wins share</h3>
          {diagnosticsLoading ? <p style={{ margin: 0, fontSize: "12px", color: "#9A9F96" }}>Loading…</p> : null}
          {!diagnosticsLoading && diagnosticsError ? <p role="alert" style={{ margin: 0, fontSize: "12px", color: "#96403C" }}>{diagnosticsError}</p> : null}
          {!diagnosticsLoading && !diagnosticsError ? (
            <SegmentChipList segments={diagnostics?.selling_skill_segments ?? []} tone="positive" />
          ) : null}
        </div>
        <div style={{ padding: "18px 20px", border: "1px solid #E4E2DA", borderRadius: "14px", background: "#fff" }}>
          <h3 style={{ margin: "0 0 10px", fontSize: "13.5px", fontWeight: 700, color: "#96403C" }}>What your misses share</h3>
          {diagnosticsLoading ? <p style={{ margin: 0, fontSize: "12px", color: "#9A9F96" }}>Loading…</p> : null}
          {!diagnosticsLoading && diagnosticsError ? <p role="alert" style={{ margin: 0, fontSize: "12px", color: "#96403C" }}>{diagnosticsError}</p> : null}
          {!diagnosticsLoading && !diagnosticsError ? (
            <SegmentChipList segments={diagnostics?.dead_weight_skill_segments ?? []} tone="negative" />
          ) : null}
        </div>
      </div>
    </div>
  );
}
