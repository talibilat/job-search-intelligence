import type { CSSProperties } from "react";

import type { ApplicationEventType, ApplicationStatus } from "../api";

type StatusVisualKey =
  | "applied"
  | "screening"
  | "interview"
  | "offer"
  | "rejected"
  | "ghosted";

const STATUS: Record<StatusVisualKey, { label: string; fg: string; bg: string }> = {
  applied: { label: "Applied", fg: "#5C6660", bg: "#EEF0ED" },
  screening: { label: "In review", fg: "#8A6A14", bg: "#F7EFDB" },
  interview: { label: "Interview", fg: "#1E5136", bg: "#E3EFE6" },
  offer: { label: "Offer", fg: "#F6F4EC", bg: "#1E5136" },
  rejected: { label: "Rejected", fg: "#96403C", bg: "#F6E9E7" },
  ghosted: { label: "No response", fg: "#6B7268", bg: "#EFEFEC" },
};

function statusVisualKey(status: ApplicationStatus): StatusVisualKey {
  switch (status) {
    case "in_review":
    case "assessment":
      return "screening";
    case "interview":
      return "interview";
    case "offer":
      return "offer";
    case "rejected":
      return "rejected";
    case "ghosted":
    case "withdrawn":
      return "ghosted";
    default:
      return "applied";
  }
}

export function pillStyle(status: ApplicationStatus): CSSProperties {
  const visual = STATUS[statusVisualKey(status)];
  return {
    display: "inline-block",
    padding: "3px 10px",
    borderRadius: "999px",
    background: visual.bg,
    color: visual.fg,
    fontSize: "11.5px",
    fontWeight: 700,
  };
}

export function pillLabel(status: ApplicationStatus): string {
  if (status === "withdrawn") {
    return "Withdrawn";
  }
  return STATUS[statusVisualKey(status)].label;
}

const LOGO_HUES: Record<string, number> = {
  V: 155,
  N: 30,
  R: 210,
  L: 260,
  F: 15,
  D: 290,
  G: 120,
  C: 190,
  S: 250,
  A: 350,
  I: 45,
};

export function logoStyle(name: string): CSSProperties {
  const initial = (name[0] ?? "?").toUpperCase();
  const hue = LOGO_HUES[initial] ?? 100;
  return {
    width: "30px",
    height: "30px",
    borderRadius: "8px",
    flex: "none",
    background: `oklch(0.93 0.03 ${hue})`,
    color: `oklch(0.4 0.08 ${hue})`,
    display: "grid",
    placeItems: "center",
    fontWeight: 700,
    fontSize: "13px",
  };
}

export const EVENT_LABELS: Record<ApplicationEventType, string> = {
  applied: "Applied",
  response: "Response received",
  assessment: "Assessment",
  interview_scheduled: "Interview scheduled",
  feedback: "Feedback received",
  rejection: "Rejected",
  offer: "Offer received",
  ghost_inferred: "Marked no response",
};

export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) {
    return "";
  }
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function formatRelativeTime(iso: string | null | undefined): string | null {
  if (!iso) {
    return null;
  }
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  const deltaMs = Date.now() - parsed.getTime();
  if (deltaMs < 0) {
    return "just now";
  }
  const minutes = Math.floor(deltaMs / 60_000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes} min ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export function daysSince(iso: string | null | undefined): number | null {
  if (!iso) {
    return null;
  }
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 86_400_000));
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

export function formatHoursAsDuration(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) {
    return "—";
  }
  if (hours < 24) {
    return `${Math.round(hours)}h`;
  }
  const days = hours / 24;
  return `${days < 10 ? Math.round(days * 10) / 10 : Math.round(days)}d`;
}
