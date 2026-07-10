import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";

const baseApplication = {
  company: "Acme Corp",
  created_at: "2026-07-01T09:00:00Z",
  currency: null,
  current_status: "interview",
  first_seen_at: "2026-07-01T09:00:00Z",
  id: "app-1",
  last_activity_at: "2026-07-03T10:00:00Z",
  location: "Remote",
  manual_lock: false,
  role_title: "Backend Engineer",
  salary_max: 150000,
  salary_min: 120000,
  seniority: "senior",
  source: "linkedin",
  sponsorship: "unknown",
  tech_stack: ["Python", "FastAPI"],
  updated_at: "2026-07-03T10:01:00Z",
  work_mode: "remote",
};

function mockApplicationResponses(options: {
  diagnosticsStatus?: number;
  summaryApplicationCount?: number;
  pipelineStatus?: unknown;
} = {}) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? `${input.pathname}${input.search}`
          : input.url;

    if (url.startsWith("/metrics/summary")) {
      return Promise.resolve(
        new Response(JSON.stringify({
          application_windows: [],
          average_time_to_first_response: {
            application_count: 2,
            average_hours: 36,
          },
          average_time_to_rejection: {
            application_count: 2,
            average_hours: 48,
          },
          distinct_company_count: 1,
          evaluated_at: "2026-07-10T00:00:00Z",
          ghost_threshold_days: 30,
          ghosted_applications: 2,
          interview_invitation_count: 1,
          offers_received: 1,
          personal_ghost_threshold: {
            threshold_days: 20,
            threshold_source: "response_percentile",
            response_sample_size: 2,
            silent_application_count: 3,
            silence_age_distribution: [
              { bucket: "0_7", min_days: 0, max_days: 7, application_count: 0 },
              { bucket: "8_14", min_days: 8, max_days: 14, application_count: 1 },
              { bucket: "15_30", min_days: 15, max_days: 30, application_count: 2 },
              { bucket: "31_60", min_days: 31, max_days: 60, application_count: 0 },
              { bucket: "61_plus", min_days: 61, max_days: null, application_count: 0 },
            ],
          },
          rejected_applications: 1,
          total_applications: options.summaryApplicationCount ?? 5,
        }), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    }

    if (url === "/pipeline/status" && options.pipelineStatus) {
      return Promise.resolve(
        new Response(JSON.stringify(options.pipelineStatus), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    }

    if (url === "/metrics/rates") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            overall_response_rate: {
              denominator: 5,
              numerator: 3,
              rate: 0.6,
            },
            rejection_rate: {
              denominator: 5,
              numerator: 1,
              rate: 0.2,
            },
            ghost_rate: {
              denominator: 5,
              numerator: 2,
              rate: 0.4,
            },
            application_to_interview_rate: {
              denominator: 5,
              numerator: 1,
              rate: 0.2,
            },
            interview_to_offer_rate: {
              denominator: 1,
              numerator: 1,
              rate: 1,
            },
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/rates?role=platform&status=rejected") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            overall_response_rate: {
              denominator: 1,
              numerator: 1,
              rate: 1,
            },
            rejection_rate: {
              denominator: 1,
              numerator: 1,
              rate: 1,
            },
            ghost_rate: {
              denominator: 1,
              numerator: 0,
              rate: 0,
            },
            application_to_interview_rate: {
              denominator: 1,
              numerator: 0,
              rate: 0,
            },
            interview_to_offer_rate: {
              denominator: 0,
              numerator: 0,
              rate: null,
            },
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/funnel") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            stages: [
              { count: 5, stage: "applied" },
              { count: 3, stage: "screen" },
              { count: 2, stage: "interview" },
              { count: 0, stage: "final" },
              { count: 1, stage: "offer" },
            ],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/funnel?role=platform&status=rejected") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            stages: [
              { count: 1, stage: "applied" },
              { count: 1, stage: "screen" },
              { count: 0, stage: "interview" },
              { count: 0, stage: "final" },
              { count: 0, stage: "offer" },
            ],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/breakdown?dimension=source") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            dimension: "source",
            rows: [
              {
                application_count: 3,
                dimension: "source",
                interview_count: 2,
                interview_rate: 2 / 3,
                offer_count: 1,
                offer_rate: 1 / 3,
                response_count: 2,
                response_rate: 2 / 3,
                value: "linkedin",
              },
              {
                application_count: 2,
                dimension: "source",
                interview_count: 0,
                interview_rate: 0,
                offer_count: 0,
                offer_rate: 0,
                response_count: 1,
                response_rate: 0.5,
                value: "company_site",
              },
            ],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/breakdown?dimension=tech") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            dimension: "tech",
            rows: [
              {
                application_count: 4,
                dimension: "tech",
                interview_count: 2,
                interview_rate: 0.5,
                offer_count: 1,
                offer_rate: 0.25,
                response_count: 3,
                response_rate: 0.75,
                value: "python",
              },
            ],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/breakdown?dimension=role") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            dimension: "role",
            rows: [
              {
                application_count: 4,
                dimension: "role",
                interview_count: 2,
                interview_rate: 0.5,
                offer_count: 1,
                offer_rate: 0.25,
                response_count: 3,
                response_rate: 0.75,
                value: "backend engineer",
              },
              {
                application_count: 3,
                dimension: "role",
                interview_count: 0,
                interview_rate: 0,
                offer_count: 0,
                offer_rate: 0,
                response_count: 1,
                response_rate: 1 / 3,
                value: "frontend engineer",
              },
            ],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/breakdown?dimension=company_type") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            dimension: "company_type",
            rows: [
              {
                application_count: 3,
                dimension: "company_type",
                interview_count: 1,
                interview_rate: 0.3333333333333333,
                offer_count: 0,
                offer_rate: 0,
                response_count: 2,
                response_rate: 0.6666666666666666,
                value: "startup",
              },
              {
                application_count: 2,
                dimension: "company_type",
                interview_count: 0,
                interview_rate: 0,
                offer_count: 0,
                offer_rate: 0,
                response_count: 0,
                response_rate: 0,
                value: "enterprise",
              },
            ],
          }),
          { headers: { "Content-Type": "application/json" }, status: 200 },
        ),
      );
    }

    if (url === "/metrics/timeseries") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            points: [
              { application_count: 2, period_start: "2026-07-01" },
              { application_count: 5, period_start: "2026-07-08" },
            ],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/timeseries?status=rejected") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            points: [{ application_count: 1, period_start: "2026-07-08" }],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/response-rate-trend") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            points: [
              {
                application_count: 2,
                period_start: "2026-07-01",
                response_count: 1,
                response_rate: 0.5,
              },
              {
                application_count: 5,
                period_start: "2026-07-08",
                response_count: 4,
                response_rate: 0.8,
              },
            ],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/breakdown?dimension=salary") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            dimension: "salary",
            rows: [
              {
                application_count: 2,
                dimension: "salary",
                interview_count: 1,
                interview_rate: 0.5,
                offer_count: 0,
                offer_rate: 0,
                response_count: 2,
                response_rate: 1,
                value: "100k_149k",
              },
            ],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/diagnostics") {
      if (options.diagnosticsStatus !== undefined && options.diagnosticsStatus !== 200) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error: {
                code: "diagnostics_unavailable",
                details: [],
                message: "Diagnostics are unavailable.",
              },
            }),
            {
              headers: { "Content-Type": "application/json" },
              status: options.diagnosticsStatus,
            },
          ),
        );
      }

      return Promise.resolve(
        new Response(
          JSON.stringify({
            baseline_response_count: 3,
            baseline_response_rate: 0.6,
            baseline_success_count: 2,
            baseline_success_rate: 0.4,
            best_roi_source: {
              application_count: 3,
              dimension: "source",
              interview_count: 1,
              interview_rate: 1 / 3,
              offer_count: 0,
              offer_rate: 0,
              response_count: 1,
              response_rate: 1 / 3,
              response_rate_lift: (1 / 3) - 0.6,
              success_count: 0,
              success_rate: 0,
              success_rate_lift: -0.4,
              negative_count: 2,
              negative_rate: 2 / 3,
              negative_rate_lift: (2 / 3) - 0.4,
              value: "linkedin",
            },
            sponsorship_response_impact: {
              application_count: 3,
              dimension: "sponsorship",
              interview_count: 0,
              interview_rate: 0,
              offer_count: 0,
              offer_rate: 0,
              response_count: 1,
              response_rate: 1 / 3,
              response_rate_lift: (1 / 3) - 0.6,
              success_count: 0,
              success_rate: 0,
              success_rate_lift: -0.4,
              negative_count: 2,
              negative_rate: 2 / 3,
              negative_rate_lift: (2 / 3) - 0.4,
              value: "not_offered",
            },
            dead_weight_skill_segments: [],
            selling_skill_segments: [
              {
                application_count: 5,
                dimension: "tech",
                interview_count: 1,
                interview_rate: 0.2,
                offer_count: 1,
                offer_rate: 0.2,
                response_count: 3,
                response_rate: 0.6,
                response_rate_lift: 0,
                success_count: 1,
                success_rate: 0.2,
                success_rate_lift: -0.2,
                negative_count: 2,
                negative_rate: 0.4,
                negative_rate_lift: 0,
                value: "python",
              },
            ],
            adjacent_role_suggestions: [
              {
                application_count: 5,
                dimension: "role",
                interview_count: 1,
                interview_rate: 0.2,
                offer_count: 1,
                offer_rate: 0.2,
                response_count: 3,
                response_rate: 0.6,
                response_rate_lift: 0,
                success_count: 1,
                success_rate: 0.2,
                success_rate_lift: -0.2,
                negative_count: 2,
                negative_rate: 0.4,
                negative_rate_lift: 0,
                value: "software engineer",
              },
            ],
            baseline_negative_count: 2,
            baseline_negative_rate: 0.4,
            negative_outcome_segments: [
              {
                application_count: 3,
                dimension: "source",
                interview_count: 1,
                interview_rate: 1 / 3,
                offer_count: 0,
                offer_rate: 0,
                response_count: 1,
                response_rate: 1 / 3,
                response_rate_lift: (1 / 3) - 0.6,
                success_count: 0,
                success_rate: 0,
                success_rate_lift: -0.4,
                negative_count: 2,
                negative_rate: 2 / 3,
                negative_rate_lift: (2 / 3) - 0.4,
                value: "linkedin",
              },
            ],
            segments: [],
            strongest_response_segments: [
              {
                application_count: 2,
                dimension: "source",
                interview_count: 1,
                interview_rate: 0.5,
                offer_count: 1,
                offer_rate: 0.5,
                response_count: 2,
                response_rate: 1,
                response_rate_lift: 0.4,
                success_count: 2,
                success_rate: 1,
                success_rate_lift: 0.6,
                negative_count: 0,
                negative_rate: 0,
                negative_rate_lift: -0.4,
                value: "referral",
              },
            ],
            strongest_response_correlate: {
              application_count: 2,
              dimension: "source",
              interview_count: 1,
              interview_rate: 0.5,
              offer_count: 1,
              offer_rate: 0.5,
              response_count: 2,
              response_rate: 1,
              response_rate_lift: 0.4,
              success_count: 2,
              success_rate: 1,
              success_rate_lift: 0.6,
              negative_count: 0,
              negative_rate: 0,
              negative_rate_lift: -0.4,
              value: "referral",
            },
            successful_application_segments: [
              {
                application_count: 2,
                dimension: "source",
                interview_count: 1,
                interview_rate: 0.5,
                offer_count: 1,
                offer_rate: 0.5,
                response_count: 2,
                response_rate: 1,
                response_rate_lift: 0.4,
                success_count: 2,
                success_rate: 1,
                success_rate_lift: 0.6,
                negative_count: 0,
                negative_rate: 0,
                negative_rate_lift: -0.4,
                value: "referral",
              },
            ],
            total_applications: 5,
            wasted_effort_segments: [
              {
                application_count: 3,
                dimension: "source",
                interview_count: 1,
                interview_rate: 1 / 3,
                offer_count: 0,
                offer_rate: 0,
                response_count: 1,
                response_rate: 1 / 3,
                response_rate_lift: (1 / 3) - 0.6,
                success_count: 0,
                success_rate: 0,
                success_rate_lift: -0.4,
                negative_count: 2,
                negative_rate: 2 / 3,
                negative_rate_lift: (2 / 3) - 0.4,
                value: "linkedin",
              },
            ],
            weakest_response_segments: [
              {
                application_count: 3,
                dimension: "source",
                interview_count: 1,
                interview_rate: 1 / 3,
                offer_count: 0,
                offer_rate: 0,
                response_count: 1,
                response_rate: 1 / 3,
                response_rate_lift: (1 / 3) - 0.6,
                success_count: 0,
                success_rate: 0,
                success_rate_lift: -0.4,
                negative_count: 2,
                negative_rate: 2 / 3,
                negative_rate_lift: (2 / 3) - 0.4,
                value: "linkedin",
              },
            ],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/metrics/diagnostics?role=platform&status=rejected") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            baseline_response_count: 1,
            baseline_response_rate: 1,
            baseline_success_count: 0,
            baseline_success_rate: 0,
            baseline_negative_count: 1,
            baseline_negative_rate: 1,
            best_roi_source: null,
            sponsorship_response_impact: null,
            dead_weight_skill_segments: [],
            adjacent_role_suggestions: [],
            negative_outcome_segments: [],
            segments: [],
            selling_skill_segments: [],
            strongest_response_correlate: null,
            strongest_response_segments: [],
            successful_application_segments: [],
            total_applications: 1,
            wasted_effort_segments: [],
            weakest_response_segments: [],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/applications?status=rejected") {
      return Promise.resolve(
        new Response(
          JSON.stringify([
            {
              ...baseApplication,
              company: "Globex",
              current_status: "rejected",
              id: "app-2",
              role_title: "Platform Engineer",
            },
          ]),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/applications?role=platform&status=rejected") {
      return Promise.resolve(
        new Response(
          JSON.stringify([
            {
              ...baseApplication,
              company: "Globex",
              current_status: "rejected",
              id: "app-2",
              role_title: "Platform Engineer",
            },
          ]),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    throw new Error(`Unhandled fetch request: ${url}`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

describe("DashboardPage", () => {
  it("keeps the dashboard status-table-free and applies the status filter to metrics", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    await screen.findByRole("region", { name: "Application funnel" });
    expect(screen.queryByText("Application statuses moved to Feature Status"))
      .toBeNull();
    expect(screen.queryByRole("table", {
      name: "Application current statuses",
    })).toBeNull();

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "rejected" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await screen.findByRole("region", { name: "Application funnel" });
    expect(window.location.search).toBe("?status=rejected");
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/timeseries?status=rejected",
      expect.objectContaining({ method: "GET" }),
    );

    window.history.pushState({}, "", "/dashboard");
    window.dispatchEvent(new Event("popstate"));

    await screen.findByRole("region", { name: "Application funnel" });
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "");
    expect(window.location.search).toBe("");
  });

  it("keeps live application lists out of the chart dashboard", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

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

  it("renders the deterministic metrics overview as chart panels instead of value cards", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const counts = await screen.findByRole("region", {
      name: "Foundational counts",
    });
    const rates = await screen.findByRole("region", {
      name: "Outcome rates",
    });

    expect(within(counts).getByRole("img")).toBeTruthy();
    expect(within(rates).getByRole("img")).toBeTruthy();
    expect(screen.queryByText("Metrics overview")).toBeNull();
    expect(screen.queryByText("Total applications")).toBeNull();
    expect(screen.queryByLabelText("Response rate metric")).toBeNull();
  });

  it("points incomplete-pipeline dashboard zeros to Feature Status instead of the removed Job Search page", async () => {
    mockApplicationResponses({
      summaryApplicationCount: 0,
      pipelineStatus: {
        connection: {
          account_id: "gmail@example.com",
          connected: true,
          display_email: "gmail@example.com",
          provider: "gmail",
          reauth_required: false,
        },
        counts: {
          classified_count: 0,
          raw_email_count: 12,
          retained_body_count: 12,
          total_filter_candidates: 12,
          total_filter_rejected: 0,
          unclassified_retained_count: 12,
          application_count: 0,
        },
        last_error: null,
        next_action: "run_classification",
        next_action_reason: "Retained emails are waiting for classification.",
        sync: {
          backfill_status: "completed",
          last_completed_at: "2026-07-10T00:00:00Z",
          last_run_status: "completed",
          mode: "full_backfill",
        },
      },
    });
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    await screen.findByText(
      "These zeros mean the pipeline has not finished, not that you applied to zero jobs",
    );

    expect(screen.queryByText(/Job Search page/i)).toBeNull();
    expect(
      screen.getByRole("link", { name: "Feature Status" }).getAttribute("href"),
    ).toBe("/features");
    expect(
      screen.getByText(/12 synced emails are waiting on the classification step/i),
    ).toBeTruthy();
  });

  it("explains the foundational counts chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const counts = await screen.findByRole("region", {
      name: "Foundational counts",
    });
    const infoControl = within(counts).getByRole("button", {
      name: "About Foundational counts",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(counts).getByText("How this chart works")).toBeTruthy();
    expect(within(counts).getByText("GET /metrics/summary")).toBeTruthy();
    expect(within(counts).getByText("applications")).toBeTruthy();
    expect(
      within(counts).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(counts).getByText(
        "If values are zero or missing, inspect Feature Status for the next missing pipeline stage: Gmail connection, sync, classification, or aggregation.",
      ),
    ).toBeTruthy();
  });

  it("explains the outcome rates chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const rates = await screen.findByRole("region", {
      name: "Outcome rates",
    });
    const infoControl = within(rates).getByRole("button", {
      name: "About Outcome rates",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(rates).getByText("How this chart works")).toBeTruthy();
    expect(within(rates).getByText("GET /metrics/rates")).toBeTruthy();
    expect(within(rates).getByText("applications and application_events")).toBeTruthy();
    expect(
      within(rates).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(rates).getByText(
        "If rates are zero or missing, check whether applications have response, rejection, interview, or offer events after classification and aggregation.",
      ),
    ).toBeTruthy();
  });

  it("explains the response timing chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const timing = await screen.findByRole("region", {
      name: "Response timing",
    });
    const infoControl = within(timing).getByRole("button", {
      name: "About Response timing",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(timing).getByText("How this chart works")).toBeTruthy();
    expect(within(timing).getByText("GET /metrics/summary")).toBeTruthy();
    expect(within(timing).getByText("applications and application_events")).toBeTruthy();
    expect(
      within(timing).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(timing).getByText(
        "If timing values are zero or missing, check whether application timelines contain response or rejection events with timestamps after aggregation.",
      ),
      ).toBeTruthy();
  });

  it("explains the application funnel chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const funnel = await screen.findByRole("region", {
      name: "Application funnel",
    });
    const infoControl = within(funnel).getByRole("button", {
      name: "About Application funnel",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(funnel).getByText("How this chart works")).toBeTruthy();
    expect(within(funnel).getByText("GET /metrics/funnel")).toBeTruthy();
    expect(within(funnel).getByText("applications and application_events")).toBeTruthy();
    expect(
      within(funnel).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(funnel).getByText(
        "If funnel rows are zero or missing, check whether classified emails have been aggregated into applications with ordered timeline events.",
      ),
    ).toBeTruthy();
  });

  it("explains the personal ghost threshold chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const ghostThreshold = await screen.findByRole("region", {
      name: "Personal ghost threshold",
    });
    const infoControl = within(ghostThreshold).getByRole("button", {
      name: "About Personal ghost threshold",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(ghostThreshold).getByText("How this chart works")).toBeTruthy();
    expect(within(ghostThreshold).getByText("GET /metrics/summary")).toBeTruthy();
    expect(
      within(ghostThreshold).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(ghostThreshold).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(ghostThreshold).getByText(
        "If silence-age buckets are zero or missing, check whether applications have applied events, later response events, and enough elapsed time for ghost inference after aggregation.",
      ),
    ).toBeTruthy();
  });

  it("explains the selected breakdown chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const breakdown = await screen.findByRole("region", {
      name: "Source applications",
    });
    const infoControl = within(breakdown).getByRole("button", {
      name: "About Source applications",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(breakdown).getByText("How this chart works")).toBeTruthy();
    expect(within(breakdown).getByText("GET /metrics/breakdown?dimension=source")).toBeTruthy();
    expect(within(breakdown).getByText("applications and application_events")).toBeTruthy();
    expect(
      within(breakdown).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(breakdown).getByText(
        "If breakdown rows are zero or missing, check whether aggregated applications have the selected segmentation field populated for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the best-converting titles chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const leaders = await screen.findByRole("region", {
      name: "Role interview conversion",
    });
    const infoControl = within(leaders).getByRole("button", {
      name: "About Role interview conversion",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(leaders).getByText("How this chart works")).toBeTruthy();
    expect(within(leaders).getByText("GET /metrics/breakdown?dimension=role")).toBeTruthy();
    expect(within(leaders).getByText("applications and application_events")).toBeTruthy();
    expect(
      within(leaders).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(leaders).getByText(
        "If role conversion rows are zero or missing, check whether aggregated applications have role titles and interview events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the company type outcomes chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const companyTypes = await screen.findByRole("region", {
      name: "Company type response conversion",
    });
    const infoControl = within(companyTypes).getByRole("button", {
      name: "About Company type response conversion",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(companyTypes).getByText("How this chart works")).toBeTruthy();
    expect(
      within(companyTypes).getByText(
        "GET /metrics/breakdown?dimension=company_type",
      ),
    ).toBeTruthy();
    expect(
      within(companyTypes).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(companyTypes).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(companyTypes).getByText(
        "If company type rows are zero or missing, check whether aggregated applications have company type metadata for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the application volume trend chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const volumeTrend = await screen.findByRole("region", {
      name: "Daily application count",
    });
    const infoControl = within(volumeTrend).getByRole("button", {
      name: "About Daily application count",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(volumeTrend).getByText("How this chart works")).toBeTruthy();
    expect(within(volumeTrend).getByText("GET /metrics/timeseries")).toBeTruthy();
    expect(within(volumeTrend).getByText("applications")).toBeTruthy();
    expect(
      within(volumeTrend).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(volumeTrend).getByText(
        "If application-volume points are zero or missing, check whether aggregation has created application rows with first_seen_at dates for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the response rate trend chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const responseTrend = await screen.findByRole("region", {
      name: "Daily response rate",
    });
    const infoControl = within(responseTrend).getByRole("button", {
      name: "About Daily response rate",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(responseTrend).getByText("How this chart works")).toBeTruthy();
    expect(within(responseTrend).getByText("GET /metrics/response-rate-trend")).toBeTruthy();
    expect(
      within(responseTrend).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(responseTrend).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(responseTrend).getByText(
        "If response-rate points are zero or missing, check whether aggregated applications have response events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the diagnostic baseline response rate chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const baseline = await within(diagnostics).findByRole("region", {
      name: "Diagnostic baseline response rate",
    });
    const infoControl = within(baseline).getByRole("button", {
      name: "About Diagnostic baseline response rate",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(baseline).getByText("How this chart works")).toBeTruthy();
    expect(within(baseline).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(
      within(baseline).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(baseline).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(baseline).getByText(
        "If the baseline rate is zero or missing, check whether aggregated applications have response events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the strongest response signals chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const strongestSignals = await within(diagnostics).findByRole("region", {
      name: "Strongest response signals",
    });
    const infoControl = within(strongestSignals).getByRole("button", {
      name: "About Strongest response signals",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(strongestSignals).getByText("How this chart works")).toBeTruthy();
    expect(within(strongestSignals).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(
      within(strongestSignals).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(strongestSignals).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(strongestSignals).getByText(
        "If strongest response signals are zero or missing, check whether aggregated applications have populated segmentation fields and response events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the successful application traits chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const successfulTraits = await within(diagnostics).findByRole("region", {
      name: "Q-32 successful application traits",
    });
    const infoControl = within(successfulTraits).getByRole("button", {
      name: "About Q-32 successful application traits",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(successfulTraits).getByText("How this chart works")).toBeTruthy();
    expect(within(successfulTraits).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(
      within(successfulTraits).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(successfulTraits).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(successfulTraits).getByText(
        "If successful application traits are zero or missing, check whether aggregated applications have interview or offer outcomes plus populated segmentation fields for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the weakest response signals chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const weakestSignals = await within(diagnostics).findByRole("region", {
      name: "Weakest response signals",
    });
    const infoControl = within(weakestSignals).getByRole("button", {
      name: "About Weakest response signals",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(weakestSignals).getByText("How this chart works")).toBeTruthy();
    expect(within(weakestSignals).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(
      within(weakestSignals).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(weakestSignals).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(weakestSignals).getByText(
        "If weakest response signals are zero or missing, check whether aggregated applications have populated segmentation fields and response events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the rejected or ghosted traits chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const rejectedOrGhostedTraits = await within(diagnostics).findByRole("region", {
      name: "Q-33 rejected or ghosted traits",
    });
    const infoControl = within(rejectedOrGhostedTraits).getByRole("button", {
      name: "About Q-33 rejected or ghosted traits",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(rejectedOrGhostedTraits).getByText("How this chart works")).toBeTruthy();
    expect(within(rejectedOrGhostedTraits).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(
      within(rejectedOrGhostedTraits).getByText(
        "applications and application_events",
      ),
    ).toBeTruthy();
    expect(
      within(rejectedOrGhostedTraits).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(rejectedOrGhostedTraits).getByText(
        "If rejected or ghosted trait values are zero or missing, check whether aggregated applications have rejected or ghosted outcomes plus populated segmentation fields for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the strongest response correlate chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const strongestCorrelate = await within(diagnostics).findByRole("region", {
      name: "Q-34 strongest response correlate",
    });
    const infoControl = within(strongestCorrelate).getByRole("button", {
      name: "About Q-34 strongest response correlate",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(strongestCorrelate).getByText("How this chart works")).toBeTruthy();
    expect(within(strongestCorrelate).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(
      within(strongestCorrelate).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(strongestCorrelate).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(strongestCorrelate).getByText(
        "If the strongest response correlate is zero or missing, check whether aggregated applications have populated segmentation fields and response events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the wasted-effort segments chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const wastedEffortSegments = await within(diagnostics).findByRole("region", {
      name: "Q-35 wasted-effort segments",
    });
    const infoControl = within(wastedEffortSegments).getByRole("button", {
      name: "About Q-35 wasted-effort segments",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(wastedEffortSegments).getByText("How this chart works")).toBeTruthy();
    expect(within(wastedEffortSegments).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(
      within(wastedEffortSegments).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(wastedEffortSegments).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(wastedEffortSegments).getByText(
        "If wasted-effort segment values are zero or missing, check whether aggregated applications have populated segmentation fields and response events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the best ROI source chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const bestRoiSource = await within(diagnostics).findByRole("region", {
      name: "Q-36 best ROI source",
    });
    const infoControl = within(bestRoiSource).getByRole("button", {
      name: "About Q-36 best ROI source",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(bestRoiSource).getByText("How this chart works")).toBeTruthy();
    expect(within(bestRoiSource).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(
      within(bestRoiSource).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(bestRoiSource).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(bestRoiSource).getByText(
        "If best ROI source values are zero or missing, check whether aggregated applications have populated source fields and interview events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the sponsorship response impact chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const sponsorshipImpact = await within(diagnostics).findByRole("region", {
      name: "Q-37 sponsorship response impact",
    });
    const infoControl = within(sponsorshipImpact).getByRole("button", {
      name: "About Q-37 sponsorship response impact",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(sponsorshipImpact).getByText("How this chart works")).toBeTruthy();
    expect(within(sponsorshipImpact).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(
      within(sponsorshipImpact).getByText("applications and application_events"),
    ).toBeTruthy();
    expect(
      within(sponsorshipImpact).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(sponsorshipImpact).getByText(
        "If sponsorship impact values are zero or missing, check whether aggregated applications have populated sponsorship fields and response events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the skill signals chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const skillSignals = await within(diagnostics).findByRole("region", {
      name: "Q-38 selling vs dead-weight skills",
    });
    const infoControl = within(skillSignals).getByRole("button", {
      name: "About Q-38 selling vs dead-weight skills",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(skillSignals).getByText("How this chart works")).toBeTruthy();
    expect(within(skillSignals).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(within(skillSignals).getByText("applications and application_events"))
      .toBeTruthy();
    expect(
      within(skillSignals).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(skillSignals).getByText(
        "If skill signal values are zero or missing, check whether aggregated applications have populated tech stack fields and interview events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("explains the adjacent role suggestions chart through an accessible info control", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const adjacentRoles = await within(diagnostics).findByRole("region", {
      name: "Q-39 adjacent role suggestions",
    });
    const infoControl = within(adjacentRoles).getByRole("button", {
      name: "About Q-39 adjacent role suggestions",
    });

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(within(adjacentRoles).getByText("How this chart works")).toBeTruthy();
    expect(within(adjacentRoles).getByText("GET /metrics/diagnostics")).toBeTruthy();
    expect(within(adjacentRoles).getByText("applications and application_events"))
      .toBeTruthy();
    expect(
      within(adjacentRoles).getByText(
        /Run sync, classification, and aggregation from Feature Status/i,
      ),
    ).toBeTruthy();
    expect(
      within(adjacentRoles).getByText(
        "If adjacent role suggestion values are zero or missing, check whether aggregated applications have populated role titles and interview events for the active filters.",
      ),
    ).toBeTruthy();
  });

  it("hydrates composed filters from the URL and clears them", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState(
      {},
      "",
      "/dashboard?status=rejected&role=platform",
    );

    render(<DashboardPage />);

    await screen.findByRole("region", { name: "Application funnel" });
    expect(screen.queryByText("Application statuses moved to Feature Status"))
      .toBeNull();
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "rejected");
    expect(screen.getByLabelText("Role")).toHaveProperty("value", "platform");
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/funnel?role=platform&status=rejected",
      expect.objectContaining({ method: "GET" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    await screen.findByRole("region", { name: "Application funnel" });
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "");
    expect(screen.getByLabelText("Role")).toHaveProperty("value", "");
    expect(window.location.search).toBe("");
  });

  it("canonicalizes invalid salary and enum query filters before loading", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState(
      {},
      "",
      "/dashboard?status=not-a-status&salary_min=abc",
    );

    render(<DashboardPage />);

    await screen.findByRole("region", { name: "Application funnel" });
    expect(screen.queryByText("Application statuses moved to Feature Status"))
      .toBeNull();
    expect(window.location.search).toBe("");
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "");
    expect(screen.getByLabelText("Salary min")).toHaveProperty("value", "");
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/funnel",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("blocks invalid salary filter submissions with actionable guidance", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    await screen.findByRole("region", { name: "Application funnel" });
    fireEvent.change(screen.getByLabelText("Salary min"), {
      target: { value: "one hundred" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    expect(
      await screen.findByText("Salary min must be a non-negative number."),
    ).toBeTruthy();
    expect(window.location.search).toBe("");
  });

  it("blocks salary range submissions when the minimum is greater than the maximum", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    await screen.findByRole("region", { name: "Application funnel" });
    fireEvent.change(screen.getByLabelText("Salary min"), {
      target: { value: "200000" },
    });
    fireEvent.change(screen.getByLabelText("Salary max"), {
      target: { value: "100000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    expect(
      await screen.findByText(
        "Salary min must be less than or equal to salary max.",
      ),
    ).toBeTruthy();
    expect(window.location.search).toBe("");
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/metrics/funnel?salary_max=100000&salary_min=200000",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-11 through Q-15 outcome rates as a deterministic chart", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const rates = await screen.findByRole("region", { name: "Outcome rates" });

    expect(within(rates).getByRole("img")).toBeTruthy();
    expect(
      within(rates).getByText(
        "Q-11 through Q-15 rates come from deterministic /metrics/rates numerators and denominators over local applications and application_events.",
      ),
    ).toBeTruthy();
    expect(within(rates).queryByLabelText("Rejection rate metric")).toBeNull();
    expect(within(rates).queryByLabelText("Ghost rate metric")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/rates",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders diagnostic comparison widgets from deterministic diagnostics", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });
    const baseline = await within(diagnostics).findByRole("region", {
      name: "Diagnostic baseline response rate",
    });

    expect(within(baseline).getByRole("img")).toBeTruthy();
    expect(within(baseline).queryByText("60%")).toBeNull();
    expect(within(baseline).queryByText("3 responses from 5 applications"))
      .toBeNull();
    const strongestResponseSignals = await within(diagnostics).findByRole("region", {
      name: "Strongest response signals",
    });

    expect(within(strongestResponseSignals).getByRole("img")).toBeTruthy();
    expect(within(strongestResponseSignals).queryByText("2 responses from 2 applications"))
      .toBeNull();
    const successfulTraits = await within(diagnostics).findByRole("region", {
      name: "Q-32 successful application traits",
    });

    expect(within(successfulTraits).getByRole("img")).toBeTruthy();
    expect(
      within(successfulTraits).getByText(
        "Q-32 successful application traits use deterministic /metrics/diagnostics success-rate lift to chart segments above the filtered success baseline.",
      ),
    ).toBeTruthy();
    expect(within(successfulTraits).queryByText("40% baseline success rate")).toBeNull();
    expect(within(successfulTraits).queryByText("+60 pp success lift")).toBeNull();
    expect(
      within(successfulTraits).queryByText("2 successful applications from 2 applications"),
    ).toBeNull();
    const rejectedOrGhostedTraits = await within(diagnostics).findByRole("region", {
      name: "Q-33 rejected or ghosted traits",
    });

    expect(within(rejectedOrGhostedTraits).getByRole("img")).toBeTruthy();
    expect(
      within(rejectedOrGhostedTraits).getByText(
        "Q-33 rejected or ghosted traits use deterministic /metrics/diagnostics negative-outcome lift to chart segments above the filtered negative-outcome baseline.",
      ),
    ).toBeTruthy();
    expect(
      within(rejectedOrGhostedTraits).queryByText("40% baseline negative rate"),
    ).toBeNull();
    expect(
      within(rejectedOrGhostedTraits).queryByText("+26.7 pp negative lift"),
    ).toBeNull();
    expect(
      within(rejectedOrGhostedTraits).queryByText(
        "2 negative outcomes from 3 applications",
      ),
    ).toBeNull();
    const strongestCorrelate = await within(diagnostics).findByRole("region", {
      name: "Q-34 strongest response correlate",
    });

    expect(within(strongestCorrelate).getByRole("img")).toBeTruthy();
    expect(within(strongestCorrelate).queryByText("Referral (Source)")).toBeNull();
    expect(
      within(strongestCorrelate).queryByText(
        "Referral (Source) is the strongest positive correlate",
      ),
    ).toBeNull();
    const wastedEffort = await within(diagnostics).findByRole("region", {
      name: "Q-35 wasted-effort segments",
    });

    expect(within(wastedEffort).getByRole("img")).toBeTruthy();
    expect(within(wastedEffort).queryByText("Linkedin (Source)")).toBeNull();
    expect(within(wastedEffort).queryByText("Linkedin (Source) is below baseline"))
      .toBeNull();
    const bestRoi = await within(diagnostics).findByRole("region", {
      name: "Q-36 best ROI source",
    });

    expect(within(bestRoi).getByRole("img")).toBeTruthy();
    expect(within(bestRoi).queryByText("Linkedin (Source)")).toBeNull();
    expect(
      within(bestRoi).queryByText("Linkedin (Source) has the best interview ROI"),
    ).toBeNull();
    const sponsorshipImpact = await within(diagnostics).findByRole("region", {
      name: "Q-37 sponsorship response impact",
    });

    expect(within(sponsorshipImpact).getByRole("img")).toBeTruthy();
    expect(
      within(sponsorshipImpact).queryByText(
        "Not offered (Sponsorship) is -26.7 pp vs baseline",
      ),
    ).toBeNull();
    const skillSignals = await within(diagnostics).findByRole("region", {
      name: "Q-38 selling vs dead-weight skills",
    });

    expect(within(skillSignals).getByRole("img")).toBeTruthy();
    expect(within(skillSignals).queryByText("Python is selling")).toBeNull();
    const adjacentRoles = await within(diagnostics).findByRole("region", {
      name: "Q-39 adjacent role suggestions",
    });

    expect(within(adjacentRoles).getByRole("img")).toBeTruthy();
    expect(
      within(adjacentRoles).queryByText(
        "Software engineer is your strongest adjacent role signal",
      ),
    ).toBeNull();
    const weakestResponseSignals = await within(diagnostics).findByRole("region", {
      name: "Weakest response signals",
    });

    expect(within(weakestResponseSignals).getByRole("img")).toBeTruthy();
    expect(
      within(weakestResponseSignals).getByText(
        "Weakest response signals use deterministic /metrics/diagnostics response-rate lift to chart segments below the filtered response baseline.",
      ),
    ).toBeTruthy();
    expect(within(weakestResponseSignals).queryByText("Linkedin (Source)")).toBeNull();
    expect(
      within(weakestResponseSignals).queryByText("-26.7 pp vs baseline"),
    ).toBeNull();
    expect(within(diagnostics).queryByText("Correlation summary")).toBeNull();
    expect(within(diagnostics).queryByText("How to read these diagnostics")).toBeNull();
    expect(
      within(diagnostics).queryByText(
        "Response-rate lift is the segment response rate minus the filtered baseline response rate.",
      ),
    ).toBeNull();
    expect(
      within(diagnostics).queryByText(
        "These are directional comparisons, not proof that a segment caused an outcome.",
      ),
    ).toBeNull();
    expect(
      within(diagnostics).queryByText(
        "Filtered baseline response rate is the response rate for every application currently included by the dashboard filters.",
      ),
    ).toBeNull();
    expect(
      within(diagnostics).queryByText(
        "A response means the application has response evidence in application_events, including interviews, offers, or other human replies.",
      ),
    ).toBeNull();
    expect(
      within(diagnostics).queryByText(
        "Strongest and weakest signals are segments ranked by positive or negative lift, not recommendations by themselves.",
      ),
    ).toBeNull();
    expect(
      within(diagnostics).queryByText(
        "Rankings use only local applications and application_events currently included by the dashboard filters.",
      ),
    ).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/diagnostics",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("does not show diagnostic explainability notes when diagnostics fail", async () => {
    mockApplicationResponses({ diagnosticsStatus: 500 });
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });

    expect(
      within(diagnostics).getByText("Diagnostics are unavailable."),
    ).toBeTruthy();
    expect(
      within(diagnostics).queryByText("How to read these diagnostics"),
    ).toBeNull();
  });

  it("renders Q-17 and Q-18 response timing as a deterministic chart", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const timing = await screen.findByRole("region", { name: "Response timing" });

    expect(within(timing).getByRole("img")).toBeTruthy();
    expect(
      within(timing).getByText(
        "Q-17 and Q-18 response timing comes from deterministic /metrics/summary average_time_to_first_response and average_time_to_rejection fields.",
      ),
    ).toBeTruthy();
    expect(within(timing).queryByLabelText("Average time to first response metric"))
      .toBeNull();
    expect(within(timing).queryByLabelText("Average time to rejection metric"))
      .toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/summary",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-19 personal ghost threshold as a chart-only surface", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const metric = await screen.findByRole("region", {
      name: "Personal ghost threshold",
    });

    expect(
      within(metric).getByRole("img", { name: "Personal ghost threshold" }),
    ).toBeTruthy();
    expect(within(metric).getByText("Personal ghost threshold")).toBeTruthy();
    expect(
      within(metric).getByText(
        "Q-19 silence-age buckets come from deterministic /metrics/summary personal_ghost_threshold data over local application timelines, then reload with the active dashboard filters.",
      ),
    ).toBeTruthy();
    expect(within(metric).queryByText("Effective dead after")).toBeNull();
    expect(within(metric).queryByText("Silent applications")).toBeNull();
    expect(within(metric).queryByText("Inferred from 2 response timings")).toBeNull();
    expect(within(metric).queryByText("3 silent applications in distribution")).toBeNull();
  });

  it("renders source breakdown as a chart-only metric surface", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const breakdown = await screen.findByRole("region", {
      name: "Source breakdown",
    });

    expect(within(breakdown).getByText("Source breakdown")).toBeTruthy();
    expect(within(breakdown).getByRole("img", { name: "Source applications" }))
      .toBeTruthy();
    expect(within(breakdown).queryByText("3 applications")).toBeNull();
    expect(within(breakdown).queryByText(/2 responses/)).toBeNull();
    expect(within(breakdown).queryByText(/66.7% response rate/)).toBeNull();
    expect(within(breakdown).queryByText(/1 offer/)).toBeNull();
    expect(within(breakdown).queryByRole("list")).toBeNull();
    expect(
      within(breakdown).queryByRole("table", {
        name: "Source metric breakdown",
      }),
    ).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/breakdown?dimension=source",
      expect.objectContaining({ method: "GET" }),
    );

    fireEvent.change(screen.getByLabelText("Dimension"), {
      target: { value: "tech" },
    });

    const techBreakdown = await screen.findByRole("region", {
      name: "Tech breakdown",
    });

    expect(within(techBreakdown).getByRole("img", { name: "Tech applications" }))
      .toBeTruthy();
    expect(within(techBreakdown).queryByText(/75% response rate/)).toBeNull();
    expect(
      within(techBreakdown).queryByRole("table", {
        name: "Tech metric breakdown",
      }),
    ).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/breakdown?dimension=tech",
      expect.objectContaining({ method: "GET" }),
    );

    fireEvent.change(screen.getByLabelText("Dimension"), {
      target: { value: "salary" },
    });

    const salaryBreakdown = await screen.findByRole("region", {
      name: "Salary breakdown",
    });

    expect(within(salaryBreakdown).getByRole("img", { name: "Salary applications" }))
      .toBeTruthy();
    expect(within(salaryBreakdown).queryByText(/100% response rate/)).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/breakdown?dimension=salary",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-20 application volume trend as a chart-only surface from deterministic timeseries metrics", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const trend = await screen.findByRole("region", {
      name: "Application volume trend",
    });

    expect(within(trend).getByText("Application volume trend")).toBeTruthy();
    expect(within(trend).getByRole("img")).toBeTruthy();
    expect(
      within(trend).queryByText("2 applications on Jul 1, 2026"),
    ).toBeNull();
    expect(
      within(trend).queryByText("5 applications on Jul 8, 2026"),
    ).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/timeseries",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("passes route-backed filters to the Q-20 application volume trend", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard?status=rejected");

    render(<DashboardPage />);

    const trend = await screen.findByRole("region", {
      name: "Application volume trend",
    });

    expect(within(trend).getByRole("img")).toBeTruthy();
    expect(
      within(trend).queryByText("1 application on Jul 8, 2026"),
    ).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/timeseries?status=rejected",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-21 response rate trend as a chart-only surface from deterministic metrics", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const trend = await screen.findByRole("region", {
      name: "Response rate trend",
    });

    expect(within(trend).getByText("Response rate trend")).toBeTruthy();
    expect(within(trend).getByRole("img")).toBeTruthy();
    expect(within(trend).queryByText("50% on Jul 1, 2026")).toBeNull();
    expect(within(trend).queryByText("80% on Jul 8, 2026")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/response-rate-trend",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-23 best-converting titles as a chart-only surface", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const leaders = await screen.findByRole("region", {
      name: "Best-converting titles",
    });

    expect(within(leaders).getByRole("img")).toBeTruthy();
    expect(within(leaders).getByText("Role interview conversion")).toBeTruthy();
    expect(within(leaders).queryByText("No title conversion rows yet")).toBeNull();
    expect(within(leaders).queryByText("50% interview rate")).toBeNull();
    expect(within(leaders).queryByText("2 of 4 applications reached interview"))
      .toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/breakdown?dimension=role",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-24 company type outcomes as a chart-only surface", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const companyTypes = await screen.findByRole("region", {
      name: "Company type outcomes",
    });

    expect(within(companyTypes).getByRole("img")).toBeTruthy();
    expect(within(companyTypes).getByText("Company type response conversion")).toBeTruthy();
    expect(within(companyTypes).queryByText("2 responses")).toBeNull();
    expect(within(companyTypes).queryByText("1 interview")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/breakdown?dimension=company_type",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-16 as a deterministic chart and reloads it with dashboard filters", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard?status=rejected&role=platform");

    render(<DashboardPage />);

    const funnel = await screen.findByRole("region", {
      name: "Application funnel",
    });

    expect(within(funnel).getByText("Application funnel")).toBeTruthy();
    expect(within(funnel).getByText("Deterministic chart")).toBeTruthy();
    expect(
      within(funnel).getByText(
        "Q-16 funnel stages come from deterministic /metrics/funnel rows over local applications and application_events, then reload with the active dashboard filters.",
      ),
    ).toBeTruthy();
    expect(within(funnel).getByRole("img")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/funnel?role=platform&status=rejected",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/diagnostics?role=platform&status=rejected",
      expect.objectContaining({ method: "GET" }),
    );
  });
});
