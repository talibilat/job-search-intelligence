import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OverviewPage } from "./OverviewPage";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });
}

const emptyEmailPage = {
  items: [],
  page: 1,
  page_size: 10,
  total_items: 0,
  total_pages: 0,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("OverviewPage request states", () => {
  it("renders unique interview tasks and persists Done through the backend", async () => {
    let attentionReads = 0;
    const item = {
      application_id: "app-aviva",
      interview_event_id: "event-aviva",
      company: "Aviva",
      role_title: "Lead AI Developer",
      interview_at: "2026-07-17T09:00:00Z",
      last_activity_at: "2026-07-17T09:00:00Z",
      current_status: "interview",
      completed_at: null,
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const pathname = new URL(path, "http://localhost").pathname;
      if (pathname === "/attention") {
        attentionReads += 1;
        return Promise.resolve(response({
          unique_interviewed_company_count: 1,
          prepare: attentionReads === 1 ? [item] : [],
          interviewed: [{ ...item, completed_at: attentionReads === 1 ? null : "2026-07-17T12:00:00Z" }],
          follow_up: [],
        }));
      }
      if (pathname === "/attention/interviews/event-aviva/complete") {
        return Promise.resolve(response({ interview_event_id: "event-aviva", application_id: "app-aviva", completed_at: "2026-07-17T12:00:00Z" }));
      }
      if (pathname === "/metrics/summary") return Promise.resolve(response({ total_applications: 1, offers_received: 0 }));
      if (pathname === "/metrics/rates") return Promise.resolve(response({}));
      if (pathname === "/metrics/funnel") return Promise.resolve(response({ stages: [{ stage: "interview", count: 1 }] }));
      if (pathname === "/applications") return Promise.resolve(response([]));
      if (pathname === "/metrics/timeseries") return Promise.resolve(response({ points: [] }));
      if (pathname.startsWith("/sync/emails")) return Promise.resolve(response(emptyEmailPage));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    expect(await screen.findByText("Prepare")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open Aviva Lead AI Developer" }).textContent).toContain("Aviva · Lead AI Developer · Jul 17");
    expect(screen.getByText("1 unique companies")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Mark Aviva interview done" }));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Mark Aviva interview done" })).toBeNull();
    });
    expect(fetchMock.mock.calls.some(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost").pathname === "/attention/interviews/event-aviva/complete")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Interview 1" }));
    expect(await screen.findByRole("dialog", { name: "Interviewed companies" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open Aviva Lead AI Developer" })).toBeTruthy();
  });

  it("marks zero metrics pending while the pipeline still needs processing", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const pathname = new URL(path, "http://localhost").pathname;
      if (pathname === "/pipeline/status") return Promise.resolve(response({
        backfill_complete: true,
        backfill_messages_processed: 20,
        backfill_pages_processed: 1,
        backfill_state: "completed",
        counts: { application_count: 0, application_event_count: 0, classified_email_count: 0, filter_candidate_count: 3, filter_decision_count: 20, filter_rejected_count: 17, job_related_email_count: 0, metadata_only_count: 17, raw_email_count: 20, retained_body_count: 3 },
        generated_at: "2026-07-14T12:00:00Z",
        gmail_connected: true,
        incremental_sync_ready: true,
        next_action: "run_classification",
        next_action_reason: "Three retained emails still need classification.",
        sync_running: false,
        unclassified_retained_count: 3,
      }));
      if (pathname === "/processing/status") return Promise.resolve(response({ state: "idle", candidate_limit: 500 }));
      if (pathname === "/config/providers/readiness") return Promise.resolve(response({ ready_to_classify: true, ready_to_sync: true, classification_generation: { state: "ready", message: "Ready." } }));
      if (pathname === "/classification/estimate") return Promise.resolve(response({ candidate_count: 3, estimated_cost_usd: 0, model: "local-model", prompt_version: "v1" }));
      if (pathname === "/metrics/summary") return Promise.resolve(response({ ghost_threshold_days: 30, ghosted_applications: 0, interview_invitation_count: 0, live_applications: 0, offers_received: 0, rejected_applications: 0, total_applications: 0 }));
      if (pathname === "/metrics/rates") return Promise.resolve(response({}));
      if (pathname === "/metrics/funnel") return Promise.resolve(response({ stages: [] }));
      if (pathname === "/applications") return Promise.resolve(response([]));
      if (pathname === "/metrics/timeseries" || pathname === "/metrics/response-rate-trend") return Promise.resolve(response({ points: [] }));
      if (pathname === "/metrics/response-silence") return Promise.resolve(response({ human_response_count: 0, silent_count: 0, total_applications: 0 }));
      if (pathname === "/metrics/diagnostics") return Promise.resolve(response({ adjacent_role_suggestions: [], dead_weight_skill_segments: [], negative_outcome_segments: [], segments: [], selling_skill_segments: [], strongest_response_segments: [], successful_application_segments: [], total_applications: 0, wasted_effort_segments: [], weakest_response_segments: [] }));
      if (pathname === "/metrics/breakdown") return Promise.resolve(response({ dimension: new URL(path, "http://localhost").searchParams.get("dimension"), rows: [] }));
      if (pathname.startsWith("/sync/emails")) return Promise.resolve(response(emptyEmailPage));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    expect(await screen.findByText("Dashboard is not final yet")).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Process 3 emails" })).toBeTruthy();
    expect((await screen.findAllByText("Pending")).length).toBeGreaterThanOrEqual(6);
    expect(screen.queryByText("Analytics will unlock after processing")).toBeTruthy();
  });

  it("renders the backend live-application count instead of deriving status semantics", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/metrics/summary") {
        return Promise.resolve(response({
          live_applications: 7,
          offers_received: 0,
          total_applications: 8,
        }));
      }
      if (path === "/metrics/rates") return Promise.resolve(response({}));
      if (path === "/metrics/funnel") return Promise.resolve(response({ stages: [] }));
      if (path === "/applications") {
        return Promise.resolve(response([{
          current_status: "applied",
          id: "application-1",
        }]));
      }
      if (path.startsWith("/sync/emails")) return Promise.resolve(response(emptyEmailPage));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    expect(await screen.findByText("7 still active")).toBeTruthy();
    expect(screen.queryByText("1 still active")).toBeNull();
  });

  it("uses backend MetricRate.rate values and labels historical populations non-exact", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/metrics/summary") return Promise.resolve(response({ total_applications: 8, offers_received: 2 }));
      if (path === "/metrics/rates") return Promise.resolve(response({
        overall_response_rate: { numerator: 3, denominator: 99, rate: 0.375 },
        rejection_rate: { numerator: 0, denominator: 8, rate: 0 },
        ghost_rate: { numerator: 0, denominator: 8, rate: 0 },
        application_to_interview_rate: { numerator: 2, denominator: 99, rate: 0.25 },
        interview_to_offer_rate: { numerator: 2, denominator: 2, rate: 1 },
      }));
      if (path === "/metrics/funnel") return Promise.resolve(response({ stages: [
        { stage: "applied", count: 8 }, { stage: "interview", count: 2 }, { stage: "offer", count: 2 },
      ] }));
      if (path === "/applications") return Promise.resolve(response([]));
      if (path.startsWith("/sync/emails")) return Promise.resolve(response(emptyEmailPage));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    expect(await screen.findByText("37.5%")).toBeTruthy();
    expect(screen.getByText("25%")).toBeTruthy();
    expect(screen.queryByText(/Interview and offer open exact current matches/)).toBeNull();
    expect(screen.getByText(/Historical event populations cannot be reproduced exactly/)).toBeTruthy();
  });

  it("distinguishes failed summary, rates, and applications from valid zero or empty", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/metrics/funnel") return Promise.resolve(response({ stages: [] }));
      if (path.startsWith("/sync/emails")) {
        return Promise.resolve(response(emptyEmailPage));
      }
      const message = path.includes("summary")
        ? "Summary failed."
        : path.includes("rates")
          ? "Rates failed."
          : path === "/applications"
            ? "Applications failed."
            : "Unexpected failure.";
      return Promise.resolve(response({ error: { code: "failed", details: [], message } }, 503));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    for (const message of ["Summary failed.", "Rates failed.", "Applications failed."]) {
      expect(await screen.findByText(message)).toBeTruthy();
    }
    expect(screen.queryByText("0%")).toBeNull();
    expect(screen.queryByText(/Nothing yet/)).toBeNull();
  });

  it("does not expose zero-based summary explainers when summary fails", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/metrics/summary") {
        return Promise.resolve(response({ error: { code: "failed", details: [], message: "Summary failed." } }, 503));
      }
      if (path === "/metrics/rates") return Promise.resolve(response({
        overall_response_rate: { numerator: 3, denominator: 8, rate: 0.375 },
        rejection_rate: { numerator: 0, denominator: 8, rate: 0 },
        ghost_rate: { numerator: 0, denominator: 8, rate: 0 },
        application_to_interview_rate: { numerator: 2, denominator: 8, rate: 0.25 },
        interview_to_offer_rate: { numerator: 1, denominator: 2, rate: 0.5 },
      }));
      if (path === "/metrics/funnel") return Promise.resolve(response({ stages: [] }));
      if (path === "/applications") return Promise.resolve(response([]));
      if (path.startsWith("/sync/emails")) return Promise.resolve(response(emptyEmailPage));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    await screen.findByText("Summary failed.");
    const applicationHow = screen.getByRole("button", { name: "How is Applications calculated?" });
    const offerHow = screen.getByRole("button", { name: "How are Offers calculated?" });
    expect(applicationHow).toHaveProperty("disabled", true);
    expect(offerHow).toHaveProperty("disabled", true);
    fireEvent.click(applicationHow);
    fireEvent.click(offerHow);
    expect(screen.queryByText(/0 distinct clusters/)).toBeNull();
    expect(screen.queryByText(/How “Applications tracked”/)).toBeNull();
    expect(screen.queryByText(/How “Offers”/)).toBeNull();
  });

  it("does not expose 0/0 rate explainers when rates fail", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/metrics/summary") return Promise.resolve(response({ total_applications: 8, offers_received: 2 }));
      if (path === "/metrics/rates") {
        return Promise.reject(new TypeError("backend unavailable"));
      }
      if (path === "/metrics/funnel") return Promise.resolve(response({ stages: [] }));
      if (path === "/applications") return Promise.resolve(response([]));
      if (path.startsWith("/sync/emails")) return Promise.resolve(response(emptyEmailPage));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    await screen.findByText("Rates could not be loaded.");
    const responseHow = screen.getByRole("button", { name: "How is Responses calculated?" });
    const interviewHow = screen.getByRole("button", { name: "How is Interviews calculated?" });
    expect(responseHow).toHaveProperty("disabled", true);
    expect(interviewHow).toHaveProperty("disabled", true);
    fireEvent.click(responseHow);
    fireEvent.click(interviewHow);
    expect(screen.queryByText(/0 ÷ 0/)).toBeNull();
  });

  it("describes offers with the exact event-based backend metric semantics", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/metrics/summary") return Promise.resolve(response({ total_applications: 8, offers_received: 2 }));
      if (path === "/metrics/rates") return Promise.resolve(response({
        overall_response_rate: { numerator: 3, denominator: 8, rate: 0.375 },
        rejection_rate: { numerator: 0, denominator: 8, rate: 0 },
        ghost_rate: { numerator: 0, denominator: 8, rate: 0 },
        application_to_interview_rate: { numerator: 2, denominator: 8, rate: 0.25 },
        interview_to_offer_rate: { numerator: 1, denominator: 2, rate: 0.5 },
      }));
      if (path === "/metrics/funnel") return Promise.resolve(response({ stages: [] }));
      if (path === "/applications") return Promise.resolve(response([]));
      if (path.startsWith("/sync/emails")) return Promise.resolve(response(emptyEmailPage));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    await screen.findByText("2 offers received");
    fireEvent.click(screen.getByRole("button", { name: "How are Offers calculated?" }));
    expect(screen.getByText("count(applications with an offer event)")).toBeTruthy();
    expect(screen.queryByText(/status = offer/)).toBeNull();
  });

  it("threads the selected sent-after boundary to the synced email request", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/metrics/summary") return Promise.resolve(response({ total_applications: 0, offers_received: 0 }));
      if (path === "/metrics/rates") return Promise.resolve(response({}));
      if (path === "/metrics/funnel") return Promise.resolve(response({ stages: [] }));
      if (path === "/applications") return Promise.resolve(response([]));
      if (path.startsWith("/sync/emails")) return Promise.resolve(response(emptyEmailPage));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <OverviewPage
        go={() => undefined}
        openApp={() => undefined}
        reloadKey={0}
        sentAfter="2026-07-05T00:00:00Z"
      />,
    );

    await screen.findByText("No emails found in the selected period.");
    const emailRequest = fetchMock.mock.calls
      .map(([input]) =>
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url,
      )
      .find((path) => path.startsWith("/sync/emails"));
    expect(emailRequest).toBeTruthy();
    expect(new URL(emailRequest!, "http://localhost").searchParams.get("sent_after")).toBe(
      "2026-07-05T00:00:00Z",
    );
  });

  it("defaults to the Overview tab and switches to the Question catalog and Visualized tabs without losing loaded data", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/metrics/summary") return Promise.resolve(response({ total_applications: 4, offers_received: 0 }));
      if (path === "/metrics/rates") return Promise.resolve(response({}));
      if (path === "/metrics/funnel") return Promise.resolve(response({ stages: [] }));
      if (path === "/applications") return Promise.resolve(response([]));
      if (path.startsWith("/sync/emails")) return Promise.resolve(response(emptyEmailPage));
      if (path === "/metrics/timeseries") return Promise.resolve(response({ points: [] }));
      if (path.startsWith("/metrics/breakdown")) return Promise.resolve(response({ dimension: "role", rows: [] }));
      if (path === "/metrics/diagnostics") {
        return Promise.resolve(
          response({
            adjacent_role_suggestions: [],
            baseline_negative_count: 0,
            baseline_response_count: 0,
            baseline_success_count: 0,
            dead_weight_skill_segments: [],
            negative_outcome_segments: [],
            segments: [],
            selling_skill_segments: [],
            strongest_response_segments: [],
            successful_application_segments: [],
            total_applications: 0,
            wasted_effort_segments: [],
            weakest_response_segments: [],
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    expect(await screen.findByText("Your search at a glance")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Question catalog" }));
    expect(await screen.findByText("Everything your search can answer")).toBeTruthy();
    expect(screen.queryByText("Your search at a glance")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Visualized" }));
    expect(await screen.findByText("Your search, visualized")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    expect(await screen.findByText("Your search at a glance")).toBeTruthy();

    expect(fetchMock.mock.calls.some(([input]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      return path === "/metrics/timeseries";
    })).toBe(true);
  });
});
