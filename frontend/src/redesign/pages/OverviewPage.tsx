import { useEffect, useMemo, useRef, useState } from "react";

import {
  getMetricsFunnelMetricsFunnelGet,
  getMetricsRatesMetricsRatesGet,
  getMetricsSummaryMetricsSummaryGet,
  listApplicationsApplicationsGet,
  type ApplicationRecord,
  type MetricsRatesResponse,
  type MetricsFunnelResponse,
  type MetricsSummaryResponse,
} from "../../api";
import type { RedesignPage, StatusChipKey } from "../RedesignApp";
import { publicApiError } from "../apiError";
import { EmailReaderDialog } from "../components/EmailReaderDialog";
import { ProcessingPanel } from "../components/ProcessingPanel";
import { SyncedEmailList } from "../components/SyncedEmailList";
import { daysSince, formatShortDate } from "../theme";

interface OverviewPageProps {
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
  explain: MetricExplain | null;
}

interface ActionCard {
  tag: string;
  color: string;
  title: string;
  body: string;
  onClick: () => void;
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

export function OverviewPage({
  go,
  openApp,
  reloadKey,
  sentAfter,
  sentBefore,
  onProcessed = () => undefined,
}: OverviewPageProps) {
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
  const [explainKey, setExplainKey] = useState<string | null>(null);
  const [openEmailPublicId, setOpenEmailPublicId] = useState<string | null>(null);
  const emailTriggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setFunnelLoading(true);
      setFunnelError(null);
      setSummaryLoading(true);
      setRatesLoading(true);
      setApplicationsLoading(true);
      setSummaryError(null);
      setRatesError(null);
      setApplicationsError(null);
      const [
        summaryResponse,
        ratesResponse,
        funnelResponse,
        applicationsResponse,
      ] = await Promise.all([
        getMetricsSummaryMetricsSummaryGet().catch((error: unknown) => ({ error })),
        getMetricsRatesMetricsRatesGet().catch((error: unknown) => ({ error })),
        getMetricsFunnelMetricsFunnelGet().catch((error: unknown) => ({
          error,
        })),
        listApplicationsApplicationsGet().catch((error: unknown) => ({ error })),
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
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const offers = summary?.offers_received;
  const responseMetric = rates?.overall_response_rate;
  const interviewMetric = rates?.application_to_interview_rate;

  const greeting =
    offers === 1
      ? `${timeGreeting()} — one offer on the table.`
      : offers !== undefined && offers > 1
        ? `${timeGreeting()} — ${offers} offers on the table.`
        : `${timeGreeting()}.`;

  const metrics: MetricCard[] = [
    {
      key: "total",
      label: "Applications",
      value: summary ? String(summary.total_applications) : "—",
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
      label: "Response rate",
      value: responseMetric?.rate != null ? ratePercent(responseMetric.rate) : "—",
      note: responseMetric?.rate != null ? `${responseMetric.numerator} of ${responseMetric.denominator} heard back` : "Rate unavailable",
      explain: responseMetric?.rate != null ? {
        title: "Response rate",
        formula: `replies ÷ applications = ${responseMetric.numerator} ÷ ${responseMetric.denominator} = ${ratePercent(responseMetric.rate)}`,
        source:
          "A “response” means at least one human or scheduling email arrived after your application confirmation. Auto-replies don't count.",
        count: responseMetric.numerator,
        filter: "all",
        exactPopulation: false,
      } : null,
    },
    {
      key: "interview",
      label: "Interview rate",
      value: interviewMetric?.rate != null ? ratePercent(interviewMetric.rate) : "—",
      note: interviewMetric?.rate != null ? `${interviewMetric.numerator} reached interviews` : "Rate unavailable",
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
      value: summary ? String(summary.offers_received) : "—",
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
    const offerApps = applications.filter(
      (application) => application.current_status === "offer",
    );
    if (offerApps.length > 0) {
      const first = offerApps[0];
      cards.push({
        tag: "Respond",
        color: "#96403C",
        title: `${first.company} offer needs an answer`,
        body: `Offer received — last activity ${formatShortDate(first.last_activity_at)}.`,
        onClick: () => openApp(first.id),
      });
    }
    const interviewApps = applications.filter(
      (application) => application.current_status === "interview",
    );
    if (interviewApps.length > 0) {
      const first = interviewApps[0];
      cards.push({
        tag: "Prepare",
        color: "#1E5136",
        title: `${first.company} interview in progress`,
        body: `Latest activity ${formatShortDate(first.last_activity_at)} — review the timeline.`,
        onClick: () => openApp(first.id),
      });
    }
    const quietApps = applications
      .filter(
        (application) =>
          application.current_status === "applied" &&
          (daysSince(application.last_activity_at) ?? 0) >= 7,
      )
      .sort(
        (a, b) =>
          (daysSince(b.last_activity_at) ?? 0) -
          (daysSince(a.last_activity_at) ?? 0),
      );
    if (quietApps.length > 0) {
      const names = quietApps
        .slice(0, 3)
        .map((application) => application.company);
      cards.push({
        tag: "Follow up",
        color: "#8A6A14",
        title: `${quietApps.length} application${quietApps.length === 1 ? "" : "s"} gone quiet`,
        body: `${names.join(", ")} ${quietApps.length === 1 ? "is" : "are"} past your usual reply window.`,
        onClick: () => go("applications", { statusFilter: "applied" }),
      });
    }
    return cards.slice(0, 3);
  }, [applications, go, openApp]);

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

      <ProcessingPanel onProcessed={onProcessed} reloadKey={reloadKey} />

      {actions.length > 0 ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3,minmax(0,1fr))",
            gap: "12px",
          }}
        >
          {actions.map((action) => (
            <button
              className="rd-hover-green-border"
              key={action.tag}
              onClick={action.onClick}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "6px",
                padding: "16px",
                border: "1px solid #E4E2DA",
                borderRadius: "14px",
                background: "#fff",
                cursor: "pointer",
                textAlign: "left",
                boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
              }}
              type="button"
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
              <span
                style={{ fontWeight: 600, fontSize: "14px", color: "#1B201C" }}
              >
                {action.title}
              </span>
              <span style={{ fontSize: "12.5px", color: "#666D66" }}>
                {action.body}
              </span>
            </button>
          ))}
        </div>
      ) : null}

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
            gridTemplateColumns: "repeat(4,minmax(0,1fr))",
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
                    onClick={() =>
                      go("applications", { statusFilter: stage.filter })
                    }
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
      {applicationsLoading ? (
        <p role="status" style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>Loading applications…</p>
      ) : null}
      {!applicationsLoading && applicationsError ? (
        <p role="status" style={{ margin: 0, fontSize: "12.5px", color: "#96403C" }}>{applicationsError}</p>
      ) : null}
      <EmailReaderDialog
        onClose={() => setOpenEmailPublicId(null)}
        publicId={openEmailPublicId}
        triggerRef={emailTriggerRef}
      />
    </section>
  );
}
