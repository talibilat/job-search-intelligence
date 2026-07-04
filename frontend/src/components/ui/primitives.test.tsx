import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Alert, DataTable, FormField, Tabs, TextInput, type DataTableColumn } from "./primitives";

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

describe("Alert", () => {
  it("does not make static non-danger tones live regions by default", () => {
    for (const tone of ["info", "success", "warning"] as const) {
      const { container, unmount } = render(
        <Alert title="Status" tone={tone}>
          Static message
        </Alert>,
      );

      expect(container.firstElementChild?.getAttribute("role")).toBeNull();
      unmount();
    }
  });

  it("uses alert for danger and lets callers opt into status", () => {
    const { container, rerender } = render(
      <Alert title="Failed" tone="danger">
        Sync failed
      </Alert>,
    );

    expect(container.firstElementChild?.getAttribute("role")).toBe("alert");

    rerender(
      <Alert role="status" title="Saved" tone="success">
        Settings saved
      </Alert>,
    );

    expect(container.firstElementChild?.getAttribute("role")).toBe("status");
  });
});

describe("DataTable", () => {
  it("throws when a non-scalar cell has no renderer", () => {
    interface RowWithDetails {
      details: { status: string };
    }

    const columns = [
      { key: "details", header: "Details" },
    ] as unknown as DataTableColumn<RowWithDetails>[];

    expect(() =>
      render(
        <DataTable
          caption="Applications"
          columns={columns}
          rowKey={() => "row-1"}
          rows={[{ details: { status: "applied" } }]}
        />,
      ),
    ).toThrow("DataTable columns for non-scalar values must define render.");
  });
});
