import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Insights } from "./Insights";

const insightTitles = [
  "Rejection themes",
  "Recurring recruiter feedback",
  "Rejected-role skill gaps",
  "Strongest and weakest signals",
  "Best-fit roles",
  "Next-week actions",
  "Search story",
] as const;

function mockFetch() {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    const path = url.startsWith("http") ? new URL(url).pathname : url;

    if (path === "/insights") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            insights: [
              {
                id: 1,
                type: "why_rejected",
                content:
                  "Rejections [especially final-round notes] repeatedly cite missing distributed systems depth. [application:app-1|event:event-1|email:email-1]",
                inputs_hash: "rejected-hash",
                is_stale: true,
                model: "llama3.1",
                generated_at: "2026-07-07T12:00:00+00:00",
              },
              {
                id: 2,
                type: "weekly_actions",
                content:
                  "1. Rewrite two project bullets around measurable backend impact. [application:app-2|event:event-2|email:email-2]\n2. Follow up with Beta LLC about the staff role. [application:app-3|event:event-3|email:email-3]\n3. Practice one system design story. [application:app-4|event:event-4|email:email-4]",
                inputs_hash: "actions-hash",
                is_stale: false,
                model: "llama3.1",
                generated_at: "2026-07-07T13:00:00+00:00",
              },
            ],
          }),
          { headers: { "Content-Type": "application/json" }, status: 200 },
        ),
      );
    }

    if (path === "/insights/regenerate") {
      expect(init).toEqual(
        expect.objectContaining({
          body: JSON.stringify({ type: "why_rejected" }),
          method: "POST",
        }),
      );
      return Promise.resolve(
        new Response(
          JSON.stringify({
            insight: {
              id: 3,
              type: "why_rejected",
              content:
                "Fresh rejection themes point to platform depth. [application:app-5|event:event-5|email:email-5]",
              inputs_hash: "fresh-rejected-hash",
              is_stale: false,
              model: "llama3.1",
              generated_at: "2026-07-07T14:00:00+00:00",
            },
            cached: false,
            evidence_citation_ids: [
              "application:app-5|event:event-5|email:email-5",
            ],
          }),
          { headers: { "Content-Type": "application/json" }, status: 200 },
        ),
      );
    }

    throw new Error(`Unhandled fetch request: ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Insights", () => {
  it("renders all cached insight cards with stale state, citations, and per-insight regeneration", async () => {
    const fetchMock = mockFetch();

    render(<Insights />);

    expect(await screen.findByText("7 Tier 5 insights")).toBeTruthy();
    expect(screen.getByText("2 cached")).toBeTruthy();
    expect(screen.getByText("1 stale")).toBeTruthy();

    for (const title of insightTitles) {
      expect(screen.getByText(title)).toBeTruthy();
    }

    expect(screen.getByText("Stale cache")).toBeTruthy();
    expect(
      screen.getByText(
        "Rejections [especially final-round notes] repeatedly cite missing distributed systems depth.",
      ),
    ).toBeTruthy();
    expect(
      screen
        .getByRole("link", {
          name: "application:app-1|event:event-1|email:email-1",
        })
        .getAttribute("href"),
    ).toBe("/applications/app-1");
    expect(
      screen.getByText(
        "No cached recurring recruiter feedback insight yet. Regenerate it after the source timeline has enough evidence.",
      ),
    ).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", { name: "Regenerate Rejection themes" }),
    );

    expect(
      await screen.findByText("Fresh rejection themes point to platform depth."),
    ).toBeTruthy();
    expect(screen.queryByText("Stale cache")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/insights/regenerate",
      expect.objectContaining({
        body: JSON.stringify({ type: "why_rejected" }),
        method: "POST",
      }),
    );
  });
});
