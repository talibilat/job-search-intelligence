import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChartPanel } from "./ChartPanel";

const chartInfo = {
  dataSource: "GET /metrics/example",
  dataTable: "applications",
  howItWorks: "Counts local applications deterministically.",
  howToGenerate: "Run sync, classification, and aggregation.",
  missingData: "Check the upstream pipeline stages.",
};

describe("ChartPanel", () => {
  it("reveals info guidance on keyboard focus and hides it on blur", () => {
    render(
      <ChartPanel
        description="Example deterministic chart"
        info={chartInfo}
        title="Example metric"
      />,
    );

    const infoControl = screen.getByRole("button", {
      name: "About Example metric",
    });

    expect(screen.queryByText("How this chart works")).toBeNull();

    fireEvent.focus(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("How this chart works")).toBeTruthy();

    fireEvent.blur(infoControl);

    expect(infoControl.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("How this chart works")).toBeNull();
  });
});
