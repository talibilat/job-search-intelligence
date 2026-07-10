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
  SetupStatusResponse,
} from "./api";

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

function setupStatusResponse(
  overrides: Partial<SetupStatusResponse> = {},
): MockObjectResponseBody {
  const response: SetupStatusResponse = {
    classification_mode: "hybrid",
    email_provider: "gmail",
    gmail_connected: true,
    llm_configured: false,
    llm_provider: "ollama",
    recommended_classification_mode: "local",
    setup_complete: true,
    ...overrides,
  };

  return response as unknown as MockObjectResponseBody;
}

function setupStatusFetchResponse(overrides: Partial<SetupStatusResponse> = {}) {
  return new Response(JSON.stringify(setupStatusResponse(overrides)), {
    headers: { "Content-Type": "application/json" },
    status: 200,
  });
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

      if (path === "/setup/status") {
        return Promise.resolve(setupStatusFetchResponse());
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
    expect(within(readiness).getByText("Estimated cost $0.42 USD")).toBeTruthy();
    expect(
      within(readiness).getByText("Model gpt-4.1-mini, prompt classification-v1"),
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
    expect(within(retainedCandidatesMetric!).getByText("Table: raw_emails")).toBeTruthy();
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
      within(estimateMetric!).getByText("Data source: GET /classification/estimate"),
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
    expect(within(rawEmailsStage!).getByText("Data source: GET /pipeline/status")).toBeTruthy();
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
    expect(within(filterStage!).getByText("Table: email_filter_decisions")).toBeTruthy();
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

    const retainedBodiesStage = (await screen.findByText("Retained bodies")).closest(
      "article",
    );
    expect(retainedBodiesStage).toBeTruthy();

    const infoButton = within(retainedBodiesStage!).getByRole("button", {
      name: "About Retained bodies",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      within(retainedBodiesStage!).getByText("Data source: GET /pipeline/status"),
    ).toBeTruthy();
    expect(within(retainedBodiesStage!).getByText("Table: raw_emails")).toBeTruthy();
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
    expect(within(applicationsStage!).getByText("Table: applications, application_events")).toBeTruthy();
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
      within(providerMessagesMetric!).getByText("Data source: GET /sync/status"),
    ).toBeTruthy();
    expect(within(providerMessagesMetric!).getByText("Table: raw_emails")).toBeTruthy();
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
    expect(within(storedRawEmailsMetric!).getByText("Table: raw_emails")).toBeTruthy();
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
    expect(screen.getByText("Data source: GET /sync/recent-emails")).toBeTruthy();
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
    expect(screen.getByText("Connect Gmail, then run sync to set mode")).toBeTruthy();
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

  it("does not expose the unfinished chat shell at the chat route", () => {
    window.history.pushState({}, "", "/chat");

    render(<App />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /your job search, from inbox to insight/i,
      }),
    ).toBeTruthy();
    expect(
      screen.queryByText(/chat agent work arrives in phase 5/i),
    ).toBeNull();
    expect(screen.queryByRole("textbox", { name: /message/i })).toBeNull();
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
    expect(screen.getByRole("region", { name: "Foundational counts" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Outcome rates" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Response timing" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Metrics overview" })).toBeNull();
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
    expect(screen.queryByText("Application statuses moved to Feature Status"))
      .toBeNull();

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
    expect(screen.getByText("Dashboard chart workspace")).toBeTruthy();
    expect(screen.queryByText(/summary metric cards/i)).toBeNull();
    expect(screen.queryByText(/Unimplemented metric values remain Pending/i)).toBeNull();
    expect(screen.getByText("Insights cached narrative view")).toBeTruthy();
    expect(screen.getByText("Chat unavailable marker")).toBeTruthy();
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
