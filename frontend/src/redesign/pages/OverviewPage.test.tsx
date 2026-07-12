import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OverviewPage } from "./OverviewPage";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("OverviewPage request states", () => {
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
      if (path.startsWith("/applications/events/recent")) return Promise.resolve(response([]));
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
      if (path === "/applications" || path.startsWith("/applications/events/recent")) return Promise.resolve(response([]));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    expect(await screen.findByText("37.5%")).toBeTruthy();
    expect(screen.getByText("25%")).toBeTruthy();
    expect(screen.queryByText(/Interview and offer open exact current matches/)).toBeNull();
    expect(screen.getByText(/Historical event populations cannot be reproduced exactly/)).toBeTruthy();
  });

  it("distinguishes failed summary, rates, applications, and activity from valid zero or empty", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/metrics/funnel") return Promise.resolve(response({ stages: [] }));
      const message = path.includes("summary")
        ? "Summary failed."
        : path.includes("rates")
          ? "Rates failed."
          : path === "/applications"
            ? "Applications failed."
            : "Activity failed.";
      return Promise.resolve(response({ error: { code: "failed", details: [], message } }, 503));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    for (const message of ["Summary failed.", "Rates failed.", "Applications failed.", "Activity failed."]) {
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
      if (path === "/applications" || path.startsWith("/applications/events/recent")) return Promise.resolve(response([]));
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
      if (path === "/applications" || path.startsWith("/applications/events/recent")) return Promise.resolve(response([]));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    await screen.findByText("Rates could not be loaded.");
    const responseHow = screen.getByRole("button", { name: "How is Response rate calculated?" });
    const interviewHow = screen.getByRole("button", { name: "How is Interview rate calculated?" });
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
      if (path === "/applications" || path.startsWith("/applications/events/recent")) return Promise.resolve(response([]));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(<OverviewPage go={() => undefined} openApp={() => undefined} reloadKey={0} />);

    await screen.findByText("2 offers received");
    fireEvent.click(screen.getByRole("button", { name: "How are Offers calculated?" }));
    expect(screen.getByText("count(applications with an offer event)")).toBeTruthy();
    expect(screen.queryByText(/status = offer/)).toBeNull();
  });
});
