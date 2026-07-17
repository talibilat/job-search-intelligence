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
  ApiErrorResponse,
  ApplicationRecord,
  MetricsBreakdownResponse,
  MetricsDiagnosticsResponse,
  MetricsFunnelResponse,
  MetricsRatesResponse,
  MetricsResponseRateTrendResponse,
  MetricsSummaryResponse,
  MetricsTimeseriesResponse,
  ProcessingRunResult,
  SetupStatusResponse,
} from "./api";

function renderAtPath(pathname: string) {
  window.history.pushState({}, "", pathname);
  return render(<App />);
}

function requestPath(input: RequestInfo | URL): string {
  return typeof input === "string"
    ? input
    : input instanceof URL
      ? input.href
      : input.url;
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

function apiErrorResponse(
  code: ApiErrorResponse["error"]["code"],
  message: string,
): ApiErrorResponse & MockObjectResponseBody {
  const response = {
    error: { code, details: [], message },
  } satisfies ApiErrorResponse;
  return response;
}

const syncFailureCodeByStatus = {
  401: "email_authorization_required",
  409: "conflict",
  429: "email_rate_limited",
  502: "email_provider_request_failed",
  503: "email_temporarily_unavailable",
} as const satisfies Record<number, ApiErrorResponse["error"]["code"]>;

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
    live_applications: 0,
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
        {
          application_count: 0,
          bucket: "61_plus",
          max_days: null,
          min_days: 61,
        },
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

function processingRunResponse(
  overrides: Partial<ProcessingRunResult> = {},
): MockObjectResponseBody {
  const response: ProcessingRunResult = {
    accepted_count: 0,
    applications_upserted: 0,
    candidate_count: 0,
    candidate_limit: 500,
    classification_mode: "hybrid",
    completion_tokens: 0,
    estimated_cost_usd: 0,
    events_upserted: 0,
    ghost_retractions: 0,
    ghost_updates: 0,
    limit_reached: false,
    llm_provider: "azure_openai",
    malformed_count: 0,
    manual_conflict_count: 0,
    model: "gpt-4o-mini",
    pending_candidate_count: 0,
    processed_count: 0,
    prompt_tokens: 0,
    prompt_version: "v1",
    skipped_not_job_count: 0,
    state: "succeeded",
    total_tokens: 0,
    ...overrides,
  };
  return response as unknown as MockObjectResponseBody;
}

function setupStatusResponse(
  overrides: Partial<SetupStatusResponse> = {},
): MockObjectResponseBody {
  const response: SetupStatusResponse = {
    classification_mode: "hybrid",
    email_provider: "gmail",
    gmail_connected: true,
    llm_configured: false,
    llm_provider: "ollama",
    readiness: {
      chat_generation: {
        action: null,
        message: "Chat generation is planned for Phase 5 and is not implemented.",
        state: "not_implemented",
      },
      classification_generation: {
        action: null,
        message: "The configured classification model is available.",
        state: "ready",
      },
      embedding_generation: {
        action: null,
        message: "The configured embedding model is available.",
        state: "ready",
      },
      gmail_sync: {
        action: null,
        message: "Gmail is authorized for read-only sync.",
        state: "ready",
      },
      ready_to_classify: true,
      ready_to_sync: true,
    },
    recommended_classification_mode: "local",
    setup_complete: true,
    ...overrides,
  };

  return response as unknown as MockObjectResponseBody;
}

function setupStatusFetchResponse(
  overrides: Partial<SetupStatusResponse> = {},
) {
  return new Response(JSON.stringify(setupStatusResponse(overrides)), {
    headers: { "Content-Type": "application/json" },
    status: 200,
  });
}

function providerConfigResponse(
  llmProvider: "azure_openai" | "ollama",
  overrides: Record<string, unknown> = {},
): MockObjectResponseBody {
  return {
    email_providers: [],
    llm_providers: [],
    recommended_classification_mode:
      llmProvider === "ollama" ? "local" : "hybrid",
    selection: {
      classification_mode: llmProvider === "ollama" ? "local" : "hybrid",
      email_provider: "gmail",
      llm_provider: llmProvider,
    },
    settings: {
      azure_openai_api_version: "2024-10-21",
      azure_openai_chat_deployment: "chat",
      azure_openai_embedding_deployment: "embedding",
      azure_openai_endpoint: "https://example.openai.azure.com",
      gmail_client_config_file: "client.json",
      gmail_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      ollama_base_url: "http://127.0.0.1:11434",
      ollama_chat_model: "llama3.1",
      ollama_embedding_model: "nomic-embed-text",
      sync_interval_seconds: 1800,
      sync_on_open: true,
    },
    ...overrides,
  };
}

function confirmedProviderConfig({
  classificationMode,
  intervalSeconds = 1800,
  llmProvider,
  recommendedMode,
}: {
  classificationMode: "hybrid" | "llm" | "local";
  intervalSeconds?: number;
  llmProvider: "azure_openai" | "ollama";
  recommendedMode: "hybrid" | "llm" | "local";
}): MockObjectResponseBody {
  const base = providerConfigResponse(llmProvider);
  return {
    ...base,
    recommended_classification_mode: recommendedMode,
    selection: {
      ...(base.selection as Record<string, unknown>),
      classification_mode: classificationMode,
    },
    settings: {
      ...(base.settings as Record<string, unknown>),
      sync_interval_seconds: intervalSeconds,
    },
  };
}

function applicationRecord(
  overrides: Partial<ApplicationRecord> = {},
): ApplicationRecord {
  return {
    company: "Acme",
    created_at: "2026-07-01T12:00:00Z",
    currency: null,
    current_status: "applied",
    first_seen_at: "2026-07-01T12:00:00Z",
    id: "app-1",
    last_activity_at: "2026-07-03T12:00:00Z",
    location: "Remote",
    manual_lock: false,
    role_title: "Platform Engineer",
    salary_max: null,
    salary_min: null,
    seniority: "senior",
    source: "linkedin",
    sponsorship: "unknown",
    tech_stack: [],
    updated_at: "2026-07-03T12:00:00Z",
    work_mode: "remote",
    ...overrides,
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
      if (path === "/auth/connections") {
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path === "/sync/stats") {
        return Promise.resolve(
          new Response(
            JSON.stringify({ last_run_at: null, total_raw_emails: 0 }),
            {
              headers: { "Content-Type": "application/json" },
              status: 200,
            },
          ),
        );
      }

      if (path === "/attention") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              unique_interviewed_company_count: 0,
              prepare: [],
              interviewed: [],
              follow_up: [],
            }),
            {
              headers: { "Content-Type": "application/json" },
              status: 200,
            },
          ),
        );
      }

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
          new Response(
            JSON.stringify(metricsBreakdownResponse({ dimension: "role" })),
            {
              headers: { "Content-Type": "application/json" },
              status: 200,
            },
          ),
        );
      }

      if (path === "/metrics/breakdown?dimension=company_type") {
        return Promise.resolve(
          new Response(
            JSON.stringify(
              metricsBreakdownResponse({ dimension: "company_type" }),
            ),
            {
              headers: { "Content-Type": "application/json" },
              status: 200,
            },
          ),
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

      if (path === "/metrics/response-silence") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              human_response_count: 0,
              question_id: "Q-04",
              silent_count: 0,
              total_applications: 0,
            }),
            {
              headers: { "Content-Type": "application/json" },
              status: 200,
            },
          ),
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

      if (path === "/setup/status") {
        return Promise.resolve(setupStatusFetchResponse());
      }

      if (path === "/applications") {
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path.startsWith("/chat/history")) {
        return Promise.resolve(
          new Response(JSON.stringify({ messages: [] }), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }

      if (path.startsWith("/sync/emails")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [],
              page: 1,
              page_size: 10,
              total_items: 0,
              total_pages: 0,
            }),
            {
              headers: { "Content-Type": "application/json" },
              status: 200,
            },
          ),
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
  it("renders recurring feedback on the legacy insights route", async () => {
    window.history.pushState({}, "", "/legacy/insights");
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
    renderAtPath("/legacy");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Your job search, from inbox to insight.",
      }),
    ).toBeTruthy();
    expect(screen.getByText("Connects to Gmail locally")).toBeTruthy();
    expect(screen.getByText("Syncs safe metadata first")).toBeTruthy();
    expect(screen.getByText("Filters and classifies job email")).toBeTruthy();
    expect(
      screen.getByText("Reconstructs applications and timelines"),
    ).toBeTruthy();
    expect(screen.getByText("Charts deterministic metrics")).toBeTruthy();
    expect(
      screen.getByText("Generates grounded insights only when supported"),
    ).toBeTruthy();
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
    expect(screen.getByText("Gmail connected:", { exact: false })).toBeTruthy();
    expect(
      await screen.findByText(
        "No synced email metadata is stored yet. Run a sync to fill this list.",
      ),
    ).toBeTruthy();
  });

  it("answers current and live application questions on the feature status page", async () => {
    const fetchMock = mockFetchResponses({
      "/applications": {
        body: [
          applicationRecord({
            company: "Acme",
            current_status: "interview",
            id: "app-1",
            role_title: "Platform Engineer",
          }),
          applicationRecord({
            company: "Globex",
            current_status: "rejected",
            id: "app-2",
            role_title: "Backend Engineer",
          }),
        ],
        status: 200,
      },
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const statusTable = await screen.findByRole("table", {
      name: "Application current statuses",
    });
    expect(statusTable.classList.contains("ui-table")).toBe(true);
    expect(within(statusTable).getByText("Acme")).toBeTruthy();
    expect(within(statusTable).getByText("Interview")).toBeTruthy();
    expect(within(statusTable).getByText("Globex")).toBeTruthy();
    expect(within(statusTable).getByText("Rejected")).toBeTruthy();

    const liveApplications = screen.getByRole("region", {
      name: "Live applications awaiting response",
    });
    expect(within(liveApplications).getByText("Acme")).toBeTruthy();
    expect(within(liveApplications).queryByText("Globex")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("does not link unsafe application ids from feature status", async () => {
    mockFetchResponses({
      "/applications": {
        body: [
          applicationRecord({
            company: "Unsafe Co",
            current_status: "interview",
            id: "app/unsafe",
            role_title: "Platform Engineer",
          }),
        ],
        status: 200,
      },
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const statusTable = await screen.findByRole("table", {
      name: "Application current statuses",
    });
    const companyCell = within(statusTable).getByText("Unsafe Co");

    expect(companyCell.closest("a")).toBeNull();
    expect(screen.queryByRole("link", { name: "Unsafe Co" })).toBeNull();
  });

  it("refreshes feature status applications after a successful classification run", async () => {
    const fetchMock = mockFetchResponses({
      "/applications": [
        { body: [], status: 200 },
        {
          body: [
            applicationRecord({
              company: "Newly Classified Co",
              current_status: "applied",
              id: "app-new",
              role_title: "Frontend Engineer",
            }),
          ],
          status: 200,
        },
      ],
      "/classification/estimate": {
        cost_estimate_available: true,
        currency: "USD",
        estimated_completion_tokens: 600,
        estimated_cost_usd: 0.42,
        estimated_prompt_tokens: 3_600,
        estimated_total_tokens: 4_200,
        llm_provider: "azure_openai",
        model: "gpt-4.1-mini",
        prompt_version: "classification-v1",
        token_estimate_method: "retained_body_length_plus_overhead",
      },
      "/classification/reprocessing-plan": {
        blocked_by_missing_target_model_count: 0,
        classification_mode: "hybrid",
        email_provider: "gmail",
        llm_provider: "azure_openai",
        reprocess_count: 1,
        retained_candidate_count: 1,
        selection_policy: "unclassified_or_stale_model_or_prompt",
        should_reprocess: true,
        stale_model_count: 0,
        stale_prompt_version_count: 0,
        target_model: "gpt-4.1-mini",
        target_model_configured: true,
        target_prompt_version: "classification-v1",
        unclassified_count: 1,
        up_to_date_count: 0,
      },
      "/classification/run": {
        accepted_count: 1,
        applications_upserted: 1,
        classified_count: 1,
        events_upserted: 1,
        malformed_count: 0,
        manual_conflict_count: 0,
        skipped_not_job_related_count: 0,
      },
      "/pipeline/status": pipelineStatusResponse({
        next_action: "run_classification",
        next_action_reason:
          "1 job-search candidate email is waiting for classification.",
        unclassified_retained_count: 1,
      }),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    await screen.findByText(
      "No application records exist yet. Run sync and classification to populate deterministic application statuses.",
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Run classification" }),
    );

    const statusTable = await screen.findByRole("table", {
      name: "Application current statuses",
    });
    expect(within(statusTable).getByText("Newly Classified Co")).toBeTruthy();
    expect(within(statusTable).getByText("Applied")).toBeTruthy();
    expect(
      fetchMock.mock.calls.filter(([input]) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        const path = url.startsWith("http") ? new URL(url).pathname : url;
        return path === "/applications";
      }).length,
    ).toBeGreaterThanOrEqual(2);
  });

  it("shows classification estimate and reprocessing readiness in the runnable feature section", async () => {
    mockFetchResponses({
      "/classification/estimate": {
        candidate_count: 3,
        classification_mode: "hybrid",
        cost_estimate_available: true,
        currency: "USD",
        estimated_completion_tokens: 1_200,
        estimated_cost_usd: 0.42,
        estimated_prompt_tokens: 3_000,
        estimated_total_tokens: 4_200,
        llm_provider: "azure_openai",
        model: "gpt-4.1-mini",
        prompt_version: "classification-v1",
        token_estimate_method: "retained_body_length_plus_overhead",
      },
      "/classification/reprocessing-plan": {
        blocked_by_missing_target_model_count: 0,
        classification_mode: "hybrid",
        email_provider: "gmail",
        llm_provider: "azure_openai",
        reprocess_count: 2,
        retained_candidate_count: 3,
        selection_policy: "unclassified_or_stale_model_or_prompt",
        should_reprocess: true,
        stale_model_count: 1,
        stale_prompt_version_count: 0,
        target_model: "gpt-4.1-mini",
        target_model_configured: true,
        target_prompt_version: "classification-v1",
        unclassified_count: 1,
        up_to_date_count: 1,
      },
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

    const readiness = await screen.findByRole("region", {
      name: "Classification readiness",
    });

    expect(within(readiness).getByText("3 retained candidates")).toBeTruthy();
    expect(within(readiness).getByText("2 need classification")).toBeTruthy();
    expect(within(readiness).getByText("1 stale model")).toBeTruthy();
    expect(within(readiness).getByText("4,200 estimated tokens")).toBeTruthy();
    expect(
      within(readiness).getByText("Estimated cost $0.42 USD"),
    ).toBeTruthy();
    expect(
      within(readiness).getByText(
        "Model gpt-4.1-mini, prompt classification-v1",
      ),
    ).toBeTruthy();
  });

  it("explains classification run results through an accessible info control", async () => {
    mockFetchResponses({
      "/classification/estimate": {
        cost_estimate_available: true,
        currency: "USD",
        estimated_completion_tokens: 600,
        estimated_cost_usd: 0.42,
        estimated_prompt_tokens: 3_600,
        estimated_total_tokens: 4_200,
        llm_provider: "azure_openai",
        model: "gpt-4.1-mini",
        prompt_version: "classification-v1",
        token_estimate_method: "retained_body_length_plus_overhead",
      },
      "/classification/reprocessing-plan": {
        blocked_by_missing_target_model_count: 0,
        classification_mode: "hybrid",
        email_provider: "gmail",
        llm_provider: "azure_openai",
        reprocess_count: 2,
        retained_candidate_count: 3,
        selection_policy: "unclassified_or_stale_model_or_prompt",
        should_reprocess: true,
        stale_model_count: 0,
        stale_prompt_version_count: 0,
        target_model: "gpt-4.1-mini",
        target_model_configured: true,
        target_prompt_version: "classification-v1",
        unclassified_count: 2,
        up_to_date_count: 1,
      },
      "/classification/run": {
        accepted_count: 2,
        applications_upserted: 1,
        classified_count: 2,
        events_upserted: 3,
        malformed_count: 0,
        manual_conflict_count: 0,
        skipped_not_job_related_count: 0,
      },
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

    fireEvent.click(
      await screen.findByRole("button", { name: "Run classification" }),
    );

    await screen.findByText(
      "Classified 2 candidate emails, upserted 1 applications and 3 timeline events.",
    );
    const resultAlert = screen
      .getByText("Classification finished")
      .closest<HTMLElement>(".ui-alert");
    expect(resultAlert).toBeTruthy();

    const infoButton = within(resultAlert!).getByRole("button", {
      name: "About Classification run results",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(resultAlert!).getByText("Data source: POST /classification/run"),
    ).toBeTruthy();
    expect(
      within(resultAlert!).getByText(
        "Table: email_classifications, applications, application_events",
      ),
    ).toBeTruthy();
    expect(
      within(resultAlert!).getByText(
        "If classified or upserted counts are zero, check Classification readiness for retained candidates, target model configuration, malformed provider output, and whether accepted classifications contained application evidence.",
      ),
    ).toBeTruthy();
  });

  it("explains retained classification candidates through an accessible info control", async () => {
    mockFetchResponses({
      "/classification/estimate": {
        cost_estimate_available: true,
        currency: "USD",
        estimated_completion_tokens: 600,
        estimated_cost_usd: 0.42,
        estimated_prompt_tokens: 3_600,
        estimated_total_tokens: 4_200,
        llm_provider: "azure_openai",
        model: "gpt-4.1-mini",
        prompt_version: "classification-v1",
        token_estimate_method: "retained_body_length_plus_overhead",
      },
      "/classification/reprocessing-plan": {
        blocked_by_missing_target_model_count: 0,
        classification_mode: "hybrid",
        email_provider: "gmail",
        llm_provider: "azure_openai",
        reprocess_count: 2,
        retained_candidate_count: 3,
        selection_policy: "unclassified_or_stale_model_or_prompt",
        should_reprocess: true,
        stale_model_count: 1,
        stale_prompt_version_count: 0,
        target_model: "gpt-4.1-mini",
        target_model_configured: true,
        target_prompt_version: "classification-v1",
        unclassified_count: 1,
        up_to_date_count: 1,
      },
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

    const retainedCandidatesMetric = (
      await screen.findByText("3 retained candidates")
    ).closest("article");
    expect(retainedCandidatesMetric).toBeTruthy();

    const infoButton = within(retainedCandidatesMetric!).getByRole("button", {
      name: "About Retained classification candidates",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(retainedCandidatesMetric!).getByText(
        "Data source: GET /classification/reprocessing-plan",
      ),
    ).toBeTruthy();
    expect(
      within(retainedCandidatesMetric!).getByText("Table: raw_emails"),
    ).toBeTruthy();
    expect(
      within(retainedCandidatesMetric!).getByText(
        "Run Gmail sync from this page after connecting Gmail on Setup. If retained candidates are zero, sync has not retained any job-search email bodies for classification yet.",
      ),
    ).toBeTruthy();
  });

  it("explains classification work waiting through an accessible info control", async () => {
    mockFetchResponses({
      "/classification/estimate": {
        cost_estimate_available: true,
        currency: "USD",
        estimated_completion_tokens: 600,
        estimated_cost_usd: 0.42,
        estimated_prompt_tokens: 3_600,
        estimated_total_tokens: 4_200,
        llm_provider: "azure_openai",
        model: "gpt-4.1-mini",
        prompt_version: "classification-v1",
        token_estimate_method: "retained_body_length_plus_overhead",
      },
      "/classification/reprocessing-plan": {
        blocked_by_missing_target_model_count: 0,
        classification_mode: "hybrid",
        email_provider: "gmail",
        llm_provider: "azure_openai",
        reprocess_count: 2,
        retained_candidate_count: 3,
        selection_policy: "unclassified_or_stale_model_or_prompt",
        should_reprocess: true,
        stale_model_count: 1,
        stale_prompt_version_count: 0,
        target_model: "gpt-4.1-mini",
        target_model_configured: true,
        target_prompt_version: "classification-v1",
        unclassified_count: 1,
        up_to_date_count: 1,
      },
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

    const needsClassificationMetric = (
      await screen.findByText("2 need classification")
    ).closest("article");
    expect(needsClassificationMetric).toBeTruthy();

    const infoButton = within(needsClassificationMetric!).getByRole("button", {
      name: "About Classification work waiting",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(needsClassificationMetric!).getByText(
        "Data source: GET /classification/reprocessing-plan",
      ),
    ).toBeTruthy();
    expect(
      within(needsClassificationMetric!).getByText(
        "Table: email_classifications",
      ),
    ).toBeTruthy();
    expect(
      within(needsClassificationMetric!).getByText(
        "Run classification from this page. If the value is zero, all retained candidates are already classified for the target model and prompt, or sync has not retained candidate bodies yet.",
      ),
    ).toBeTruthy();
  });

  it("explains classification freshness through an accessible info control", async () => {
    mockFetchResponses({
      "/classification/estimate": {
        cost_estimate_available: true,
        currency: "USD",
        estimated_completion_tokens: 600,
        estimated_cost_usd: 0.42,
        estimated_prompt_tokens: 3_600,
        estimated_total_tokens: 4_200,
        llm_provider: "azure_openai",
        model: "gpt-4.1-mini",
        prompt_version: "classification-v1",
        token_estimate_method: "retained_body_length_plus_overhead",
      },
      "/classification/reprocessing-plan": {
        blocked_by_missing_target_model_count: 0,
        classification_mode: "hybrid",
        email_provider: "gmail",
        llm_provider: "azure_openai",
        reprocess_count: 2,
        retained_candidate_count: 3,
        selection_policy: "unclassified_or_stale_model_or_prompt",
        should_reprocess: true,
        stale_model_count: 1,
        stale_prompt_version_count: 0,
        target_model: "gpt-4.1-mini",
        target_model_configured: true,
        target_prompt_version: "classification-v1",
        unclassified_count: 1,
        up_to_date_count: 1,
      },
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

    const freshnessMetric = (await screen.findByText("1 stale model")).closest(
      "article",
    );
    expect(freshnessMetric).toBeTruthy();

    const infoButton = within(freshnessMetric!).getByRole("button", {
      name: "About Classification freshness",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(freshnessMetric!).getByText(
        "Data source: GET /classification/reprocessing-plan",
      ),
    ).toBeTruthy();
    expect(
      within(freshnessMetric!).getByText("Table: email_classifications"),
    ).toBeTruthy();
    expect(
      within(freshnessMetric!).getByText(
        "Run classification from this page when stale model or stale prompt counts are non-zero. If every candidate is up to date, this card should show skipped candidates instead of queued work.",
      ),
    ).toBeTruthy();
  });

  it("explains classification token and cost estimates through an accessible info control", async () => {
    mockFetchResponses({
      "/classification/estimate": {
        cost_estimate_available: true,
        currency: "USD",
        estimated_completion_tokens: 600,
        estimated_cost_usd: 0.42,
        estimated_prompt_tokens: 3_600,
        estimated_total_tokens: 4_200,
        llm_provider: "azure_openai",
        model: "gpt-4.1-mini",
        prompt_version: "classification-v1",
        token_estimate_method: "retained_body_length_plus_overhead",
      },
      "/classification/reprocessing-plan": {
        blocked_by_missing_target_model_count: 0,
        classification_mode: "hybrid",
        email_provider: "gmail",
        llm_provider: "azure_openai",
        reprocess_count: 2,
        retained_candidate_count: 3,
        selection_policy: "unclassified_or_stale_model_or_prompt",
        should_reprocess: true,
        stale_model_count: 1,
        stale_prompt_version_count: 0,
        target_model: "gpt-4.1-mini",
        target_model_configured: true,
        target_prompt_version: "classification-v1",
        unclassified_count: 1,
        up_to_date_count: 1,
      },
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

    const estimateMetric = (
      await screen.findByText("4,200 estimated tokens")
    ).closest("article");
    expect(estimateMetric).toBeTruthy();

    const infoButton = within(estimateMetric!).getByRole("button", {
      name: "About Classification cost estimate",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(estimateMetric!).getByText(
        "Data source: GET /classification/estimate",
      ),
    ).toBeTruthy();
    expect(within(estimateMetric!).getByText("Table: raw_emails")).toBeTruthy();
    expect(
      within(estimateMetric!).getByText(
        "Run Gmail sync to retain candidate bodies, then review this estimate before running classification. If tokens or cost are missing, configure a target LLM provider on Setup or use local Ollama where hosted cost is zero.",
      ),
    ).toBeTruthy();
  });

  it("disables classification runs with a clear reason when the target model is not configured", async () => {
    const fetchMock = mockFetchResponses({
      "/classification/estimate": {
        cost_estimate_available: false,
        currency: "USD",
        estimated_completion_tokens: 600,
        estimated_cost_usd: null,
        estimated_prompt_tokens: 3_600,
        estimated_total_tokens: 4_200,
        llm_provider: "azure_openai",
        model: "gpt-4.1-mini",
        prompt_version: "classification-v1",
        token_estimate_method: "retained_body_length_plus_overhead",
      },
      "/classification/reprocessing-plan": {
        blocked_by_missing_target_model_count: 2,
        classification_mode: "hybrid",
        email_provider: "gmail",
        llm_provider: "azure_openai",
        reprocess_count: 2,
        retained_candidate_count: 3,
        selection_policy: "unclassified_or_stale_model_or_prompt",
        should_reprocess: true,
        stale_model_count: 0,
        stale_prompt_version_count: 0,
        target_model: "gpt-4.1-mini",
        target_model_configured: false,
        target_prompt_version: "classification-v1",
        unclassified_count: 2,
        up_to_date_count: 1,
      },
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

    const runButton = await screen.findByRole("button", {
      name: "Run classification",
    });

    expect(runButton.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText(
        "Classification is blocked because no target LLM model is configured. Open Setup to choose Azure OpenAI or Ollama before running classification.",
      ),
    ).toBeTruthy();

    fireEvent.click(runButton);

    const requestedPaths = fetchMock.mock.calls.map(([input]) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      return url.startsWith("http") ? new URL(url).pathname : url;
    });
    expect(requestedPaths).not.toContain("/classification/run");
  });

  it("disables classification runs while readiness is unavailable", async () => {
    const fetchMock = mockFetchResponses({
      "/classification/estimate": {
        body: {
          error: {
            code: "classification_estimate_unavailable",
            details: [],
            message: "Classification estimate is unavailable.",
          },
        },
        status: 503,
      },
      "/classification/reprocessing-plan": {
        body: {
          error: {
            code: "classification_plan_unavailable",
            details: [],
            message: "Classification reprocessing plan is unavailable.",
          },
        },
        status: 503,
      },
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
      await screen.findByText(
        "Classification readiness is unavailable. Start the local backend and configure an LLM provider to see estimates.",
      ),
    ).toBeTruthy();

    const runButton = screen.getByRole("button", {
      name: "Run classification",
    });
    expect(runButton.hasAttribute("disabled")).toBe(true);

    fireEvent.click(runButton);

    const requestedPaths = fetchMock.mock.calls.map(([input]) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      return url.startsWith("http") ? new URL(url).pathname : url;
    });
    expect(requestedPaths).not.toContain("/classification/run");
  });

  it("explains runnable feature guide entries through accessible info controls", () => {
    renderAtPath("/features");

    const syncInfoButton = screen.getByRole("button", {
      name: "About Sync mailbox metadata",
    });
    expect(syncInfoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(syncInfoButton);

    expect(syncInfoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      screen.getByText("Data source: POST /sync and GET /sync/status"),
    ).toBeTruthy();
    expect(screen.getByText("Table: raw_emails")).toBeTruthy();
    expect(
      screen.getByText(
        "If values are zero or missing, connect Gmail on Setup, then run Sync now in this Feature Status section.",
      ),
    ).toBeTruthy();

    fireEvent.click(syncInfoButton);
    expect(syncInfoButton.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(syncInfoButton);
    expect(syncInfoButton.getAttribute("aria-expanded")).toBe("false");
    expect(
      screen.queryByText("Data source: POST /sync and GET /sync/status"),
    ).toBeNull();

    fireEvent.click(syncInfoButton);
    expect(syncInfoButton.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(syncInfoButton);
    expect(syncInfoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.mouseEnter(syncInfoButton);
    expect(syncInfoButton.getAttribute("aria-expanded")).toBe("true");
    fireEvent.mouseLeave(syncInfoButton);
    expect(syncInfoButton.getAttribute("aria-expanded")).toBe("false");
  });

  it("points runnable feature guide steps to Feature Status instead of stale Job Search copy", () => {
    renderAtPath("/features");

    expect(
      screen.getByText(
        'Feature Status runnable sync pipeline: press "Sync now". Optional limits (email count, dates, pages) bound each run.',
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        'Feature Status runnable sync pipeline: press "Run classification" when candidates are waiting. Requires a configured LLM provider (Ollama or Azure OpenAI).',
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/Job Search page/)).toBeNull();
  });

  it("explains the Raw emails pipeline stage through an accessible info control", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const rawEmailsStage = (await screen.findByText("Raw emails")).closest(
      "article",
    );
    expect(rawEmailsStage).toBeTruthy();

    const infoButton = within(rawEmailsStage!).getByRole("button", {
      name: "About Raw emails",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(rawEmailsStage!).getByText("Data source: GET /pipeline/status"),
    ).toBeTruthy();
    expect(within(rawEmailsStage!).getByText("Table: raw_emails")).toBeTruthy();
    expect(
      within(rawEmailsStage!).getByText(
        "Run Gmail sync from this page after connecting Gmail on Setup. If the count is zero, the mailbox metadata backfill has not stored any rows yet.",
      ),
    ).toBeTruthy();
  });

  it("explains the Filter decisions pipeline stage through an accessible info control", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const filterStage = (await screen.findByText("Filter decisions")).closest(
      "article",
    );
    expect(filterStage).toBeTruthy();

    const infoButton = within(filterStage!).getByRole("button", {
      name: "About Filter decisions",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(filterStage!).getByText("Data source: GET /pipeline/status"),
    ).toBeTruthy();
    expect(
      within(filterStage!).getByText("Table: email_filter_decisions"),
    ).toBeTruthy();
    expect(
      within(filterStage!).getByText(
        "Run Gmail sync after connecting Gmail on Setup. If both kept and skipped are zero, the broad job-search filter has not evaluated any synced metadata yet.",
      ),
    ).toBeTruthy();
  });

  it("explains the Retained bodies pipeline stage through an accessible info control", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const retainedBodiesStage = (
      await screen.findByText("Retained bodies")
    ).closest("article");
    expect(retainedBodiesStage).toBeTruthy();

    const infoButton = within(retainedBodiesStage!).getByRole("button", {
      name: "About Retained bodies",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(retainedBodiesStage!).getByText(
        "Data source: GET /pipeline/status",
      ),
    ).toBeTruthy();
    expect(
      within(retainedBodiesStage!).getByText("Table: raw_emails"),
    ).toBeTruthy();
    expect(
      within(retainedBodiesStage!).getByText(
        "Run Gmail sync after connecting Gmail on Setup. If this count is zero while filter candidates exist, retained body fetching has not completed or the provider could not fetch selected candidate bodies.",
      ),
    ).toBeTruthy();
  });

  it("explains the Classified pipeline stage through an accessible info control", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const classifiedStage = (await screen.findByText("Classified")).closest(
      "article",
    );
    expect(classifiedStage).toBeTruthy();

    const infoButton = within(classifiedStage!).getByRole("button", {
      name: "About Classified",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(classifiedStage!).getByText("Data source: GET /pipeline/status"),
    ).toBeTruthy();
    expect(
      within(classifiedStage!).getByText("Table: email_classifications"),
    ).toBeTruthy();
    expect(
      within(classifiedStage!).getByText(
        "Run classification from this page after sync has retained candidate bodies. If this count is zero while retained bodies exist, the classification run has not completed or the configured LLM provider needs attention on Setup.",
      ),
    ).toBeTruthy();
  });

  it("explains the Applications pipeline stage through an accessible info control", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const applicationsStage = (await screen.findByText("Applications")).closest(
      "article",
    );
    expect(applicationsStage).toBeTruthy();

    const infoButton = within(applicationsStage!).getByRole("button", {
      name: "About Applications",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(applicationsStage!).getByText("Data source: GET /pipeline/status"),
    ).toBeTruthy();
    expect(
      within(applicationsStage!).getByText(
        "Table: applications, application_events",
      ),
    ).toBeTruthy();
    expect(
      within(applicationsStage!).getByText(
        "Run classification after sync has retained candidate bodies. If applications are zero while classified job-related emails exist, aggregation has not created application timeline records yet or classified emails did not contain application evidence.",
      ),
    ).toBeTruthy();
  });

  it("explains the Provider messages sync metric through an accessible info control", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const providerMessagesMetric = (
      await screen.findByText("Provider messages")
    ).closest("article");
    expect(providerMessagesMetric).toBeTruthy();

    const infoButton = within(providerMessagesMetric!).getByRole("button", {
      name: "About Provider messages",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(providerMessagesMetric!).getByText(
        "Data source: GET /sync/status",
      ),
    ).toBeTruthy();
    expect(
      within(providerMessagesMetric!).getByText("Table: raw_emails"),
    ).toBeTruthy();
    expect(
      within(providerMessagesMetric!).getByText(
        "Run Sync now after connecting Gmail. If this stays zero, no Gmail provider page has returned message metadata for this run yet.",
      ),
    ).toBeTruthy();
  });

  it("explains the Stored in raw_emails sync metric through an accessible info control", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const storedRawEmailsMetric = (
      await screen.findByText("Stored in raw_emails")
    ).closest("article");
    expect(storedRawEmailsMetric).toBeTruthy();

    const infoButton = within(storedRawEmailsMetric!).getByRole("button", {
      name: "About Stored in raw_emails",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(storedRawEmailsMetric!).getByText("Data source: GET /sync/status"),
    ).toBeTruthy();
    expect(
      within(storedRawEmailsMetric!).getByText("Table: raw_emails"),
    ).toBeTruthy();
    expect(
      within(storedRawEmailsMetric!).getByText(
        "Run Sync now after connecting Gmail. If this is lower than Provider messages, the current run has not finished reconciling Gmail metadata into local raw_emails rows yet.",
      ),
    ).toBeTruthy();
  });

  it("explains the Pages processed sync metric through an accessible info control", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const pagesProcessedMetric = (
      await screen.findByText("Pages processed")
    ).closest("article");
    expect(pagesProcessedMetric).toBeTruthy();

    const infoButton = within(pagesProcessedMetric!).getByRole("button", {
      name: "About Pages processed",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(pagesProcessedMetric!).getByText("Data source: GET /sync/status"),
    ).toBeTruthy();
    expect(
      within(pagesProcessedMetric!).getByText("Table: email_backfill_state"),
    ).toBeTruthy();
    expect(
      within(pagesProcessedMetric!).getByText(
        "Run Sync now after connecting Gmail. If this stays zero, the sync has not completed a Gmail provider page yet or the run is using incremental sync with no new messages.",
      ),
    ).toBeTruthy();
  });

  it("explains the Retained body fetch issues sync metric through an accessible info control", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    const retainedBodyFetchIssuesMetric = (
      await screen.findByText("Retained body fetch issues")
    ).closest("article");
    expect(retainedBodyFetchIssuesMetric).toBeTruthy();

    const infoButton = within(retainedBodyFetchIssuesMetric!).getByRole(
      "button",
      {
        name: "About Retained body fetch issues",
      },
    );
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(retainedBodyFetchIssuesMetric!).getByText(
        "Data source: GET /sync/status",
      ),
    ).toBeTruthy();
    expect(
      within(retainedBodyFetchIssuesMetric!).getByText("Table: raw_emails"),
    ).toBeTruthy();
    expect(
      within(retainedBodyFetchIssuesMetric!).getByText(
        "If this value is above zero, sync stored public-safe metadata but could not fetch or normalize retained bodies for some candidate messages. Retry Sync now after checking Gmail access; persistent failures mean those messages may need provider-specific investigation without exposing raw email content.",
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
    });

    renderAtPath("/dashboard");

    const counts = await screen.findByRole("region", {
      name: "Foundational counts",
    });

    expect(within(counts).getByRole("img")).toBeTruthy();
    expect(
      within(counts).getByText(
        "Q-01, Q-03, Q-05, Q-06, Q-07, and Q-08 counts come from deterministic /metrics/summary fields over local applications and application_events.",
      ),
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

    const rates = await screen.findByRole("region", { name: "Outcome rates" });

    expect(within(rates).getByRole("img")).toBeTruthy();
    expect(
      within(rates).getByText(
        "Q-11 through Q-15 rates come from deterministic /metrics/rates numerators and denominators over local applications and application_events.",
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
            : path === "/setup/status"
              ? setupStatusResponse()
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

      if (pathname === "/setup/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(setupStatusFetchResponse());
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

    fireEvent.click(screen.getByRole("button", { name: /Subject captured/ }));
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

  it("explains recent synced email metadata through an accessible info control", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse(),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    expect(
      await screen.findByText("Newest synced mailbox messages"),
    ).toBeTruthy();

    const infoButton = screen.getByRole("button", {
      name: "About synced email metadata",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      screen.getByText("Data source: GET /sync/recent-emails"),
    ).toBeTruthy();
    expect(screen.getByText("Table: raw_emails")).toBeTruthy();
    expect(
      screen.getByText(
        "Run Sync now after connecting Gmail. If this list is empty while sync counts are non-zero, the backend has not stored public-safe raw email metadata yet or the selected ordering has no rows to show.",
      ),
    ).toBeTruthy();
  });

  it("shows actionable sync metadata fallbacks before the first Gmail run", async () => {
    mockFetchResponses({
      "/pipeline/status": pipelineStatusResponse({
        account_display: null,
        gmail_connected: false,
        next_action: "connect_gmail",
        next_action_reason: "Connect Gmail read-only before syncing.",
      }),
      "/setup/status": setupStatusResponse({
        gmail_connected: false,
        setup_complete: false,
      }),
      "/sync/status": idleSyncStatusResponse(),
      "/sync/recent-emails?limit=50&order=sent_at": { body: [], status: 200 },
    });

    renderAtPath("/features");

    expect(await screen.findByText("No sync run yet")).toBeTruthy();
    expect(screen.getByText("Run sync to measure progress")).toBeTruthy();
    expect(screen.getByText("Connect Gmail on Setup")).toBeTruthy();
    expect(
      screen.getByText("Connect Gmail, then run sync to set mode"),
    ).toBeTruthy();
    expect(screen.getByText("Connect Gmail to choose an account")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Sync unavailable" }),
    ).toHaveProperty("disabled", true);
    expect(
      screen.getByRole("link", { name: "Open Setup" }).getAttribute("href"),
    ).toBe("/setup");
    expect(screen.queryByText("Progress pending")).toBeNull();
    expect(screen.queryByText("Provider pending")).toBeNull();
    expect(screen.queryByText("Mode pending")).toBeNull();
    expect(screen.queryByText("Account pending")).toBeNull();
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

      if (path === "/setup/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(setupStatusFetchResponse());
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
    expect(
      screen.getByRole<HTMLButtonElement>("button", { name: "Sync running" })
        .disabled,
    ).toBe(true);
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

      if (path === "/setup/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(setupStatusFetchResponse());
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

  it("blocks non-integer sync extraction limits before posting to the API", async () => {
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
        expect(init?.method).toBe("POST");
        return Promise.resolve(
          new Response(JSON.stringify(idleSyncStatusResponse()), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
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

      if (path === "/setup/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(setupStatusFetchResponse());
      }

      if (path !== "/sync/status") {
        throw new Error(`Unexpected fetch request: ${path}`);
      }

      expect(init?.method).toBe("GET");
      return Promise.resolve(
        new Response(JSON.stringify(idleSyncStatusResponse()), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/features");

    const emailCountInput = await screen.findByLabelText("Email count");
    fireEvent.change(emailCountInput, { target: { value: "1.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    expect(
      await screen.findByText("Email count must be a whole number."),
    ).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/sync",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("blocks oversized sync extraction limits before posting to the API", async () => {
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
        expect(init?.method).toBe("POST");
        return Promise.resolve(
          new Response(JSON.stringify(idleSyncStatusResponse()), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
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

      if (path === "/setup/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(setupStatusFetchResponse());
      }

      if (path !== "/sync/status") {
        throw new Error(`Unexpected fetch request: ${path}`);
      }

      expect(init?.method).toBe("GET");
      return Promise.resolve(
        new Response(JSON.stringify(idleSyncStatusResponse()), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/features");

    const emailCountInput = await screen.findByLabelText("Email count");
    fireEvent.change(emailCountInput, { target: { value: "100001" } });
    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    expect(
      await screen.findByText("Email count must be 100,000 or less."),
    ).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/sync",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("blocks malformed sync date limits before posting to the API", async () => {
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
        expect(init?.method).toBe("POST");
        return Promise.resolve(
          new Response(JSON.stringify(idleSyncStatusResponse()), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
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

      if (path === "/setup/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(setupStatusFetchResponse());
      }

      if (path !== "/sync/status") {
        throw new Error(`Unexpected fetch request: ${path}`);
      }

      expect(init?.method).toBe("GET");
      return Promise.resolve(
        new Response(JSON.stringify(idleSyncStatusResponse()), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/features");

    const sinceDateInput = await screen.findByLabelText("Since date");
    Object.defineProperty(sinceDateInput, "value", {
      configurable: true,
      value: "2026-02-30",
    });
    fireEvent.input(sinceDateInput);
    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    expect(
      await screen.findByText("Since date must be a valid calendar date."),
    ).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/sync",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("trims sync date limits before posting to the API", async () => {
    let postedOptions: Record<string, unknown> | null = null;
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
        expect(init?.method).toBe("POST");
        if (typeof init?.body !== "string") {
          throw new Error("Expected sync request body to be JSON text.");
        }
        postedOptions = JSON.parse(init.body) as Record<string, unknown>;
        return Promise.resolve(
          new Response(JSON.stringify(idleSyncStatusResponse()), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
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

      if (path === "/setup/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(setupStatusFetchResponse());
      }

      if (path !== "/sync/status") {
        throw new Error(`Unexpected fetch request: ${path}`);
      }

      expect(init?.method).toBe("GET");
      return Promise.resolve(
        new Response(JSON.stringify(idleSyncStatusResponse()), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/features");

    const sinceDateInput = await screen.findByLabelText("Since date");
    Object.defineProperty(sinceDateInput, "value", {
      configurable: true,
      value: " 2026-07-01 ",
    });
    fireEvent.input(sinceDateInput);
    const beforeDateInput = await screen.findByLabelText("Before date");
    Object.defineProperty(beforeDateInput, "value", {
      configurable: true,
      value: " 2026-08-01 ",
    });
    fireEvent.input(beforeDateInput);

    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    await waitFor(() => {
      expect(postedOptions).toEqual(
        expect.objectContaining({
          before_date: "2026-08-01",
          since_date: "2026-07-01",
        }),
      );
    });
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

      if (path === "/setup/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(setupStatusFetchResponse());
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

      if (path === "/setup/status") {
        expect(init?.method).toBe("GET");
        return Promise.resolve(setupStatusFetchResponse());
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
    renderAtPath("/legacy");

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

  it("shows a setup-status disabled reason when setup choices cannot load", async () => {
    const fetchMock = vi.fn(() =>
      Promise.reject(new TypeError("backend unavailable")),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/setup");

    expect(await screen.findByText("Setup status unavailable")).toBeTruthy();
    expect(
      screen.getByText(
        "Setup status is unavailable. Start the local backend before saving setup choices or connecting Gmail.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Save setup choices" }),
    ).toHaveProperty("disabled", true);
    expect(screen.queryByText("Gmail auth failed")).toBeNull();
  });

  it("submits the selected setup classification mode", async () => {
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
      "/setup": {
        classification_mode: "hybrid",
        email_provider: "gmail",
        gmail_connected: false,
        llm_configured: false,
        llm_provider: "ollama",
        recommended_classification_mode: "local",
        setup_complete: false,
        status: "accepted",
      },
    });

    renderAtPath("/setup");

    fireEvent.click(await screen.findByRole("radio", { name: /hybrid/i }));
    fireEvent.click(screen.getByRole("button", { name: "Save setup choices" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/setup",
        expect.objectContaining({
          body: JSON.stringify({
            classification_mode: "hybrid",
            email_provider: "gmail",
            llm_provider: "ollama",
          }),
          method: "POST",
        }),
      );
    });
    expect(await screen.findByText("Setup choices saved")).toBeTruthy();
  });

  it("opens the grounded chat workspace at the direct chat route", async () => {
    window.history.pushState({}, "", "/chat");
    mockFetchResponses({});

    render(<App />);

    expect(
      screen.getByRole("complementary", { name: "Ask AI drawer" }),
    ).toBeTruthy();
    expect(
      await screen.findByText("Ask from your actual search history"),
    ).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Message" })).toBeTruthy();
  });

  it("renders the redesigned application detail page on application detail routes", async () => {
    mockFetchResponses({
      "/applications/app-1": {
        company: "Acme Corp",
        created_at: "2026-07-01T09:00:00Z",
        currency: null,
        current_status: "applied",
        first_seen_at: "2026-07-01T09:00:00Z",
        id: "app-1",
        last_activity_at: "2026-07-01T09:00:00Z",
        location: null,
        manual_lock: false,
        role_title: "Software Engineer",
        salary_max: null,
        salary_min: null,
        seniority: null,
        source: "other",
        sponsorship: "unknown",
        tech_stack: [],
        updated_at: "2026-07-01T09:00:00Z",
        work_mode: null,
      },
      "/applications/app-1/events": { body: [], status: 200 },
    });

    renderAtPath("/applications/app-1");

    expect(
      await screen.findByRole("heading", { name: "Acme Corp" }),
    ).toBeTruthy();
    expect(screen.getByText(/Software Engineer · applied/)).toBeTruthy();
    expect(screen.getByText("What happened, step by step")).toBeTruthy();
  });

  it("shows a public-safe application unavailable state for malformed application detail URLs", () => {
    const fetchMock = mockFetchResponses({});

    renderAtPath("/applications/%E0%A4%A");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Application unavailable",
      }),
    ).toBeTruthy();
    expect(
      screen.getByText("The application link is malformed or unsupported.", {
        exact: false,
      }),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        requestPath(input).includes("/applications"),
      ),
    ).toBe(false);
  });

  it("does not send encoded slash application route segments to backend paths", () => {
    const fetchMock = mockFetchResponses({});

    renderAtPath("/applications/%2F");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Application unavailable",
      }),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        requestPath(input).includes("/applications"),
      ),
    ).toBe(false);
  });

  it("does not send encoded query delimiter application route segments to backend paths", () => {
    const fetchMock = mockFetchResponses({});

    renderAtPath("/applications/app%3Fdebug");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Application unavailable",
      }),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        requestPath(input).includes("/applications"),
      ),
    ).toBe(false);
  });

  it("does not send encoded backslash application route segments to backend paths", () => {
    const fetchMock = mockFetchResponses({});

    renderAtPath("/applications/app%5Cdebug");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Application unavailable",
      }),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        requestPath(input).includes("/applications"),
      ),
    ).toBe(false);
  });

  it("does not send double-encoded slash application route segments to backend paths", () => {
    const fetchMock = mockFetchResponses({});

    renderAtPath("/applications/%252F");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Application unavailable",
      }),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        requestPath(input).includes("/applications"),
      ),
    ).toBe(false);
  });

  it("does not send encoded control-character application route segments to backend paths", () => {
    const fetchMock = mockFetchResponses({});

    renderAtPath("/applications/app%00debug");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Application unavailable",
      }),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        requestPath(input).includes("/applications"),
      ),
    ).toBe(false);
  });

  it("does not send whitespace-padded application route segments to backend paths", () => {
    const fetchMock = mockFetchResponses({});

    renderAtPath("/applications/%20app-1%20");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Application unavailable",
      }),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        requestPath(input).includes("/applications"),
      ),
    ).toBe(false);
  });

  it("shows application unavailable for unsupported application subroutes", () => {
    const fetchMock = mockFetchResponses({});

    renderAtPath("/applications/app-1/events");

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Application unavailable",
      }),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        requestPath(input).includes("/applications"),
      ),
    ).toBe(false);
  });

  it("keeps the dashboard chart-focused and moves the Q-09 status table out", async () => {
    mockFetchResponses({
      "/metrics/summary": metricsSummaryResponse(),
      "/metrics/rates": metricsRatesResponse(),
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
      screen.getByRole("region", { name: "Foundational counts" }),
    ).toBeTruthy();
    expect(screen.getByRole("region", { name: "Outcome rates" })).toBeTruthy();
    expect(
      screen.getByRole("region", { name: "Response timing" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("region", { name: "Metrics overview" }),
    ).toBeNull();
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
    expect(
      screen.queryByText("Application statuses moved to Feature Status"),
    ).toBeNull();

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

  it("renders Q-07 interview invitations from the metrics summary chart", async () => {
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
    });

    renderAtPath("/dashboard");

    const counts = await screen.findByRole("region", {
      name: "Foundational counts",
    });

    expect(within(counts).getByRole("img")).toBeTruthy();
    expect(
      within(counts).getByText(
        "Q-01, Q-03, Q-05, Q-06, Q-07, and Q-08 counts come from deterministic /metrics/summary fields over local applications and application_events.",
      ),
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

    const counts = await screen.findByRole("region", {
      name: "Foundational counts",
    });

    expect(within(counts).getByRole("img")).toBeTruthy();
    expect(
      within(counts).getByText(
        "Q-01, Q-03, Q-05, Q-06, Q-07, and Q-08 counts come from deterministic /metrics/summary fields over local applications and application_events.",
      ),
    ).toBeTruthy();
  });

  it("keeps live application lists off the dashboard route", async () => {
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
    });

    renderAtPath("/dashboard");

    await screen.findByRole("region", { name: "Application funnel" });

    expect(
      screen.queryByRole("region", {
        name: "Live applications awaiting response",
      }),
    ).toBeNull();
    expect(
      fetchMock.mock.calls.some(([input]) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        return url.startsWith("/applications?status=");
      }),
    ).toBe(false);
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
    expect(screen.queryByRole("link", { name: "Job Search page" })).toBeNull();
    const pipelineAlert = screen
      .getByText(
        "These zeros mean the pipeline has not finished, not that you applied to zero jobs",
      )
      .closest(".ui-alert");

    expect(pipelineAlert).toBeTruthy();
    expect(
      within(pipelineAlert as HTMLElement)
        .getByRole("link", { name: "Feature Status" })
        .getAttribute("href"),
    ).toBe("/features");
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
    });

    renderAtPath("/dashboard");

    expect(
      await screen.findByText("Zero applications is a real zero"),
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

    const counts = await screen.findByRole("region", {
      name: "Foundational counts",
    });

    expect(within(counts).getByRole("img")).toBeTruthy();
    expect(screen.queryByText("Total applications")).toBeNull();
  });

  it("shows the lifetime applications chart as unavailable when summary loading fails", async () => {
    mockFetchResponses({
      "/metrics/summary": {
        body: { error: { code: "internal_error", message: "Failed" } },
        status: 500,
      },
    });

    renderAtPath("/dashboard");

    const counts = await screen.findByRole("region", {
      name: "Foundational counts",
    });

    expect(
      within(counts).getByRole("status", { name: "No count data yet" }),
    ).toBeTruthy();
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
    expect(screen.getByText("Classify and build applications")).toBeTruthy();
    expect(screen.getByText("Application status table")).toBeTruthy();
    expect(screen.getByText("Live applications queue")).toBeTruthy();
    expect(
      screen.getByText(
        "Available through Ask AI and /chat with persisted local history, grounded refusals, retries, and cited sources.",
      ),
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
    expect(screen.getByText("Dashboard chart workspace")).toBeTruthy();
    expect(screen.queryByText(/summary metric cards/i)).toBeNull();
    expect(
      screen.queryByText(/Unimplemented metric values remain Pending/i),
    ).toBeNull();
    expect(screen.getByText("Insights cached narrative view")).toBeTruthy();
    expect(screen.getByText("Grounded chat workspace")).toBeTruthy();
    expect(
      screen.getByText(
        "QA can ask a quantitative fixture question that matches the dashboard and a content question that links to safe source evidence.",
      ),
    ).toBeTruthy();
    expect(
      screen.queryByText(/Direct \/chat falls back to the landing page/i),
    ).toBeNull();
    expect(screen.queryByText("Chat route shell")).toBeNull();
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
    expect(frontendApiIntegrations?.textContent).toContain("POST /setup");
    expect(frontendApiIntegrations?.textContent).not.toContain(
      "Future GET /metrics/summary",
    );
    expect(frontendApiIntegrations?.textContent).toContain("POST /chat");

    const connectGmailInfo = screen.getByRole("button", {
      name: "About Connect Gmail",
    });
    fireEvent.focus(connectGmailInfo);
    expect(connectGmailInfo.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(connectGmailInfo);
    expect(connectGmailInfo.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(connectGmailInfo);
    expect(connectGmailInfo.getAttribute("aria-expanded")).toBe("false");

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

  it("canonicalizes padded feature status enum query filters", () => {
    renderAtPath(
      "/features?tab=%20backend%20&status=%20completed%20&testable=%20yes%20",
    );

    expect(
      screen.getByRole("tab", { name: "Backend", selected: true }),
    ).toBeTruthy();
    expect(screen.getByLabelText<HTMLSelectElement>("Status").value).toBe(
      "completed",
    );
    expect(screen.getByLabelText<HTMLSelectElement>("Testable").value).toBe(
      "yes",
    );

    const queryParams = new URLSearchParams(window.location.search);
    expect(queryParams.get("tab")).toBe("backend");
    expect(queryParams.get("status")).toBe("completed");
    expect(queryParams.get("testable")).toBe("yes");
  });

  it("canonicalizes padded feature status text filter edits", () => {
    renderAtPath("/features");

    fireEvent.change(screen.getByLabelText("Search features"), {
      target: { value: "  sync  " },
    });
    fireEvent.change(
      screen.getByLabelText("Module, API, screen, or component"),
      {
        target: { value: "  POST /sync  " },
      },
    );

    expect(
      screen.getByLabelText<HTMLInputElement>("Search features").value,
    ).toBe("sync");
    expect(
      screen.getByLabelText<HTMLInputElement>(
        "Module, API, screen, or component",
      ).value,
    ).toBe("POST /sync");

    const queryParams = new URLSearchParams(window.location.search);
    expect(queryParams.get("search")).toBe("sync");
    expect(queryParams.get("scope")).toBe("POST /sync");
  });

  it("redesign Gmail requests the typed authorization URL once and redirects to Google", async () => {
    let resolveAuthorization: (response: Response) => void = () => {
      throw new Error("Gmail authorization was not requested.");
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/auth/gmail") {
        return new Promise<Response>((resolve) => {
          resolveAuthorization = resolve;
        });
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    const assignSpy = vi.fn();
    const originalWindow = window;
    const locationProxy = new Proxy(
      {},
      {
        get(_target, property) {
          return property === "assign"
            ? assignSpy
            : (Reflect.get(
                originalWindow.location,
                property,
                originalWindow.location,
              ) as unknown);
        },
      },
    );
    vi.stubGlobal(
      "window",
      new Proxy(
        {},
        {
          get(_target, property) {
            return property === "location"
              ? locationProxy
              : (Reflect.get(
                  originalWindow,
                  property,
                  originalWindow,
                ) as unknown);
          },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/settings");
    fireEvent.click(
      screen.getByRole("button", { name: "+ Add another inbox" }),
    );
    const gmailButton = screen.getByRole("button", { name: "G Gmail" });
    fireEvent.click(gmailButton);
    fireEvent.click(gmailButton);

    expect(gmailButton).toHaveProperty("disabled", true);
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => requestPath(input) === "/auth/gmail",
      ),
    ).toHaveLength(1);

    resolveAuthorization(
      new Response(
        JSON.stringify({
          authorization_url:
            "https://accounts.google.com/o/oauth2/v2/auth?state=issued-state&safe=true",
          provider: "gmail",
          requested_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
          state: "issued-state",
        }),
        { headers: { "Content-Type": "application/json" }, status: 200 },
      ),
    );

    await waitFor(() => {
      expect(assignSpy).toHaveBeenCalledWith(
        "https://accounts.google.com/o/oauth2/v2/auth?state=issued-state&safe=true",
      );
    });
    expect(assignSpy).not.toHaveBeenCalledWith("/auth/gmail");
  });

  it("redesign Gmail renders typed authorization failures", async () => {
    mockFetchResponses({
      "/auth/gmail": {
        body: apiErrorResponse(
          "bad_request",
          "Configure your Gmail OAuth client before connecting.",
        ),
        status: 400,
      },
    });

    renderAtPath("/settings");
    fireEvent.click(
      screen.getByRole("button", { name: "+ Add another inbox" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "G Gmail" }));

    expect(
      await screen.findByText(
        "Configure your Gmail OAuth client before connecting.",
      ),
    ).toBeTruthy();
  });

  it("redesign sync starts custom dates empty and blocks an incomplete range", () => {
    const fetchMock = mockFetchResponses({});

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    fireEvent.click(
      screen.getByRole("button", { name: /A specific date range/ }),
    );

    expect(
      screen.getByLabelText<HTMLInputElement>("Sync from date").value,
    ).toBe("");
    expect(screen.getByLabelText<HTMLInputElement>("Sync to date").value).toBe(
      "",
    );
    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    const submit = within(menu!).getByRole("button", { name: "Sync" });
    expect(submit).toHaveProperty("disabled", true);
    fireEvent.click(submit);
    expect(
      fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/sync"),
    ).toHaveLength(0);
  });

  it("redesign sync describes a required lifetime backfill honestly", async () => {
    mockFetchResponses({
      "/sync/estimate": {
        basis: "full_backfill",
        estimated_message_count: null,
        total_local_emails: 0,
        window_end: null,
        window_start: null,
      },
    });

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));

    expect(
      await screen.findByText("Full mailbox history · time depends on mailbox size"),
    ).toBeTruthy();
    expect(screen.queryByText(/New mail only/)).toBeNull();
  });

  it("redesign sync describes a message cap as an upper bound", async () => {
    mockFetchResponses({
      "/sync/estimate": {
        basis: "unknown_incremental",
        estimated_message_count: null,
        total_local_emails: 2,
        window_end: null,
        window_start: null,
      },
      "/sync/estimate?max_messages=500": {
        basis: "message_cap",
        estimated_message_count: 500,
        total_local_emails: 2,
        window_end: null,
        window_start: null,
      },
    });

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    fireEvent.click(
      screen.getByRole("button", { name: /Only the most recent emails/ }),
    );

    expect(await screen.findByText("Up to 500 new emails")).toBeTruthy();
  });

  it("redesign sync reports an unknown incremental date-window count", async () => {
    mockFetchResponses({
      "/sync/estimate": {
        basis: "unknown_incremental",
        estimated_message_count: null,
        total_local_emails: 2,
        window_end: null,
        window_start: null,
      },
      "/sync/estimate?max_age_days=7": {
        basis: "unknown_incremental_window",
        estimated_message_count: null,
        total_local_emails: 2,
        window_end: null,
        window_start: "2026-07-05T00:00:00Z",
      },
    });

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    fireEvent.click(screen.getByRole("button", { name: /Last 7 days/ }));

    expect(
      await screen.findByText("New mail in selected date range · count unknown"),
    ).toBeTruthy();
  });

  it.each([
    ["New mail since last sync", null],
    ["Last 7 days", { max_age_days: 7 }],
    ["Last 30 days", { max_age_days: 30 }],
    ["Only the most recent emails", { max_messages: 500 }],
  ])(
    "redesign sync sends the exact %s payload",
    async (scopeName, expectedBody) => {
      const fetchMock = mockFetchResponses({
        "/sync": { state: "succeeded" },
      });

      renderAtPath("/");
      fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
      fireEvent.click(
        screen.getByRole("button", { name: new RegExp(scopeName) }),
      );
      const menu = screen.getByText("What should I check?").parentElement;
      expect(menu).toBeTruthy();
      fireEvent.click(within(menu!).getByRole("button", { name: "Sync" }));

      await waitFor(() => {
        const syncCall = fetchMock.mock.calls.find(
          ([input]) => requestPath(input) === "/sync",
        );
        expect(syncCall).toBeTruthy();
        const [, init] = syncCall as unknown as [
          RequestInfo | URL,
          RequestInit?,
        ];
        if (typeof init?.body !== "string") {
          throw new Error("Expected the sync request body to be JSON text.");
        }
        expect(JSON.parse(init.body)).toEqual(expectedBody);
      });
      expect(
        fetchMock.mock.calls.filter(
          ([input]) => requestPath(input) === "/sync/status",
        ),
      ).toHaveLength(0);
    },
  );

  it("redesign sync polls live progress before the sync request finishes", async () => {
    vi.useFakeTimers();
    let resolveSyncRequest: (response: Response) => void = () => {
      throw new Error("Sync request was not started.");
    };
    const fallbackFetch = mockFetchResponses({
      "/sync/stats": { last_run_at: null, total_raw_emails: 47 },
      "/sync/status": { message_count: 37, state: "running" },
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (requestPath(input) === "/sync") {
        return new Promise<Response>((resolve) => {
          resolveSyncRequest = resolve;
        });
      }
      return fallbackFetch(input);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    fireEvent.click(within(menu!).getByRole("button", { name: "Sync" }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    expect(screen.getByText("37 new for this run · 47 total emails synced")).toBeTruthy();
    expect(
      fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/sync/status"),
    ).toHaveLength(1);

    resolveSyncRequest(
      new Response(JSON.stringify({ last_error: "Test run stopped.", state: "failed" }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );
    await act(async () => {
      await Promise.resolve();
    });
  });

  it("redesign successful seven-day sync scopes the email list without classification", async () => {
    const startedAt = Date.now();
    const fetchMock = mockFetchResponses({
      "/sync": { state: "succeeded" },
    });

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    fireEvent.click(screen.getByRole("button", { name: /Last 7 days/ }));
    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    fireEvent.click(within(menu!).getByRole("button", { name: "Sync" }));

    await waitFor(() => {
      const scopedRequest = fetchMock.mock.calls
        .map(([input]) => requestPath(input))
        .filter((path) => path.startsWith("/sync/emails"))
        .find((path) =>
          new URL(path, "http://localhost").searchParams.has("sent_after"),
        );
      expect(scopedRequest).toBeTruthy();
      const sentAfter = new URL(
        scopedRequest!,
        "http://localhost",
      ).searchParams.get("sent_after");
      const boundary = Date.parse(sentAfter ?? "");
      expect(Number.isNaN(boundary)).toBe(false);
      expect(boundary).toBeGreaterThanOrEqual(
        startedAt - 7 * 24 * 60 * 60 * 1000 - 1_000,
      );
      expect(boundary).toBeLessThanOrEqual(
        Date.now() - 7 * 24 * 60 * 60 * 1000 + 1_000,
      );
    });

    expect(
      fetchMock.mock.calls.filter(([input]) =>
        ["/classification/run", "/processing/run"].includes(requestPath(input)),
      ),
    ).toHaveLength(0);
  });

  it("redesign sync processes every bounded classification batch before reporting completion", async () => {
    vi.useFakeTimers();
    const firstBatch = processingRunResponse({
      accepted_count: 500,
      applications_upserted: 80,
      candidate_count: 600,
      limit_reached: true,
      pending_candidate_count: 100,
      processed_count: 500,
    });
    const finalBatch = processingRunResponse({
      accepted_count: 100,
      applications_upserted: 20,
      candidate_count: 100,
      pending_candidate_count: 0,
      processed_count: 100,
    });
    const fetchMock = mockFetchResponses({
      "/config/providers/readiness": {
        classification_generation: { message: "Ready.", state: "ready" },
        ready_to_classify: true,
      },
      "/processing/run": [firstBatch, finalBatch],
      "/processing/status": [firstBatch, finalBatch],
      "/sync": { message_count: 12, state: "succeeded" },
    });

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    fireEvent.click(within(menu!).getByRole("button", { name: "Sync" }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_000);
    });

    expect(screen.getByRole("heading", { name: "Your inbox is up to date" })).toBeTruthy();
    expect(screen.getByText("Saved 600 classifications and updated 100 applications.")).toBeTruthy();
    expect(
      fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/processing/run"),
    ).toHaveLength(2);
  });

  it("redesign email reader closes without changing the selected inbox page", async () => {
    const emailRecord = (index: number) => ({
      body_retention_state: "metadata_only",
      classification_category: null,
      classification_is_job_related: null,
      filter_outcome: null,
      filter_reason: null,
      from_domain: `sender-${index}.example`,
      has_retained_body: false,
      ingested_at: "2026-07-12T12:00:00Z",
      provider: "gmail",
      public_id: `email-${index}`,
      sent_at: "2026-07-12T12:00:00Z",
      subject: `Subject ${index}`,
      subject_present: true,
      to_domains: ["recipient.example"],
    });
    mockFetchResponses({
      "/sync/emails?page=1&page_size=10": {
        items: Array.from({ length: 10 }, (_, index) => emailRecord(index + 1)),
        page: 1,
        page_size: 10,
        total_items: 11,
        total_pages: 2,
      },
      "/sync/emails?page=2&page_size=10": {
        items: [emailRecord(11)],
        page: 2,
        page_size: 10,
        total_items: 11,
        total_pages: 2,
      },
      "/sync/emails/email-11/content": {
        body_retention_state: "metadata_only",
        body_text: "Reader body",
        from_addr: "Sender 11 <jobs@sender-11.example>",
        from_domain: "sender-11.example",
        ingested_at: "2026-07-12T12:05:00Z",
        labels: ["INBOX"],
        provider: "gmail",
        public_id: "email-11",
        sent_at: "2026-07-12T12:00:00Z",
        subject: "Subject 11",
        to_addr: "me@recipient.example",
      },
    });

    renderAtPath("/");
    fireEvent.click(await screen.findByRole("button", { name: "2" }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "2" }).getAttribute("aria-current"),
      ).toBe("page");
    });
    const emailRow = (await screen.findByText("Subject 11")).closest("button");
    expect(emailRow).toBeTruthy();
    fireEvent.click(emailRow!);
    expect(await screen.findByText("Reader body")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close email" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(
      screen.getByRole("button", { name: "2" }).getAttribute("aria-current"),
    ).toBe("page");
  });

  it("redesign sync includes the selected custom end date", async () => {
    const fetchMock = mockFetchResponses({
      "/sync": { state: "succeeded" },
    });

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    fireEvent.click(
      screen.getByRole("button", { name: /A specific date range/ }),
    );
    fireEvent.change(screen.getByLabelText("Sync from date"), {
      target: { value: "2026-06-01" },
    });
    fireEvent.change(screen.getByLabelText("Sync to date"), {
      target: { value: "2026-07-10" },
    });
    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    fireEvent.click(within(menu!).getByRole("button", { name: "Sync" }));

    await waitFor(() => {
      const syncCall = fetchMock.mock.calls.find(
        ([input]) => requestPath(input) === "/sync",
      );
      const [, init] = syncCall as unknown as [RequestInfo | URL, RequestInit?];
      if (typeof init?.body !== "string") {
        throw new Error("Expected the sync request body to be JSON text.");
      }
      expect(JSON.parse(init.body)).toEqual({
        before_date: "2026-07-11",
        since_date: "2026-06-01",
      });
    });

    await waitFor(() => {
      const scopedRequest = fetchMock.mock.calls
        .map(([input]) => requestPath(input))
        .filter((path) => path.startsWith("/sync/emails"))
        .find((path) => {
          const params = new URL(path, "http://localhost").searchParams;
          return params.has("sent_after") && params.has("sent_before");
        });
      expect(scopedRequest).toBeTruthy();
      const params = new URL(scopedRequest!, "http://localhost").searchParams;
      expect(params.get("sent_after")).toBe("2026-06-01T00:00:00.000Z");
      expect(params.get("sent_before")).toBe("2026-07-11T00:00:00.000Z");
    });
  });

  it("redesign sync rejects a reversed custom date range", () => {
    const fetchMock = mockFetchResponses({});

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    fireEvent.click(
      screen.getByRole("button", { name: /A specific date range/ }),
    );
    fireEvent.change(screen.getByLabelText("Sync from date"), {
      target: { value: "2026-07-10" },
    });
    fireEvent.change(screen.getByLabelText("Sync to date"), {
      target: { value: "2026-06-01" },
    });

    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    const submit = within(menu!).getByRole("button", { name: "Sync" });
    expect(submit).toHaveProperty("disabled", true);
    expect(within(menu!).getByText("Choose a valid date range")).toBeTruthy();
    fireEvent.click(submit);
    expect(
      fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/sync"),
    ).toHaveLength(0);
  });

  it("redesign sync rejects an equal custom date range", () => {
    const fetchMock = mockFetchResponses({});
    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    fireEvent.click(screen.getByRole("button", { name: /A specific date range/ }));
    fireEvent.change(screen.getByLabelText("Sync from date"), { target: { value: "2026-07-10" } });
    fireEvent.change(screen.getByLabelText("Sync to date"), { target: { value: "2026-07-10" } });

    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    expect(within(menu!).getByRole("button", { name: "Sync" })).toHaveProperty("disabled", true);
    expect(fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/sync")).toHaveLength(0);
  });

  it("redesign sync closes only after running transitions to succeeded", async () => {
    const fetchMock = mockFetchResponses({
      "/sync": { state: "running" },
      "/sync/status": { state: "succeeded" },
    });

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    fireEvent.click(within(menu!).getByRole("button", { name: "Sync" }));

    await waitFor(() => {
      expect(screen.queryByText("What should I check?")).toBeNull();
    });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => requestPath(input) === "/sync/status",
      ),
    ).toHaveLength(1);
  });

  it("redesign sync shows the final last_error when running transitions to failed", async () => {
    mockFetchResponses({
      "/sync": { state: "running" },
      "/sync/status": {
        last_error: "Gmail rejected the final sync page.",
        state: "failed",
      },
    });

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    fireEvent.click(within(menu!).getByRole("button", { name: "Sync" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Gmail rejected the final sync page.",
    );
    expect(screen.getByText("What should I check?")).toBeTruthy();
  });

  it("redesign sync shows an honest error when the start response is idle", async () => {
    mockFetchResponses({
      "/sync": { state: "idle" },
    });

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    fireEvent.click(within(menu!).getByRole("button", { name: "Sync" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Sync did not start. Try again.",
    );
    expect(screen.getByText("What should I check?")).toBeTruthy();
  });

  it("redesign sync reports a still-running timeout after polling exhaustion", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = requestPath(input);
      const body =
        path === "/sync" || path === "/sync/status"
          ? { state: "running" }
          : null;
      if (!body) {
        return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
      }
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    fireEvent.click(within(menu!).getByRole("button", { name: "Sync" }));

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(
      screen.getByText("Sync is still running. Check again in a moment.")
        .textContent,
    ).toContain("Sync is still running. Check again in a moment.");
    expect(screen.getByText("What should I check?")).toBeTruthy();
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => requestPath(input) === "/sync/status",
      ),
    ).toHaveLength(600);
  });

  it("redesign sync disables duplicate controls while the start request is pending", () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/sync") {
        return new Promise<Response>(() => undefined);
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/");
    const menuButton = screen.getByRole("button", { name: "Sync ▾" });
    fireEvent.click(menuButton);
    const menu = screen.getByText("What should I check?").parentElement;
    expect(menu).toBeTruthy();
    const submit = within(menu!).getByRole("button", { name: "Sync" });
    fireEvent.click(submit);
    fireEvent.click(submit);

    expect(menuButton).toHaveProperty("disabled", true);
    expect(submit).toHaveProperty("disabled", true);
    expect(
      fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/sync"),
    ).toHaveLength(1);
  });

  it.each([401, 409, 429, 502, 503] as const)(
    "redesign sync renders typed %i failures",
    async (status) => {
      const message = `Typed sync failure ${status}.`;
      mockFetchResponses({
        "/sync": {
          body: apiErrorResponse(syncFailureCodeByStatus[status], message),
          status,
        },
      });

      renderAtPath("/");
      fireEvent.click(screen.getByRole("button", { name: "Sync ▾" }));
      const menu = screen.getByText("What should I check?").parentElement;
      expect(menu).toBeTruthy();
      fireEvent.click(within(menu!).getByRole("button", { name: "Sync" }));

      expect((await screen.findByRole("alert")).textContent).toContain(message);
    },
  );

  it("renders the exact five authoritative funnel stages from metrics funnel", async () => {
    mockFetchResponses({
      "/metrics/summary": metricsSummaryResponse({
        offers_received: 91,
        total_applications: 999,
      }),
      "/metrics/rates": metricsRatesResponse({
        application_to_interview_rate: {
          denominator: 999,
          numerator: 88,
          rate: 0.088,
        },
        overall_response_rate: { denominator: 999, numerator: 77, rate: 0.077 },
      }),
      "/metrics/funnel": metricsFunnelResponse({
        stages: [
          { count: 50, stage: "applied" },
          { count: 31, stage: "screen" },
          { count: 17, stage: "interview" },
          { count: 6, stage: "final" },
          { count: 2, stage: "offer" },
        ],
      }),
    });

    renderAtPath("/");

    const heading = await screen.findByRole("heading", {
      name: "Where applications stand",
    });
    const funnel = heading.parentElement?.parentElement;
    expect(funnel).toBeTruthy();
    for (const [label, count] of [
      ["Applied", "50"],
      ["Screen", "31"],
      ["Interview", "17"],
      ["Final", "6"],
      ["Offer", "2"],
    ]) {
      const stage = within(funnel!).getByRole("button", {
        name: new RegExp(`^${label}\\s+${count}$`),
      });
      expect(stage).toBeTruthy();
    }
  });

  it("distinguishes funnel loading, successful empty, and typed failure", async () => {
    let resolveFunnel: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/metrics/funnel") {
        return new Promise<Response>((resolve) => {
          resolveFunnel = resolve;
        });
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderAtPath("/");
    expect(screen.getByText("Loading funnel…")).toBeTruthy();

    resolveFunnel(
      new Response(JSON.stringify(metricsFunnelResponse()), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );
    expect(await screen.findByText("No funnel activity yet.")).toBeTruthy();

    cleanup();
    mockFetchResponses({
      "/metrics/funnel": {
        body: apiErrorResponse("validation_error", "Funnel is unavailable."),
        status: 422,
      },
    });
    renderAtPath("/");
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Funnel is unavailable.",
    );
  });

  it("restores application status filters on reload and browser navigation", async () => {
    mockFetchResponses({
      "/applications?status=offer": [],
      "/applications?status=interview": [],
    });
    renderAtPath("/applications?status=offer&sort=recent");
    expect(
      await screen.findByRole("button", { name: /^Offer 0$/ }),
    ).toHaveProperty("style.background", "rgb(30, 81, 54)");

    fireEvent.click(screen.getByRole("button", { name: /^Interview 0$/ }));
    expect(window.location.search).toBe("?sort=recent&status=interview");

    window.history.pushState({}, "", "/applications?sort=recent&status=offer");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Offer 0$/ })).toHaveProperty(
        "style.background",
        "rgb(30, 81, 54)",
      );
    });
  });

  it("requests canonical composite statuses, dedupes IDs, and keeps one population across views", async () => {
    const shared = applicationRecord({
      company: "Shared Co",
      current_status: "assessment",
      id: "shared",
    });
    const review = applicationRecord({
      company: "Review Co",
      current_status: "in_review",
      id: "review",
    });
    const fetchMock = mockFetchResponses({
      "/applications?status=in_review": { body: [review, shared], status: 200 },
      "/applications?status=assessment": { body: [shared], status: 200 },
      "/applications/shared/events": { body: [], status: 200 },
      "/applications/review/events": {
        body: apiErrorResponse("service_unavailable", "Timeline unavailable."),
        status: 503,
      },
    });

    renderAtPath("/applications?status=screening");
    expect(
      await screen.findByText("2 of 2 applications", { exact: false }),
    ).toBeTruthy();
    expect(screen.getAllByText("Shared Co")).toHaveLength(1);
    expect(screen.getAllByText("Review Co")).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications?status=in_review",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications?status=assessment",
      expect.objectContaining({ method: "GET" }),
    );
    expect(
      fetchMock.mock.calls.some(([input]) =>
        requestPath(input).includes("/events"),
      ),
    ).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Board" }));
    expect(screen.getAllByText("Shared Co")).toHaveLength(1);
    expect(screen.getAllByText("Review Co")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Timeline" }));
    expect(await screen.findByText("No timeline events")).toBeTruthy();
    expect(await screen.findByText("Timeline unavailable.")).toBeTruthy();
    expect(screen.getAllByText("Shared Co")).toHaveLength(1);
    expect(screen.getAllByText("Review Co")).toHaveLength(1);
  });

  it.each([
    ["applied", ["applied"]],
    ["interview", ["interview"]],
    ["offer", ["offer"]],
    ["closed", ["rejected", "ghosted", "withdrawn"]],
  ] as const)(
    "maps the %s chip to canonical backend status requests",
    async (filter, statuses) => {
      const responses = Object.fromEntries(
        statuses.map((status) => [`/applications?status=${status}`, []]),
      );
      const fetchMock = mockFetchResponses(responses);
      renderAtPath(`/applications?status=${filter}`);

      await waitFor(() => {
        for (const status of statuses) {
          expect(fetchMock).toHaveBeenCalledWith(
            `/applications?status=${status}`,
            expect.objectContaining({ method: "GET" }),
          );
        }
      });
    },
  );

  it("redesign settings stays neutral and blocks config writes while the initial GET is pending", () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/config/providers" && init?.method === "GET") {
        return new Promise<Response>(() => undefined);
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/settings");

    const local = screen.getByRole("button", { name: /On this computer/ });
    const cloud = screen.getByRole("button", { name: /Cloud AI/ });
    const interval =
      screen.getByLabelText<HTMLSelectElement>("Auto-sync interval");
    const classification = screen.getByRole("switch", {
      name: "Toggle pre-filtering",
    });
    expect(screen.getByText("Loading provider settings...")).toBeTruthy();
    expect(screen.queryByText(/Currently using:/)).toBeNull();
    expect(local).toHaveProperty("disabled", true);
    expect(cloud).toHaveProperty("disabled", true);
    expect(interval).toHaveProperty("disabled", true);
    expect(interval.value).toBe("");
    expect(classification).toHaveProperty("disabled", true);

    fireEvent.click(local);
    fireEvent.click(cloud);
    fireEvent.change(interval, { target: { value: "hour" } });
    fireEvent.click(classification);

    expect(
      fetchMock.mock.calls.filter(
        ([input, init]) =>
          requestPath(input) === "/config/providers" && init?.method === "PUT",
      ),
    ).toHaveLength(0);
  });

  it("redesign settings shows a typed initial config failure and keeps controls disabled", async () => {
    mockFetchResponses({
      "/config/providers": {
        body: apiErrorResponse(
          "service_unavailable",
          "Provider settings are temporarily unavailable.",
        ),
        status: 503,
      },
    });

    renderAtPath("/settings");

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Provider settings are temporarily unavailable.",
    );
    expect(screen.queryByText(/Currently using:/)).toBeNull();
    expect(
      screen.getByRole("button", { name: /On this computer/ }),
    ).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: /Cloud AI/ })).toHaveProperty(
      "disabled",
      true,
    );
    expect(screen.getByLabelText("Auto-sync interval")).toHaveProperty(
      "disabled",
      true,
    );
    expect(
      screen.getByRole("switch", { name: "Toggle pre-filtering" }),
    ).toHaveProperty("disabled", true);
    expect(
      screen.getByRole("button", { name: "Retry provider settings" }),
    ).toBeTruthy();
  });

  it("redesign settings retries initial config loading and enables confirmed values", async () => {
    const fetchMock = mockFetchResponses({
      "/config/providers": [
        {
          body: apiErrorResponse(
            "service_unavailable",
            "Provider settings are temporarily unavailable.",
          ),
          status: 503,
        },
        providerConfigResponse("ollama"),
      ],
    });

    renderAtPath("/settings");
    fireEvent.click(
      await screen.findByRole("button", { name: "Retry provider settings" }),
    );

    expect(
      await screen.findByText(/Currently using: a local model/),
    ).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      screen.getByRole("button", { name: /On this computer/ }),
    ).toHaveProperty("disabled", false);
    expect(screen.getByRole("button", { name: /Cloud AI/ })).toHaveProperty(
      "disabled",
      false,
    );
    expect(
      screen.getByLabelText<HTMLSelectElement>("Auto-sync interval").value,
    ).toBe("30min");
    expect(
      screen.getByRole("switch", { name: "Toggle pre-filtering" }),
    ).toHaveProperty("disabled", false);
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => requestPath(input) === "/config/providers",
      ),
    ).toHaveLength(2);
  });

  it("redesign settings recovers from an initial transport failure through a serialized retry", async () => {
    let configAttempts = 0;
    let resolveRetry: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/config/providers" && init?.method === "GET") {
        configAttempts += 1;
        if (configAttempts === 1) {
          return Promise.reject(new Error("private transport detail"));
        }
        return new Promise<Response>((resolve) => {
          resolveRetry = resolve;
        });
      }
      if (path === "/auth/connections") {
        return Promise.resolve(new Response(JSON.stringify([]), { headers: { "Content-Type": "application/json" }, status: 200 }));
      }
      if (path === "/sync/stats") {
        return Promise.resolve(new Response(JSON.stringify({ last_run_at: null, total_raw_emails: 0 }), { headers: { "Content-Type": "application/json" }, status: 200 }));
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/settings");

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Provider settings could not be loaded. Check the local backend.",
    );
    expect(screen.queryByText("private transport detail")).toBeNull();
    expect(screen.queryByText(/Currently using:/)).toBeNull();
    expect(
      screen.getByRole("button", { name: /On this computer/ }),
    ).toHaveProperty("disabled", true);
    expect(screen.getByLabelText("Auto-sync interval")).toHaveProperty(
      "disabled",
      true,
    );
    expect(
      screen.getByRole("switch", { name: "Toggle pre-filtering" }),
    ).toHaveProperty("disabled", true);

    const retry = screen.getByRole("button", {
      name: "Retry provider settings",
    });
    fireEvent.click(retry);
    fireEvent.click(retry);

    expect(configAttempts).toBe(2);
    resolveRetry(
      new Response(JSON.stringify(providerConfigResponse("ollama")), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );

    expect(
      await screen.findByText(/Currently using: a local model/),
    ).toBeTruthy();
    expect(configAttempts).toBe(2);
  });

  it.each([
    [900, "Every 15 minutes"],
    [5400, "Every 90 minutes"],
  ])(
    "redesign settings labels the confirmed %i-second interval without submitting it",
    async (intervalSeconds, expectedLabel) => {
      const fetchMock = vi.fn(
        (input: RequestInfo | URL, init?: RequestInit) => {
          const path = requestPath(input);
          if (path === "/config/providers" && init?.method === "GET") {
            return Promise.resolve(
              new Response(
                JSON.stringify(
                  confirmedProviderConfig({
                    classificationMode: "local",
                    intervalSeconds,
                    llmProvider: "ollama",
                    recommendedMode: "local",
                  }),
                ),
                {
                  headers: { "Content-Type": "application/json" },
                  status: 200,
                },
              ),
            );
          }
          return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
        },
      );
      vi.stubGlobal("fetch", fetchMock);

      renderAtPath("/settings");

      await screen.findByText(/Currently using: a local model/);
      const interval =
        screen.getByLabelText<HTMLSelectElement>("Auto-sync interval");
      expect(interval.selectedOptions[0]?.textContent).toBe(expectedLabel);
      expect(
        fetchMock.mock.calls.filter(
          ([input, init]) =>
            requestPath(input) === "/config/providers" &&
            init?.method === "PUT",
        ),
      ).toHaveLength(0);
    },
  );

  it("redesign settings restores Ollama pre-filtering to the confirmed local recommendation", async () => {
    const requests: Record<string, unknown>[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/config/providers" && init?.method === "GET") {
        return Promise.resolve(
          new Response(
            JSON.stringify(
              confirmedProviderConfig({
                classificationMode: "llm",
                llmProvider: "ollama",
                recommendedMode: "local",
              }),
            ),
            { headers: { "Content-Type": "application/json" }, status: 200 },
          ),
        );
      }
      if (path === "/config/providers" && init?.method === "PUT") {
        if (typeof init.body !== "string") {
          throw new Error(
            "Expected provider config request body to be JSON text.",
          );
        }
        const request = JSON.parse(init.body) as Record<string, unknown>;
        requests.push(request);
        return Promise.resolve(
          new Response(
            JSON.stringify(
              confirmedProviderConfig({
                classificationMode: "local",
                llmProvider: "ollama",
                recommendedMode: "local",
              }),
            ),
            { headers: { "Content-Type": "application/json" }, status: 200 },
          ),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/settings");
    const toggle = await screen.findByRole("switch", {
      name: "Toggle pre-filtering",
    });
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(toggle);

    await waitFor(() =>
      expect(requests).toEqual([{ classification_mode: "local" }]),
    );
    expect(toggle.getAttribute("aria-checked")).toBe("true");
  });

  it("redesign settings restores Azure pre-filtering to the last confirmed hybrid mode", async () => {
    const requests: Record<string, unknown>[] = [];
    const responses = [
      confirmedProviderConfig({
        classificationMode: "llm",
        llmProvider: "azure_openai",
        recommendedMode: "hybrid",
      }),
      confirmedProviderConfig({
        classificationMode: "hybrid",
        llmProvider: "azure_openai",
        recommendedMode: "hybrid",
      }),
    ];
    const initial = confirmedProviderConfig({
      classificationMode: "hybrid",
      llmProvider: "azure_openai",
      recommendedMode: "hybrid",
    });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/config/providers" && init?.method === "GET") {
        return Promise.resolve(
          new Response(JSON.stringify(initial), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }
      if (path === "/config/providers" && init?.method === "PUT") {
        if (typeof init.body !== "string") {
          throw new Error(
            "Expected provider config request body to be JSON text.",
          );
        }
        requests.push(JSON.parse(init.body) as Record<string, unknown>);
        const response = responses.shift();
        return Promise.resolve(
          new Response(JSON.stringify(response), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/settings");
    const toggle = await screen.findByRole("switch", {
      name: "Toggle pre-filtering",
    });
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(toggle.getAttribute("aria-checked")).toBe("false"),
    );
    fireEvent.click(toggle);

    await waitFor(() =>
      expect(requests).toEqual([
        { classification_mode: "llm" },
        { classification_mode: "hybrid" },
      ]),
    );
    expect(toggle.getAttribute("aria-checked")).toBe("true");
  });

  it("redesign settings confirms a provider only after success and checks unavailable health", async () => {
    let resolveUpdate: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/config/providers" && init?.method === "GET") {
        return Promise.resolve(
          new Response(JSON.stringify(providerConfigResponse("ollama")), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }
      if (path === "/config/providers" && init?.method === "PUT") {
        return new Promise<Response>((resolve) => {
          resolveUpdate = resolve;
        });
      }
      if (path === "/config/providers/llm/health") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              checks: [
                {
                  detail: "The configured deployment could not be reached.",
                  kind: "chat",
                  model: "chat",
                  status: "unavailable",
                },
              ],
              provider_name: "Azure OpenAI",
              status: "unavailable",
            }),
            { headers: { "Content-Type": "application/json" }, status: 200 },
          ),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/settings");
    await screen.findByText(/Currently using: a local model/);
    const cloud = screen.getByRole("button", { name: /Cloud AI/ });
    const local = screen.getByRole("button", { name: /On this computer/ });
    fireEvent.click(cloud);
    fireEvent.click(cloud);

    expect(screen.getByText(/Currently using: a local model/)).toBeTruthy();
    expect(cloud).toHaveProperty("disabled", true);
    expect(local).toHaveProperty("disabled", true);
    expect(
      fetchMock.mock.calls.filter(
        ([input, init]) =>
          requestPath(input) === "/config/providers" && init?.method === "PUT",
      ),
    ).toHaveLength(1);

    resolveUpdate(
      new Response(JSON.stringify(providerConfigResponse("azure_openai")), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );

    expect(
      await screen.findByText(/Currently using: your own cloud AI account/),
    ).toBeTruthy();
    expect(await screen.findByText("Azure OpenAI unavailable")).toBeTruthy();
    expect(screen.queryByText(/operational/i)).toBeNull();
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => requestPath(input) === "/config/providers/llm/health",
      ),
    ).toHaveLength(1);
  });

  it("redesign settings shows typed provider-health transport failure", async () => {
    const fetchMock = mockFetchResponses({
      "/config/providers": [providerConfigResponse("ollama"), providerConfigResponse("azure_openai")],
      "/config/providers/llm/health": {
        body: apiErrorResponse("llm_provider_unavailable", "The selected provider cannot be reached."),
        status: 503,
      },
    });
    renderAtPath("/settings");
    await screen.findByText(/Currently using: a local model/);
    fireEvent.click(screen.getByRole("button", { name: /Cloud AI/ }));

    expect(await screen.findByText("The selected provider cannot be reached.")).toBeTruthy();
    expect(screen.queryByText(/operational/i)).toBeNull();
    expect(fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/config/providers/llm/health")).toHaveLength(1);
  });

  it("redesign settings serializes disconnect and shows typed failure", async () => {
    let resolveDisconnect: (response: Response) => void = () => undefined;
    const baseFetch = mockFetchResponses({
      "/auth/connections": {
        body: [{
          account: { account_id: "first", provider: "gmail" },
          connected_at: "2026-07-10T12:00:00Z",
          credential_ref: { kind: "oauth_token", name: "first", provider: "gmail" },
          display_email: { address: "first@example.com" },
          granted_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
          reauth_required: false,
        }],
        status: 200,
      },
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      requestPath(input) === "/auth/connections/gmail/first"
        ? new Promise<Response>((resolve) => { resolveDisconnect = resolve; })
        : baseFetch(input));
    vi.stubGlobal("fetch", fetchMock);
    renderAtPath("/settings");
    const disconnect = await screen.findByRole("button", { name: "Disconnect" });
    fireEvent.click(disconnect);
    fireEvent.click(disconnect);
    expect(disconnect).toHaveProperty("disabled", true);
    expect(fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/auth/connections/gmail/first")).toHaveLength(1);
    resolveDisconnect(new Response(JSON.stringify(apiErrorResponse("service_unavailable", "Stored credentials could not be removed.")), { headers: { "Content-Type": "application/json" }, status: 503 }));
    const feedback = await screen.findByText("Stored credentials could not be removed.");
    const connectedSection = screen.getByRole("heading", { name: "Connected inboxes" }).parentElement;
    const wipeSection = screen.getByRole("heading", { name: "Delete everything" }).parentElement;
    expect(connectedSection?.contains(feedback)).toBe(true);
    expect(wipeSection?.contains(feedback)).toBe(false);
  });

  it.each([
    ["typed", new Response(JSON.stringify(apiErrorResponse("service_unavailable", "Connections are unavailable.")), { headers: { "Content-Type": "application/json" }, status: 503 })],
    ["transport", new TypeError("backend unavailable")],
  ])("redesign shell distinguishes %s connection failure from empty and recovers", async (_kind, failure) => {
    let attempts = 0;
    const baseFetch = mockFetchResponses({
      "/sync/stats": { last_run_at: "2026-07-10T12:00:00Z", total_raw_emails: 42 },
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (requestPath(input) !== "/auth/connections") return baseFetch(input);
      attempts += 1;
      if (attempts === 1) {
        return failure instanceof Response ? Promise.resolve(failure) : Promise.reject(failure);
      }
      return Promise.resolve(new Response(JSON.stringify([]), { headers: { "Content-Type": "application/json" }, status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/settings");

    const fallback = _kind === "typed" ? "Connections are unavailable." : "Inbox connections could not be loaded. Check the local backend.";
    expect(await screen.findAllByText(fallback)).not.toHaveLength(0);
    expect(screen.queryByText("No inbox connected")).toBeNull();
    expect(screen.queryByText("No connected inboxes yet.")).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Retry inbox connections" })[0]);
    expect(await screen.findByText("No inbox connected")).toBeTruthy();
    expect(screen.getByText("No connected inboxes yet.")).toBeTruthy();
    expect(attempts).toBe(2);
  });

  it.each([
    ["typed", new Response(JSON.stringify(apiErrorResponse("service_unavailable", "Sync statistics are unavailable.")), { headers: { "Content-Type": "application/json" }, status: 503 })],
    ["transport", new TypeError("backend unavailable")],
  ])("redesign shell distinguishes %s sync-stat failure from zero and recovers", async (_kind, failure) => {
    let attempts = 0;
    const baseFetch = mockFetchResponses({
      "/auth/connections": {
        body: [{
          account: { account_id: "first", provider: "gmail" },
          connected_at: "2026-07-10T12:00:00Z",
          credential_ref: { kind: "oauth_token", name: "first", provider: "gmail" },
          display_email: { address: "first@example.com" },
          granted_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
          reauth_required: false,
        }],
        status: 200,
      },
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (requestPath(input) !== "/sync/stats") return baseFetch(input);
      attempts += 1;
      if (attempts === 1) {
        return failure instanceof Response ? Promise.resolve(failure) : Promise.reject(failure);
      }
      return Promise.resolve(new Response(JSON.stringify({ last_run_at: null, total_raw_emails: 0 }), { headers: { "Content-Type": "application/json" }, status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/");

    const fallback = _kind === "typed" ? "Sync statistics are unavailable." : "Sync statistics could not be loaded. Check the local backend.";
    expect(await screen.findByText(fallback)).toBeTruthy();
    expect(screen.queryByText(/not synced yet/)).toBeNull();
    expect(screen.queryByText(/0 emails read/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry sync statistics" }));
    expect(await screen.findByText(/not synced yet · 0 emails read/)).toBeTruthy();
    expect(attempts).toBe(2);
  });

  it("redesign settings renders disconnect success beside connected inboxes", async () => {
    const connection = {
      account: { account_id: "first", provider: "gmail" },
      connected_at: "2026-07-10T12:00:00Z",
      credential_ref: { kind: "oauth_token", name: "first", provider: "gmail" },
      display_email: { address: "first@example.com" },
      granted_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      reauth_required: false,
    };
    mockFetchResponses({
      "/auth/connections": { body: [connection], status: 200 },
      "/auth/connections/gmail/first": connection,
    });

    renderAtPath("/settings");
    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));

    const feedback = await screen.findByText("Inbox disconnected successfully.");
    const connectedSection = screen.getByRole("heading", { name: "Connected inboxes" }).parentElement;
    const wipeSection = screen.getByRole("heading", { name: "Delete everything" }).parentElement;
    expect(connectedSection?.contains(feedback)).toBe(true);
    expect(wipeSection?.contains(feedback)).toBe(false);
  });

  it("redesign settings serializes wipe and reports success", async () => {
    let resolveWipe: (response: Response) => void = () => undefined;
    const baseFetch = mockFetchResponses({});
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      requestPath(input) === "/local-data/wipe"
        ? new Promise<Response>((resolve) => { resolveWipe = resolve; })
        : baseFetch(input));
    vi.stubGlobal("fetch", fetchMock);
    renderAtPath("/settings");
    const wipe = await screen.findByRole("button", { name: "Delete all local data…" });
    fireEvent.click(wipe);
    const confirm = screen.getByRole("button", { name: /Click again to confirm/ });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(confirm).toHaveProperty("disabled", true);
    expect(fetchMock.mock.calls.filter(([input]) => requestPath(input) === "/local-data/wipe")).toHaveLength(1);
    resolveWipe(new Response(JSON.stringify({ status: "wiped" }), { headers: { "Content-Type": "application/json" }, status: 200 }));
    expect(await screen.findByText("Local data deleted successfully.")).toBeTruthy();
  });

  it("redesign settings preserves confirmed provider and interval after typed failures", async () => {
    const fetchMock = mockFetchResponses({
      "/config/providers": [
        providerConfigResponse("ollama"),
        {
          body: apiErrorResponse("service_unavailable", "Provider unchanged."),
          status: 503,
        },
        {
          body: apiErrorResponse("service_unavailable", "Schedule unchanged."),
          status: 503,
        },
      ],
    });

    renderAtPath("/settings");
    await screen.findByText(/Currently using: a local model/);
    fireEvent.click(screen.getByRole("button", { name: /Cloud AI/ }));

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Provider unchanged.",
    );
    expect(screen.getByText(/Currently using: a local model/)).toBeTruthy();

    const interval =
      screen.getByLabelText<HTMLSelectElement>("Auto-sync interval");
    fireEvent.change(interval, { target: { value: "hour" } });

    await waitFor(() => expect(interval.value).toBe("30min"));
    expect(screen.getByRole("alert")).toHaveProperty(
      "textContent",
      "Schedule unchanged.",
    );
    expect(
      fetchMock.mock.calls.some(
        ([input]) => requestPath(input) === "/config/providers/llm/health",
      ),
    ).toBe(false);
  });

  it("redesign settings confirms the interval from the typed response and disables duplicates", async () => {
    let resolveUpdate: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === "/config/providers" && init?.method === "GET") {
        return Promise.resolve(
          new Response(JSON.stringify(providerConfigResponse("ollama")), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }
      if (path === "/config/providers" && init?.method === "PUT") {
        return new Promise<Response>((resolve) => {
          resolveUpdate = resolve;
        });
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/settings");
    const interval =
      await screen.findByLabelText<HTMLSelectElement>("Auto-sync interval");
    expect(interval.value).toBe("30min");
    fireEvent.change(interval, { target: { value: "hour" } });
    fireEvent.change(interval, { target: { value: "manual" } });

    expect(interval.value).toBe("30min");
    expect(interval).toHaveProperty("disabled", true);
    expect(
      fetchMock.mock.calls.filter(
        ([input, init]) =>
          requestPath(input) === "/config/providers" && init?.method === "PUT",
      ),
    ).toHaveLength(1);

    resolveUpdate(
      new Response(
        JSON.stringify(
          providerConfigResponse("ollama", {
            settings: {
              ...(providerConfigResponse("ollama").settings as Record<
                string,
                unknown
              >),
              sync_interval_seconds: 3600,
            },
          }),
        ),
        { headers: { "Content-Type": "application/json" }, status: 200 },
      ),
    );

    await waitFor(() => expect(interval.value).toBe("hour"));
  });

  it("redesign settings describes accounts as stored when no active account is identified", async () => {
    mockFetchResponses({
      "/auth/connections": {
        body: [
          {
            account: { account_id: "first", provider: "gmail" },
            connected_at: "2026-07-10T12:00:00Z",
            credential_ref: {
              kind: "oauth_token",
              name: "first",
              provider: "gmail",
            },
            display_email: { address: "first@example.com" },
            granted_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
            reauth_required: false,
          },
          {
            account: { account_id: "second", provider: "gmail" },
            connected_at: "2026-07-09T12:00:00Z",
            credential_ref: {
              kind: "oauth_token",
              name: "second",
              provider: "gmail",
            },
            display_email: { address: "second@example.com" },
            granted_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
            reauth_required: false,
          },
        ],
        status: 200,
      },
    });

    renderAtPath("/settings");

    const connectionsCard = screen.getByRole("heading", {
      name: "Connected inboxes",
    }).parentElement;
    expect(connectionsCard).toBeTruthy();
    expect(
      await within(connectionsCard!).findAllByText("Stored connection"),
    ).toHaveLength(2);
    expect(within(connectionsCard!).queryByText("Primary")).toBeNull();
    expect(within(connectionsCard!).queryByText("Connected")).toBeNull();
    expect(within(connectionsCard!).queryByText(/synced/)).toBeNull();
  });

  it("opens Phase 5 chat from the operational redesign", async () => {
    const fetchMock = mockFetchResponses({});
    renderAtPath("/");
    fireEvent.click(screen.getByRole("button", { name: "Ask AI" }));
    expect(await screen.findByText("Ask from your actual search history")).toBeTruthy();
    expect(screen.getAllByText("Ask your job search")).toHaveLength(2);
    expect(window.location.pathname).toBe("/chat");
    expect(screen.getByLabelText("Ask AI drawer")).toBeTruthy();

    expect(
      fetchMock.mock.calls.some(([input]) =>
        requestPath(input).startsWith("/chat/history"),
      ),
    ).toBe(true);
  });

  it("redesign developer derives truthful statuses from the feature registry", () => {
    renderAtPath("/dev");

    expect(screen.getByText("Gmail sync").closest("div")?.textContent).toContain(
      "Completed",
    );
    expect(
      screen.getByText("Email classification").closest("div")?.textContent,
    ).toContain("Completed");
    expect(
      screen.getByText("Applications & timeline").closest("div")?.textContent,
    ).toContain("Completed");
    expect(
      screen.getByText("Manual corrections").closest("div")?.textContent,
    ).toContain("Completed");
    expect(
      screen.getByText("Cached insights").closest("div")?.textContent,
    ).toContain("Completed");
    const chatRow = screen.getByText("Chat agent (RAG)").closest("div");
    expect(chatRow?.textContent).toContain("Phase 5");
    expect(chatRow?.textContent).toContain("Completed");
    expect(screen.queryByText("Live")).toBeNull();
  });
});
