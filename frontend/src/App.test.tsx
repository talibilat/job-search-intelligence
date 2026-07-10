import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type {
  MetricsBreakdownResponse,
  MetricsDiagnosticsResponse,
  MetricsFunnelResponse,
  MetricsRatesResponse,
  MetricsResponseRateTrendResponse,
  MetricsSummaryResponse,
  MetricsTimeseriesResponse,
} from "./api";
import styles from "./index.css?raw";

function renderAtPath(pathname: string) {
  window.history.pushState({}, "", pathname);
  return render(<App />);
}

type MockObjectResponseBody = Record<string, unknown>;
type MockResponseBody = MockObjectResponseBody | unknown[];

type MockResponse =
  | MockObjectResponseBody
  | {
      body: MockResponseBody;
      status: number;
    };

type MockResponseConfig = MockResponse | MockResponse[];

function metricsSummaryResponse(
  overrides: Partial<MetricsSummaryResponse> = {},
): MockObjectResponseBody {
  const response: MetricsSummaryResponse = {
    application_windows: [],
    average_time_to_first_response: {
      application_count: 0,
      average_hours: null,
    },
    average_time_to_rejection: {
      application_count: 0,
      average_hours: null,
    },
    distinct_company_count: 0,
    evaluated_at: "2026-07-07T20:00:00Z",
    ghost_threshold_days: 30,
    ghosted_applications: 0,
    interview_invitation_count: 0,
    offers_received: 0,
    personal_ghost_threshold: {
      threshold_days: 30,
      threshold_source: "configured_fallback",
      response_sample_size: 0,
      silent_application_count: 0,
      silence_age_distribution: [
        { application_count: 0, bucket: "0_7", max_days: 7, min_days: 0 },
        { application_count: 0, bucket: "8_14", max_days: 14, min_days: 8 },
        { application_count: 0, bucket: "15_30", max_days: 30, min_days: 15 },
        { application_count: 0, bucket: "31_60", max_days: 60, min_days: 31 },
        { application_count: 0, bucket: "61_plus", max_days: null, min_days: 61 },
      ],
    },
    rejected_applications: 0,
    total_applications: 0,
    ...overrides,
  };
  return response as unknown as MockObjectResponseBody;
}

function pipelineStatusResponse(
  overrides: Record<string, unknown> = {},
): MockObjectResponseBody {
  return {
    account_display: "me@example.com",
    backfill_complete: false,
    backfill_messages_processed: 13,
    backfill_pages_processed: 3,
    backfill_state: "running",
    counts: {
      application_count: 0,
      application_event_count: 0,
      classified_email_count: 0,
      filter_candidate_count: 5,
      filter_decision_count: 10,
      filter_rejected_count: 5,
      job_related_email_count: 0,
      metadata_only_count: 8,
      raw_email_count: 10,
      retained_body_count: 2,
    },
    generated_at: "2026-07-07T12:00:00Z",
    gmail_connected: true,
    incremental_sync_ready: false,
    last_error: null,
    last_sync_finished_at: null,
    last_sync_started_at: null,
    next_action: "continue_backfill",
    next_action_reason: "The one-time historical backfill has not finished.",
    reauth_required: false,
    sync_mode: null,
    sync_running: false,
    unclassified_retained_count: 0,
    ...overrides,
  };
}

function idleSyncStatusResponse(): MockObjectResponseBody {
  return {
    account_id: null,
    finished_at: null,
    last_error: null,
    message_count: 0,
    mode: null,
    page_count: 0,
    progress: 0,
    provider: null,
    raw_email_count: 0,
    recovered_from_expired_cursor: false,
    retained_body_failure_count: 0,
    started_at: null,
    state: "idle",
    target_message_count: null,
  };
}

function metricsRatesResponse(
  overrides: Partial<MetricsRatesResponse> = {},
): MockObjectResponseBody {
  const response: MetricsRatesResponse = {
    overall_response_rate: {
      denominator: 0,
      numerator: 0,
      rate: null,
    },
    rejection_rate: {
      denominator: 0,
      numerator: 0,
      rate: null,
    },
    ghost_rate: {
      denominator: 0,
      numerator: 0,
      rate: null,
    },
    application_to_interview_rate: {
      denominator: 0,
      numerator: 0,
      rate: null,
    },
    interview_to_offer_rate: {
      denominator: 0,
      numerator: 0,
      rate: null,
    },
    ...overrides,
  };
  return response as unknown as MockObjectResponseBody;
}

function metricsBreakdownResponse(
  overrides: Partial<MetricsBreakdownResponse> = {},
): MockObjectResponseBody {
  const response: MetricsBreakdownResponse = {
    dimension: "source",
    rows: [],
    ...overrides,
  };
  return response as unknown as MockObjectResponseBody;
}

function metricsTimeseriesResponse(
  overrides: Partial<MetricsTimeseriesResponse> = {},
): MockObjectResponseBody {
  const response: MetricsTimeseriesResponse = {
    points: [],
    ...overrides,
  };
  return response as unknown as MockObjectResponseBody;
}

function metricsResponseRateTrendResponse(
  overrides: Partial<MetricsResponseRateTrendResponse> = {},
): MockObjectResponseBody {
  const response: MetricsResponseRateTrendResponse = {
    points: [],
    ...overrides,
  };
  return response as unknown as MockObjectResponseBody;
}

function metricsFunnelResponse(
  overrides: Partial<MetricsFunnelResponse> = {},
): MockObjectResponseBody {
  const response: MetricsFunnelResponse = {
    stages: [],
    ...overrides,
  };
  return response as unknown as MockObjectResponseBody;
}

function metricsDiagnosticsResponse(
  overrides: Partial<MetricsDiagnosticsResponse> = {},
): MockObjectResponseBody {
  const response: MetricsDiagnosticsResponse = {
    adjacent_role_suggestions: [],
    best_roi_source: null,
    sponsorship_response_impact: null,
    dead_weight_skill_segments: [],
    baseline_response_count: 0,
    baseline_response_rate: null,
    baseline_success_count: 0,
    baseline_success_rate: null,
    baseline_negative_count: 0,
    baseline_negative_rate: null,
    negative_outcome_segments: [],
    segments: [],
    selling_skill_segments: [],
    strongest_response_correlate: null,
    strongest_response_segments: [],
    successful_application_segments: [],
    total_applications: 0,
    wasted_effort_segments: [],
    weakest_response_segments: [],
    ...overrides,
  };
  return response as unknown as MockObjectResponseBody;
}

function isMockResponseConfig(
  value: MockResponse,
): value is { body: MockResponseBody; status: number } {
  return "body" in value && "status" in value;
}

function mockFetchResponses(responses: Record<string, MockResponseConfig>) {
  const responseQueues = new Map<string, MockResponse[]>();

  for (const [path, response] of Object.entries(responses)) {
    responseQueues.set(
      path,
      Array.isArray(response) ? [...response] : [response],
    );
  }

  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    const path = url.startsWith("http") ? new URL(url).pathname : url;
    const config = responseQueues.get(path);

    if (!config) {
      if (path === "/metrics/funnel") {
        return Promise.resolve(
          new Response(JSON.stringify(metricsFunnelResponse()), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path === "/metrics/breakdown?dimension=source") {
        return Promise.resolve(
          new Response(JSON.stringify(metricsBreakdownResponse()), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path === "/metrics/breakdown?dimension=role") {
        return Promise.resolve(
          new Response(JSON.stringify(metricsBreakdownResponse({ dimension: "role" })), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path === "/metrics/breakdown?dimension=company_type") {
        return Promise.resolve(
          new Response(JSON.stringify(metricsBreakdownResponse({ dimension: "company_type" })), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path === "/metrics/timeseries") {
        return Promise.resolve(
          new Response(JSON.stringify(metricsTimeseriesResponse()), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path === "/metrics/response-rate-trend") {
        return Promise.resolve(
          new Response(JSON.stringify(metricsResponseRateTrendResponse()), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path === "/metrics/diagnostics") {
        return Promise.resolve(
          new Response(JSON.stringify(metricsDiagnosticsResponse()), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      throw new Error(`Unhandled fetch request: ${path}`);
    }

    const nextConfig = config.length > 1 ? config.shift() : config[0];

    if (!nextConfig) {
      throw new Error(`No mock fetch responses left for: ${path}`);
    }

    const body = isMockResponseConfig(nextConfig)
      ? nextConfig.body
      : nextConfig;
    const status = isMockResponseConfig(nextConfig) ? nextConfig.status : 200;

    return Promise.resolve(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status,
      }),
    );
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

describe("App", () => {
  it("renders recurring feedback on the insights route", async () => {
    window.history.pushState({}, "", "/insights");
    mockFetchResponses({
      "/insights": {
        insights: [
          {
            id: 1,
            type: "recurring_feedback",
            content:
              "Feedback consistently says to improve system design examples. [application:app-1|event:event-1|email:email-1]",
            inputs_hash: "inputs-hash",
            is_stale: false,
            model: "llama3.1",
            generated_at: "2026-07-07T12:00:00+00:00",
          },
        ],
      },
    });

    render(<App />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Insights" }),
    ).toBeTruthy();
    expect(
      await screen.findByText("Recurring recruiter feedback"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Feedback consistently says to improve system design examples.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("application:app-1|event:event-1|email:email-1"),
    ).toBeTruthy();
  });

  it("renders a clean landing page that explains the local inbox-to-dashboard flow", () => {
    renderAtPath("/");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Your job search, from inbox to insight.",
      }),
    ).toBeTruthy();
    expect(screen.getByText("Connects to Gmail locally")).toBeTruthy();
    expect(screen.getByText("Syncs safe metadata first")).toBeTruthy();
    expect(screen.getByText("Filters and classifies job email")).toBeTruthy();
    expect(screen.getByText("Reconstructs applications and timelines")).toBeTruthy();
    expect(screen.getByText("Charts deterministic metrics")).toBeTruthy();
    expect(screen.getByText("Generates grounded insights only when supported"))
      .toBeTruthy();
    expect(screen.getByRole("link", { name: "Run features" })).toHaveProperty(
      "href",
      `${window.location.origin}/features`,
    );
    expect(screen.queryByRole("button", { name: "Sync now" })).toBeNull();
    expect(screen.queryByText("Raw emails")).toBeNull();
  });

  it("renders the runnable sync pipeline section on the feature status page", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse({
        next_action: "run_classification",
        next_action_reason:
          "2 job-search candidate emails are waiting for classification.",
        unclassified_retained_count: 2,
      }),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    expect(
      screen.getByRole("region", { name: "Runnable sync pipeline" }),
    ).toBeTruthy();

    expect(
      await screen.findByText("Candidates are waiting for classification"),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Run classification" }),
    ).toBeTruthy();
    expect(screen.getByText("Raw emails")).toBeTruthy();
    expect(screen.getByText("Filter decisions")).toBeTruthy();
    expect(screen.getByText("Retained bodies")).toBeTruthy();
    expect(screen.getByText("Applications")).toBeTruthy();
    expect(
      screen.getByText("Gmail connected:", { exact: false }),
    ).toBeTruthy();
    expect(
      await screen.findByText(
        "No synced email metadata is stored yet. Run a sync to fill this list.",
      ),
    ).toBeTruthy();
  });

  it("renders the Q-03 distinct company count on the dashboard", async () => {
    mockFetchResponses({
      "/metrics/summary": metricsSummaryResponse({
        total_applications: 12,
        distinct_company_count: 3,
      }),
      "/metrics/rates": metricsRatesResponse(),
      "/applications": { body: [], status: 200 },
      "/applications?status=applied": { body: [], status: 200 },
      "/applications?status=in_review": { body: [], status: 200 },
      "/applications?status=assessment": { body: [], status: 200 },
      "/applications?status=interview": { body: [], status: 200 },
    });

    renderAtPath("/dashboard");

    expect(await screen.findByText("3")).toBeTruthy();
    expect(screen.getByText("Distinct companies")).toBeTruthy();
    expect(
      screen.getByText("Q-03 counted from normalized applications"),
    ).toBeTruthy();
  });

  it("shows the deterministic response rate on the dashboard", async () => {
    mockFetchResponses({
      "/metrics/summary": {
        distinct_company_count: 3,
      },
      "/metrics/rates": metricsRatesResponse({
        overall_response_rate: {
          numerator: 3,
          denominator: 5,
          rate: 0.6,
        },
      }),
    });

    renderAtPath("/dashboard");

    const responseRateCard = screen.getByLabelText("Response rate metric");

    expect(await within(responseRateCard).findByText("60%"));
    expect(
      within(responseRateCard).getByText(
        "3 of 5 applications have response evidence",
      ),
    ).toBeTruthy();
  });

  it("shows sync status progress, counts, last run, and starts manual sync", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const pathWithSearch = url.startsWith("http")
        ? new URL(url).pathname + new URL(url).search
        : url;
      const path = pathWithSearch.split("?")[0];
      const body =
        path === "/sync"
          ? {
              account_id: "talib@example.test",
              finished_at: null,
              last_error: null,
              message_count: 2600,
              mode: "incremental",
              page_count: 13,
              provider: "gmail",
              raw_email_count: 1305,
              recovered_from_expired_cursor: false,
              retained_body_failure_count: 2,
              started_at: "2026-07-05T10:00:00Z",
              state: "running",
            }
          : path === "/sync/status"
            ? {
                account_id: "talib@example.test",
                finished_at: "2026-07-05T09:45:30Z",
                last_error: null,
                message_count: 2500,
                mode: "full_backfill",
                page_count: 12,
                provider: "gmail",
                raw_email_count: 1240,
                recovered_from_expired_cursor: true,
                retained_body_failure_count: 1,
                started_at: "2026-07-05T09:15:00Z",
                state: "succeeded",
              }
            : path === "/sync/recent-emails"
              ? []
            : null;

      if (!body) {
        throw new Error(`Unhandled fetch request: ${path}`);
      }

      expect(path === "/sync" ? init?.method : "GET").toBe(
        path === "/sync" ? "POST" : "GET",
      );

      return Promise.resolve(
        new Response(JSON.stringify(body), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/features");

    expect(await screen.findByText("Last sync succeeded")).toBeTruthy();
    expect(screen.getByText("1,240 raw emails")).toBeTruthy();
    expect(screen.getByText("2,500 messages")).toBeTruthy();
    expect(screen.getByText("12 pages")).toBeTruthy();
    expect(screen.getByText("1 body fetch issue")).toBeTruthy();
    expect(screen.getByText("Finished Jul 5, 2026, 9:45 AM UTC")).toBeTruthy();
    expect(screen.getByText("Recovered expired cursor")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/sync/status",
      expect.objectContaining({ method: "GET" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    expect(await screen.findByText("Sync is running")).toBeTruthy();
    expect(screen.getByText("1,305 raw emails")).toBeTruthy();
    expect(screen.getByText("2 body fetch issues")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/sync",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows recent synced email metadata so the user can inspect what was retrieved", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const path = url.startsWith("http")
        ? new URL(url).pathname + new URL(url).search
        : url;
      const pathname = path.split("?")[0];

      if (pathname === "/sync/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(
          new Response(
            JSON.stringify({
              account_id: "talib@example.test",
              finished_at: "2026-07-05T09:45:30Z",
              last_error: null,
              message_count: 2,
              mode: "full_backfill",
              page_count: 1,
              provider: "gmail",
              raw_email_count: 2,
              recovered_from_expired_cursor: false,
              started_at: "2026-07-05T09:15:00Z",
              state: "succeeded",
            }),
            {
              headers: { "Content-Type": "application/json" },
              status: 200,
            },
          ),
        );
      }

      if (pathname === "/pipeline/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(
          new Response(JSON.stringify(pipelineStatusResponse()), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (pathname === "/sync/recent-emails") {
        expect(init?.method).toBe("GET");
        expect(path).toContain("limit=50");
        expect(path).toContain("order=sent_at");
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                from_domain: "example.com",
                to_domains: ["example.com"],
                subject_present: true,
                sent_at: "2026-07-05T12:00:00Z",
                body_retention_state: "retained",
                has_retained_body: true,
                provider: "gmail",
                ingested_at: "2026-07-05T12:01:00Z",
                filter_outcome: "candidate",
                filter_reason: "sender_domain:example.com",
              },
            ]),
            {
              headers: { "Content-Type": "application/json" },
              status: 200,
            },
          ),
        );
      }

      throw new Error(`Unhandled fetch request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/features");

    expect(
      await screen.findByText("Newest synced mailbox messages"),
    ).toBeTruthy();
    expect(screen.getByText("Subject captured")).toBeTruthy();
    expect(screen.getAllByText("example.com").length).toBeGreaterThan(0);
    expect(screen.getByText("kept by filter")).toBeTruthy();
    expect(screen.getByText("body retained")).toBeTruthy();
    expect(screen.queryByText("Private body")).toBeNull();
    expect(screen.queryByText("gmail-msg-1")).toBeNull();
    expect(screen.queryByText("thread-1")).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: /Subject captured/ }),
    );
    expect(screen.getByText("Provider")).toBeTruthy();
    expect(screen.getByText("From domain")).toBeTruthy();
    expect(screen.getByText("To domains")).toBeTruthy();
    expect(
      screen.getByText("sender_domain:example.com", { exact: false }),
    ).toBeTruthy();
    expect(screen.queryByText("body_text")).toBeNull();

    expect(
      screen.getByRole("button", { name: "Recently ingested" }),
    ).toBeTruthy();
  });

  it("shows running progress immediately while the sync start request is pending", async () => {
    let syncRequestStarted = false;
    let resolveSyncRequest: (response: Response) => void = () => {
      throw new Error("Sync request was not started.");
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const pathWithSearch = url.startsWith("http")
        ? new URL(url).pathname + new URL(url).search
        : url;
      const path = pathWithSearch.split("?")[0];

      if (path === "/sync") {
        syncRequestStarted = true;
        expect(init?.method).toBe("POST");
        return new Promise<Response>((resolve) => {
          resolveSyncRequest = resolve;
        });
      }

      if (path === "/sync/recent-emails") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path !== "/sync/status") {
        throw new Error(`Unhandled fetch request: ${path}`);
      }

      return Promise.resolve(
        new Response(
          JSON.stringify({
            account_id: "talib@example.test",
            finished_at: "2026-07-05T09:45:30Z",
            last_error: "Previous sync failed.",
            message_count: 0,
            mode: "full_backfill",
            page_count: 0,
            provider: "gmail",
            raw_email_count: 0,
            recovered_from_expired_cursor: false,
            started_at: "2026-07-05T09:15:00Z",
            state: "failed",
            target_message_count: 500,
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/features");

    expect(await screen.findByText("Last sync failed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    expect(syncRequestStarted).toBe(true);
    expect(await screen.findByText("Sync is running")).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Sync running" }).disabled).toBe(
      true,
    );
    expect(
      screen
        .getByRole("progressbar", { name: "Sync progress" })
        .className.includes("sync-panel__progress--indeterminate"),
    ).toBe(true);
    resolveSyncRequest(
      new Response(JSON.stringify({ state: "running" }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );
  });

  it("blocks invalid sync extraction counts before posting to the API", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const pathWithSearch = url.startsWith("http")
        ? new URL(url).pathname + new URL(url).search
        : url;
      const path = pathWithSearch.split("?")[0];

      if (path === "/sync/recent-emails") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path !== "/sync/status") {
        throw new Error(`Unexpected fetch request: ${path}`);
      }

      expect(init?.method).toBe("GET");

      return Promise.resolve(
        new Response(
          JSON.stringify({
            account_id: null,
            finished_at: null,
            last_error: null,
            message_count: 0,
            mode: null,
            page_count: 0,
            provider: null,
            raw_email_count: 0,
            recovered_from_expired_cursor: false,
            started_at: null,
            state: "idle",
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/features");

    const emailCountInput = await screen.findByLabelText("Email count");
    fireEvent.change(emailCountInput, { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    expect(
      await screen.findByText("Email count must be at least 1."),
    ).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/sync",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows public sync status API errors instead of idle progress", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const pathWithSearch = url.startsWith("http")
        ? new URL(url).pathname + new URL(url).search
        : url;
      const path = pathWithSearch.split("?")[0];

      if (path === "/sync/recent-emails") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      expect(path).toBe("/sync/status");
      expect(init?.method).toBe("GET");

      return Promise.resolve(
        new Response(
          JSON.stringify({
            error: {
              code: "email_authorization_required",
              details: [],
              message: "Reconnect Gmail before syncing.",
            },
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 401,
          },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/features");

    expect(
      await screen.findByText("Reconnect Gmail before syncing."),
    ).toBeTruthy();
    expect(screen.queryByText("No sync run yet")).toBeNull();
  });

  it("refreshes running sync status until the latest run completes", async () => {
    vi.useFakeTimers();
    const runningStatus = {
      account_id: "talib@example.test",
      finished_at: null,
      last_error: null,
      message_count: 2600,
      mode: "incremental",
      page_count: 13,
      provider: "gmail",
      raw_email_count: 1305,
      recovered_from_expired_cursor: false,
      started_at: "2026-07-05T10:00:00Z",
      state: "running",
    };
    const completedStatus = {
      ...runningStatus,
      finished_at: "2026-07-05T10:05:00Z",
      message_count: 2700,
      page_count: 14,
      raw_email_count: 1325,
      state: "succeeded",
    };
    const statusResponses = [runningStatus, completedStatus];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const pathWithSearch = url.startsWith("http")
        ? new URL(url).pathname + new URL(url).search
        : url;
      const path = pathWithSearch.split("?")[0];

      if (path === "/sync/recent-emails") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      expect(path).toBe("/sync/status");
      expect(init?.method).toBe("GET");

      return Promise.resolve(
        new Response(JSON.stringify(statusResponses.shift()), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/features");

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("Sync is running")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sync running" })).toHaveProperty(
      "disabled",
      true,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(screen.getByText("Last sync succeeded")).toBeTruthy();
    expect(screen.getByText("1,325 raw emails")).toBeTruthy();
    expect(screen.getByText("2,700 messages")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sync now" })).toHaveProperty(
      "disabled",
      false,
    );
    const statusCallCount = fetchMock.mock.calls.filter(([input]) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const path = url.startsWith("http") ? new URL(url).pathname : url;
      return path === "/sync/status";
    }).length;
    expect(statusCallCount).toBe(2);
  });

  it("renders the first-run setup shell at /setup", () => {
    window.history.pushState({}, "", "/setup");

    render(<App />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Set up JobTracker locally",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("navigation", { name: "Primary" }).textContent,
    ).toContain("Setup");
    expect(
      screen.getByRole("region", { name: "Setup checklist" }),
    ).toBeTruthy();
    expect(screen.getByText("Choose provider")).toBeTruthy();
    expect(screen.getByText("Connect Gmail read-only")).toBeTruthy();
  });

  it("hides the unfinished chat feature from primary navigation", () => {
    renderAtPath("/");

    const primaryNavigation = screen.getByRole("navigation", {
      name: "Primary",
    });

    expect(
      within(primaryNavigation).queryByRole("link", { name: "Chat" }),
    ).toBeNull();
  });

  it("starts Gmail OAuth from the setup page and exposes the read-only authorization link", async () => {
    const fetchMock = mockFetchResponses({
      "/setup/status": {
        classification_mode: "local",
        email_provider: "gmail",
        gmail_connected: false,
        llm_configured: false,
        llm_provider: "ollama",
        recommended_classification_mode: "local",
        setup_complete: false,
      },
      "/auth/gmail": {
        authorization_url:
          "https://accounts.google.com/o/oauth2/v2/auth?state=issued-state",
        provider: "gmail",
        requested_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
        state: "issued-state",
      },
    });

    renderAtPath("/setup");

    fireEvent.click(
      await screen.findByRole("button", { name: "Start Gmail OAuth" }),
    );

    const googleLink = await screen.findByRole("link", {
      name: "Continue to Google",
    });

    expect(googleLink.getAttribute("href")).toBe(
      "https://accounts.google.com/o/oauth2/v2/auth?state=issued-state",
    );
    expect(
      screen.getByText(
        "Requested scope: https://www.googleapis.com/auth/gmail.readonly",
      ),
    ).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/auth/gmail",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("shows Gmail callback completion when setup status reports a connection", async () => {
    mockFetchResponses({
      "/setup/status": {
        classification_mode: "local",
        email_provider: "gmail",
        gmail_connected: true,
        llm_configured: false,
        llm_provider: "ollama",
        recommended_classification_mode: "local",
        setup_complete: false,
      },
    });

    renderAtPath("/setup");

    expect(await screen.findByText("Gmail callback complete")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Gmail connected" }),
    ).toHaveProperty("disabled", true);
  });

  it("preselects the recommended classification mode in setup", async () => {
    mockFetchResponses({
      "/setup/status": {
        classification_mode: "llm",
        email_provider: "gmail",
        gmail_connected: false,
        llm_configured: false,
        llm_provider: "azure_openai",
        recommended_classification_mode: "hybrid",
        setup_complete: false,
      },
    });

    renderAtPath("/setup");

    const hybridMode = await screen.findByRole("radio", {
      name: /hybrid/i,
    });

    await waitFor(() => {
      expect(hybridMode).toHaveProperty("checked", true);
    });
    expect(
      screen.getByText("Preselected from Azure OpenAI setup"),
    ).toBeTruthy();
  });

  it("renders the empty chat shell at the chat route", () => {
    window.history.pushState({}, "", "/chat");

    render(<App />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /ask your job search history/i,
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("main", { name: /ask your job search history/i }),
    ).toBeTruthy();
    expect(screen.getByRole("textbox", { name: /message/i })).toHaveProperty(
      "disabled",
      true,
    );
    expect(
      screen.getByText(/chat agent work arrives in phase 5/i),
    ).toBeTruthy();
  });

  it("keeps the chat shell constrained on narrow mobile viewports", () => {
    expect(styles).toContain(".chat-hero h1");
    expect(styles).toContain("font-size: clamp(2rem, 9vw, 2.45rem)");
    expect(styles).toContain("width: min(100%, 390px)");
    expect(styles).toContain("margin: 0 auto 0 0");
    expect(styles).toContain(".chat-panel");
    expect(styles).toContain("padding: 18px");
    expect(styles).toContain(".chat-card");
    expect(styles).toContain("padding: 20px");
  });

  it("keeps the dashboard chart-focused and moves the Q-09 status table out", async () => {
    mockFetchResponses({
      "/metrics/summary": metricsSummaryResponse(),
      "/metrics/rates": metricsRatesResponse(),
      "/applications?status=applied": { body: [], status: 200 },
      "/applications?status=in_review": { body: [], status: 200 },
      "/applications?status=assessment": { body: [], status: 200 },
      "/applications?status=interview": { body: [], status: 200 },
    });

    renderAtPath("/dashboard");

    expect(screen.getByRole("main", { name: "Dashboard" })).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 1, name: "Dashboard" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("region", { name: "Dashboard filters" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("region", { name: "Metrics overview" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("region", {
        name: "Current status of every application",
      }),
    ).toBeNull();
    expect(
      screen.queryByRole("table", {
        name: "Application current statuses",
      }),
    ).toBeNull();
    expect(screen.getByText("Application statuses moved to Feature Status"))
      .toBeTruthy();

    const volumeTrend = screen.getByRole("region", {
      name: "Application volume trend",
    });
    const emptyState = await within(volumeTrend).findByRole("status", {
      name: "No application volume yet",
    });

    expect(emptyState.textContent).toContain(
      "No applications exist for the volume trend yet.",
    );
  });

  it("renders Q-07 interview invitations from the metrics summary", async () => {
    mockFetchResponses({
      "/metrics/summary": metricsSummaryResponse({
        total_applications: 12,
        distinct_company_count: 7,
        evaluated_at: "2026-07-07T12:00:00Z",
        ghosted_applications: 2,
        interview_invitation_count: 3,
        rejected_applications: 1,
      }),
      "/metrics/rates": metricsRatesResponse(),
      "/applications": { body: [], status: 200 },
      "/applications?status=applied": { body: [], status: 200 },
      "/applications?status=in_review": { body: [], status: 200 },
      "/applications?status=assessment": { body: [], status: 200 },
      "/applications?status=interview": { body: [], status: 200 },
    });

    renderAtPath("/dashboard");

    expect(
      await screen.findByRole("heading", {
        level: 3,
        name: "Interview invitations",
      }),
    ).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(
      screen.getByText("Q-07 - Counted from interview_scheduled events"),
    ).toBeTruthy();
  });

  it("renders offers received on the dashboard from the metrics summary", async () => {
    mockFetchResponses({
      "/metrics/summary": {
        distinct_company_count: 3,
        ghost_threshold_days: 30,
        ghosted_applications: 0,
        interview_invitation_count: 0,
        offers_received: 2,
        evaluated_at: "2026-07-07T12:00:00+00:00",
      },
      "/metrics/rates": metricsRatesResponse(),
    });

    renderAtPath("/dashboard");

    const overview = screen.getByRole("region", { name: "Metrics overview" });
    expect(
      await within(overview).findByRole("heading", {
        level: 3,
        name: "Offers received",
      }),
    ).toBeTruthy();
    expect(within(overview).getByText("2")).toBeTruthy();
    expect(
      within(overview).getByText("Q-08 counted from offer events"),
    ).toBeTruthy();
  });

  it("shows live applications awaiting a reply on the dashboard", async () => {
    const fetchMock = mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/metrics/summary": metricsSummaryResponse({
        total_applications: 12,
        distinct_company_count: 7,
        evaluated_at: "2026-07-07T12:00:00Z",
        ghosted_applications: 3,
        interview_invitation_count: 4,
        rejected_applications: 1,
      }),
      "/metrics/rates": metricsRatesResponse(),
      "/applications?status=applied": {
        body: [
          {
            id: "app-applied",
            company: "Acme Corp",
            role_title: "Backend Engineer",
            source: "linkedin",
            first_seen_at: "2026-07-01T09:00:00Z",
            current_status: "applied",
            salary_min: 100000,
            salary_max: 120000,
            currency: "USD",
            location: "Remote",
            work_mode: "remote",
            seniority: "senior",
            sponsorship: "unknown",
            tech_stack: ["Python"],
            last_activity_at: "2026-07-03T09:00:00+01:00",
            manual_lock: false,
            created_at: "2026-07-01T09:01:00Z",
            updated_at: "2026-07-03T10:01:00Z",
          },
        ],
        status: 200,
      },
      "/applications?status=in_review": {
        body: [
          {
            id: "app-review",
            company: "Beta LLC",
            role_title: "Frontend Engineer",
            source: "company_site",
            first_seen_at: "2026-06-15T09:00:00Z",
            current_status: "in_review",
            salary_min: null,
            salary_max: null,
            currency: null,
            location: "London",
            work_mode: "hybrid",
            seniority: "mid",
            sponsorship: "not_offered",
            tech_stack: ["React"],
            last_activity_at: "2026-07-03T08:30:00Z",
            manual_lock: false,
            created_at: "2026-06-15T09:01:00Z",
            updated_at: "2026-06-18T10:01:00Z",
          },
        ],
        status: 200,
      },
      "/applications?status=assessment": {
        body: [
          {
            id: "app-applied",
            company: "Acme Corp",
            role_title: "Backend Engineer",
            source: "linkedin",
            first_seen_at: "2026-07-01T09:00:00Z",
            current_status: "applied",
            salary_min: 100000,
            salary_max: 120000,
            currency: "USD",
            location: "Remote",
            work_mode: "remote",
            seniority: "senior",
            sponsorship: "unknown",
            tech_stack: ["Python"],
            last_activity_at: "2026-07-03T09:00:00+01:00",
            manual_lock: false,
            created_at: "2026-07-01T09:01:00Z",
            updated_at: "2026-07-03T10:01:00Z",
          },
        ],
        status: 200,
      },
      "/applications?status=interview": { body: [], status: 200 },
      "/applications": { body: [], status: 200 },
    });

    renderAtPath("/dashboard");

    const liveApplications = await screen.findByRole("region", {
      name: "Live applications awaiting response",
    });

    expect(
      await within(liveApplications).findByText("2 live applications"),
    ).toBeTruthy();
    const liveApplicationLinks = within(liveApplications).getAllByRole("link");
    expect(liveApplicationLinks.map((link) => link.textContent)).toEqual([
      "Acme Corp",
      "Beta LLC",
    ]);
    expect(
      liveApplicationLinks.map((link) => link.getAttribute("href")),
    ).toEqual(["/applications/app-applied", "/applications/app-review"]);
    expect(within(liveApplications).getByText("Backend Engineer")).toBeTruthy();
    expect(
      within(liveApplications).getByText("Frontend Engineer"),
    ).toBeTruthy();
    expect(within(liveApplications).getByText("applied")).toBeTruthy();
    expect(within(liveApplications).getByText("in review")).toBeTruthy();
    expect(fetchMock.mock.calls.map(([input]) => input)).toEqual([
      "/pipeline/status",
      "/metrics/summary",
      "/metrics/breakdown?dimension=company_type",
      "/applications?status=applied",
      "/applications?status=in_review",
      "/applications?status=assessment",
      "/applications?status=interview",
      "/metrics/response-rate-trend",
      "/metrics/funnel",
      "/metrics/breakdown?dimension=source",
      "/metrics/breakdown?dimension=role",
      "/metrics/timeseries",
      "/metrics/diagnostics",
      "/metrics/rates",
    ]);
  });

  it("explains zero dashboard metrics when the pipeline has not finished", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse({
        next_action: "run_classification",
        next_action_reason:
          "2 job-search candidate emails are waiting for classification.",
        unclassified_retained_count: 2,
      }),
      "/metrics/summary": metricsSummaryResponse({ total_applications: 0 }),
      "/metrics/rates": metricsRatesResponse({
        overall_response_rate: { denominator: 0, numerator: 0, rate: null },
      }),
      "/applications?status=applied": { body: [], status: 200 },
      "/applications?status=in_review": { body: [], status: 200 },
      "/applications?status=assessment": { body: [], status: 200 },
      "/applications?status=interview": { body: [], status: 200 },
      "/applications": { body: [], status: 200 },
    });

    renderAtPath("/dashboard");

    expect(
      await screen.findByText(
        "These zeros mean the pipeline has not finished, not that you applied to zero jobs",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "2 job-search candidate emails are waiting for classification.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Job Search page" })).toBeTruthy();
  });

  it("marks zero applications as a real zero when the pipeline is up to date", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse({
        backfill_complete: true,
        backfill_state: "completed",
        incremental_sync_ready: true,
        next_action: "review_dashboard",
        next_action_reason:
          "All candidates are classified and none produced a job application.",
      }),
      "/metrics/summary": metricsSummaryResponse({ total_applications: 0 }),
      "/metrics/rates": metricsRatesResponse({
        overall_response_rate: { denominator: 0, numerator: 0, rate: null },
      }),
      "/applications?status=applied": { body: [], status: 200 },
      "/applications?status=in_review": { body: [], status: 200 },
      "/applications?status=assessment": { body: [], status: 200 },
      "/applications?status=interview": { body: [], status: 200 },
      "/applications": { body: [], status: 200 },
    });

    renderAtPath("/dashboard");

    expect(
      await screen.findByText("Zero applications is a real zero"),
    ).toBeTruthy();
  });

  it("shows an empty live applications state on the dashboard", async () => {
    mockFetchResponses({
      "/metrics/summary": metricsSummaryResponse({
        evaluated_at: "2026-07-07T12:00:00Z",
      }),
      "/metrics/rates": metricsRatesResponse(),
      "/applications?status=applied": { body: [], status: 200 },
      "/applications?status=in_review": { body: [], status: 200 },
      "/applications?status=assessment": { body: [], status: 200 },
      "/applications?status=interview": { body: [], status: 200 },
      "/applications": { body: [], status: 200 },
    });

    renderAtPath("/dashboard");

    const liveApplications = await screen.findByRole("region", {
      name: "Live applications awaiting response",
    });

    expect(
      await within(liveApplications).findByText("0 live applications"),
    ).toBeTruthy();
    expect(
      within(liveApplications).getByText(
        "No live applications are awaiting a reply right now.",
      ),
    ).toBeTruthy();
  });

  it("shows the lifetime applications count on the dashboard", async () => {
    mockFetchResponses({
      "/metrics/summary": metricsSummaryResponse({
        total_applications: 3,
        distinct_company_count: 2,
      }),
    });

    renderAtPath("/dashboard");

    const totalApplicationsCard = screen
      .getByText("Total applications")
      .closest("article");

    await waitFor(() => {
      expect(totalApplicationsCard?.textContent).toContain("3");
    });
    expect(totalApplicationsCard?.textContent).toContain(
      "Q-01 reconciled from applications",
    );
  });

  it("shows the lifetime applications count as unavailable when summary loading fails", async () => {
    mockFetchResponses({
      "/metrics/summary": {
        body: { error: { code: "internal_error", message: "Failed" } },
        status: 500,
      },
    });

    renderAtPath("/dashboard");

    const totalApplicationsCard = screen
      .getByText("Total applications")
      .closest("article");

    await waitFor(() => {
      expect(totalApplicationsCard?.textContent).toContain("Unavailable");
    });
  });

  it("renders the feature status dashboard with searchable frontend feature metadata", () => {
    renderAtPath("/features");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "What JobTracker can do today",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("navigation", { name: "Primary" }).textContent,
    ).toContain("Feature Status");

    expect(screen.getByText("Features and how to run them")).toBeTruthy();
    expect(screen.getByText("Connect Gmail")).toBeTruthy();
    expect(screen.getByText("Sync mailbox metadata")).toBeTruthy();
    expect(
      screen.getByText("Classify and build applications"),
    ).toBeTruthy();
    expect(screen.getByText("Glossary")).toBeTruthy();
    expect(screen.getByText("Raw email")).toBeTruthy();
    expect(screen.getByText("Retained body")).toBeTruthy();
    expect(screen.getByText("Filter decision")).toBeTruthy();
    expect(screen.getByText("Application")).toBeTruthy();

    fireEvent.click(
      screen.getByText(
        "Advanced: developer inventory (files, APIs, modules, and test entry points)",
      ),
    );

    expect(screen.getAllByText("Completed features").length).toBeGreaterThan(0);
    expect(screen.getByText("First-run setup shell")).toBeTruthy();
    expect(screen.getByText("Dashboard route shell")).toBeTruthy();
    expect(screen.getByText("Insights cached narrative view")).toBeTruthy();
    expect(screen.getByText("Chat route shell")).toBeTruthy();
    expect(screen.getByText("Feature Status Dashboard inventory")).toBeTruthy();
    expect(screen.getByText("Manual sync status panel")).toBeTruthy();
    expect(
      screen.getByText("How to use Feature Status Dashboard inventory"),
    ).toBeTruthy();
    expect(screen.getByText("How to use First-run setup shell")).toBeTruthy();
    expect(screen.getByText("Setup wizard API")).toBeTruthy();
    expect(screen.getByText("Frontend routes")).toBeTruthy();
    expect(screen.getByText("Frontend shared UI elements")).toBeTruthy();
    expect(
      screen.getByText("Frontend state management connections"),
    ).toBeTruthy();
    expect(screen.getByText("Frontend API integrations")).toBeTruthy();
    expect(
      screen.getByText("Backend services consumed by frontend"),
    ).toBeTruthy();

    const frontendApiIntegrations = screen.getByText(
      "Frontend API integrations",
    ).parentElement;
    expect(frontendApiIntegrations).toBeTruthy();
    expect(frontendApiIntegrations?.textContent).toContain("GET /setup/status");
    expect(frontendApiIntegrations?.textContent).toContain("GET /insights");
    expect(frontendApiIntegrations?.textContent).toContain(
      "GET /metrics/summary",
    );
    expect(frontendApiIntegrations?.textContent).toContain(
      "POST /insights/regenerate",
    );
    expect(frontendApiIntegrations?.textContent).not.toContain("POST /setup");
    expect(frontendApiIntegrations?.textContent).not.toContain(
      "Future GET /metrics/summary",
    );
    expect(frontendApiIntegrations?.textContent).not.toContain("POST /setup");
    expect(frontendApiIntegrations?.textContent).not.toContain("POST /chat");

    fireEvent.change(screen.getByLabelText("Search features"), {
      target: { value: "sync" },
    });

    expect(screen.getByText("Manual sync status panel")).toBeTruthy();
    expect(screen.queryByText("First-run setup shell")).toBeNull();

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "in_progress" },
    });

    expect(
      screen.getAllByText("No completed features match these filters.").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Sync orchestration UI hardening")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Search features"), {
      target: { value: "feature status" },
    });
    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "completed" },
    });

    expect(screen.getByText("Feature Status Dashboard inventory")).toBeTruthy();
    expect(screen.getByText("FeatureStatusDashboard")).toBeTruthy();

    fireEvent.change(
      screen.getByLabelText("Module, API, screen, or component"),
      {
        target: { value: "/features" },
      },
    );

    expect(screen.getByText("Feature Status Dashboard inventory")).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Backend" }));

    expect(screen.getByText("Controllers")).toBeTruthy();
    expect(screen.getByText("Services")).toBeTruthy();
    expect(screen.getByText("Database models")).toBeTruthy();
    expect(screen.getByText("DTOs and models")).toBeTruthy();
    expect(screen.getByText("Background jobs")).toBeTruthy();
    expect(screen.getByText("Workers")).toBeTruthy();
    expect(screen.getByText("Queues")).toBeTruthy();
    expect(screen.getAllByText("Dependencies").length).toBeGreaterThan(0);
    expect(screen.queryByText("External integrations")).toBeNull();
    expect(screen.getByText("Frontend consumers")).toBeTruthy();
  });

  it("separates backend runtime and config from database models", () => {
    renderAtPath("/features");

    fireEvent.click(screen.getByRole("tab", { name: "Backend" }));

    const databaseModels = screen.getByText("Database models").parentElement;
    expect(databaseModels).toBeTruthy();
    expect(databaseModels?.textContent).not.toContain("FastAPI runtime");
    expect(databaseModels?.textContent).not.toContain("Settings");
    expect(databaseModels?.textContent).not.toContain("AppSettings");

    const runtimeAndConfig =
      screen.getByText("Runtime and config").parentElement;
    expect(runtimeAndConfig).toBeTruthy();
    expect(runtimeAndConfig?.textContent).toContain("FastAPI runtime");
    expect(runtimeAndConfig?.textContent).toContain("Settings");
    expect(runtimeAndConfig?.textContent).toContain("AppSettings");
  });

  it("separates backend DTOs from services", () => {
    renderAtPath("/features");

    fireEvent.click(screen.getByRole("tab", { name: "Backend" }));

    const services = screen.getByText("Services").parentElement;
    expect(services).toBeTruthy();
    expect(services?.textContent).not.toContain("HealthResponse");

    const dtosAndModels = screen.getByText("DTOs and models").parentElement;
    expect(dtosAndModels).toBeTruthy();
    expect(dtosAndModels?.textContent).toContain("HealthResponse");
  });

  it("surfaces implemented backend APIs with testing details and API filtering", () => {
    renderAtPath("/features");

    fireEvent.click(screen.getByRole("tab", { name: "Backend" }));

    expect(screen.getByText("Gmail read-only OAuth API")).toBeTruthy();
    expect(screen.getByText("Manual sync API")).toBeTruthy();
    expect(screen.getByText("Local data wipe API")).toBeTruthy();
    expect(screen.getByText("Provider configuration API")).toBeTruthy();
    expect(screen.getByText("Classification control API")).toBeTruthy();
    expect(screen.getByText("Application read API")).toBeTruthy();
    expect(screen.getByText("Application manual corrections API")).toBeTruthy();
    expect(screen.getByText("Health check API")).toBeTruthy();
    expect(screen.getByText("How to use Local data wipe API")).toBeTruthy();
    expect(screen.getAllByText("POST /local-data/wipe").length).toBeGreaterThan(
      0,
    );

    const providerConfigApi = screen
      .getByText("Provider configuration API")
      .closest("article");
    expect(providerConfigApi).toBeTruthy();
    expect(
      within(providerConfigApi!).getByText("Current blockers").parentElement
        ?.textContent,
    ).toContain(
      "LLM health checks remain blocked until the config route is wired to a configured provider adapter.",
    );
    expect(
      within(providerConfigApi!).getByText("Endpoints").parentElement
        ?.textContent,
    ).not.toContain("POST /config/providers/llm/health");

    fireEvent.change(
      screen.getByLabelText("Module, API, screen, or component"),
      {
        target: { value: "GET /config/providers" },
      },
    );

    expect(screen.getByText("Provider configuration API")).toBeTruthy();
    expect(screen.getAllByText("GET /config/providers").length).toBeGreaterThan(
      0,
    );
    expect(screen.queryByText("Gmail read-only OAuth API")).toBeNull();
    expect(screen.queryByText("Manual sync API")).toBeNull();
    expect(screen.queryByText("Local data wipe API")).toBeNull();

    fireEvent.change(
      screen.getByLabelText("Module, API, screen, or component"),
      {
        target: { value: "GET /classification/estimate" },
      },
    );

    expect(screen.getByText("Classification control API")).toBeTruthy();
    expect(
      screen.getAllByText("GET /classification/estimate").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("Provider configuration API")).toBeNull();

    fireEvent.change(
      screen.getByLabelText("Module, API, screen, or component"),
      {
        target: { value: "GET /applications/{id}/events" },
      },
    );

    expect(screen.getByText("Application read API")).toBeTruthy();
    expect(
      screen.getAllByText("GET /applications/{id}/events").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("Classification control API")).toBeNull();

    fireEvent.change(
      screen.getByLabelText("Module, API, screen, or component"),
      {
        target: { value: "PATCH /applications/{application_id}/status" },
      },
    );

    expect(screen.getByText("Application manual corrections API")).toBeTruthy();
    expect(
      screen.getAllByText("PATCH /applications/{application_id}/status").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("Application read API")).toBeNull();

    fireEvent.change(
      screen.getByLabelText("Module, API, screen, or component"),
      {
        target: { value: "POST /applications/{application_id}/split" },
      },
    );

    expect(screen.getByText("Application manual corrections API")).toBeTruthy();
    expect(
      screen.getAllByText("POST /applications/{application_id}/split").length,
    ).toBeGreaterThan(0);
    expect(
      within(
        screen.getByText("How to use Application manual corrections API")
          .parentElement!,
      ).getByText(/Call POST \/applications\/\{application_id\}\/split/),
    ).toBeTruthy();
    expect(screen.queryByText("Application read API")).toBeNull();

    fireEvent.change(
      screen.getByLabelText("Module, API, screen, or component"),
      {
        target: { value: "GET /health" },
      },
    );

    expect(screen.getByText("Health check API")).toBeTruthy();
    expect(screen.getAllByText("GET /health").length).toBeGreaterThan(0);
    expect(screen.queryByText("Application manual corrections API")).toBeNull();
  });

  it("keeps feature status filters and active tab in the route query string", () => {
    renderAtPath(
      "/features?tab=backend&search=health&status=completed&testable=yes&scope=GET+%2Fhealth",
    );

    expect(
      screen.getByRole("tab", { name: "Backend", selected: true }),
    ).toBeTruthy();
    expect(
      screen.getByLabelText<HTMLInputElement>("Search features").value,
    ).toBe("health");
    expect(screen.getByLabelText<HTMLSelectElement>("Status").value).toBe(
      "completed",
    );
    expect(screen.getByLabelText<HTMLSelectElement>("Testable").value).toBe(
      "yes",
    );
    expect(
      screen.getByLabelText<HTMLInputElement>(
        "Module, API, screen, or component",
      ).value,
    ).toBe("GET /health");
    expect(screen.getByText("Health check API")).toBeTruthy();
    expect(screen.queryByText("Provider configuration API")).toBeNull();

    fireEvent.change(screen.getByLabelText("Search features"), {
      target: { value: "sync" },
    });
    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "all" },
    });
    fireEvent.change(screen.getByLabelText("Testable"), {
      target: { value: "all" },
    });
    fireEvent.change(
      screen.getByLabelText("Module, API, screen, or component"),
      {
        target: { value: "POST /sync" },
      },
    );
    fireEvent.click(screen.getByRole("tab", { name: "Frontend" }));

    const queryParams = new URLSearchParams(window.location.search);
    expect(queryParams.get("tab")).toBe("frontend");
    expect(queryParams.get("search")).toBe("sync");
    expect(queryParams.has("status")).toBe(false);
    expect(queryParams.has("testable")).toBe(false);
    expect(queryParams.get("scope")).toBe("POST /sync");
  });
});
