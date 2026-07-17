import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MetricsRatesResponse, MetricsSummaryResponse } from "../../../api";
import { QuestionCatalogTab } from "./QuestionCatalogTab";

afterEach(() => {
  cleanup();
});

describe("QuestionCatalogTab", () => {
  it("marks Tier 1 and Tier 6 rows shipped, Tier 5 rows as on the Insights page, and Tier 7 rows planned", () => {
    render(<QuestionCatalogTab go={vi.fn()} rates={null} summary={null} />);

    expect(screen.getByText("50 of 54")).toBeTruthy();

    const q01 = screen.getByText("Q-01").closest("button");
    expect(q01).toBeTruthy();
    expect(within(q01 as HTMLElement).getByText("Shipped")).toBeTruthy();

    const q40 = screen.getByText("Q-40").closest("button");
    expect(within(q40 as HTMLElement).getByText("On Insights page")).toBeTruthy();

    const q47 = screen.getByText("Q-47").closest("button");
    expect(within(q47 as HTMLElement).getByText("Shipped")).toBeTruthy();

    const q51 = screen.getByText("Q-51").closest("button");
    expect(within(q51 as HTMLElement).getByText("Planned")).toBeTruthy();
  });

  it("expands a shipped row to show the real deterministic answer already loaded by OverviewPage, without a new fetch", () => {
    const summary: Partial<MetricsSummaryResponse> = { total_applications: 12 };
    render(
      <QuestionCatalogTab
        go={vi.fn()}
        rates={null}
        summary={summary as MetricsSummaryResponse}
      />,
    );

    fireEvent.click(screen.getByText("Q-01"));
    expect(screen.getByText("Current answer: 12")).toBeTruthy();
  });

  it("expands a Tier 5 row and navigates to the Insights page on click", () => {
    const go = vi.fn();
    render(<QuestionCatalogTab go={go} rates={null} summary={null} />);

    fireEvent.click(screen.getByText("Q-40"));
    fireEvent.click(screen.getByRole("button", { name: /See this on the Insights page/ }));
    expect(go).toHaveBeenCalledWith("insights");
  });

  it("expands a Tier 6 row and navigates to the shipped chat agent", () => {
    const go = vi.fn();
    render(<QuestionCatalogTab go={go} rates={null} summary={null} />);

    fireEvent.click(screen.getByText("Q-47"));
    expect(screen.getByText(/Answered by the grounded chat agent/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Ask this in chat" }));
    expect(go).toHaveBeenCalledWith("chat");
  });

  it("does not crash when summary and rates are partially populated (defensive against missing fields)", () => {
    const rates: Partial<MetricsRatesResponse> = {};
    render(
      <QuestionCatalogTab
        go={vi.fn()}
        rates={rates as MetricsRatesResponse}
        summary={{ total_applications: 1 } as MetricsSummaryResponse}
      />,
    );

    fireEvent.click(screen.getByText("Q-11"));
    expect(screen.getByText(/Answered from your applications and events data/)).toBeTruthy();
  });
});
