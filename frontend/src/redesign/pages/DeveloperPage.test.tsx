import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DeveloperPage } from "./DeveloperPage";

afterEach(() => {
  cleanup();
});

describe("DeveloperPage", () => {
  it("shows which screen each backend surface is wired to, sourced from the feature status registry", () => {
    render(<DeveloperPage />);

    const syncRow = screen.getByText("Gmail sync").closest("span");
    expect(syncRow).toBeTruthy();
    expect(screen.getByText(/Wired to Overview/)).toBeTruthy();
  });

  it("shows the grounded chat screen after the chat surface is registered", () => {
    render(<DeveloperPage />);

    expect(screen.getByText("Wired to Grounded chat drawer")).toBeTruthy();
  });
});
