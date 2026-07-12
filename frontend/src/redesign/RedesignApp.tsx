import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import {
  listEmailConnectionsAuthConnectionsGet,
  syncEstimateSyncEstimateGet,
  syncNowSyncPost,
  syncStatusSyncStatusGet,
  type EmailConnection,
  type EmailSyncOptions,
  type SyncLocalStats,
  syncStatsSyncStatsGet,
} from "../api";
import { safeDecodeApplicationRouteSegment } from "../lib/applicationRoutes";
import { enumQueryParam, parseRouteQuery, updateRouteQuery } from "../lib/routeQuery";
import { publicApiError } from "./apiError";
import { formatCount, formatRelativeTime } from "./theme";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { ChatDrawer } from "./ChatDrawer";
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
  | "settings"
  | "dev";

export interface RedesignRoute {
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
  settings: "Settings",
  dev: "For developers",
};

type SyncScopeKey = "new" | "7" | "30" | "custom" | "count";

const SYNC_SCOPES: { key: SyncScopeKey; label: string; note: string }[] = [
  { key: "new", label: "New mail since last sync", note: "Recommended — fastest" },
  { key: "7", label: "Last 7 days", note: "Re-checks the past week" },
  { key: "30", label: "Last 30 days", note: "Catches late replies" },
  { key: "custom", label: "A specific date range", note: "Pick start and end dates" },
  { key: "count", label: "Only the most recent emails", note: "Cap by number of emails" },
];

const SYNC_POLL_MAX_ATTEMPTS = 600;
const SYNC_POLL_INTERVAL_MS = 1000;

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
      before_date: customTo || null,
      since_date: customFrom || null,
    };
  }
  if (scope === "count") {
    return { max_messages: lastCount };
  }
  return null;
}

export function RedesignApp({ initialRoute }: { initialRoute: RedesignRoute }) {
  const [route, setRoute] = useState<RedesignRoute>(() => {
    const parsed = redesignRouteFromPath(window.location.pathname);
    return parsed
      ? redesignRouteFromLocation(window.location.pathname, window.location.search)
      : initialRoute;
  });
  const [chatOpen, setChatOpen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [connections, setConnections] = useState<EmailConnection[]>([]);
  const [syncStats, setSyncStats] = useState<SyncLocalStats | null>(null);

  const [syncMenuOpen, setSyncMenuOpen] = useState(false);
  const [syncScope, setSyncScope] = useState<SyncScopeKey>("new");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [lastCount, setLastCount] = useState(500);
  const [syncEstimateLabel, setSyncEstimateLabel] = useState("");
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const syncingRef = useRef(false);
  const customRangeInvalid =
    syncScope === "custom" && (!customFrom || !customTo || customFrom >= customTo);

  const refresh = useCallback(() => {
    setReloadKey((value) => value + 1);
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

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const [connectionsResponse, statsResponse] = await Promise.all([
        listEmailConnectionsAuthConnectionsGet().catch(() => null),
        syncStatsSyncStatsGet().catch(() => null),
      ]);
      if (cancelled) {
        return;
      }
      if (connectionsResponse?.status === 200) {
        setConnections(connectionsResponse.data);
      }
      if (statsResponse?.status === 200) {
        setSyncStats(statsResponse.data);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

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
    syncingRef.current = true;
    setSyncing(true);
    setSyncError(null);
    try {
      const options = syncOptionsForScope(syncScope, customFrom, customTo, lastCount);
      const response = await syncNowSyncPost(options);
      if (response.status !== 200) {
        setSyncError(publicApiError({ response }, "Sync could not start. Try again."));
        return;
      }

      let state = response.data;
      if (state.state === "running") {
        for (let attempt = 0; attempt < SYNC_POLL_MAX_ATTEMPTS; attempt += 1) {
          const status = await syncStatusSyncStatusGet();
          state = status.data;
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
          setSyncMenuOpen(false);
          return;
        case "failed":
          setSyncError(state.last_error ?? "Sync failed. Try again.");
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
      setSyncError(publicApiError(error, "Sync could not start. Check the local backend."));
    } finally {
      syncingRef.current = false;
      setSyncing(false);
      refresh();
    }
  }, [syncScope, customFrom, customTo, lastCount, customRangeInvalid, refresh]);

  const toggleChat = useCallback(() => {
    setChatOpen((value) => !value);
  }, []);

  const navItems = useMemo(
    () =>
      [
        { key: "overview" as const, label: "Overview" },
        { key: "applications" as const, label: "Applications" },
        { key: "insights" as const, label: "Insights" },
        { key: "settings" as const, label: "Settings" },
      ].map((item) => {
        const active =
          route.page === item.key || (route.page === "detail" && item.key === "applications");
        const style: CSSProperties = {
          display: "block",
          width: "100%",
          textAlign: "left",
          padding: "9px 12px",
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
    [route.page],
  );

  const inboxLabel =
    connections.length === 0
      ? "No inbox connected"
      : connections.length === 1
        ? "Gmail connected"
        : `${connections.length} inboxes connected`;
  const syncedRelative = formatRelativeTime(syncStats?.last_run_at) ?? "not synced yet";
  const syncedCount = formatCount(syncStats?.total_raw_emails ?? 0);
  const inboxNote =
    connections.length === 0
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
          width: "224px",
          flex: "none",
          display: "flex",
          flexDirection: "column",
          gap: "4px",
          padding: "20px 12px 16px",
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
          <div>
            <div style={{ fontWeight: 700, fontSize: "14.5px", letterSpacing: "-0.01em" }}>
              JobTracker
            </div>
            <div style={{ fontSize: "10.5px", color: "#8B9189" }}>Your inbox, decoded</div>
          </div>
        </div>

        {navItems.map((item) => (
          <button key={item.key} onClick={() => go(item.key)} style={item.style} type="button">
            {item.label}
          </button>
        ))}

        <div style={{ flex: 1 }} />

        <button
          onClick={toggleChat}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            margin: "0 0 10px",
            padding: "10px 12px",
            border: "1px solid #D9D2EE",
            borderRadius: "10px",
            background: "#F4F2FB",
            color: "#4B3FA6",
            fontWeight: 600,
            fontSize: "13px",
            cursor: "pointer",
            textAlign: "left",
          }}
          type="button"
        >
          <span
            style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#6C5FC7" }}
          />
          Ask your job search
        </button>

        <div
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
          <div style={{ fontSize: "11px", color: "#66886F", marginTop: "2px" }}>{inboxNote}</div>
        </div>

        <button
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
        </button>
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
                {syncing ? "Checking inboxes…" : "Sync"}{" "}
                <span style={{ fontSize: "10px", color: "#9A9F96" }}>▾</span>
              </button>
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
            <button
              className="rd-hover-dark-green"
              onClick={toggleChat}
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
              Ask AI
            </button>
          </div>
        </div>

        {route.page === "overview" ? (
          <OverviewPage go={go} openApp={openApp} reloadKey={reloadKey} />
        ) : null}
        {route.page === "applications" ? (
          <ApplicationsPage
            openApp={openApp}
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
        {route.page === "settings" ? (
          <SettingsPage connections={connections} onChanged={refresh} syncStats={syncStats} />
        ) : null}
        {route.page === "dev" ? <DeveloperPage /> : null}
      </main>

      {chatOpen ? <ChatDrawer onClose={toggleChat} /> : null}
    </div>
  );
}
