import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { InsightRecord, InsightType } from "../../api";
import { InsightsPage } from "./InsightsPage";

function insight(type: InsightType, overrides: Partial<InsightRecord> = {}): InsightRecord {
  return {
    citations: [],
    content: `${type} content`,
    generated_at: "2026-07-11T12:00:00Z",
    id: 1,
    inputs_hash: `hash-${type}`,
    is_stale: false,
    model: "local-model",
    type,
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });
}

function deferredResponse() {
  let resolve: (response: Response) => void = () => undefined;
  const promise = new Promise<Response>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("InsightsPage", () => {
  it("shows loading and typed initial failure instead of no insights", async () => {
    const pending = deferredResponse();
    vi.stubGlobal("fetch", vi.fn(() => pending.promise));
    render(<InsightsPage openApp={() => undefined} reloadKey={0} />);

    expect(screen.getByText("Loading insights…")).toBeTruthy();
    expect(screen.queryByText(/No insights yet/)).toBeNull();
    pending.resolve(jsonResponse({ error: { code: "insights_failed", details: [], message: "Insight cache is unavailable." } }, 503));
    expect((await screen.findByRole("alert")).textContent).toContain("Insight cache is unavailable.");
    expect(screen.queryByText(/No insights yet/)).toBeNull();
  });
  it("presents Q-40 through Q-46 in order without inferred-evidence claims", async () => {
    const types: InsightType[] = [
      "why_rejected",
      "recurring_feedback",
      "skill_gaps",
      "strongest_weakest_signals",
      "role_fit",
      "weekly_actions",
      "story",
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({
            insights: types.map((type, index) => insight(type, { id: index + 1 })),
            regeneration_cost_estimates: [],
          }),
        ),
      ),
    );

    render(<InsightsPage openApp={() => undefined} reloadKey={0} />);

    const questions = await screen.findAllByText(/^Q-4[0-6]/);
    expect(questions.map((question) => question.textContent?.slice(0, 4))).toEqual([
      "Q-40",
      "Q-41",
      "Q-42",
      "Q-43",
      "Q-44",
      "Q-45",
      "Q-46",
    ]);
    expect(screen.getByRole("heading", { name: "Rejection themes" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Recurring recruiter feedback" })).toBeTruthy();
    expect(document.body.textContent?.toLowerCase()).not.toContain("inferred reasons");
  });

  it("generates the first insight from an empty cache", async () => {
    const generated = insight("why_rejected", {
      content: "Generated rejection evidence.",
    });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/insights") {
        return Promise.resolve(
          jsonResponse({ insights: [], regeneration_cost_estimates: [] }),
        );
      }
      if (path === "/insights/regenerate") {
        const body = init?.body;
        if (typeof body !== "string") {
          throw new Error("Expected a JSON request body.");
        }
        expect(JSON.parse(body)).toEqual({ type: "why_rejected" });
        return Promise.resolve(
          jsonResponse({
            cached: false,
            cost: {
              cost_estimate_available: false,
              estimated_completion_tokens: 0,
              estimated_prompt_tokens: 0,
              estimated_total_tokens: 0,
              token_estimate_method: "unavailable",
            },
            evidence_citation_ids: [],
            insight: generated,
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<InsightsPage openApp={() => undefined} reloadKey={0} />);

    expect(await screen.findByRole("heading", { name: "Rejection themes" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Generate insight" })).toHaveLength(7);
    fireEvent.click(screen.getAllByRole("button", { name: "Generate insight" })[0]);

    expect(await screen.findByText("Generated rejection evidence.")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Generate insight" })).toHaveLength(6);
    expect(
      fetchMock.mock.calls.filter(([input]) => input === "/insights/regenerate"),
    ).toHaveLength(1);
  });

  it("keeps cached content, blocks repeat regeneration, and shows typed failures", async () => {
    const pending = deferredResponse();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/insights") {
        return Promise.resolve(
          jsonResponse({
            insights: [
              insight("why_rejected", {
                content: "Cached rejection evidence remains visible.",
                is_stale: true,
              }),
            ],
            regeneration_cost_estimates: [],
          }),
        );
      }
      if (path === "/insights/regenerate") return pending.promise;
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<InsightsPage openApp={() => undefined} reloadKey={0} />);

    const regenerate = await screen.findByRole("button", { name: "Rewrite with latest data" });
    fireEvent.click(regenerate);
    fireEvent.click(regenerate);
    expect(regenerate).toHaveProperty("disabled", true);
    expect(screen.getByText("Cached rejection evidence remains visible.")).toBeTruthy();
    expect(
      fetchMock.mock.calls.filter(([input]) => input === "/insights/regenerate"),
    ).toHaveLength(1);

    pending.resolve(
      jsonResponse(
        {
          error: {
            code: "llm_provider_unavailable",
            details: [],
            message: "The configured model is unavailable.",
          },
        },
        503,
      ),
    );
    expect((await screen.findByRole("alert")).textContent).toContain(
      "The configured model is unavailable.",
    );
    expect(screen.getByText("Cached rejection evidence remains visible.")).toBeTruthy();
  });

  it("replaces only a successful type and opens only valid citation records", async () => {
    const openApp = vi.fn();
    const original = insight("role_fit", {
      citations: [
        {
          application_id: "app-1",
          citation_id: "application:app-1|email:email-1",
          company: "Acme",
          email_id: "email-1",
          email_subject: "Interview follow-up",
          role_title: "Platform Engineer",
        },
        {
          application_id: "bad/id",
          citation_id: "application:bad/id|email:email-2",
          company: "Unsafe Co",
          email_id: "email-2",
          email_subject: "Malformed destination",
          role_title: "Engineer",
        },
      ],
      content: "Original role evidence.",
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/insights") {
        return Promise.resolve(
          jsonResponse({ insights: [original], regeneration_cost_estimates: [] }),
        );
      }
      if (path === "/insights/regenerate") {
        return Promise.resolve(
          jsonResponse({
            cached: false,
            cost: {
              cost_estimate_available: false,
              estimated_completion_tokens: 0,
              estimated_prompt_tokens: 0,
              estimated_total_tokens: 0,
              token_estimate_method: "unavailable",
            },
            evidence_citation_ids: ["application:app-1|email:email-1"],
            insight: { ...original, content: "Updated role evidence.", id: 2 },
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<InsightsPage openApp={openApp} reloadKey={0} />);

    const card = (await screen.findByRole("heading", { name: "Best-fit roles" })).parentElement
      ?.parentElement?.parentElement;
    expect(card).toBeTruthy();
    fireEvent.click(within(card!).getByRole("button", { name: "Rewrite with latest data" }));
    expect(await screen.findByText("Updated role evidence.")).toBeTruthy();
    expect(screen.queryByText("Original role evidence.")).toBeNull();

    expect(screen.getByText(/Unsafe Co/).closest("button")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Acme.*Interview follow-up/ }));
    expect(openApp).toHaveBeenCalledOnce();
    expect(openApp).toHaveBeenCalledWith("app-1");
  });
});
