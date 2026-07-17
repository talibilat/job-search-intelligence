import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import {
  completeInterviewTaskAttentionInterviewsInterviewEventIdCompletePut,
  getAttentionAttentionGet,
  getMetricsFunnelMetricsFunnelGet,
  getMetricsRatesMetricsRatesGet,
  getMetricsSummaryMetricsSummaryGet,
  getMetricsTimeseriesMetricsTimeseriesGet,
  listApplicationsApplicationsGet,
  type ApplicationRecord,
  type AttentionOverviewResponse,
  type InterviewAttentionItem,
  type MetricsRatesResponse,
  type MetricsFunnelResponse,
  type MetricsSummaryResponse,
  type PipelineStatus,
  type MetricsTimeseriesResponse,
} from "../../api";
import type { RedesignPage, StatusChipKey } from "../RedesignApp";
import { publicApiError } from "../apiError";
import { EmailReaderDialog } from "../components/EmailReaderDialog";
import { ProcessingPanel } from "../components/ProcessingPanel";
import { DashboardAnalytics } from "../components/DashboardAnalytics";
import { DashboardFilterPanel } from "../components/DashboardFilterPanel";
import { SyncedEmailList } from "../components/SyncedEmailList";
import {
  apiParamsFromFilters,
  filtersFromSearch,
  searchFromFilters,
  type DashboardFilters,
} from "../dashboardFilters";
import { daysSince, formatHoursAsDuration, formatShortDate } from "../theme";
import { QuestionCatalogTab } from "./overview/QuestionCatalogTab";
import { VisualizedTab } from "./overview/VisualizedTab";

type OverviewTabKey = "overview" | "catalog" | "visualized";

const OVERVIEW_TABS: { key: OverviewTabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "catalog", label: "Question catalog" },
  { key: "visualized", label: "Visualized" },
];

interface OverviewPageProps {
  processingActive?: boolean;
  userName?: string;
  go: (page: RedesignPage, extra?: { statusFilter?: StatusChipKey }) => void;
  openApp: (id: string) => void;
  reloadKey: number;
  sentAfter?: string;
  sentBefore?: string;
  onProcessed?: () => void;
}

interface MetricExplain {
  title: string;
  formula: string;
  source: string;
  count: number;
  filter: StatusChipKey;
  exactPopulation: boolean;
}

interface MetricCard {
  key: string;
  label: string;
  value: string;
  note: string;
  rateValue?: string;
  explain: MetricExplain | null;
}

interface ActionCard {
  tag: string;
  color: string;
  items: ActionItem[];
}

interface ActionItem {
  applicationId: string;
  company: string;
  date: string;
  interviewEventId?: string;
  role: string;
}

function timeGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) {
    return "Good morning";
  }
  if (hour < 18) {
    return "Good afternoon";
  }
  return "Good evening";
}

function ratePercent(rate: number): string {
  return `${Math.round(rate * 1_000) / 10}%`;
}

function attentionActionItem(item: InterviewAttentionItem): ActionItem {
  return {
    applicationId: item.application_id,
    company: item.company,
    date: item.interview_at,
    interviewEventId: item.interview_event_id,
    role: item.role_title,
  };
}

export function OverviewPage({
  processingActive = false,
  userName,
  go,
  openApp,
  reloadKey,
  sentAfter,
  sentBefore,
  onProcessed = () => undefined,
}: OverviewPageProps) {
  const [tab, setTab] = useState<OverviewTabKey>("overview");
  const [summary, setSummary] = useState<MetricsSummaryResponse | null>(null);
  const [rates, setRates] = useState<MetricsRatesResponse | null>(null);
  const [funnel, setFunnel] = useState<MetricsFunnelResponse | null>(null);
  const [funnelError, setFunnelError] = useState<string | null>(null);
  const [funnelLoading, setFunnelLoading] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [ratesError, setRatesError] = useState<string | null>(null);
  const [applicationsError, setApplicationsError] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [ratesLoading, setRatesLoading] = useState(true);
  const [applicationsLoading, setApplicationsLoading] = useState(true);
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [timeseries, setTimeseries] = useState<MetricsTimeseriesResponse | null>(null);
  const [timeseriesError, setTimeseriesError] = useState<string | null>(null);
  const [timeseriesLoading, setTimeseriesLoading] = useState(true);
  const [explainKey, setExplainKey] = useState<string | null>(null);
  const [openEmailPublicId, setOpenEmailPublicId] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [attention, setAttention] = useState<AttentionOverviewResponse | null>(null);
  const [attentionError, setAttentionError] = useState<string | null>(null);
  const [attentionReloadKey, setAttentionReloadKey] = useState(0);
  const [completingEventId, setCompletingEventId] = useState<string | null>(null);
  const [interviewHistoryOpen, setInterviewHistoryOpen] = useState(false);
  const [momentumOffset, setMomentumOffset] = useState(0);
  const [momentumFrom, setMomentumFrom] = useState("");
  const [momentumTo, setMomentumTo] = useState("");
  const [filters, setFilters] = useState<DashboardFilters>(() =>
    filtersFromSearch(window.location.search),
  );
  const emailTriggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const syncFiltersFromLocation = () => setFilters(filtersFromSearch(window.location.search));
    window.addEventListener("popstate", syncFiltersFromLocation);
    return () => window.removeEventListener("popstate", syncFiltersFromLocation);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setFunnelLoading(true);
      setFunnelError(null);
      setSummaryLoading(true);
      setRatesLoading(true);
      setApplicationsLoading(true);
      setTimeseriesLoading(true);
      setSummaryError(null);
      setRatesError(null);
      setApplicationsError(null);
      setTimeseriesError(null);
      setAttentionError(null);
      const [
        summaryResponse,
        ratesResponse,
        funnelResponse,
        applicationsResponse,
        timeseriesResponse,
        attentionResponse,
      ] = await Promise.all([
        getMetricsSummaryMetricsSummaryGet(apiParamsFromFilters(filters)).catch((error: unknown) => ({ error })),
        getMetricsRatesMetricsRatesGet(apiParamsFromFilters(filters)).catch((error: unknown) => ({ error })),
        getMetricsFunnelMetricsFunnelGet(apiParamsFromFilters(filters)).catch((error: unknown) => ({
          error,
        })),
        listApplicationsApplicationsGet(apiParamsFromFilters(filters)).catch((error: unknown) => ({ error })),
        getMetricsTimeseriesMetricsTimeseriesGet(apiParamsFromFilters(filters)).catch((error: unknown) => ({ error })),
        getAttentionAttentionGet().catch((error: unknown) => ({ error })),
      ]);
      if (cancelled) {
        return;
      }
      if ("status" in summaryResponse && summaryResponse.status === 200) {
        setSummary(summaryResponse.data);
      } else {
        setSummary(null);
        setSummaryError(publicApiError("status" in summaryResponse ? { response: summaryResponse } : summaryResponse.error, "Summary could not be loaded."));
      }
      setSummaryLoading(false);
      if ("status" in ratesResponse && ratesResponse.status === 200) {
        setRates(ratesResponse.data);
      } else {
        setRates(null);
        setRatesError(publicApiError("status" in ratesResponse ? { response: ratesResponse } : ratesResponse.error, "Rates could not be loaded."));
      }
      setRatesLoading(false);
      if ("status" in funnelResponse && funnelResponse.status === 200) {
        setFunnel(funnelResponse.data);
      } else {
        setFunnel(null);
        setFunnelError(
          publicApiError(
            "status" in funnelResponse
              ? { response: funnelResponse }
              : funnelResponse.error,
            "Funnel could not be loaded.",
          ),
        );
      }
      setFunnelLoading(false);
      if ("status" in applicationsResponse && applicationsResponse.status === 200) {
        setApplications(applicationsResponse.data);
      } else {
        setApplications([]);
        setApplicationsError(publicApiError("status" in applicationsResponse ? { response: applicationsResponse } : applicationsResponse.error, "Applications could not be loaded."));
      }
      setApplicationsLoading(false);
      if ("status" in timeseriesResponse && timeseriesResponse.status === 200) {
        setTimeseries(timeseriesResponse.data);
      } else {
        setTimeseries(null);
        setTimeseriesError(publicApiError("status" in timeseriesResponse ? { response: timeseriesResponse } : timeseriesResponse.error, "Momentum could not be loaded."));
      }
      setTimeseriesLoading(false);
      if ("status" in attentionResponse && attentionResponse.status === 200) {
        setAttention(attentionResponse.data);
      } else {
        setAttention(null);
        setAttentionError(publicApiError("status" in attentionResponse ? { response: attentionResponse } : attentionResponse.error, "Interview tasks could not be loaded."));
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [attentionReloadKey, filters, reloadKey]);

  const completeInterviewTask = async (item: ActionItem) => {
    if (!item.interviewEventId || completingEventId) return;
    setCompletingEventId(item.interviewEventId);
    setAttentionError(null);
    try {
      const response = await completeInterviewTaskAttentionInterviewsInterviewEventIdCompletePut(item.interviewEventId);
      if (response.status !== 200) {
        setAttentionError(publicApiError({ response }, "Interview task could not be completed."));
        return;
      }
      setAttentionReloadKey((value) => value + 1);
    } catch (error) {
      setAttentionError(publicApiError(error, "Interview task could not be completed."));
    } finally {
      setCompletingEventId(null);
    }
  };

  const publishable = pipeline?.next_action === "review_dashboard";
  const applyFilters = (next: DashboardFilters) => {
    window.history.pushState(null, "", `/${searchFromFilters(next)}`);
    setFilters(next);
  };
  const countValue = (value: number | undefined) =>
    value === undefined ? "—" : !publishable && value === 0 ? "Pending" : String(value);

  const offers = summary?.offers_received;
  const responseMetric = rates?.overall_response_rate;
  const interviewMetric = rates?.application_to_interview_rate;

  const greeting =
    offers === 1
      ? `${timeGreeting()}${userName ? `, ${userName}` : ""} — one offer on the table.`
      : offers !== undefined && offers > 1
        ? `${timeGreeting()}${userName ? `, ${userName}` : ""} — ${offers} offers on the table.`
        : `${timeGreeting()}${userName ? `, ${userName}` : ""}.`;

  const metrics: MetricCard[] = [
    {
      key: "total",
      label: "Applications",
      value: countValue(summary?.total_applications),
      note: summary ? `${summary.live_applications} still active` : "Active count unavailable",
      explain: summary ? {
        title: "Applications tracked",
        formula: "count(applications)",
        source: `Each application is a cluster of related emails from one company about one role. We found ${summary.total_applications} distinct clusters in your inbox.`,
        count: summary.total_applications,
        filter: "all",
        exactPopulation: true,
      } : null,
    },
    {
      key: "response",
      label: "Responses",
      value: countValue(responseMetric?.numerator),
      note: responseMetric?.rate != null ? `${responseMetric.numerator} of ${responseMetric.denominator} heard back` : "Rate unavailable",
      rateValue: responseMetric?.rate != null ? ratePercent(responseMetric.rate) : undefined,
      explain: responseMetric?.rate != null ? {
        title: "Responses",
        formula: `replies ÷ applications = ${responseMetric.numerator} ÷ ${responseMetric.denominator} = ${ratePercent(responseMetric.rate)}`,
        source:
          "A “response” means at least one human or scheduling email arrived after your application confirmation. Auto-replies don't count.",
        count: responseMetric.numerator,
        filter: "all",
        exactPopulation: false,
      } : null,
    },
    {
      key: "rejection",
      label: "Rejections",
      value: countValue(summary?.rejected_applications),
      note: rates?.rejection_rate?.rate != null ? `${ratePercent(rates.rejection_rate.rate)} of applications` : "Count unavailable",
      explain: summary ? { title: "Rejections", formula: "count(applications with rejection evidence)", source: "Distinct submitted applications with a rejection event.", count: summary.rejected_applications, filter: "closed", exactPopulation: false } : null,
    },
    {
      key: "interview",
      label: "Interviews",
      value: countValue(summary?.interview_invitation_count),
      note: interviewMetric?.rate != null ? `${interviewMetric.numerator} reached interviews` : "Rate unavailable",
      rateValue: interviewMetric?.rate != null ? ratePercent(interviewMetric.rate) : undefined,
      explain: interviewMetric?.rate != null ? {
        title: "Interview rate",
        formula: `interviews ÷ applications = ${interviewMetric.numerator} ÷ ${interviewMetric.denominator} = ${ratePercent(interviewMetric.rate)}`,
        source:
          "Counted when an email confirms a scheduled interview — detected phrases like “interview scheduled” or calendar invites from the company.",
        count: interviewMetric.numerator,
        filter: "interview",
        exactPopulation: false,
      } : null,
    },
    {
      key: "offer",
      label: "Offers",
      value: countValue(summary?.offers_received),
      note:
        !summary
          ? "Offer count unavailable"
          : summary.offers_received > 0
          ? `${summary.offers_received} offer${summary.offers_received === 1 ? "" : "s"} received`
          : "None yet",
      explain: summary ? {
        title: "Offers",
        formula: "count(applications with an offer event)",
        source:
          "An offer is detected from emails containing offer letters or compensation details.",
        count: summary.offers_received,
        filter: "offer",
        exactPopulation: false,
      } : null,
    },
    {
      key: "ghost",
      label: "Ghosts",
      value: countValue(summary?.ghosted_applications),
      note: rates?.ghost_rate?.rate != null ? `${ratePercent(rates.ghost_rate.rate)} of applications` : "Count unavailable",
      explain: summary ? { title: "Ghosts", formula: `no response after ${summary.ghost_threshold_days} days`, source: "Ghosts are inferred deterministically from the event timeline.", count: summary.ghosted_applications, filter: "closed", exactPopulation: false } : null,
    },
    {
      key: "live",
      label: "Live applications",
      value: countValue(summary?.live_applications),
      note: "Still awaiting a terminal outcome",
      explain: summary ? { title: "Live applications", formula: "applied + in review + assessment + interview", source: "Canonical current statuses that are still active.", count: summary.live_applications, filter: "all", exactPopulation: false } : null,
    },
  ];

  const explain =
    metrics.find((metric) => metric.key === explainKey)?.explain ?? null;

  const funnelStages = (funnel?.stages ?? []).map((stage) => ({
    ...stage,
    filter:
      stage.stage === "interview"
        ? ("interview" as const)
        : stage.stage === "offer"
          ? ("offer" as const)
          : stage.stage === "screen"
            ? ("screening" as const)
            : ("all" as const),
    label: {
      applied: "Applied",
      screen: "Screen",
      interview: "Interview",
      final: "Final",
      offer: "Offer",
    }[stage.stage],
    exact: false,
  }));

  const actions = useMemo<ActionCard[]>(() => {
    const cards: ActionCard[] = [];
    const activeApplications = applications.filter(
      (application) => (daysSince(application.last_activity_at) ?? 0) <= 60,
    );
    const offerApps = activeApplications.filter(
      (application) => application.current_status === "offer",
    );
    if (offerApps.length > 0) {
      cards.push({
        tag: "Respond",
        color: "#96403C",
        items: offerApps.slice(0, 5).map((application) => ({
          applicationId: application.id,
          company: application.company,
          date: application.last_activity_at,
          role: application.role_title || application.current_status,
        })),
      });
    }
    if ((attention?.prepare.length ?? 0) > 0) {
      cards.push({
        tag: "Prepare",
        color: "#1E5136",
        items: (attention?.prepare ?? []).slice(0, 5).map(attentionActionItem),
      });
    }
    if ((attention?.follow_up.length ?? 0) > 0) {
      cards.push({
        tag: "Follow up",
        color: "#8A6A14",
        items: (attention?.follow_up ?? []).slice(0, 5).map(attentionActionItem),
      });
    }
    return cards.slice(0, 3);
  }, [applications, attention]);

  return (
    <section
      style={{
        maxWidth: "1060px",
        margin: "0 auto",
        padding: "28px 32px 60px",
        display: "flex",
        flexDirection: "column",
        gap: "24px",
      }}
    >
      <div>
        <h1
          style={{
            margin: 0,
            fontSize: "24px",
            fontWeight: 700,
            letterSpacing: "-0.02em",
          }}
        >
          {greeting}
        </h1>
        <p style={{ margin: "6px 0 0", color: "#666D66", fontSize: "14px" }}>
          Everything below was built automatically from your email — nothing to
          enter by hand.{" "}
          <a href="/dev" style={{ fontWeight: 600 }}>
            How does this work?
          </a>
        </p>
      </div>

      <ProcessingPanel externalProcessingActive={processingActive} onPipelineStatus={setPipeline} onProcessed={onProcessed} reloadKey={reloadKey} />
      <DashboardFilterPanel
        filters={filters}
        key={searchFromFilters(filters)}
        onApply={applyFilters}
      />

      {pipeline && !publishable ? (
        <div className="rd-incomplete" role="status">
          <strong>Dashboard is not final yet</strong>
          <p>{pipeline.next_action_reason} Zero-valued metrics stay marked Pending until processing is complete.</p>
        </div>
      ) : null}

      <div
        style={{
          display: "flex",
          gap: "2px",
          padding: "3px",
          border: "1px solid #E4E2DA",
          borderRadius: "10px",
          background: "#fff",
          alignSelf: "flex-start",
        }}
      >
        {OVERVIEW_TABS.map((item) => {
          const tabButtonStyle: CSSProperties = {
            padding: "6px 14px",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
            fontSize: "12.5px",
            fontWeight: 600,
            background: tab === item.key ? "#1B201C" : "transparent",
            color: tab === item.key ? "#fff" : "#666D66",
          };
          return (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              style={tabButtonStyle}
              type="button"
            >
              {item.label}
            </button>
          );
        })}
      </div>

      {tab === "catalog" ? (
        <QuestionCatalogTab go={go} rates={rates} summary={summary} />
      ) : null}

      {tab === "visualized" ? (
        <VisualizedTab funnel={funnel} rates={rates} summary={summary} timeseries={timeseries} />
      ) : null}

      {tab === "overview" && actions.length > 0 ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3,minmax(0,1fr))",
            gap: "12px",
          }}
        >
          {actions.map((action) => (
            <div
              className="rd-hover-green-border"
              key={action.tag}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "6px",
                padding: "16px",
                border: "1px solid #E4E2DA",
                borderRadius: "14px",
                background: "#fff",
                textAlign: "left",
                minHeight: "210px",
                boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
              }}
            >
              <span
                style={{
                  fontSize: "10.5px",
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: action.color,
                }}
              >
                {action.tag}
              </span>
              {action.items.map((item) => (
                <div key={item.interviewEventId ?? item.applicationId} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "8px", alignItems: "center", padding: "8px 0", borderTop: "1px solid #F0EEE7" }}>
                  <button aria-label={`Open ${item.company} ${item.role}`} onClick={() => openApp(item.applicationId)} style={{ minWidth: 0, overflow: "hidden", border: "none", background: "transparent", cursor: "pointer", textAlign: "left", textOverflow: "ellipsis", whiteSpace: "nowrap" }} type="button">
                    <strong>{item.company}</strong><span style={{ color: "#666D66" }}> · {item.role} · {formatShortDate(item.date)}</span>
                  </button>
                  {action.tag === "Prepare" && item.interviewEventId ? (
                    <button aria-label={`Mark ${item.company} interview done`} disabled={completingEventId !== null} onClick={() => void completeInterviewTask(item)} style={{ width: "26px", height: "26px", border: "1px solid #B9CDBE", borderRadius: "50%", background: "#F3F8F4", color: "#1E5136", cursor: completingEventId ? "wait" : "pointer", fontWeight: 800 }} type="button">✓</button>
                  ) : null}
                </div>
              ))}
            </div>
          ))}
        </div>
      ) : null}

      {tab === "overview" && attentionError ? (
        <p role="status" style={{ margin: 0, color: "#96403C", fontSize: "12.5px" }}>{attentionError}</p>
      ) : null}

      {tab === "overview" && attention && attention.interviewed.length > 0 ? (
        <section style={{ padding: "14px 16px", border: "1px solid #D8DED7", borderRadius: "14px", background: "#F8FBF8" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px" }}>
            <div><strong style={{ color: "#1E5136" }}>Interviewed</strong><span style={{ marginLeft: "8px", color: "#666D66", fontSize: "12px" }}>{attention.unique_interviewed_company_count} unique companies</span></div>
            <button onClick={() => setInterviewHistoryOpen(true)} style={{ border: "1px solid #B9CDBE", borderRadius: "999px", background: "#fff", padding: "6px 11px", color: "#1E5136", cursor: "pointer", fontWeight: 700 }} type="button">View all</button>
          </div>
        </section>
      ) : null}

      {tab === "overview" ? (
      <>
      <div>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginBottom: "10px",
          }}
        >
          <h2 style={{ margin: 0, fontSize: "15px", fontWeight: 700 }}>
            Your search at a glance
          </h2>
          <span style={{ fontSize: "12px", color: "#9A9F96" }}>
            Counted from applications, not guesses — tap “How?” on any number
          </span>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit,minmax(145px,1fr))",
            gap: "12px",
          }}
        >
          {[summaryLoading ? "Loading summary…" : summaryError, ratesLoading ? "Loading rates…" : ratesError]
            .filter((message): message is string => !!message)
            .map((message) => (
              <p key={message} role="status" style={{ gridColumn: "1 / -1", margin: 0, fontSize: "12.5px", color: message.includes("Loading") ? "#9A9F96" : "#96403C" }}>
                {message}
              </p>
            ))}
          {metrics.map((metric) => (
            <div
              key={metric.key}
              style={{
                minWidth: 0,
                padding: "16px 18px",
                borderRadius: "14px",
                background: "#fff",
                border:
                  explainKey === metric.key
                    ? "1px solid #6C5FC7"
                    : "1px solid #E4E2DA",
                boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "8px",
                  minHeight: "22px",
                }}
              >
                <span
                  style={{
                    fontSize: "12.5px",
                    fontWeight: 600,
                    color: "#666D66",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {metric.label}
                </span>
                <button
                  aria-label={`${metric.label === "Offers" ? "How are" : "How is"} ${metric.label} calculated?`}
                  className="rd-hover-purple"
                  disabled={!metric.explain}
                  onClick={() =>
                    setExplainKey((current) =>
                      current === metric.key ? null : metric.key,
                    )
                  }
                  style={{
                    flex: "none",
                    padding: "2px 8px",
                    border: "1px solid #E4E2DA",
                    borderRadius: "999px",
                    background: "#FAFAF7",
                    color: "#666D66",
                    fontSize: "10.5px",
                    fontWeight: 600,
                    cursor: metric.explain ? "pointer" : "not-allowed",
                    opacity: metric.explain ? 1 : 0.55,
                  }}
                  type="button"
                >
                  How?
                </button>
              </div>
              <div
                style={{
                  fontSize: "30px",
                  fontWeight: 700,
                  letterSpacing: "-0.03em",
                  marginTop: "6px",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {metric.value}
              </div>
              <div
                style={{ fontSize: "12px", color: "#9A9F96", marginTop: "2px" }}
              >
                {metric.note}
                {metric.rateValue ? <span style={{ display: "block", color: "#1E5136", fontWeight: 600 }}>{metric.rateValue}</span> : null}
              </div>
            </div>
          ))}
        </div>

        {explain ? (
          <div
            style={{
              marginTop: "12px",
              padding: "18px 20px",
              border: "1px solid #D9D2EE",
              borderRadius: "14px",
              background: "#F4F2FB",
              display: "flex",
              flexDirection: "column",
              gap: "10px",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div
                style={{
                  fontWeight: 700,
                  fontSize: "13.5px",
                  color: "#4B3FA6",
                }}
              >
                How “{explain.title}” is calculated
              </div>
              <button
                onClick={() => setExplainKey(null)}
                style={{
                  border: "none",
                  background: "none",
                  color: "#8B84B8",
                  fontSize: "12px",
                  cursor: "pointer",
                  fontWeight: 600,
                }}
                type="button"
              >
                Close ✕
              </button>
            </div>
            <div
              style={{
                fontFamily: "'JetBrains Mono',monospace",
                fontSize: "12.5px",
                color: "#3F3776",
                background: "#fff",
                border: "1px solid #E4DFF5",
                borderRadius: "8px",
                padding: "10px 12px",
              }}
            >
              {explain.formula}
            </div>
            <div style={{ fontSize: "13px", color: "#565073" }}>
              {explain.source}
            </div>
            <button
              onClick={() =>
                go("applications", { statusFilter: explain.filter })
              }
              style={{
                alignSelf: "flex-start",
                padding: "7px 14px",
                border: "none",
                borderRadius: "999px",
                background: "#6C5FC7",
                color: "#fff",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
              type="button"
            >
              {explain.exactPopulation
                ? `See the ${explain.count} applications behind this number →`
                : "Browse current applications related to this metric →"}
            </button>
          </div>
        ) : null}
      </div>

      <DashboardAnalytics filters={filters} publishable={publishable} reloadKey={reloadKey} />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1.2fr) minmax(0,1fr)",
          gap: "12px",
        }}
      >
        <div
          style={{
            padding: "20px",
            border: "1px solid #E4E2DA",
            borderRadius: "14px",
            background: "#fff",
            boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              marginBottom: "4px",
            }}
          >
            <h2 style={{ margin: 0, fontSize: "15px", fontWeight: 700 }}>
              Where applications stand
            </h2>
            <span style={{ fontSize: "11.5px", color: "#9A9F96" }}>
              Historical event counts open related current statuses
            </span>
          </div>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "10px",
              marginTop: "14px",
            }}
          >
            {funnelLoading ? (
              <p style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>
                Loading funnel…
              </p>
            ) : null}
            {!funnelLoading && funnelError ? (
              <p
                role="alert"
                style={{ margin: 0, fontSize: "12.5px", color: "#96403C" }}
              >
                {funnelError}
              </p>
            ) : null}
            {!funnelLoading && !funnelError && funnelStages.length === 0 ? (
              <p style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>
                No funnel activity yet.
              </p>
            ) : null}
            {!funnelLoading && !funnelError
              ? funnelStages.map((stage) => (
                  <button
                    key={stage.label}
                    onClick={() => {
                      if (stage.stage === "interview") {
                        setInterviewHistoryOpen(true);
                        return;
                      }
                      go("applications", { statusFilter: stage.filter });
                    }}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "110px 1fr 40px",
                      alignItems: "center",
                      gap: "12px",
                      border: "none",
                      background: "none",
                      padding: "4px 0",
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                    type="button"
                    title={
                      stage.exact
                        ? undefined
                        : "Shows related current statuses, not this exact historical stage population"
                    }
                  >
                    <span
                      style={{
                        fontSize: "13px",
                        fontWeight: 600,
                        color: "#1B201C",
                      }}
                    >
                      {stage.label}
                    </span>
                    <span
                      style={{
                        height: "22px",
                        borderRadius: "6px",
                        background: "#EDEBE4",
                        overflow: "hidden",
                        display: "block",
                      }}
                    >
                      <span
                        style={{
                          display: "block",
                          height: "100%",
                          width: `${funnelStages[0]?.count ? Math.max(4, (stage.count / funnelStages[0].count) * 100) : 4}%`,
                          background: "#1E5136",
                          borderRadius: "6px",
                          opacity: 0.85,
                        }}
                      />
                    </span>
                    <span
                      style={{
                        fontSize: "13.5px",
                        fontWeight: 700,
                        textAlign: "right",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {stage.count}
                    </span>
                  </button>
                ))
              : null}
          </div>
          <p style={{ margin: "14px 0 0", fontSize: "12px", color: "#9A9F96" }}>
            Historical event populations cannot be reproduced exactly by the
            current-status application list.
          </p>
        </div>

        <div
          style={{
            padding: "20px",
            border: "1px solid #E4E2DA",
            borderRadius: "14px",
            background: "#fff",
            boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
          }}
        >
          <h2 style={{ margin: "0 0 14px", fontSize: "15px", fontWeight: 700 }}>
            Latest from your inbox
          </h2>
          <SyncedEmailList
            onOpenEmail={(email) => {
              emailTriggerRef.current =
                document.activeElement instanceof HTMLElement
                  ? document.activeElement
                  : null;
              setOpenEmailPublicId(email.public_id);
            }}
            refreshToken={reloadKey}
            sentAfter={sentAfter}
            sentBefore={sentBefore}
          />
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)",
          gap: "12px",
        }}
      >
        <div
          style={{
            padding: "20px",
            border: "1px solid #E4E2DA",
            borderRadius: "14px",
            background: "#fff",
            boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
          }}
        >
          <h2 style={{ margin: "0 0 2px", fontSize: "15px", fontWeight: 700 }}>
            How fast companies reply
          </h2>
          <p style={{ margin: "0 0 12px", fontSize: "11.5px", color: "#9A9F96" }}>
            Averaged across every application with a recorded response.
          </p>
          {summaryLoading ? (
            <p style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>Loading…</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <span style={{ fontSize: "12.5px", fontWeight: 600, color: "#1B201C" }}>
                  Time to first response
                </span>
                <span style={{ fontSize: "16px", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  {formatHoursAsDuration(summary?.average_time_to_first_response?.average_hours)}
                </span>
              </div>
              <span style={{ fontSize: "11px", color: "#9A9F96" }}>
                Based on {summary?.average_time_to_first_response?.application_count ?? 0} applications with a response.
              </span>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <span style={{ fontSize: "12.5px", fontWeight: 600, color: "#1B201C" }}>
                  Time to rejection
                </span>
                <span style={{ fontSize: "16px", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  {formatHoursAsDuration(summary?.average_time_to_rejection?.average_hours)}
                </span>
              </div>
              <span style={{ fontSize: "11px", color: "#9A9F96" }}>
                Based on {summary?.average_time_to_rejection?.application_count ?? 0} rejected applications.
              </span>
            </div>
          )}
        </div>

        <div
          style={{
            padding: "20px",
            border: "1px solid #E4E2DA",
            borderRadius: "14px",
            background: "#fff",
            boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px", marginBottom: "10px" }}><h2 style={{ margin: 0, fontSize: "15px", fontWeight: 700 }}>Your momentum</h2><div style={{ display: "flex", gap: "6px" }}><button aria-label="Move momentum back two months" onClick={() => setMomentumOffset((value) => value + 2)} type="button">← 2m</button><button aria-label="Move momentum forward two months" disabled={momentumOffset === 0} onClick={() => setMomentumOffset((value) => Math.max(0, value - 2))} type="button">2m →</button></div></div>
          <div style={{ display: "flex", gap: "6px", marginBottom: "12px" }}><input aria-label="Momentum from" onChange={(event) => setMomentumFrom(event.target.value)} type="month" value={momentumFrom} /><input aria-label="Momentum to" onChange={(event) => setMomentumTo(event.target.value)} type="month" value={momentumTo} /><button onClick={() => { setMomentumFrom(""); setMomentumTo(""); setMomentumOffset(0); }} type="button">Reset</button></div>
          {timeseriesLoading ? (
            <p style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>Loading…</p>
          ) : null}
          {!timeseriesLoading && timeseriesError ? (
            <p role="alert" style={{ margin: 0, fontSize: "12.5px", color: "#96403C" }}>
              {timeseriesError}
            </p>
          ) : null}
          {!timeseriesLoading && !timeseriesError && (timeseries?.points.length ?? 0) === 0 ? (
            <p style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>No application volume yet.</p>
          ) : null}
          {!timeseriesLoading && !timeseriesError && timeseries && timeseries.points.length > 0 ? (
            (() => {
              const rangedPoints = timeseries.points.filter((point) => (!momentumFrom || point.period_start.slice(0, 7) >= momentumFrom) && (!momentumTo || point.period_start.slice(0, 7) <= momentumTo));
              const visiblePoints = rangedPoints.slice(Math.max(0, rangedPoints.length - 12 - momentumOffset), Math.max(0, rangedPoints.length - momentumOffset));
              const maxCount = Math.max(...visiblePoints.map((point) => point.application_count), 1);
              return (
                <div
                  style={{
                    flex: 1,
                    display: "grid",
                    gridAutoFlow: "column",
                    gridAutoColumns: "1fr",
                    gap: "8px",
                    alignItems: "end",
                    minHeight: "96px",
                  }}
                >
                  {visiblePoints.map((point) => (
                    <div
                      key={point.period_start}
                      style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "5px", height: "100%" }}
                    >
                      <div style={{ flex: 1, width: "100%", display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
                        <span
                          style={{
                            width: "14px",
                            height: `${Math.max(4, (point.application_count / maxCount) * 100)}%`,
                            background: "#1E5136",
                            borderRadius: "3px",
                            display: "block",
                          }}
                        />
                      </div>
                      <span style={{ fontSize: "9.5px", color: "#9A9F96", whiteSpace: "nowrap" }}>
                        {new Intl.DateTimeFormat("en-US", { month: "short" }).format(new Date(point.period_start))}
                      </span>
                    </div>
                  ))}
                </div>
              );
            })()
          ) : null}
        </div>
      </div>

      {applicationsLoading ? (
        <p role="status" style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>Loading applications…</p>
      ) : null}
      {!applicationsLoading && applicationsError ? (
        <p role="status" style={{ margin: 0, fontSize: "12.5px", color: "#96403C" }}>{applicationsError}</p>
      ) : null}
      </>
      ) : null}
      <EmailReaderDialog
        onClose={() => setOpenEmailPublicId(null)}
        publicId={openEmailPublicId}
        triggerRef={emailTriggerRef}
      />
      {interviewHistoryOpen && attention ? (
        <div className="email-reader-overlay">
          <section aria-modal="true" className="email-reader-dialog" role="dialog" aria-label="Interviewed companies">
            <header className="email-reader-header"><div className="email-reader-heading-group"><h2>Interviewed</h2><p className="email-reader-metadata">{attention.unique_interviewed_company_count} unique companies</p></div><button aria-label="Close interviewed companies" className="email-reader-close" onClick={() => setInterviewHistoryOpen(false)} type="button">×</button></header>
            <div className="email-reader-content">
              {attention.interviewed.map((item) => (
                <button aria-label={`Open ${item.company} ${item.role_title}`} key={item.interview_event_id} onClick={() => openApp(item.application_id)} style={{ display: "block", width: "100%", minHeight: "42px", overflow: "hidden", padding: "10px 0", border: "none", borderBottom: "1px solid #F0EEE7", background: "transparent", cursor: "pointer", textAlign: "left", textOverflow: "ellipsis", whiteSpace: "nowrap" }} type="button">
                  <strong>{item.company}</strong><span style={{ color: "#666D66" }}> · {item.role_title} · {formatShortDate(item.interview_at)}</span>
                </button>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
