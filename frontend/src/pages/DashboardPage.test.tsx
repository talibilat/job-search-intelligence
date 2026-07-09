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

function mockApplicationResponses(options: { diagnosticsStatus?: number } = {}) {
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
          average_time_to_first_response: {
            application_count: 2,
            average_hours: 36,
          },
          average_time_to_rejection: {
            application_count: 2,
            average_hours: 48,
          },
          distinct_company_count: 1,
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
        }), {
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
                value: "referral",
              },
            ],
            total_applications: 5,
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
            segments: [],
            strongest_response_segments: [],
            total_applications: 1,
            weakest_response_segments: [],
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/applications") {
      return Promise.resolve(
        new Response(JSON.stringify([baseApplication]), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
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

    if (
      url === "/applications?status=applied" ||
      url === "/applications?status=in_review" ||
      url === "/applications?status=assessment" ||
      url === "/applications?status=interview"
    ) {
      return Promise.resolve(
        new Response(JSON.stringify([]), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
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
  it("renders Q-09 application statuses and applies the status filter", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    expect(await screen.findByText("Acme Corp")).toBeTruthy();
    const table = screen.getByRole("table", {
      name: "Application current statuses",
    });
    expect(table).toBeTruthy();
    expect(screen.getByText("Backend Engineer")).toBeTruthy();
    expect(within(table).getByText("Interview")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications",
      expect.objectContaining({ method: "GET" }),
    );

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "rejected" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    expect(await screen.findByText("Globex")).toBeTruthy();
    expect(within(table).getByText("Rejected")).toBeTruthy();
    expect(window.location.search).toBe("?status=rejected");
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications?status=rejected",
      expect.objectContaining({ method: "GET" }),
    );

    window.history.pushState({}, "", "/dashboard");
    window.dispatchEvent(new Event("popstate"));

    expect(await screen.findByText("Acme Corp")).toBeTruthy();
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "");
    expect(window.location.search).toBe("");
  });

  it("hydrates composed filters from the URL and clears them", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState(
      {},
      "",
      "/dashboard?status=rejected&role=platform",
    );

    render(<DashboardPage />);

    expect(await screen.findByText("Globex")).toBeTruthy();
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "rejected");
    expect(screen.getByLabelText("Role")).toHaveProperty("value", "platform");
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications?role=platform&status=rejected",
      expect.objectContaining({ method: "GET" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(await screen.findByText("Acme Corp")).toBeTruthy();
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

    expect(await screen.findByText("Acme Corp")).toBeTruthy();
    expect(window.location.search).toBe("");
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "");
    expect(screen.getByLabelText("Salary min")).toHaveProperty("value", "");
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-12 rejection rate from deterministic metrics", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const metric = await screen.findByLabelText("Rejection rate metric");

    expect(await within(metric).findByText("20%")).toBeTruthy();
    expect(
      within(metric).getByText("1 of 5 applications are rejected"),
    ).toBeTruthy();
  });

  it("renders Q-13 ghost rate from deterministic metrics", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const metric = await screen.findByLabelText("Ghost rate metric");

    expect(await within(metric).findByText("40%")).toBeTruthy();
    expect(
      within(metric).getByText("2 of 5 applications are ghosted or silent past threshold"),
    ).toBeTruthy();
  });

  it("renders Q-14 application to interview rate from deterministic metrics", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const metric = await screen.findByLabelText("Application to interview rate metric");

    expect(await within(metric).findByText("20%")).toBeTruthy();
    expect(
      within(metric).getByText("1 of 5 applications reached interview"),
    ).toBeTruthy();
  });

  it("renders Q-15 interview to offer rate from deterministic metrics", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const metric = await screen.findByLabelText("Interview to offer rate metric");

    expect(await within(metric).findByText("100%")).toBeTruthy();
    expect(
      within(metric).getByText("1 of 1 interviewed applications reached offer"),
    ).toBeTruthy();
  });

  it("renders diagnostic comparison widgets from deterministic diagnostics", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const diagnostics = await screen.findByRole("region", {
      name: "Diagnostic comparisons",
    });

    expect(within(diagnostics).getByText("Baseline response rate")).toBeTruthy();
    expect(within(diagnostics).getByText("60%")).toBeTruthy();
    expect(within(diagnostics).getByText("Strongest response signals")).toBeTruthy();
    expect(within(diagnostics).getByText("Referral (Source)")).toBeTruthy();
    expect(within(diagnostics).getByText("+40 pp vs baseline")).toBeTruthy();
    expect(within(diagnostics).getByText("Weakest response signals")).toBeTruthy();
    expect(within(diagnostics).getByText("Linkedin (Source)")).toBeTruthy();
    expect(within(diagnostics).getByText("-26.7 pp vs baseline")).toBeTruthy();
    expect(within(diagnostics).getByText("Correlation summary")).toBeTruthy();
    expect(within(diagnostics).getByText("How to read these diagnostics")).toBeTruthy();
    expect(
      within(diagnostics).getByText(
        "Response-rate lift is the segment response rate minus the filtered baseline response rate.",
      ),
    ).toBeTruthy();
    expect(
      within(diagnostics).getByText(
        "These are directional comparisons, not proof that a segment caused an outcome.",
      ),
    ).toBeTruthy();
    expect(
      within(diagnostics).getByText(
        "Filtered baseline response rate is the response rate for every application currently included by the dashboard filters.",
      ),
    ).toBeTruthy();
    expect(
      within(diagnostics).getByText(
        "A response means the application has response evidence in application_events, including interviews, offers, or other human replies.",
      ),
    ).toBeTruthy();
    expect(
      within(diagnostics).getByText(
        "Strongest and weakest signals are segments ranked by positive or negative lift, not recommendations by themselves.",
      ),
    ).toBeTruthy();
    expect(
      within(diagnostics).getByText(
        "Rankings use only local applications and application_events currently included by the dashboard filters.",
      ),
    ).toBeTruthy();
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

  it("renders Q-17 average time to first response from deterministic metrics", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const metric = await screen.findByLabelText("Average time to first response metric");

    expect(await within(metric).findByText("1.5 days")).toBeTruthy();
    expect(
      within(metric).getByText("Averaged across 2 applications with response evidence"),
    ).toBeTruthy();
  });

  it("renders Q-18 average time to rejection from deterministic metrics", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const metric = await screen.findByLabelText("Average time to rejection metric");

    expect(await within(metric).findByText("2 days")).toBeTruthy();
    expect(
      within(metric).getByText("Averaged across 2 rejected applications"),
    ).toBeTruthy();
  });

  it("renders Q-19 personal ghost threshold and silence age distribution", async () => {
    mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const metric = await screen.findByRole("region", {
      name: "Personal ghost threshold",
    });

    expect(within(metric).getByText("20 days")).toBeTruthy();
    expect(within(metric).getByText("Inferred from 2 response timings")).toBeTruthy();
    expect(within(metric).getByText("3 silent applications in distribution")).toBeTruthy();
    expect(within(metric).getByText("8 to 14 days")).toBeTruthy();
    expect(within(metric).getByText("1")).toBeTruthy();
    expect(within(metric).getByText("15 to 30 days")).toBeTruthy();
    expect(within(metric).getByText("2")).toBeTruthy();
  });

  it("renders source breakdown chart summary and table from deterministic metrics", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const breakdown = await screen.findByRole("region", {
      name: "Source breakdown",
    });

    expect(within(breakdown).getByText("Source breakdown")).toBeTruthy();
    expect(within(breakdown).getAllByText("Linkedin").length).toBeGreaterThan(0);
    expect(within(breakdown).getAllByText("Company site").length).toBeGreaterThan(0);
    expect(within(breakdown).getByText("3 applications")).toBeTruthy();
    expect(within(breakdown).getByText(/2 responses/)).toBeTruthy();
    expect(within(breakdown).getByText(/66.7% response rate/)).toBeTruthy();
    expect(within(breakdown).getByText(/1 offer/)).toBeTruthy();
    expect(
      within(breakdown).getByRole("table", {
        name: "Source metric breakdown",
      }),
    ).toBeTruthy();
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

    expect(within(techBreakdown).getAllByText("Python").length).toBeGreaterThan(0);
    expect(within(techBreakdown).getByText(/75% response rate/)).toBeTruthy();
    expect(
      within(techBreakdown).getByRole("table", {
        name: "Tech metric breakdown",
      }),
    ).toBeTruthy();
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

    expect(within(salaryBreakdown).getAllByText("100k 149k").length).toBeGreaterThan(0);
    expect(within(salaryBreakdown).getByText(/100% response rate/)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/breakdown?dimension=salary",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-20 application volume trend from deterministic timeseries metrics", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const trend = await screen.findByRole("region", {
      name: "Application volume trend",
    });

    expect(within(trend).getByText("Application volume trend")).toBeTruthy();
    expect(within(trend).getByText("2 applications on Jul 1, 2026")).toBeTruthy();
    expect(within(trend).getByText("5 applications on Jul 8, 2026")).toBeTruthy();
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

    expect(within(trend).getByText("1 application on Jul 8, 2026")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/timeseries?status=rejected",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-21 response rate trend from deterministic metrics", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const trend = await screen.findByRole("region", {
      name: "Response rate trend",
    });

    expect(within(trend).getByText("Response rate trend")).toBeTruthy();
    expect(within(trend).getByText("50% on Jul 1, 2026"));
    expect(within(trend).getByText("80% on Jul 8, 2026"));
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/response-rate-trend",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-23 best-converting titles by interview conversion", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const leaders = await screen.findByRole("region", {
      name: "Best-converting titles",
    });

    expect(within(leaders).getByText("Backend engineer")).toBeTruthy();
    expect(within(leaders).getByText("50% interview rate")).toBeTruthy();
    expect(within(leaders).getByText("2 of 4 applications reached interview")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/breakdown?dimension=role",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-24 company type outcomes", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    const companyTypes = await screen.findByRole("region", {
      name: "Company type outcomes",
    });

    expect(within(companyTypes).getByText("Startup")).toBeTruthy();
    expect(within(companyTypes).getByText("2 responses")).toBeTruthy();
    expect(within(companyTypes).getByText("1 interview")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/metrics/breakdown?dimension=company_type",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("renders Q-16 funnel stages and reloads them with dashboard filters", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard?status=rejected&role=platform");

    render(<DashboardPage />);

    const funnel = await screen.findByRole("region", {
      name: "Application funnel",
    });

    expect(within(funnel).getByText("Application funnel")).toBeTruthy();
    expect(within(funnel).getByText("Applied")).toBeTruthy();
    expect(within(funnel).getByText("Screen")).toBeTruthy();
    expect(within(funnel).getByText("Interview")).toBeTruthy();
    expect(within(funnel).getByText("Final")).toBeTruthy();
    expect(within(funnel).getByText("Offer")).toBeTruthy();
    expect(within(funnel).getAllByText("1 application").length).toBeGreaterThan(0);
    expect(within(funnel).getAllByText("0 applications").length).toBeGreaterThan(0);
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
