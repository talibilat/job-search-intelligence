import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MetricsDiagnosticsResponse } from "../../../api";
import { VisualizedTab } from "./VisualizedTab";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });
}

function emptyDiagnostics(): MetricsDiagnosticsResponse {
  return {
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
  };
}

function emptyBreakdown() {
  return { dimension: "role", rows: [] };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("VisualizedTab", () => {
  it("loads breakdown and diagnostics data for each dimension and renders real values, not fixed placeholders", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path.startsWith("/metrics/breakdown?dimension=role")) {
        return Promise.resolve(jsonResponse({
          dimension: "role",
          rows: [{ application_count: 5, dimension: "role", interview_count: 2, interview_rate: 0.4, offer_count: 0, offer_rate: 0, response_count: 3, response_rate: 0.6, value: "Platform Engineer" }],
        }));
      }
      if (path.startsWith("/metrics/breakdown")) {
        return Promise.resolve(jsonResponse(emptyBreakdown()));
      }
      if (path === "/metrics/diagnostics") {
        return Promise.resolve(jsonResponse({
          ...emptyDiagnostics(),
          selling_skill_segments: [{ application_count: 4, dimension: "tech", interview_count: 3, negative_count: 0, offer_count: 1, response_count: 3, success_count: 3, success_rate: 0.75, value: "Kubernetes" }],
        }));
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <VisualizedTab
        funnel={{ stages: [{ count: 10, stage: "applied" }, { count: 3, stage: "interview" }] }}
        rates={null}
        summary={null}
        timeseries={null}
      />,
    );

    expect(await screen.findByText("Platform Engineer")).toBeTruthy();
    expect(await screen.findByText("Kubernetes")).toBeTruthy();
    expect(screen.getByText("Where everyone goes")).toBeTruthy();
    expect(screen.getByText("10")).toBeTruthy();

    expect(fetchMock.mock.calls.some(([input]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      return path.startsWith("/metrics/breakdown?dimension=tech");
    })).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      return path.startsWith("/metrics/breakdown?dimension=salary");
    })).toBe(true);
  });

  it("shows an actionable breakdown error on every breakdown panel instead of silently rendering nothing", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path.startsWith("/metrics/breakdown")) {
        return Promise.resolve(jsonResponse({ error: { code: "failed", details: [], message: "Breakdown failed." } }, 503));
      }
      if (path === "/metrics/diagnostics") {
        return Promise.resolve(jsonResponse(emptyDiagnostics()));
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(<VisualizedTab funnel={null} rates={null} summary={null} timeseries={null} />);

    const errors = await screen.findAllByText("Breakdown failed.");
    expect(errors.length).toBeGreaterThan(0);
  });

  it("does not render a per-company response-time bar chart (no backing endpoint) and instead shows aggregate stats", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path.startsWith("/metrics/breakdown")) {
        return Promise.resolve(jsonResponse(emptyBreakdown()));
      }
      if (path === "/metrics/diagnostics") {
        return Promise.resolve(jsonResponse(emptyDiagnostics()));
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(
      <VisualizedTab
        funnel={null}
        rates={null}
        summary={{
          average_time_to_first_response: { application_count: 4, average_hours: 36 },
          average_time_to_rejection: { application_count: 2, average_hours: 96 },
          distinct_company_count: 3,
          evaluated_at: "2026-07-13T00:00:00Z",
          ghost_threshold_days: 21,
          ghosted_applications: 0,
          interview_invitation_count: 1,
          live_applications: 2,
          offers_received: 0,
          personal_ghost_threshold: {
            response_sample_size: 4,
            silence_age_distribution: [],
            silent_application_count: 1,
            threshold_days: 21,
            threshold_source: "response_percentile",
          },
          rejected_applications: 1,
          total_applications: 5,
          application_windows: [],
        }}
        timeseries={null}
      />,
    );

    expect(screen.getByText("1.5d")).toBeTruthy();
    expect(screen.getByText("4d")).toBeTruthy();
    expect(screen.getByText("Your personal ghost threshold")).toBeTruthy();
    expect(screen.getByText("21 days")).toBeTruthy();
    expect(screen.queryByText(/GET \/metrics\/response-times/)).toBeNull();

    await screen.findAllByText("Not enough data yet.");
  });
});
