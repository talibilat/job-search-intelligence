import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Insights } from "./Insights";
import { renderTextWithCitationLinks } from "./insightDisplay";

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
            regeneration_cost_estimates: [
              {
                type: "why_rejected",
                cost: {
                  estimated_prompt_tokens: 315,
                  estimated_completion_tokens: 1200,
                  estimated_total_tokens: 1515,
                  estimated_cost_usd: 2.715,
                  actual_prompt_tokens: null,
                  actual_completion_tokens: null,
                  actual_total_tokens: null,
                  actual_cost_usd: null,
                  currency: "USD",
                  cost_estimate_available: true,
                  token_estimate_method:
                    "ceil(insight prompt characters / 10) + configured max output tokens",
                },
              },
              {
                type: "recurring_feedback",
                cost: {
                  estimated_prompt_tokens: 100,
                  estimated_completion_tokens: 1200,
                  estimated_total_tokens: 1300,
                  estimated_cost_usd: 0.42,
                  actual_prompt_tokens: null,
                  actual_completion_tokens: null,
                  actual_total_tokens: null,
                  actual_cost_usd: null,
                  currency: "USD",
                  cost_estimate_available: true,
                  token_estimate_method:
                    "ceil(insight prompt characters / 10) + configured max output tokens",
                },
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
            cost: {
              estimated_prompt_tokens: 315,
              estimated_completion_tokens: 1200,
              estimated_total_tokens: 1515,
              estimated_cost_usd: 2.715,
              actual_prompt_tokens: 80,
              actual_completion_tokens: 20,
              actual_total_tokens: 100,
              actual_cost_usd: 0.12,
              currency: "USD",
              cost_estimate_available: true,
              token_estimate_method:
                "ceil(insight prompt characters / 10) + configured max output tokens",
            },
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
  it("does not link unsafe application citation IDs", () => {
    const { container } = render(
      <p>
        {renderTextWithCitationLinks(
          "Review the cited application. [application:app/1|event:event-1|email:email-1]",
        )}
      </p>,
    );

    expect(container.textContent).toContain(
      "[application:app/1|event:event-1|email:email-1]",
    );
    expect(
      screen.queryByRole("link", {
        name: "application:app/1|event:event-1|email:email-1",
      }),
    ).toBeNull();
  });

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
    expect(screen.getByText("Estimated cost $2.715")).toBeTruthy();
    expect(screen.getByText("1,515 estimated tokens")).toBeTruthy();
    expect(screen.getByText("Estimated cost $0.42")).toBeTruthy();
    expect(screen.queryByText("Actual cost $0.12")).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: "Regenerate Rejection themes" }),
    );

    expect(
      await screen.findByText("Fresh rejection themes point to platform depth."),
    ).toBeTruthy();
    expect(screen.getByText("Estimated cost $2.715")).toBeTruthy();
    expect(screen.getByText("Actual cost $0.12")).toBeTruthy();
    expect(screen.getByText("100 actual tokens")).toBeTruthy();
    expect(screen.queryByText("Stale cache")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/insights/regenerate",
      expect.objectContaining({
        body: JSON.stringify({ type: "why_rejected" }),
        method: "POST",
      }),
    );
  });

  it("explains cached insight generation through an accessible info control", async () => {
    mockFetch();

    render(<Insights />);

    await screen.findByText("7 Tier 5 insights");

    const rejectionThemesInfo = screen.getByRole("button", {
      name: "About Rejection themes",
    });
    expect(rejectionThemesInfo.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(rejectionThemesInfo);

    expect(rejectionThemesInfo.getAttribute("aria-expanded")).toBe("true");
    expect(
      screen.getByText(
        "Data source: GET /insights and POST /insights/regenerate",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Table: insights plus cited applications, application_events, and raw_emails",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Builds deterministic cited rejection evidence first, then asks the configured LLM for cached narrative synthesis only when regeneration is requested.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "If this insight is empty, sync Gmail, run classification to create rejected applications with cited evidence, configure an LLM provider, then regenerate Rejection themes.",
      ),
    ).toBeTruthy();

    fireEvent.click(rejectionThemesInfo);
    expect(rejectionThemesInfo.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(rejectionThemesInfo);
    expect(rejectionThemesInfo.getAttribute("aria-expanded")).toBe("false");
  });

  it("disables regeneration when cached insights fail to load", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const path = url.startsWith("http") ? new URL(url).pathname : url;

      if (path === "/insights") {
        return Promise.resolve(new Response("{}", { status: 503 }));
      }

      throw new Error(`Unhandled fetch request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Insights />);

    expect(
      await screen.findByText(
        "Insights are unavailable. Start the local backend and try again.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Regeneration is disabled until cached insights load from the local backend.",
      ),
    ).toBeTruthy();

    const regenerateButton = screen.getByRole("button", {
      name: "Regenerate Rejection themes",
    });
    expect(regenerateButton).toHaveProperty("disabled", true);

    fireEvent.click(regenerateButton);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("explains why other regenerate actions are disabled during regeneration", async () => {
    const pendingRegeneration = {
      resolve: null as ((value: Response) => void) | null,
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
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
              insights: [],
              regeneration_cost_estimates: [],
            }),
            { headers: { "Content-Type": "application/json" }, status: 200 },
          ),
        );
      }

      if (path === "/insights/regenerate") {
        return new Promise<Response>((resolve) => {
          pendingRegeneration.resolve = resolve;
        });
      }

      throw new Error(`Unhandled fetch request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Insights />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Regenerate Rejection themes" }),
    );

    expect(
      await screen.findByText(
        "Regeneration is in progress. Other regenerate actions are disabled until it finishes.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: "Regenerate Recurring recruiter feedback",
      }),
    ).toHaveProperty("disabled", true);

    pendingRegeneration.resolve?.(
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
          cost: {
            estimated_prompt_tokens: 315,
            estimated_completion_tokens: 1200,
            estimated_total_tokens: 1515,
            estimated_cost_usd: 2.715,
            actual_prompt_tokens: 80,
            actual_completion_tokens: 20,
            actual_total_tokens: 100,
            actual_cost_usd: 0.12,
            currency: "USD",
            cost_estimate_available: true,
            token_estimate_method:
              "ceil(insight prompt characters / 10) + configured max output tokens",
          },
        }),
        { headers: { "Content-Type": "application/json" }, status: 200 },
      ),
    );
  });
});
