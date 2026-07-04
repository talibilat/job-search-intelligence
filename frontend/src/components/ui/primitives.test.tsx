import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FormField, Tabs, TextInput } from "./primitives";

describe("FormField", () => {
  it("uses one id for the label target and child control", () => {
    render(
      <FormField htmlFor="company-filter" label="Company">
        <TextInput id="stale-id" name="company" />
      </FormField>,
    );

    const input = screen.getByLabelText("Company");

    expect(input.id).toBe("company-filter");
  });
});

describe("Tabs", () => {
  it("renders every tab panel referenced by aria-controls", () => {
    render(
      <Tabs
        label="Application views"
        items={[
          { id: "summary", label: "Summary", content: <p>Summary metrics</p> },
          { id: "events", label: "Events", content: <p>Application events</p> },
        ]}
      />,
    );

    const tabs = screen.getAllByRole("tab");

    for (const tab of tabs) {
      const controlledPanelId = tab.getAttribute("aria-controls");

      expect(controlledPanelId).toBeTruthy();
      expect(document.getElementById(controlledPanelId ?? "")).not.toBeNull();
    }
  });
});
