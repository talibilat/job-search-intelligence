import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("shows a chart foundation empty state without implementing dashboard metrics", () => {
    render(<App />);

    expect(screen.getByRole("region", { name: "Chart foundation" })).toBeTruthy();

    const emptyState = screen.getByRole("status", {
      name: "Dashboard data pending",
    });

    expect(emptyState.textContent).toContain(
      "Future deterministic dashboard metrics will render here after the metrics API exists.",
    );
  });
});
