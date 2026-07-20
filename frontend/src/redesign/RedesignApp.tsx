import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import {
  listEmailConnectionsAuthConnectionsGet,
  syncEstimateSyncEstimateGet,
  syncNowSyncPost,
  syncStatusSyncStatusGet,
  providerReadinessConfigProvidersReadinessGet,
  processingRunProcessingRunPost,
  processingStatusProcessingStatusGet,
  type EmailConnection,
  type EmailSyncOptions,
  type EmailSyncStatus,
  type ProcessingStatus,
  type SyncLocalStats,
  syncStatsSyncStatsGet,
} from "../api";
import { safeDecodeApplicationRouteSegment } from "../lib/applicationRoutes";
import { enumQueryParam, parseRouteQuery, updateRouteQuery } from "../lib/routeQuery";
import { publicApiError } from "./apiError";
import { ChatDrawer } from "./ChatDrawer";
import { formatCount, formatRelativeTime } from "./theme";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { ChatArchitecturePage } from "./pages/ChatArchitecturePage";
import { DetailPage } from "./pages/DetailPage";
import { DeveloperPage } from "./pages/DeveloperPage";
import { InsightsPage } from "./pages/InsightsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SettingsPage } from "./pages/SettingsPage";
import "./redesign.css";

export type RedesignPage =
  | "overview"
  | "applications"
  | "detail"
  | "insights"
  | "chat"
  | "chatArchitecture"
  | "settings"
  | "dev";

interface RedesignRoute {
  page: RedesignPage;
  detailId: string | null;
  statusFilter: StatusChipKey;
}

export type StatusChipKey =
  | "all"
  | "applied"
  | "screening"
  | "interview"
  | "offer"
  | "closed";

export type RequestLoadState = "error" | "loading" | "ready";

const STATUS_FILTERS: readonly StatusChipKey[] = [
  "all",
  "applied",
  "screening",
  "interview",
  "offer",
  "closed",
];

const redesignQuerySchema = {
  statusFilter: enumQueryParam("status", STATUS_FILTERS, "all"),
} as const;

export function redesignRouteFromPath(pathname: string): RedesignRoute | null {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/") {
    return { page: "overview", detailId: null, statusFilter: "all" };
  }
  if (path === "/applications") {
    return { page: "applications", detailId: null, statusFilter: "all" };
  }
  const detailMatch = /^\/applications\/([^/]+)$/.exec(path);
  if (detailMatch) {
    const decoded = safeDecodeApplicationRouteSegment(detailMatch[1]);
    if (decoded) {
      return { page: "detail", detailId: decoded, statusFilter: "all" };
    }
    return null;
  }
  if (path === "/insights") {
    return { page: "insights", detailId: null, statusFilter: "all" };
  }
  if (path === "/chat") {
    return { page: "chat", detailId: null, statusFilter: "all" };
  }
  if (path === "/chat/architecture") {
    return { page: "chatArchitecture", detailId: null, statusFilter: "all" };
  }
  if (path === "/settings") {
    return { page: "settings", detailId: null, statusFilter: "all" };
  }
  if (path === "/dev") {
    return { page: "dev", detailId: null, statusFilter: "all" };
  }
  return null;
}

export function redesignRouteFromLocation(
  pathname: string,
  search: string,
): RedesignRoute {
  const route = redesignRouteFromPath(pathname) ?? {
    page: "detail" as const,
    detailId: null,
    statusFilter: "all" as const,
  };
  if (route.page !== "applications") {
    return route;
  }
  const { statusFilter } = parseRouteQuery(search, redesignQuerySchema);
  return { ...route, statusFilter: statusFilter ?? "all" };
}

export function pathForRoute(route: RedesignRoute, search = ""): string {
  let path: string;
  if (route.page === "overview") {
    path = "/";
  } else if (route.page === "detail" && route.detailId) {
    path = `/applications/${encodeURIComponent(route.detailId)}`;
  } else if (route.page === "chatArchitecture") {
    path = "/chat/architecture";
  } else {
    path = `/${route.page}`;
  }
  if (route.page !== "applications") {
    return path;
  }
  return `${path}${updateRouteQuery(search, { statusFilter: route.statusFilter }, redesignQuerySchema)}`;
}

const PAGE_TITLES: Record<RedesignPage, string> = {
  overview: "Overview",
  applications: "Applications",
  detail: "Application",
  insights: "Insights",
  chat: "Ask your job search",
  chatArchitecture: "Chat architecture",
  settings: "Settings",
  dev: "For developers",
};

type SyncScopeKey = "new" | "7" | "30" | "custom" | "count";

type CompletedSyncScope = Readonly<{
  sentAfter?: string;
  sentBefore?: string;
}>;

const SYNC_SCOPES: { key: SyncScopeKey; label: string; note: string }[] = [
  { key: "new", label: "New mail since last sync", note: "Recommended — fastest" },
  { key: "7", label: "Last 7 days", note: "Re-checks the past week" },
  { key: "30", label: "Last 30 days", note: "Catches late replies" },
  { key: "custom", label: "A specific date range", note: "Pick start and end dates" },
  { key: "count", label: "Only the most recent emails", note: "Cap by number of emails" },
];

const SYNC_POLL_MAX_ATTEMPTS = 600;
const SYNC_POLL_INTERVAL_MS = 1000;

function exclusiveDayAfter(dateInput: string): string {
  const [year, month, day] = dateInput.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + 1))
    .toISOString()
    .slice(0, 10);
}

function syncOptionsForScope(
  scope: SyncScopeKey,
  customFrom: string,
  customTo: string,
  lastCount: number,
): EmailSyncOptions | null {
  if (scope === "7") {
    return { max_age_days: 7 };
  }
  if (scope === "30") {
    return { max_age_days: 30 };
  }
  if (scope === "custom") {
    return {
      before_date: customTo ? exclusiveDayAfter(customTo) : null,
      since_date: customFrom || null,
    };
  }
  if (scope === "count") {
    return { max_messages: lastCount };
  }
  return null;
}

function completedSyncScope(
  scope: SyncScopeKey,
  customFrom: string,
  customTo: string,
): CompletedSyncScope {
  if (scope === "7" || scope === "30") {
    const days = Number(scope);
    return {
      sentAfter: new Date(
        Date.now() - days * 24 * 60 * 60 * 1000,
      ).toISOString(),
    };
  }
  if (scope === "custom") {
    let sentAfter: string | undefined;
    let sentBefore: string | undefined;
    if (customFrom) {
      const [fromYear, fromMonth, fromDay] = customFrom.split("-").map(Number);
      sentAfter = new Date(
        Date.UTC(fromYear, fromMonth - 1, fromDay),
      ).toISOString();
    }
    if (customTo) {
      sentBefore = new Date(
        `${exclusiveDayAfter(customTo)}T00:00:00Z`,
      ).toISOString();
    }
    return { sentAfter, sentBefore };
  }
  return {};
}

export function RedesignApp({ initialRoute }: { initialRoute: RedesignRoute }) {
  const [route, setRoute] = useState<RedesignRoute>(() => {
    const parsed = redesignRouteFromPath(window.location.pathname);
    return parsed
      ? redesignRouteFromLocation(window.location.pathname, window.location.search)
      : initialRoute;
  });
  const [reloadKey, setReloadKey] = useState(0);
  const [completedScope, setCompletedScope] = useState<CompletedSyncScope>({});

  const [connections, setConnections] = useState<EmailConnection[]>([]);
  const [connectionsLoadState, setConnectionsLoadState] = useState<RequestLoadState>("loading");
  const [connectionsError, setConnectionsError] = useState<string | null>(null);
  const [syncStats, setSyncStats] = useState<SyncLocalStats | null>(null);
  const [syncStatsLoadState, setSyncStatsLoadState] = useState<RequestLoadState>("loading");
  const [syncStatsError, setSyncStatsError] = useState<string | null>(null);
  const connectionsRequestId = useRef(0);
  const syncStatsRequestId = useRef(0);

  const [syncMenuOpen, setSyncMenuOpen] = useState(false);
  const [syncScope, setSyncScope] = useState<SyncScopeKey>("new");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [lastCount, setLastCount] = useState(500);
  const [syncEstimateLabel, setSyncEstimateLabel] = useState("");
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [syncFlowOpen, setSyncFlowOpen] = useState(false);
  const [syncFlowStage, setSyncFlowStage] = useState<"syncing" | "filtering" | "retaining" | "classifying" | "complete" | "failed">("syncing");
  const [syncFlowEmailCount, setSyncFlowEmailCount] = useState(0);
  const [syncFlowTotalEmailCount, setSyncFlowTotalEmailCount] = useState(0);
  const [processingStatus, setProcessingStatus] = useState<ProcessingStatus | null>(null);
  const syncingRef = useRef(false);
  const syncRunIdRef = useRef(0);
  const customRangeInvalid =
    syncScope === "custom" && (!customFrom || !customTo || customFrom >= customTo);

  const refresh = useCallback(() => {
    setReloadKey((value) => value + 1);
  }, []);

  useEffect(() => () => {
    syncRunIdRef.current += 1;
    syncingRef.current = false;
  }, []);

  const navigate = useCallback((next: RedesignRoute) => {
    setRoute(next);
    const path = pathForRoute(next, next.page === "applications" ? window.location.search : "");
    if (`${window.location.pathname}${window.location.search}` !== path) {
      window.history.pushState(null, "", path);
    }
    window.scrollTo(0, 0);
  }, []);

  useEffect(() => {
    const onPopState = () => {
      const parsed = redesignRouteFromPath(window.location.pathname);
      if (parsed) {
        setRoute(redesignRouteFromLocation(window.location.pathname, window.location.search));
      } else {
        window.location.reload();
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const go = useCallback(
    (page: RedesignPage, extra?: { statusFilter?: StatusChipKey }) => {
      if (extra?.statusFilter) {
        navigate({ page, detailId: null, statusFilter: extra.statusFilter });
        return;
      }
      navigate({ page, detailId: null, statusFilter: page === "applications" ? route.statusFilter : "all" });
    },
    [navigate, route.statusFilter],
  );

  const openApp = useCallback(
    (id: string) => {
      navigate({ page: "detail", detailId: id, statusFilter: "all" });
    },
    [navigate],
  );

  const loadConnections = useCallback(async () => {
    await Promise.resolve();
    const requestId = ++connectionsRequestId.current;
    setConnectionsLoadState("loading");
    setConnectionsError(null);
    try {
      const response = await listEmailConnectionsAuthConnectionsGet();
      if (requestId !== connectionsRequestId.current) return;
      if (response.status !== 200) {
        setConnections([]);
        setConnectionsError(publicApiError({ response }, "Inbox connections could not be loaded."));
        setConnectionsLoadState("error");
        return;
      }
      setConnections(response.data);
      setConnectionsLoadState("ready");
    } catch (error) {
      if (requestId !== connectionsRequestId.current) return;
      setConnections([]);
      setConnectionsError(publicApiError(error, "Inbox connections could not be loaded. Check the local backend."));
      setConnectionsLoadState("error");
    }
  }, []);

  const loadSyncStats = useCallback(async () => {
    await Promise.resolve();
    const requestId = ++syncStatsRequestId.current;
    setSyncStatsLoadState("loading");
    setSyncStatsError(null);
    try {
      const response = await syncStatsSyncStatsGet();
      if (requestId !== syncStatsRequestId.current) return;
      if (response.status !== 200) {
        setSyncStats(null);
        setSyncStatsError(publicApiError({ response }, "Sync statistics could not be loaded."));
        setSyncStatsLoadState("error");
        return;
      }
      setSyncStats(response.data);
      setSyncStatsLoadState("ready");
    } catch (error) {
      if (requestId !== syncStatsRequestId.current) return;
      setSyncStats(null);
      setSyncStatsError(publicApiError(error, "Sync statistics could not be loaded. Check the local backend."));
      setSyncStatsLoadState("error");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) {
        void loadConnections();
        void loadSyncStats();
      }
    });
    return () => {
      cancelled = true;
      connectionsRequestId.current += 1;
      syncStatsRequestId.current += 1;
    };
  }, [loadConnections, loadSyncStats, reloadKey]);

  useEffect(() => {
    if (!syncMenuOpen) {
      return;
    }
    let cancelled = false;
    const options = syncOptionsForScope(syncScope, customFrom, customTo, lastCount);
    if (customRangeInvalid) {
      return;
    }
    const load = async () => {
      const response = await syncEstimateSyncEstimateGet({
        before_date: options?.before_date ?? undefined,
        max_age_days: options?.max_age_days ?? undefined,
        max_messages: options?.max_messages ?? undefined,
        since_date: options?.since_date ?? undefined,
      }).catch(() => null);
      if (cancelled) {
        return;
      }
      if (response?.status !== 200) {
        setSyncEstimateLabel("Estimate unavailable");
        return;
      }
      const estimate = response.data;
      if (estimate.basis === "full_backfill") {
        setSyncEstimateLabel("Full mailbox history · time depends on mailbox size");
        return;
      }
      if (estimate.basis === "unknown_incremental_window") {
        setSyncEstimateLabel("New mail in selected date range · count unknown");
        return;
      }
      if (
        estimate.basis === "message_cap" &&
        estimate.estimated_message_count !== null &&
        estimate.estimated_message_count !== undefined
      ) {
        setSyncEstimateLabel(
          `Up to ${formatCount(estimate.estimated_message_count)} new emails`,
        );
        return;
      }
      if (estimate.estimated_message_count === null || estimate.estimated_message_count === undefined) {
        setSyncEstimateLabel("New mail only · usually under a minute");
        return;
      }
      const count = estimate.estimated_message_count;
      const duration = count < 200 ? "under a minute" : count < 1000 ? "1–2 min" : "a few min";
      setSyncEstimateLabel(`~${formatCount(count)} emails · ${duration}`);
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [syncMenuOpen, syncScope, customFrom, customTo, lastCount, customRangeInvalid]);

  const startSync = useCallback(async () => {
    if (syncingRef.current || customRangeInvalid) {
      return;
    }
    const syncRunId = ++syncRunIdRef.current;
    const isActive = () => syncRunIdRef.current === syncRunId;
    syncingRef.current = true;
    setSyncing(true);
    setSyncError(null);
    setSyncFlowOpen(true);
    setSyncFlowStage("syncing");
    setSyncFlowEmailCount(0);
    setSyncFlowTotalEmailCount(syncStats?.total_raw_emails ?? 0);
    setProcessingStatus(null);
    try {
      const options = syncOptionsForScope(syncScope, customFrom, customTo, lastCount);
      let syncRequestSettled = false;
      let syncRequestError: unknown = null;
      const syncRequest = syncNowSyncPost(options).catch((error: unknown) => {
        syncRequestError = error;
        return null;
      });
      void syncRequest.then(() => {
        syncRequestSettled = true;
      });
      for (let attempt = 0; attempt < SYNC_POLL_MAX_ATTEMPTS; attempt += 1) {
        const next = await Promise.race([
          syncRequest.then(() => "settled" as const),
          new Promise<"poll">((resolve) => {
            setTimeout(() => resolve("poll"), SYNC_POLL_INTERVAL_MS);
          }),
        ]);
        if (next === "settled" || syncRequestSettled) {
          break;
        }
        const status = await syncStatusSyncStatusGet().catch(() => null);
        if (status?.status === 200 && status.data.state === "running") {
          setSyncFlowEmailCount(status.data.message_count ?? 0);
          const stats = await syncStatsSyncStatsGet().catch(() => null);
          if (stats?.status === 200) setSyncFlowTotalEmailCount(stats.data.total_raw_emails);
        }
      }
      const response = await syncRequest;
      if (!isActive()) return;
      if (response === null) {
        throw syncRequestError;
      }
      let state: EmailSyncStatus;
      if (response.status === 200) {
        state = response.data;
      } else if (response.status === 409) {
        const current = await syncStatusSyncStatusGet().catch(() => null);
        if (current?.status === 200 && current.data.state === "running") {
          state = current.data;
          setSyncFlowEmailCount(state.message_count ?? 0);
          const stats = await syncStatsSyncStatsGet().catch(() => null);
          if (stats?.status === 200) setSyncFlowTotalEmailCount(stats.data.total_raw_emails);
        } else {
          setSyncError(publicApiError({ response }, "Sync could not start. Try again."));
          setSyncFlowStage("failed");
          return;
        }
      } else {
        setSyncError(publicApiError({ response }, "Sync could not start. Try again."));
        setSyncFlowStage("failed");
        return;
      }
      if (state.state === "running") {
        for (let attempt = 0; attempt < SYNC_POLL_MAX_ATTEMPTS; attempt += 1) {
          const status = await syncStatusSyncStatusGet();
          state = status.data;
          setSyncFlowEmailCount(state.message_count ?? 0);
          const stats = await syncStatsSyncStatsGet().catch(() => null);
          if (stats?.status === 200) setSyncFlowTotalEmailCount(stats.data.total_raw_emails);
          if (state.state !== "running") {
            break;
          }
          if (attempt < SYNC_POLL_MAX_ATTEMPTS - 1) {
            await new Promise((resolve) => setTimeout(resolve, SYNC_POLL_INTERVAL_MS));
          }
        }
      }

      switch (state.state) {
        case "succeeded":
          setCompletedScope(completedSyncScope(syncScope, customFrom, customTo));
          setSyncMenuOpen(false);
          setSyncFlowEmailCount(state.message_count ?? 0);
          {
            const stats = await syncStatsSyncStatsGet().catch(() => null);
            if (stats?.status === 200) setSyncFlowTotalEmailCount(stats.data.total_raw_emails);
          }
          setSyncFlowStage("filtering");
          await new Promise((resolve) => setTimeout(resolve, 650));
          if (!isActive()) return;
          setSyncFlowStage("retaining");
          await new Promise((resolve) => setTimeout(resolve, 500));
          if (!isActive()) return;
          setSyncFlowStage("classifying");
          {
            const readiness = await providerReadinessConfigProvidersReadinessGet().catch(() => null);
            if (!readiness?.data.ready_to_classify) {
              setSyncError(
                readiness?.data.classification_generation.action
                  ?? readiness?.data.classification_generation.message
                  ?? "Azure OpenAI is not ready for classification. Check its settings and retry.",
              );
              setSyncFlowStage("failed");
              return;
            }
            let cumulativeStatus: ProcessingStatus | null = null;
            while (true) {
              let processingRequestError: unknown = null;
              const runPromise = processingRunProcessingRunPost({ max_candidates: 500 }).catch((error) => {
                processingRequestError = error;
                return null;
              });
              for (let attempt = 0; attempt < SYNC_POLL_MAX_ATTEMPTS; attempt += 1) {
                await new Promise((resolve) => setTimeout(resolve, 700));
                const status = await processingStatusProcessingStatusGet().catch(() => null);
                if (processingRequestError !== null) {
                  setSyncError(publicApiError(processingRequestError, "Classification failed. Check Azure OpenAI and retry."));
                  setSyncFlowStage("failed");
                  return;
                }
                if (status === null) continue;
                if (status.status === 200) {
                  setProcessingStatus(status.data);
                  if (status.data.state === "failed") {
                    setSyncError(status.data.last_error ?? "Classification failed. Try again.");
                    setSyncFlowStage("failed");
                    return;
                  }
                  if (status.data.state === "succeeded") break;
                }
              }
              const result = await runPromise;
              if (result === null) {
                setSyncError(publicApiError(processingRequestError, "Classification failed. Check Azure OpenAI and retry."));
                setSyncFlowStage("failed");
                return;
              }
              if (result.status !== 200) {
                setSyncError(publicApiError({ response: result }, "Classification failed. Check Azure OpenAI and retry."));
                setSyncFlowStage("failed");
                return;
              }
              const batch = result.data;
              cumulativeStatus = cumulativeStatus === null
                ? { ...batch, state: "succeeded" }
                : {
                    ...batch,
                    accepted_count: cumulativeStatus.accepted_count + batch.accepted_count,
                    applications_upserted: cumulativeStatus.applications_upserted + batch.applications_upserted,
                    candidate_count: cumulativeStatus.candidate_count,
                    candidate_limit: cumulativeStatus.candidate_limit + Math.min(batch.candidate_limit, batch.candidate_count),
                    completion_tokens: cumulativeStatus.completion_tokens + batch.completion_tokens,
                    estimated_cost_usd: cumulativeStatus.estimated_cost_usd + batch.estimated_cost_usd,
                    events_upserted: cumulativeStatus.events_upserted + batch.events_upserted,
                    ghost_retractions: cumulativeStatus.ghost_retractions + batch.ghost_retractions,
                    ghost_updates: cumulativeStatus.ghost_updates + batch.ghost_updates,
                    malformed_count: cumulativeStatus.malformed_count + batch.malformed_count,
                    manual_conflict_count: cumulativeStatus.manual_conflict_count + batch.manual_conflict_count,
                    processed_count: cumulativeStatus.processed_count + batch.processed_count,
                    prompt_tokens: cumulativeStatus.prompt_tokens + batch.prompt_tokens,
                    skipped_not_job_count: cumulativeStatus.skipped_not_job_count + batch.skipped_not_job_count,
                    started_at: cumulativeStatus.started_at,
                    state: "succeeded",
                    total_tokens: cumulativeStatus.total_tokens + batch.total_tokens,
                  };
              setProcessingStatus(cumulativeStatus);
              if (batch.pending_candidate_count === 0) {
                setSyncFlowStage("complete");
                break;
              }
              if (!batch.limit_reached || batch.pending_candidate_count >= batch.candidate_count) {
                setSyncError(`${formatCount(batch.pending_candidate_count)} candidate emails still need classification. Review the provider output, then retry processing.`);
                setSyncFlowStage("failed");
                return;
              }
            }
          }
          return;
        case "failed":
          setSyncError(state.last_error ?? "Sync failed. Try again.");
          setSyncFlowStage("failed");
          return;
        case "idle":
          setSyncError("Sync did not start. Try again.");
          return;
        case "running":
          setSyncError("Sync is still running. Check again in a moment.");
          return;
        default: {
          const unexpectedState: never = state.state;
          return unexpectedState;
        }
      }
    } catch (error) {
      if (!isActive()) return;
      setSyncError(publicApiError(error, "Sync could not start. Check the local backend."));
      setSyncFlowStage("failed");
    } finally {
      if (isActive()) {
        syncingRef.current = false;
        setSyncing(false);
        refresh();
      }
    }
  }, [syncScope, customFrom, customTo, lastCount, customRangeInvalid, refresh, syncStats]);

  const progressPercent = syncFlowStage === "syncing"
    ? 12
    : syncFlowStage === "filtering"
      ? 38
      : syncFlowStage === "retaining"
        ? 52
        : syncFlowStage === "classifying"
          ? 55 + Math.round(42 * ((processingStatus?.processed_count ?? 0) / Math.max(processingStatus?.candidate_limit ?? 500, 1)))
          : 100;

  const navItems = useMemo(
    () =>
      [
        { key: "overview" as const, label: "Overview", icon: "⌂" },
        { key: "applications" as const, label: "Applications", icon: "▤" },
        { key: "insights" as const, label: "Insights", icon: "◫" },
        { key: "settings" as const, label: "Settings", icon: "⚙" },
      ].map((item) => {
        const active =
          route.page === item.key || (route.page === "detail" && item.key === "applications");
        const style: CSSProperties = {
          display: "block",
          width: "100%",
          textAlign: "left",
          padding: navCollapsed ? "9px" : "9px 12px",
          border: "none",
          borderRadius: "9px",
          cursor: "pointer",
          fontSize: "13.5px",
          fontWeight: 600,
          background: active ? "#FFFFFF" : "transparent",
          color: active ? "#1B201C" : "#666D66",
          boxShadow: active ? "0 1px 2px rgba(20,25,20,0.06)" : "none",
        };
        return { ...item, style };
      }),
    [navCollapsed, route.page],
  );

  const gmailName = connections.find((connection) => connection.display_email)?.display_email?.display_name
    ?? connections.find((connection) => connection.display_email)?.display_email?.address.split("@")[0];

  const inboxLabel = connectionsLoadState === "loading"
    ? "Checking inbox connection"
    : connectionsLoadState === "error"
      ? "Inbox connection unavailable"
      : connections.some((connection) => connection.reauth_required)
        ? "Gmail needs reconnecting"
      : connections.length === 0
      ? "No inbox connected"
      : connections.length === 1
        ? "Gmail connected"
        : `${connections.length} inboxes connected`;
  const syncedRelative = syncStats ? formatRelativeTime(syncStats.last_run_at) ?? "not synced yet" : null;
  const syncedCount = syncStats ? formatCount(syncStats.total_raw_emails) : null;
  const inboxNote = connectionsLoadState === "loading"
    ? "Loading connection details"
    : connectionsLoadState === "error"
      ? connectionsError
      : syncStatsLoadState === "loading"
        ? "Loading sync statistics"
    : syncStatsLoadState === "error"
          ? syncStatsError
          : connections.some((connection) => connection.reauth_required)
            ? "Reconnect Gmail in Settings to resume sync"
          : connections.length === 0
            ? "Connect Gmail in Settings"
            : `Synced ${syncedRelative} · ${syncedCount} emails read`;

  return (
    <div
      className="rd-root"
      style={{
        display: "flex",
        height: "100vh",
        overflow: "hidden",
        background: "#F4F3EF",
        fontSize: "14px",
        lineHeight: 1.5,
      }}
    >
      <nav
        aria-label="Primary"
        style={{
          width: navCollapsed ? "68px" : "224px",
          flex: "none",
          display: "flex",
          flexDirection: "column",
          gap: "4px",
          padding: "20px 12px 16px",
          transition: "width 180ms ease",
          borderRight: "1px solid #E4E2DA",
          background: "#EFEEE8",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "0 10px 18px" }}>
          <div
            style={{
              width: "28px",
              height: "28px",
              borderRadius: "8px",
              background: "#1E5136",
              color: "#F6F4EC",
              display: "grid",
              placeItems: "center",
              fontWeight: 700,
              fontSize: "14px",
            }}
          >
            J
          </div>
          {!navCollapsed ? <div>
            <div style={{ fontWeight: 700, fontSize: "14.5px", letterSpacing: "-0.01em" }}>
              JobTracker
            </div>
            <div style={{ fontSize: "10.5px", color: "#8B9189" }}>Your inbox, decoded</div>
          </div> : null}
          <button aria-label={navCollapsed ? "Expand navigation" : "Collapse navigation"} onClick={() => setNavCollapsed((value) => !value)} style={{ marginLeft: "auto", border: "none", background: "transparent", cursor: "pointer", color: "#666D66" }} type="button">{navCollapsed ? "›" : "‹"}</button>
        </div>

        {navItems.map((item) => (
          <button key={item.key} onClick={() => go(item.key)} style={item.style} type="button">
            <span aria-hidden="true" style={{ display: "inline-block", width: navCollapsed ? "100%" : "22px", textAlign: "center" }}>{item.icon}</span>{navCollapsed ? <span className="rd-sr-only">{item.label}</span> : item.label}
          </button>
        ))}

        <div style={{ flex: 1 }} />

        {!navCollapsed ? <div
          style={{
            padding: "10px 12px",
            borderRadius: "10px",
            background: "#E7EFE8",
            border: "1px solid #D4E2D6",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              fontWeight: 600,
              color: "#1E5136",
            }}
          >
            <span
              style={{ width: "7px", height: "7px", borderRadius: "50%", background: "#2E7D4F" }}
            />
            {inboxLabel}
          </div>
          <div style={{ fontSize: "11px", color: connectionsLoadState === "error" || syncStatsLoadState === "error" ? "#96403C" : "#66886F", marginTop: "2px" }}>{inboxNote}</div>
          {connectionsLoadState === "error" && syncStatsLoadState === "error" ? (
            <div style={{ color: "#96403C", fontSize: "11px", marginTop: "2px" }}>{syncStatsError}</div>
          ) : null}
          {connectionsLoadState === "error" ? (
            <button aria-label="Retry inbox connections" onClick={() => void loadConnections()} style={{ border: "none", background: "none", color: "#1E5136", cursor: "pointer", fontSize: "11px", fontWeight: 700, padding: "4px 0 0" }} type="button">Retry</button>
          ) : null}
          {syncStatsLoadState === "error" ? (
            <button aria-label="Retry sync statistics" onClick={() => void loadSyncStats()} style={{ border: "none", background: "none", color: "#1E5136", cursor: "pointer", fontSize: "11px", fontWeight: 700, padding: "4px 0 0" }} type="button">Retry</button>
          ) : null}
        </div> : null}

        {!navCollapsed ? <button
          onClick={() => go("dev")}
          style={{
            marginTop: "8px",
            padding: "6px 12px",
            border: "none",
            background: "none",
            color: "#9A9F96",
            fontSize: "11px",
            cursor: "pointer",
            textAlign: "left",
          }}
          type="button"
        >
          For developers →
        </button> : null}
      </nav>

      <main style={{ flex: 1, minWidth: 0, overflowY: "auto", position: "relative" }}>
        <div
          style={{
            position: "sticky",
            top: 0,
            zIndex: 5,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            padding: "14px 32px",
            background: "rgba(244,243,239,0.92)",
            backdropFilter: "blur(8px)",
            borderBottom: "1px solid #E9E7DF",
          }}
        >
          <div style={{ fontWeight: 700, fontSize: "16px", letterSpacing: "-0.01em" }}>
            {PAGE_TITLES[route.page]}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <button
              aria-current={route.page === "chat" ? "page" : undefined}
              className="rd-ask-ai-button"
              onClick={() => go("chat")}
              type="button"
            >
              <span aria-hidden="true">✦</span> Ask AI
            </button>
            <div style={{ position: "relative" }}>
              <button
                disabled={syncing}
                onClick={() => setSyncMenuOpen((value) => !value)}
                style={{
                  padding: "8px 14px",
                  border: "1px solid #E4E2DA",
                  borderRadius: "999px",
                  background: "#fff",
                  color: "#1B201C",
                  fontSize: "12.5px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
                type="button"
              >
                {syncing ? "Processing..." : "Sync"}{" "}
                <span style={{ fontSize: "10px", color: "#9A9F96" }}>▾</span>
              </button>
              {syncing ? (
                <button
                  onClick={() => setSyncFlowOpen(true)}
                  style={{ marginLeft: "8px", padding: "8px 12px", border: "1px solid #1E5136", borderRadius: "999px", background: "#F3F8F4", color: "#1E5136", cursor: "pointer", fontSize: "12px", fontWeight: 700 }}
                  type="button"
                >
                  View progress
                </button>
              ) : null}
              {syncMenuOpen ? (
                <div
                  style={{
                    position: "absolute",
                    right: 0,
                    top: "44px",
                    zIndex: 20,
                    width: "320px",
                    padding: "16px",
                    border: "1px solid #E4E2DA",
                    borderRadius: "14px",
                    background: "#fff",
                    boxShadow: "0 12px 40px rgba(20,25,20,0.14)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "10px",
                    textAlign: "left",
                  }}
                >
                  <div style={{ fontWeight: 700, fontSize: "13.5px" }}>What should I check?</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                    {SYNC_SCOPES.map((scope) => (
                      <button
                        disabled={syncing}
                        key={scope.key}
                        onClick={() => setSyncScope(scope.key)}
                        style={{
                          display: "block",
                          width: "100%",
                          textAlign: "left",
                          padding: "8px 10px",
                          borderRadius: "9px",
                          cursor: "pointer",
                          border:
                            syncScope === scope.key ? "1.5px solid #1E5136" : "1px solid #F0EEE7",
                          background: syncScope === scope.key ? "#F3F8F4" : "#fff",
                        }}
                        type="button"
                      >
                        <span style={{ display: "block", fontWeight: 600, fontSize: "12.5px" }}>
                          {scope.label}
                        </span>
                        <span style={{ display: "block", fontSize: "11.5px", color: "#9A9F96" }}>
                          {scope.note}
                        </span>
                      </button>
                    ))}
                  </div>
                  {syncScope === "custom" ? (
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                        fontSize: "12px",
                        color: "#4A5049",
                      }}
                    >
                      <input
                        aria-label="Sync from date"
                        disabled={syncing}
                        onChange={(event) => setCustomFrom(event.target.value)}
                        style={{
                          flex: 1,
                          padding: "7px 9px",
                          border: "1px solid #E4E2DA",
                          borderRadius: "8px",
                          background: "#FAFAF7",
                          fontSize: "12px",
                        }}
                        type="date"
                        value={customFrom}
                      />
                      <span style={{ color: "#9A9F96" }}>to</span>
                      <input
                        aria-label="Sync to date"
                        disabled={syncing}
                        onChange={(event) => setCustomTo(event.target.value)}
                        style={{
                          flex: 1,
                          padding: "7px 9px",
                          border: "1px solid #E4E2DA",
                          borderRadius: "8px",
                          background: "#FAFAF7",
                          fontSize: "12px",
                        }}
                        type="date"
                        value={customTo}
                      />
                    </div>
                  ) : null}
                  {syncScope === "count" ? (
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                        fontSize: "12px",
                        color: "#4A5049",
                      }}
                    >
                      <span>Most recent</span>
                      <input
                        aria-label="Most recent email count"
                        disabled={syncing}
                        min={50}
                        onChange={(event) =>
                          setLastCount(Math.max(1, Number(event.target.value) || 0))
                        }
                        step={50}
                        style={{
                          width: "90px",
                          padding: "7px 9px",
                          border: "1px solid #E4E2DA",
                          borderRadius: "8px",
                          background: "#FAFAF7",
                          fontSize: "12.5px",
                          fontVariantNumeric: "tabular-nums",
                        }}
                        type="number"
                        value={lastCount}
                      />
                      <span>emails</span>
                    </div>
                  ) : null}
                  {syncError ? (
                    <div
                      role="alert"
                      style={{ fontSize: "12px", color: "#96403C" }}
                    >
                      {syncError}
                    </div>
                  ) : null}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "10px",
                      borderTop: "1px solid #F0EEE7",
                      paddingTop: "12px",
                    }}
                  >
                    <span style={{ fontSize: "11.5px", color: "#9A9F96" }}>
                      {customRangeInvalid ? "Choose a valid date range" : syncEstimateLabel}
                    </span>
                    <button
                      disabled={
                        syncing ||
                        customRangeInvalid
                      }
                      onClick={() => void startSync()}
                      style={{
                        padding: "8px 16px",
                        border: "none",
                        borderRadius: "999px",
                        background: "#1E5136",
                        color: "#F6F4EC",
                        fontSize: "12.5px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                      type="button"
                    >
                      Sync
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>

        {route.page === "overview" || route.page === "chat" ? (
          <OverviewPage
            processingActive={syncing}
            userName={gmailName}
            go={go}
            openApp={openApp}
            onProcessed={refresh}
            reloadKey={reloadKey}
            sentAfter={completedScope.sentAfter}
            sentBefore={completedScope.sentBefore}
          />
        ) : null}
        {route.page === "applications" ? (
          <ApplicationsPage
            processingActive={syncing}
            openApp={openApp}
            onProcessed={refresh}
            reloadKey={reloadKey}
            setStatusFilter={(statusFilter) =>
              navigate({ page: "applications", detailId: null, statusFilter })
            }
            statusFilter={route.statusFilter}
          />
        ) : null}
        {route.page === "detail" && route.detailId ? (
          <DetailPage applicationId={route.detailId} go={go} onChanged={refresh} />
        ) : null}
        {route.page === "detail" && !route.detailId ? (
          <section
            style={{
              maxWidth: "860px",
              margin: "0 auto",
              padding: "24px 32px 60px",
              display: "flex",
              flexDirection: "column",
              gap: "18px",
            }}
          >
            <button
              onClick={() => go("applications")}
              style={{
                alignSelf: "flex-start",
                border: "none",
                background: "none",
                color: "#666D66",
                fontSize: "12.5px",
                fontWeight: 600,
                cursor: "pointer",
                padding: 0,
              }}
              type="button"
            >
              ← All applications
            </button>
            <div
              style={{
                padding: "22px 24px",
                border: "1px solid #E4E2DA",
                borderRadius: "16px",
                background: "#fff",
              }}
            >
              <h1 style={{ margin: 0, fontSize: "20px", fontWeight: 700 }}>
                Application unavailable
              </h1>
              <p style={{ margin: "6px 0 0", color: "#666D66", fontSize: "13.5px" }}>
                The application link is malformed or unsupported. Open an application from the
                Applications page.
              </p>
            </div>
          </section>
        ) : null}
        {route.page === "insights" ? <InsightsPage openApp={openApp} reloadKey={reloadKey} /> : null}
        {route.page === "chatArchitecture" ? <ChatArchitecturePage /> : null}
        {route.page === "settings" ? (
          <SettingsPage
            connections={connections}
            connectionsError={connectionsError}
            connectionsLoadState={connectionsLoadState}
            onChanged={refresh}
            onRetryConnections={loadConnections}
            syncStats={syncStats}
          />
        ) : null}
        {route.page === "dev" ? <DeveloperPage /> : null}
      </main>
      {route.page === "chat" ? (
        <ChatDrawer
          onClose={() => go("overview")}
          onOpenApplication={openApp}
          onOpenSettings={() => go("settings")}
        />
      ) : null}
      {syncFlowOpen ? (
        <div
          aria-modal="true"
          role="dialog"
          aria-labelledby="sync-progress-title"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 100,
            display: "grid",
            placeItems: "center",
            padding: "24px",
            background: "rgba(20, 25, 20, 0.34)",
          }}
        >
          <section style={{ width: "min(510px, 100%)", padding: "26px", borderRadius: "18px", background: "#fff", boxShadow: "0 24px 70px rgba(20,25,20,0.25)" }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "20px" }}>
              <div>
                <div style={{ color: "#1E5136", fontSize: "11px", fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>Inbox processing</div>
                <h2 id="sync-progress-title" style={{ margin: "4px 0 0", fontSize: "22px", letterSpacing: "-0.03em" }}>
                  {syncFlowStage === "complete" ? "Your inbox is up to date" : syncFlowStage === "failed" ? "Processing needs attention" : "Building your application history"}
                </h2>
              </div>
              <button onClick={() => setSyncFlowOpen(false)} style={{ border: "1px solid #E4E2DA", borderRadius: "999px", background: "#fff", padding: "6px 11px", cursor: "pointer", fontWeight: 700 }} type="button">
                {syncFlowStage === "complete" || syncFlowStage === "failed" ? "Close" : "Continue in background"}
              </button>
            </div>
            <div style={{ height: "8px", margin: "22px 0 20px", overflow: "hidden", borderRadius: "999px", background: "#EEEDE7" }}>
              <div style={{ width: `${progressPercent}%`, height: "100%", borderRadius: "inherit", background: "linear-gradient(90deg, #1E5136, #5E9A71)", transition: "width 500ms ease" }} />
            </div>
            <ol style={{ display: "grid", gap: "14px", margin: 0, padding: 0, listStyle: "none" }}>
              <SyncFlowStep active={syncFlowStage === "syncing"} complete={!["syncing", "failed"].includes(syncFlowStage)} title="Syncing emails" detail={`${formatCount(syncFlowEmailCount)} new for this run · ${formatCount(syncFlowTotalEmailCount)} total emails synced`} />
              <SyncFlowStep active={syncFlowStage === "filtering"} complete={["retaining", "classifying", "complete"].includes(syncFlowStage)} title="Applying job-search filters" detail="Filtering runs locally against sender, subject, and message metadata." />
              <SyncFlowStep active={syncFlowStage === "retaining"} complete={["classifying", "complete"].includes(syncFlowStage)} title="Candidate bodies retained" detail="Only broad job-search candidates keep body text for classification and reconciliation." />
              <SyncFlowStep active={syncFlowStage === "classifying"} complete={syncFlowStage === "complete"} title="Classifying with Azure OpenAI" detail={processingStatus ? `${formatCount(processingStatus.processed_count)} candidate emails processed · ${formatCount(processingStatus.pending_candidate_count)} remaining.` : "Preparing the first bounded classification run."} />
            </ol>
            {syncFlowStage === "complete" && processingStatus ? <p role="status" style={{ margin: "20px 0 0", color: "#1E5136", fontSize: "13px", fontWeight: 600 }}>Saved {formatCount(processingStatus.accepted_count)} classifications and updated {formatCount(processingStatus.applications_upserted)} applications.</p> : null}
            {syncFlowStage === "syncing" || syncFlowStage === "classifying" ? <p role="status" style={{ margin: "18px 0 0", color: "#666D66", fontSize: "11.5px" }}>Live backend updates are polling every second.</p> : null}
            {syncFlowStage === "failed" ? <p role="status" style={{ margin: "20px 0 0", color: "#96403C", fontSize: "13px" }}>{syncError ?? "The current step did not finish. No uncommitted classification results were shown as complete."}</p> : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}

function SyncFlowStep({ active, complete, title, detail }: { active: boolean; complete: boolean; title: string; detail: string }) {
  return <li style={{ display: "grid", gridTemplateColumns: "24px 1fr", gap: "10px", alignItems: "start", opacity: active || complete ? 1 : 0.52 }}>
    <span aria-hidden="true" style={{ width: "22px", height: "22px", display: "grid", placeItems: "center", borderRadius: "50%", background: complete ? "#1E5136" : active ? "#E6F0E8" : "#F0EFEA", color: complete ? "#fff" : "#1E5136", fontSize: "12px", fontWeight: 800 }}>{complete ? "✓" : active ? "…" : ""}</span>
    <span><strong style={{ display: "block", fontSize: "13.5px" }}>{title}</strong><span style={{ display: "block", marginTop: "2px", color: "#666D66", fontSize: "12px" }}>{detail}</span></span>
  </li>;
}
