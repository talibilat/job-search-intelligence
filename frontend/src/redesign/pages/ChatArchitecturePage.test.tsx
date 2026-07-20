import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ChatArchitecturePage } from "./ChatArchitecturePage";
import { redesignRouteFromPath } from "../RedesignApp";

afterEach(() => cleanup());

describe("ChatArchitecturePage", () => {
  it("is available through the dedicated chat architecture route", () => {
    expect(redesignRouteFromPath("/chat/architecture")?.page).toBe("chatArchitecture");
  });

  it("documents the chat-only execution path and function contracts", () => {
    render(<ChatArchitecturePage />);

    expect(screen.getByText("Every function.")).toBeTruthy();
    expect(screen.getAllByText("ChatDrawer.ask").length).toBeGreaterThan(0);
    expect(screen.getAllByText("question: string, retryTurn?: PendingTurn").length).toBeGreaterThan(0);
    expect(screen.getByText(/FR-5.1 through FR-5.6/)).toBeTruthy();
  });

  it("switches feature tabs and advances through intermediate functions", () => {
    render(<ChatArchitecturePage />);

    fireEvent.click(screen.getByRole("tab", { name: /Retrieval/ }));
    expect(screen.getByRole("heading", { name: "Email recall with exact source evidence" })).toBeTruthy();
    expect(screen.getAllByText("ChatIndexService.reconcile").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Next step →" }));
    expect(screen.getByRole("heading", { name: "Choose retrieval" })).toBeTruthy();
    expect(screen.getByText("Next: Search")).toBeTruthy();
  });
});
