import { useState } from "react";

import type { MetricsRatesResponse, MetricsSummaryResponse } from "../../../api";
import type { RedesignPage } from "../../RedesignApp";
import { formatCount } from "../../theme";

interface QuestionCatalogTabProps {
  go: (page: RedesignPage) => void;
  rates: MetricsRatesResponse | null;
  summary: MetricsSummaryResponse | null;
}

type CatalogStatus = "shipped" | "narrative" | "planned";

interface CatalogQuestion {
  id: string;
  text: string;
  /** For "shipped" rows with data already loaded by OverviewPage — no extra fetch. */
  answer?: (summary: MetricsSummaryResponse | null, rates: MetricsRatesResponse | null) => string | null;
  plannedNote?: string;
}

interface CatalogTier {
  n: number;
  name: string;
  capability: string;
  phase: string;
  status: CatalogStatus;
  questions: CatalogQuestion[];
}

function ratePercent(rate: number | null | undefined): string | null {
  if (rate === null || rate === undefined) {
    return null;
  }
  return `${Math.round(rate * 1_000) / 10}%`;
}

function safeCount(value: number | null | undefined): string | null {
  return value === null || value === undefined ? null : formatCount(value);
}

const CATALOG: CatalogTier[] = [
  {
    n: 1,
    name: "Foundational Counts",
    capability: "Pure COUNT once emails are classified.",
    phase: "Shipped",
    status: "shipped",
    questions: [
      { id: "Q-01", text: "How many jobs have I applied to, lifetime?", answer: (s) => safeCount(s?.total_applications) },
      { id: "Q-02", text: "How many applications in a given window (this week / month / year)?", answer: (s) => (s?.application_windows?.length ? s.application_windows.map((w) => `${w.window}: ${safeCount(w.application_count) ?? "—"}`).join(" · ") : null) },
      { id: "Q-03", text: "How many distinct companies have I applied to?", answer: (s) => safeCount(s?.distinct_company_count) },
      { id: "Q-04", text: "How many applications got at least one human response vs. total silence?" },
      { id: "Q-05", text: "How many rejections have I received?", answer: (s) => safeCount(s?.rejected_applications) },
      { id: "Q-06", text: "How many applications got no response at all (ghosted)?", answer: (s) => safeCount(s?.ghosted_applications) },
      { id: "Q-07", text: "How many interview invitations have I received?", answer: (s) => safeCount(s?.interview_invitation_count) },
      { id: "Q-08", text: "How many offers have I received?", answer: (s) => safeCount(s?.offers_received) },
      { id: "Q-09", text: "What's the current status of every application?" },
      { id: "Q-10", text: "Which applications are still \"live\" (awaiting a reply right now)?", answer: (s) => safeCount(s?.live_applications) },
    ],
  },
  {
    n: 2,
    name: "Rates, Funnels & Time",
    capability: "Ratios and date math on the same table.",
    phase: "Shipped",
    status: "shipped",
    questions: [
      { id: "Q-11", text: "What's my overall response rate?", answer: (_s, r) => ratePercent(r?.overall_response_rate?.rate) },
      { id: "Q-12", text: "What's my rejection rate?", answer: (_s, r) => ratePercent(r?.rejection_rate?.rate) },
      { id: "Q-13", text: "What's my ghost rate (% that go silent)?", answer: (_s, r) => ratePercent(r?.ghost_rate?.rate) },
      { id: "Q-14", text: "What's my application → interview conversion rate?", answer: (_s, r) => ratePercent(r?.application_to_interview_rate?.rate) },
      { id: "Q-15", text: "What's my interview → offer conversion rate?", answer: (_s, r) => ratePercent(r?.interview_to_offer_rate?.rate) },
      { id: "Q-16", text: "What does my full funnel look like (applied → screen → interview → final → offer)?" },
      { id: "Q-17", text: "What's the average time from applying to a first response?" },
      { id: "Q-18", text: "What's the average time-to-rejection?" },
      { id: "Q-19", text: "After how many days of silence is an application effectively dead? (my personal \"ghost threshold\")", answer: (s) => (s?.ghost_threshold_days === undefined ? null : `${s.ghost_threshold_days} days`) },
      { id: "Q-20", text: "How has my application volume trended over time?" },
      { id: "Q-21", text: "Is my response rate improving over time — am I getting better?" },
    ],
  },
  {
    n: 3,
    name: "Segmentation & Breakdowns",
    capability: "GROUP BY role / source / salary / tech / sponsorship.",
    phase: "Shipped",
    status: "shipped",
    questions: [
      { id: "Q-22", text: "Which job titles do I apply to most — and how does each convert?" },
      { id: "Q-23", text: "Which roles get me the most interviews (best-converting titles)?" },
      { id: "Q-24", text: "Which company types (startup vs. enterprise, by industry) respond best?" },
      { id: "Q-25", text: "How do outcomes differ by application source?" },
      { id: "Q-26", text: "What salary bands am I targeting, and how do they convert?" },
      { id: "Q-27", text: "How do remote vs. hybrid vs. onsite roles convert for me?" },
      { id: "Q-28", text: "How many jobs offered visa sponsorship vs. didn't?" },
      { id: "Q-29", text: "What's my response/interview rate for sponsorship vs. non-sponsorship roles?" },
      { id: "Q-30", text: "Which tech stacks/skills show up in the jobs I apply to, and which convert best?" },
      { id: "Q-31", text: "Which seniority levels convert best for me?" },
    ],
  },
  {
    n: 4,
    name: "Diagnostic & Comparative",
    capability: "Correlations; what winners vs. losers share; light stats.",
    phase: "Shipped",
    status: "shipped",
    questions: [
      { id: "Q-32", text: "What do my successful applications (interview/offer) have in common?" },
      { id: "Q-33", text: "What do my rejected/ghosted applications have in common?" },
      { id: "Q-34", text: "Which single factor correlates most with getting a response?" },
      { id: "Q-35", text: "Am I pouring effort into a role/company-type that never converts?" },
      { id: "Q-36", text: "Which application source gives the best ROI (interviews per application)?" },
      { id: "Q-37", text: "Is my sponsorship requirement measurably hurting my response rate — and by how much?" },
      { id: "Q-38", text: "Which of the skills I list actually \"sell\" vs. which are dead weight?" },
      { id: "Q-39", text: "Are there adjacent roles I don't apply to but should?" },
    ],
  },
  {
    n: 5,
    name: "Narrative \"Why\"",
    capability: "LLM synthesis over cited rejection emails, feedback, and related evidence, cached.",
    phase: "Shipped",
    status: "narrative",
    questions: [
      { id: "Q-40", text: "Why am I getting rejected — what are the recurring themes across rejection emails?" },
      { id: "Q-41", text: "What does recruiter/interviewer feedback consistently say I should improve?" },
      { id: "Q-42", text: "Which technologies/skills keep appearing in roles I get rejected from?" },
      { id: "Q-43", text: "What are my strongest and weakest signals across the whole history?" },
      { id: "Q-44", text: "Which roles genuinely suit me best, based on the pattern of my wins?" },
      { id: "Q-45", text: "What are the 3 concrete things I should do next week to improve outcomes?" },
      { id: "Q-46", text: "What's the \"story\" my last 6–12 months of job searching tells?" },
    ],
  },
  {
    n: 6,
    name: "Conversational Recall",
    capability: "Hybrid RAG using semantic retrieval plus structured-query tools.",
    phase: "Planned · Phase 5",
    status: "planned",
    questions: [
      { id: "Q-47", text: "\"What exactly did the recruiter at [Company] say in their last email?\"", plannedNote: "Needs the Phase 5 chat agent and semantic retrieval." },
      { id: "Q-48", text: "\"Show me every rejection that mentioned experience / every company that mentioned sponsorship.\"", plannedNote: "Needs the Phase 5 chat agent and semantic retrieval." },
      { id: "Q-49", text: "\"Who am I waiting on, and who's overdue for a follow-up?\"", plannedNote: "Needs the Phase 5 chat agent." },
      { id: "Q-50", text: "Free-form: ask anything about my job search in natural language.", plannedNote: "Needs the Phase 5 chat agent." },
    ],
  },
  {
    n: 7,
    name: "Predictive / Prescriptive / External",
    capability: "External data or job-board/recruiter APIs.",
    phase: "Planned · Phase 6+",
    status: "planned",
    questions: [
      { id: "Q-51", text: "What's the probability this application converts, given my history?", plannedNote: "Needs a predictive model, not yet planned in detail." },
      { id: "Q-52", text: "How does my response rate compare to benchmarks for my role/market?", plannedNote: "Needs external benchmark data." },
      { id: "Q-53", text: "Which currently-open roles should I prioritize applying to next?", plannedNote: "Needs a job-board API integration." },
      { id: "Q-54", text: "Is this company/recruiter still actively hiring / have they gone quiet on everyone?", plannedNote: "Needs a job-board or recruiter-activity API integration." },
    ],
  },
];

const STATUS_TAG: Record<CatalogStatus, { label: string; bg: string; fg: string }> = {
  shipped: { label: "Shipped", bg: "#E3EFE6", fg: "#1E5136" },
  narrative: { label: "On Insights page", bg: "#F4F2FB", fg: "#4B3FA6" },
  planned: { label: "Planned", bg: "#F7EFDB", fg: "#8A6A14" },
};

export function QuestionCatalogTab({ go, rates, summary }: QuestionCatalogTabProps) {
  const [openId, setOpenId] = useState<string | null>(null);

  const totalQuestions = CATALOG.reduce((sum, tier) => sum + tier.questions.length, 0);
  const answeredQuestions = CATALOG.filter((tier) => tier.status !== "planned").reduce(
    (sum, tier) => sum + tier.questions.length,
    0,
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <div>
        <h1 style={{ margin: 0, fontSize: "22px", fontWeight: 700, letterSpacing: "-0.02em" }}>
          Everything your search can answer
        </h1>
        <p style={{ margin: "6px 0 0", color: "#666D66", fontSize: "13.5px", maxWidth: "660px" }}>
          <strong style={{ color: "#1E5136" }}>
            {answeredQuestions} of {totalQuestions}
          </strong>{" "}
          questions are answerable from your data today, grouped by capability tier and build phase.
          Counts and rates are computed on the backend. Tap any question to see how it's answered.
        </p>
      </div>

      {CATALOG.map((tier) => (
        <div key={tier.n} style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "4px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ margin: 0, fontSize: "12px", fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase", color: "#66886F" }}>
              Tier {tier.n} · {tier.name}
            </h2>
            <span style={{ height: "1px", flex: 1, background: "#E4E2DA", display: "block" }} />
            <span
              style={{
                fontSize: "11px",
                fontWeight: 700,
                padding: "3px 10px",
                borderRadius: "999px",
                background: STATUS_TAG[tier.status].bg,
                color: STATUS_TAG[tier.status].fg,
              }}
            >
              {tier.phase}
            </span>
          </div>
          <div style={{ fontSize: "12px", color: "#9A9F96", margin: "-2px 0 2px" }}>{tier.capability}</div>
          <div style={{ border: "1px solid #E4E2DA", borderRadius: "14px", background: "#fff", overflow: "hidden", boxShadow: "0 1px 2px rgba(20,25,20,0.04)" }}>
            {tier.questions.map((question) => {
              const isOpen = openId === question.id;
              const answer = question.answer?.(summary, rates) ?? null;
              return (
                <div key={question.id} style={{ borderBottom: "1px solid #F0EEE7" }}>
                  <button
                    className="rd-hover-soft"
                    onClick={() => setOpenId((current) => (current === question.id ? null : question.id))}
                    style={{ display: "flex", alignItems: "center", gap: "12px", width: "100%", padding: "12px 16px", border: "none", background: "none", cursor: "pointer", textAlign: "left" }}
                    type="button"
                  >
                    <span style={{ fontSize: "10.5px", fontWeight: 700, color: "#9A9F96", fontFamily: "'JetBrains Mono',monospace", width: "40px", flex: "none" }}>
                      {question.id}
                    </span>
                    <span style={{ flex: 1, fontSize: "13px", color: "#1B201C" }}>{question.text}</span>
                    <span
                      style={{
                        fontSize: "10.5px",
                        fontWeight: 700,
                        padding: "3px 10px",
                        borderRadius: "999px",
                        background: STATUS_TAG[tier.status].bg,
                        color: STATUS_TAG[tier.status].fg,
                        flex: "none",
                      }}
                    >
                      {STATUS_TAG[tier.status].label}
                    </span>
                  </button>
                  {isOpen ? (
                    <div style={{ padding: "0 16px 16px 56px", display: "flex", flexDirection: "column", gap: "10px" }}>
                      {tier.status === "shipped" ? (
                        <p style={{ margin: 0, fontSize: "13px", color: "#4A5049", lineHeight: 1.6 }}>
                          {answer !== null
                            ? `Current answer: ${answer}`
                            : "Answered from your applications and events data. See the Applications and Overview tabs for the full breakdown."}
                        </p>
                      ) : null}
                      {tier.status === "narrative" ? (
                        <>
                          <p style={{ margin: 0, fontSize: "13px", color: "#4A5049", lineHeight: 1.6 }}>
                            Answered as a cached, evidence-cited narrative on the Insights page.
                          </p>
                          <button
                            className="rd-hover-purple"
                            onClick={() => go("insights")}
                            style={{ alignSelf: "flex-start", padding: "7px 14px", border: "none", borderRadius: "999px", background: "#6C5FC7", color: "#fff", fontSize: "12px", fontWeight: 600, cursor: "pointer" }}
                            type="button"
                          >
                            See this on the Insights page →
                          </button>
                        </>
                      ) : null}
                      {tier.status === "planned" ? (
                        <div style={{ fontSize: "12px", color: "#8A6A14", background: "#F7EFDB", borderRadius: "8px", padding: "8px 12px" }}>
                          Planned — {question.plannedNote ?? "not built yet."}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
