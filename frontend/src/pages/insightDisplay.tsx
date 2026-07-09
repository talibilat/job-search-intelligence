import { Fragment, type ReactNode } from "react";

import { InsightType, type InsightRecord } from "../api";

export interface InsightDisplayConfig {
  description: string;
  emptyMessage: string;
  question: string;
  title: string;
  type: InsightRecord["type"];
}

export const INSIGHT_CARDS: InsightDisplayConfig[] = [
  {
    description:
      "Recurring rejection themes from cited rejection evidence, not dashboard counts.",
    emptyMessage:
      "No cached rejection themes insight yet. Regenerate it after rejection evidence is available.",
    question: "Q-40",
    title: "Rejection themes",
    type: InsightType.why_rejected,
  },
  {
    description:
      "Consistent recruiter or interviewer feedback from cited feedback timeline events.",
    emptyMessage:
      "No cached recurring recruiter feedback insight yet. Regenerate it after the source timeline has enough evidence.",
    question: "Q-41",
    title: "Recurring recruiter feedback",
    type: InsightType.recurring_feedback,
  },
  {
    description:
      "Technologies and skills that recur in rejected-role evidence.",
    emptyMessage:
      "No cached rejected-role skill gaps insight yet. Regenerate it after rejected applications include skill evidence.",
    question: "Q-42",
    title: "Rejected-role skill gaps",
    type: InsightType.skill_gaps,
  },
  {
    description:
      "Whole-history strongest and weakest signals grounded in cited applications.",
    emptyMessage:
      "No cached strongest and weakest signals insight yet. Regenerate it after application history is available.",
    question: "Q-43",
    title: "Strongest and weakest signals",
    type: InsightType.strongest_weakest_signals,
  },
  {
    description:
      "Role-fit synthesis from deterministic win/loss role summaries and citations.",
    emptyMessage:
      "No cached best-fit roles insight yet. Regenerate it after enough role outcome evidence is available.",
    question: "Q-44",
    title: "Best-fit roles",
    type: InsightType.role_fit,
  },
  {
    description:
      "Exactly three cited actions to improve outcomes during the next week.",
    emptyMessage:
      "No cached next-week actions insight yet. Regenerate it after open-application evidence is available.",
    question: "Q-45",
    title: "Next-week actions",
    type: InsightType.weekly_actions,
  },
  {
    description:
      "A cited narrative of the last 6 to 12 months of job-search evidence.",
    emptyMessage:
      "No cached search story insight yet. Regenerate it after recent timeline evidence is available.",
    question: "Q-46",
    title: "Search story",
    type: InsightType.story,
  },
];

function splitCitationTokens(value: string) {
  return value
    .replaceAll(";", ",")
    .split(/[,\n]/)
    .map((citationId) => citationId.trim())
    .filter(Boolean);
}

function isCitationLike(value: string) {
  return /(^|\|)(application|event|email):[^|\s]+/.test(value);
}

function applicationCitationHref(citationId: string) {
  const match = /(^|\|)application:([^|]+)/.exec(citationId);
  if (!match) {
    return null;
  }

  return `/applications/${encodeURIComponent(match[2])}`;
}

export function renderTextWithCitationLinks(content: string) {
  const parts: ReactNode[] = [];
  let lastIndex = 0;

  for (const match of content.matchAll(/\[([^\]]+)\]/g)) {
    const matchIndex = match.index;
    if (matchIndex > lastIndex) {
      parts.push(content.slice(lastIndex, matchIndex));
    }

    const citationIds = splitCitationTokens(match[1]);
    if (citationIds.length > 0 && citationIds.every(isCitationLike)) {
      parts.push(
        <span className="insight-card__inline-citations" key={matchIndex}>
          [
          {citationIds.map((citationId, index) => {
            const href = applicationCitationHref(citationId);
            return (
              <Fragment key={citationId}>
                {index > 0 ? "; " : null}
                {href ? <a href={href}>{citationId}</a> : citationId}
              </Fragment>
            );
          })}
          ]
        </span>,
      );
    } else {
      parts.push(match[0]);
    }

    lastIndex = matchIndex + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }

  return parts;
}
