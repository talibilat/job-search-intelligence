import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

import {
  getApplicationEventsApplicationsIdEventsGet,
  getApplicationStatusCountsApplicationsStatusCountsGet,
  listApplicationsApplicationsGet,
  type ApplicationRecord,
  type ApplicationStatus,
  type ApplicationStatusCountsResponse,
} from "../../api";
import type { StatusChipKey } from "../RedesignApp";
import { publicApiError } from "../apiError";
import {
  daysSince,
  EVENT_LABELS,
  formatShortDate,
  logoStyle,
  pillLabel,
  pillStyle,
} from "../theme";

interface ApplicationsPageProps {
  openApp: (id: string) => void;
  reloadKey: number;
  setStatusFilter: (key: StatusChipKey) => void;
  statusFilter: StatusChipKey;
}

type ViewKey = "table" | "board" | "list";

interface TimelineDot {
  title: string;
  isLast: boolean;
}

type TimelineState =
  | { state: "loading" }
  | { state: "success"; dots: TimelineDot[] }
  | { state: "error"; message: string };

const CLOSED_STATUSES: ApplicationStatus[] = ["rejected", "ghosted", "withdrawn"];
const SCREENING_STATUSES: ApplicationStatus[] = ["in_review", "assessment"];

function chipMatches(chip: StatusChipKey, status: ApplicationStatus): boolean {
  switch (chip) {
    case "all":
      return true;
    case "closed":
      return CLOSED_STATUSES.includes(status);
    case "screening":
      return SCREENING_STATUSES.includes(status);
    default:
      return status === chip;
  }
}

function statusesForChip(chip: StatusChipKey): ApplicationStatus[] {
  if (chip === "all") {
    return [];
  }
  if (chip === "closed") {
    return CLOSED_STATUSES;
  }
  if (chip === "screening") {
    return SCREENING_STATUSES;
  }
  return [chip];
}

function latestUpdateText(application: ApplicationRecord): string {
  const date = formatShortDate(application.last_activity_at);
  switch (application.current_status) {
    case "applied": {
      const quietDays = daysSince(application.last_activity_at);
      return quietDays !== null && quietDays > 0
        ? `No response yet (${quietDays} day${quietDays === 1 ? "" : "s"})`
        : "Application sent";
    }
    case "in_review":
      return `In review since ${date}`;
    case "assessment":
      return `Assessment in progress · ${date}`;
    case "interview":
      return `Interview activity ${date}`;
    case "offer":
      return `Offer received ${date}`;
    case "rejected":
      return `Rejected ${date}`;
    case "ghosted": {
      const silentDays = daysSince(application.last_activity_at);
      return silentDays !== null ? `No reply in ${silentDays} days` : "No reply";
    }
    case "withdrawn":
      return `Withdrawn ${date}`;
    default:
      return date;
  }
}

export function ApplicationsPage({
  openApp,
  reloadKey,
  setStatusFilter,
  statusFilter,
}: ApplicationsPageProps) {
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [counts, setCounts] = useState<ApplicationStatusCountsResponse | null>(null);
  const [view, setView] = useState<ViewKey>("table");
  const [timelineStates, setTimelineStates] = useState<Record<string, TimelineState>>({});
  const [applicationsLoading, setApplicationsLoading] = useState(true);
  const [applicationsError, setApplicationsError] = useState<string | null>(null);
  const [countsError, setCountsError] = useState<string | null>(null);
  const applicationGeneration = `${reloadKey}:${statusFilter}`;
  const [loadedApplicationGeneration, setLoadedApplicationGeneration] = useState<string | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setApplicationsLoading(true);
      setApplicationsError(null);
      setApplications([]);
      setCounts(null);
      setCountsError(null);
      setTimelineStates({});
      setLoadedApplicationGeneration(null);
      const statuses = statusesForChip(statusFilter);
      const [applicationsResponse, countsResponse] = await Promise.all([
        Promise.all(
          (statuses.length > 0 ? statuses : [null]).map((status) =>
            listApplicationsApplicationsGet(status ? { status } : undefined).catch((error: unknown) => ({ error })),
          ),
        ),
        getApplicationStatusCountsApplicationsStatusCountsGet().catch((error: unknown) => ({ error })),
      ]);
      if (cancelled) {
        return;
      }
      const failedResponse = applicationsResponse.find(
        (response) => !("status" in response) || response.status !== 200,
      );
      if (failedResponse) {
        setApplications([]);
        setApplicationsError(
          publicApiError(
            "status" in failedResponse ? { response: failedResponse } : failedResponse.error,
            "Applications could not be loaded.",
          ),
        );
      } else {
        const merged = new Map<string, ApplicationRecord>();
        for (const response of applicationsResponse) {
          if ("status" in response && response.status === 200) {
            for (const application of response.data) {
              merged.set(application.id, application);
            }
          }
        }
        setApplications(
          [...merged.values()].sort(
            (left, right) =>
              Date.parse(right.first_seen_at) - Date.parse(left.first_seen_at) ||
              left.id.localeCompare(right.id),
          ),
        );
      }
      setApplicationsLoading(false);
      setLoadedApplicationGeneration(applicationGeneration);
      if ("status" in countsResponse && countsResponse.status === 200) {
        setCounts(countsResponse.data);
      } else {
        setCounts(null);
        setCountsError(publicApiError("status" in countsResponse ? { response: countsResponse } : countsResponse.error, "Status totals could not be loaded."));
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [applicationGeneration, statusFilter]);

  const filtered = useMemo(
    () =>
      applications.filter((application) => chipMatches(statusFilter, application.current_status)),
    [applications, statusFilter],
  );

  useEffect(() => {
    if (view !== "list" || loadedApplicationGeneration !== applicationGeneration) {
      return;
    }
    let cancelled = false;
    const missing = filtered.filter((application) => !(application.id in timelineStates));
    if (missing.length === 0) {
      return;
    }
    const load = async () => {
      const results = await Promise.all(
        missing.map(async (application) => {
          const response = await getApplicationEventsApplicationsIdEventsGet(
            application.id,
          ).catch(() => null);
          if (response?.status !== 200) {
            return [
              application.id,
              {
                state: "error",
                message: publicApiError(
                  response ? { response } : response,
                  "Timeline could not be loaded.",
                ),
              } satisfies TimelineState,
            ] as const;
          }
          const events = response.data;
          const dots = events.map((event, index) => ({
            title: `${EVENT_LABELS[event.event_type]} · ${formatShortDate(event.event_at)}`,
            isLast: index === events.length - 1,
          }));
          return [application.id, { state: "success", dots } satisfies TimelineState] as const;
        }),
      );
      if (cancelled) {
        return;
      }
      setTimelineStates((current) => {
        const next = { ...current };
        for (const [id, state] of results) {
          next[id] = state;
        }
        return next;
      });
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [view, filtered, timelineStates, applicationGeneration, loadedApplicationGeneration]);

  const total = counts?.total ?? applications.length;
  const countFor = (chip: StatusChipKey): number => {
    if (!counts) {
      return applications.filter((application) =>
        chipMatches(chip, application.current_status),
      ).length;
    }
    if (chip === "all") {
      return counts.total;
    }
    if (chip === "closed") {
      return CLOSED_STATUSES.reduce((sum, status) => sum + (counts.counts[status] ?? 0), 0);
    }
    if (chip === "screening") {
      return SCREENING_STATUSES.reduce((sum, status) => sum + (counts.counts[status] ?? 0), 0);
    }
    return counts.counts[chip] ?? 0;
  };

  const chips: { key: StatusChipKey; label: string }[] = [
    { key: "all", label: "All" },
    { key: "applied", label: "Applied" },
    { key: "screening", label: "In review" },
    { key: "interview", label: "Interview" },
    { key: "offer", label: "Offer" },
    { key: "closed", label: "Closed" },
  ];

  const viewButtonStyle = (key: ViewKey): CSSProperties => ({
    padding: "6px 14px",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    fontSize: "12.5px",
    fontWeight: 600,
    background: view === key ? "#1B201C" : "transparent",
    color: view === key ? "#fff" : "#666D66",
  });

  const boardColumns: { key: StatusChipKey; title: string }[] = [
    { key: "applied", title: "Applied" },
    { key: "screening", title: "In review" },
    { key: "interview", title: "Interview" },
    { key: "offer", title: "Offer" },
    { key: "closed", title: "Closed" },
  ];

  return (
    <section
      style={{
        maxWidth: "1060px",
        margin: "0 auto",
        padding: "28px 32px 60px",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: "22px", fontWeight: 700, letterSpacing: "-0.02em" }}>
            Applications
          </h1>
          <p style={{ margin: "4px 0 0", color: "#666D66", fontSize: "13px" }}>
            {filtered.length} of {total} applications — found automatically in your email.{" "}
            <a href="/settings">Missing one?</a>
          </p>
        </div>
        <div
          style={{
            display: "flex",
            gap: "2px",
            padding: "3px",
            border: "1px solid #E4E2DA",
            borderRadius: "10px",
            background: "#fff",
          }}
        >
          <button onClick={() => setView("table")} style={viewButtonStyle("table")} type="button">
            Table
          </button>
          <button onClick={() => setView("board")} style={viewButtonStyle("board")} type="button">
            Board
          </button>
          <button onClick={() => setView("list")} style={viewButtonStyle("list")} type="button">
            Timeline
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        {chips.map((chip) => {
          const selected = statusFilter === chip.key;
          return (
            <button
              key={chip.key}
              onClick={() => setStatusFilter(chip.key)}
              style={{
                padding: "6px 13px",
                borderRadius: "999px",
                cursor: "pointer",
                fontSize: "12.5px",
                fontWeight: 600,
                border: selected ? "1px solid #1E5136" : "1px solid #E4E2DA",
                background: selected ? "#1E5136" : "#fff",
                color: selected ? "#F6F4EC" : "#4A5049",
              }}
              type="button"
            >
              {chip.label} <span style={{ opacity: 0.6 }}>{countFor(chip.key)}</span>
            </button>
          );
        })}
      </div>
      {countsError ? (
        <p role="alert" style={{ margin: 0, fontSize: "12.5px", color: "#96403C" }}>{countsError} Showing counts from the visible applications only.</p>
      ) : null}

      {applicationsLoading ? (
        <p style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>Loading applications…</p>
      ) : null}
      {!applicationsLoading && applicationsError ? (
        <p role="alert" style={{ margin: 0, fontSize: "12.5px", color: "#96403C" }}>
          {applicationsError}
        </p>
      ) : null}
      {!applicationsLoading && !applicationsError && filtered.length === 0 ? (
        <p style={{ margin: 0, fontSize: "12.5px", color: "#9A9F96" }}>No applications match this status.</p>
      ) : null}

      {view === "table" ? (
        <div
          style={{
            border: "1px solid #E4E2DA",
            borderRadius: "14px",
            background: "#fff",
            overflow: "hidden",
            boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "2fr 1.6fr 1fr 1fr 1.6fr",
              gap: "12px",
              padding: "10px 18px",
              background: "#FAFAF7",
              borderBottom: "1px solid #E9E7DF",
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "#9A9F96",
            }}
          >
            <span>Company</span>
            <span>Role</span>
            <span>Status</span>
            <span>Applied</span>
            <span>Latest update</span>
          </div>
          {filtered.map((application) => (
            <button
              className="rd-hover-row"
              key={application.id}
              onClick={() => openApp(application.id)}
              style={{
                display: "grid",
                gridTemplateColumns: "2fr 1.6fr 1fr 1fr 1.6fr",
                gap: "12px",
                alignItems: "center",
                width: "100%",
                padding: "13px 18px",
                border: "none",
                borderBottom: "1px solid #F0EEE7",
                background: "#fff",
                cursor: "pointer",
                textAlign: "left",
                fontSize: "13.5px",
              }}
              type="button"
            >
              <span style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
                <span style={logoStyle(application.company)}>{application.company[0]}</span>
                <span style={{ fontWeight: 600, color: "#1B201C" }}>{application.company}</span>
              </span>
              <span style={{ color: "#4A5049" }}>{application.role_title}</span>
              <span>
                <span style={pillStyle(application.current_status)}>
                  {pillLabel(application.current_status)}
                </span>
              </span>
              <span style={{ color: "#666D66", fontVariantNumeric: "tabular-nums" }}>
                {formatShortDate(application.first_seen_at)}
              </span>
              <span style={{ color: "#666D66", fontSize: "12.5px" }}>
                {latestUpdateText(application)}
              </span>
            </button>
          ))}
        </div>
      ) : null}

      {view === "board" ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(5,minmax(0,1fr))",
            gap: "12px",
            alignItems: "start",
          }}
        >
          {boardColumns.map((column) => {
            const cards = filtered.filter((application) =>
              chipMatches(column.key, application.current_status),
            );
            return (
              <div
                key={column.key}
                style={{ display: "flex", flexDirection: "column", gap: "8px" }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "4px 4px 2px",
                  }}
                >
                  <span style={{ fontSize: "12px", fontWeight: 700, color: "#4A5049" }}>
                    {column.title}
                  </span>
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 600,
                      color: "#9A9F96",
                      background: "#EDEBE4",
                      borderRadius: "999px",
                      padding: "1px 8px",
                    }}
                  >
                    {cards.length}
                  </span>
                </div>
                {cards.map((application) => (
                  <button
                    className="rd-hover-green-border"
                    key={application.id}
                    onClick={() => openApp(application.id)}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "5px",
                      padding: "12px 14px",
                      border: "1px solid #E4E2DA",
                      borderRadius: "12px",
                      background: "#fff",
                      cursor: "pointer",
                      textAlign: "left",
                      boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
                    }}
                    type="button"
                  >
                    <span style={{ fontWeight: 600, fontSize: "13px", color: "#1B201C" }}>
                      {application.company}
                    </span>
                    <span style={{ fontSize: "12px", color: "#666D66" }}>
                      {application.role_title}
                    </span>
                    <span style={{ fontSize: "11px", color: "#9A9F96" }}>
                      {latestUpdateText(application)}
                    </span>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      ) : null}

      {view === "list" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {filtered.map((application) => {
            const timeline = timelineStates[application.id] ?? { state: "loading" as const };
            const dots = timeline.state === "success" ? timeline.dots : [];
            return (
              <button
                className="rd-hover-green-border"
                key={application.id}
                onClick={() => openApp(application.id)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "2fr 3fr 1.4fr",
                  gap: "16px",
                  alignItems: "center",
                  padding: "14px 18px",
                  border: "1px solid #E4E2DA",
                  borderRadius: "12px",
                  background: "#fff",
                  cursor: "pointer",
                  textAlign: "left",
                }}
                type="button"
              >
                <span style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span style={logoStyle(application.company)}>{application.company[0]}</span>
                  <span>
                    <span style={{ display: "block", fontWeight: 600, fontSize: "13.5px" }}>
                      {application.company}
                    </span>
                    <span style={{ display: "block", fontSize: "12px", color: "#666D66" }}>
                      {application.role_title}
                    </span>
                  </span>
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                  {dots.map((dot, index) => (
                    <span
                      key={index}
                      style={{ display: "flex", alignItems: "center", gap: "4px" }}
                    >
                      <span
                        style={{
                          width: "9px",
                          height: "9px",
                          borderRadius: "50%",
                          flex: "none",
                          background: dot.isLast ? "#1E5136" : "#B9C9BD",
                        }}
                        title={dot.title}
                      />
                      {dot.isLast ? null : (
                        <span
                          style={{
                            display: "block",
                            width: "14px",
                            height: "2px",
                            background: "#DCE5DE",
                          }}
                        />
                      )}
                    </span>
                  ))}
                  <span style={{ fontSize: "11.5px", color: "#9A9F96", marginLeft: "6px" }}>
                    {timeline.state === "loading"
                      ? "Loading…"
                      : timeline.state === "error"
                        ? timeline.message
                        : dots.length > 0
                          ? `${dots.length} step${dots.length > 1 ? "s" : ""}`
                          : "No timeline events"}
                  </span>
                </span>
                <span style={{ textAlign: "right" }}>
                  <span style={pillStyle(application.current_status)}>
                    {pillLabel(application.current_status)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
