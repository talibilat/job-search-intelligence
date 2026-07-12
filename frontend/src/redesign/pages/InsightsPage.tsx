import { useEffect, useRef, useState } from "react";

import {
  listInsightsInsightsGet,
  regenerateInsightInsightsRegeneratePost,
  type InsightListResponse,
  type InsightRecord,
  type InsightType,
} from "../../api";
import { Alert, Button } from "../../components/ui";
import { isSafeApplicationRouteId } from "../../lib/applicationRoutes";
import { formatShortDate } from "../theme";
import { publicApiError } from "../apiError";

interface InsightsPageProps {
  openApp: (id: string) => void;
  reloadKey: number;
}

const INSIGHT_COPY: Record<
  InsightType,
  { q: string; title: string; howInputs: string; howDid: string }
> = {
  why_rejected: {
    q: "Q-40 · Why am I getting rejected?",
    title: "Rejection themes",
    howInputs: "Cited rejection events and their source-email metadata.",
    howDid: "Grouped recurring themes supported by rejection evidence.",
  },
  recurring_feedback: {
    q: "Q-41 · What feedback says to improve",
    title: "Recurring recruiter feedback",
    howInputs: "Cited recruiter and interviewer feedback timeline events.",
    howDid: "Summarized repeated feedback only when the timeline contains enough feedback evidence.",
  },
  skill_gaps: {
    q: "Q-42 · Which skills recur in rejected roles?",
    title: "Rejected-role skill gaps",
    howInputs: "Cited rejected-role evidence with technologies and skills.",
    howDid: "Grouped skill mentions that appear in the cited rejected-role evidence.",
  },
  strongest_weakest_signals: {
    q: "Q-43 · What are my strongest and weakest signals?",
    title: "Strongest and weakest signals",
    howInputs: "Deterministic whole-history application and event facts with citations.",
    howDid: "Explained patterns from the prepared facts without inventing dashboard counts.",
  },
  role_fit: {
    q: "Q-44 · Which roles genuinely suit me best?",
    title: "Best-fit roles",
    howInputs: "Deterministic role outcomes and cited applications.",
    howDid: "Compared grounded win patterns across role families.",
  },
  weekly_actions: {
    q: "Q-45 · What should I do next week?",
    title: "Next-week actions",
    howInputs: "Cited recent and open-application evidence.",
    howDid: "Turned grounded evidence into exactly three concrete actions for the next week.",
  },
  story: {
    q: "Q-46 · What story does my recent search tell?",
    title: "Search story",
    howInputs: "Chronological cited evidence from the recent 6 to 12 month search window.",
    howDid: "Arranged the grounded timeline into phases, turning points, and repeated patterns.",
  },
};

const DISPLAY_ORDER: InsightType[] = [
  "why_rejected",
  "recurring_feedback",
  "skill_gaps",
  "strongest_weakest_signals",
  "role_fit",
  "weekly_actions",
  "story",
];

function costLabel(response: InsightListResponse | null, type: InsightType): string {
  const estimate = response?.regeneration_cost_estimates?.find((item) => item.type === type);
  const usd = estimate?.cost.estimated_cost_usd;
  if (usd === null || usd === undefined) {
    return "Rewrite with latest data";
  }
  const rounded = usd < 0.01 ? `~$${usd.toFixed(3)}` : `~$${usd.toFixed(2)}`;
  return `Rewrite with latest data · ${rounded}`;
}

export function InsightsPage({ openApp, reloadKey }: InsightsPageProps) {
  const [response, setResponse] = useState<InsightListResponse | null>(null);
  const [howOpen, setHowOpen] = useState<Record<string, boolean>>({});
  const [regenerating, setRegenerating] = useState<InsightType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const regenerationRef = useRef<InsightType | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      const listResponse = await listInsightsInsightsGet().catch((requestError: unknown) => ({ error: requestError }));
      if (cancelled) {
        return;
      }
      if ("status" in listResponse && listResponse.status === 200) {
        setResponse(listResponse.data);
        setError(null);
      } else {
        setResponse(null);
        setError(publicApiError("status" in listResponse ? { response: listResponse } : listResponse.error, "Insights are unavailable. Check that the local backend is running."));
      }
      setLoading(false);
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const insights: InsightRecord[] = (response?.insights ?? [])
    .slice()
    .sort((a, b) => DISPLAY_ORDER.indexOf(a.type) - DISPLAY_ORDER.indexOf(b.type));

  const regenerate = async (type: InsightType) => {
    if (regenerationRef.current) {
      return;
    }
    regenerationRef.current = type;
    setRegenerating(type);
    setError(null);
    try {
      const regenerateResponse = await regenerateInsightInsightsRegeneratePost({ type });
      if (regenerateResponse.status === 200) {
        setResponse((current) => {
          if (!current) {
            return current;
          }
          const nextInsights = current.insights.map((insight) =>
            insight.type === type ? regenerateResponse.data.insight : insight,
          );
          return { ...current, insights: nextInsights };
        });
      } else {
        setError(
          publicApiError({ response: regenerateResponse }, `${INSIGHT_COPY[type].title} could not be rewritten.`),
        );
      }
    } catch {
      setError(`${INSIGHT_COPY[type].title} could not be rewritten. Check that the local backend is running.`);
    } finally {
      regenerationRef.current = null;
      setRegenerating(null);
    }
  };

  return (
    <section
      style={{
        maxWidth: "860px",
        margin: "0 auto",
        padding: "28px 32px 60px",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
      }}
    >
      <div>
        <h1 style={{ margin: 0, fontSize: "22px", fontWeight: 700, letterSpacing: "-0.02em" }}>
          What your search is telling you
        </h1>
        <p
          style={{
            margin: "6px 0 0",
            color: "#666D66",
            fontSize: "13.5px",
            maxWidth: "620px",
          }}
        >
          AI reads the patterns across your applications and explains them in plain language. The
          numbers always come from your real data. The AI only writes the narrative, and the
          evidence chips below come from saved citation records.
        </p>
      </div>

      {error ? (
        <Alert
          tone="danger"
          style={{
            display: "block",
            padding: "11px 14px",
            border: "1px solid #E8C8C2",
            borderRadius: "10px",
            background: "#FFF4F2",
            color: "#8A3328",
            fontSize: "12.5px",
          }}
        >
          {error}
        </Alert>
      ) : null}
      {loading ? (
        <div style={{ padding: "22px 24px", border: "1px solid #E4E2DA", borderRadius: "16px", background: "#fff", fontSize: "13.5px", color: "#666D66" }}>
          Loading insights…
        </div>
      ) : null}

      {!loading && !error && insights.length === 0 ? (
        <div
          style={{
            padding: "22px 24px",
            border: "1px solid #E4E2DA",
            borderRadius: "16px",
            background: "#fff",
            fontSize: "13.5px",
            color: "#666D66",
          }}
        >
          No insights yet. Sync your inbox and classify your email first, then insights are
          generated from your real application data.
        </div>
      ) : null}

      {insights.map((insight) => {
        const copy = INSIGHT_COPY[insight.type];
        const fresh = insight.is_stale
          ? `Stale · data changed since ${formatShortDate(insight.generated_at)}`
          : `Fresh · ${formatShortDate(insight.generated_at)}`;
        const isOpen = !!howOpen[insight.type];
        return (
          <div
            key={insight.id}
            style={{
              padding: "22px 24px",
              border: "1px solid #E4E2DA",
              borderRadius: "16px",
              background: "#fff",
              boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
              display: "flex",
              flexDirection: "column",
              gap: "12px",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "flex-start",
                justifyContent: "space-between",
                gap: "12px",
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: "#8B84B8",
                  }}
                >
                  {copy.q}
                </div>
                <h2
                  style={{
                    margin: "4px 0 0",
                    fontSize: "16.5px",
                    fontWeight: 700,
                    letterSpacing: "-0.01em",
                  }}
                >
                  {copy.title}
                </h2>
              </div>
              <span
                style={{
                  flex: "none",
                  fontSize: "11px",
                  fontWeight: 700,
                  padding: "3px 10px",
                  borderRadius: "999px",
                  background: insight.is_stale ? "#F7EFDB" : "#E3EFE6",
                  color: insight.is_stale ? "#8A6A14" : "#1E5136",
                }}
              >
                {fresh}
              </span>
            </div>
            <p style={{ margin: 0, fontSize: "14px", color: "#33382F", lineHeight: 1.65 }}>
              {insight.content}
            </p>
            {insight.citations && insight.citations.length > 0 ? (
              <div
                style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}
              >
                <span style={{ fontSize: "11.5px", color: "#9A9F96" }}>Evidence:</span>
                {insight.citations.map((citation) => {
                  const label = `${citation.company}${citation.email_subject ? ` - ${citation.email_subject}` : ""}`;
                  const citationStyle = {
                    border: "1px solid #E4E2DA",
                    borderRadius: "999px",
                    background: "#FAFAF7",
                    padding: "3px 10px",
                    fontSize: "11.5px",
                    fontWeight: 600,
                    color: "#1E5136",
                  };
                  return isSafeApplicationRouteId(citation.application_id) ? (
                    <Button
                      className="rd-hover-green-border"
                      key={citation.citation_id}
                      onClick={() => openApp(citation.application_id)}
                      style={{
                        ...citationStyle,
                        minHeight: 0,
                        minWidth: 0,
                        cursor: "pointer",
                        lineHeight: "normal",
                        transform: "none",
                        transition: "none",
                      }}
                      variant="ghost"
                    >
                      {label}
                    </Button>
                  ) : (
                    <span key={citation.citation_id} style={citationStyle}>
                      {label}
                    </span>
                  );
                })}
              </div>
            ) : null}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                borderTop: "1px solid #F0EEE7",
                paddingTop: "12px",
              }}
            >
              <Button
                disabled={regenerating !== null}
                onClick={() => void regenerate(insight.type)}
                style={{
                  minHeight: 0,
                  minWidth: 0,
                  padding: "7px 14px",
                  border: "1px solid #E4E2DA",
                  borderRadius: "999px",
                  background: "#fff",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "#1B201C",
                  cursor: regenerating !== null ? "wait" : "pointer",
                  lineHeight: "normal",
                  transform: "none",
                  transition: "none",
                }}
                variant="ghost"
              >
                {regenerating === insight.type ? "Rewriting…" : costLabel(response, insight.type)}
              </Button>
              <Button
                onClick={() =>
                  setHowOpen((current) => ({ ...current, [insight.type]: !current[insight.type] }))
                }
                style={{
                  minHeight: 0,
                  minWidth: 0,
                  border: "none",
                  background: "none",
                  color: "#6C5FC7",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                  lineHeight: "normal",
                  padding: 0,
                  transform: "none",
                  transition: "none",
                }}
                variant="ghost"
              >
                {isOpen ? "Hide how this was made" : "How was this made?"}
              </Button>
            </div>
            {isOpen ? (
              <div
                style={{
                  border: "1px solid #E4DFF5",
                  borderRadius: "10px",
                  background: "#F4F2FB",
                  padding: "14px 16px",
                  fontSize: "12.5px",
                  color: "#565073",
                  display: "flex",
                  flexDirection: "column",
                  gap: "6px",
                }}
              >
                <div>
                  <strong style={{ color: "#4B3FA6" }}>What went in:</strong> {copy.howInputs}
                </div>
                <div>
                  <strong style={{ color: "#4B3FA6" }}>What the AI did:</strong> {copy.howDid}
                </div>
                <div>
                  <strong style={{ color: "#4B3FA6" }}>What it can't do:</strong> invent numbers.
                  All counts are computed from your database first, then handed to the AI.
                </div>
              </div>
            ) : null}
          </div>
        );
      })}
    </section>
  );
}
