import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatCitationCards } from "./ChatCitationCards";

afterEach(cleanup);

describe("ChatCitationCards", () => {
  it("renders application metadata prominently and opens the application", () => {
    const onOpenApplication = vi.fn();
    render(
      <ChatCitationCards
        citations={[{
          application_id: "app-1",
          citation_id: "application:app-1",
          company: "Acme Labs",
          current_status: "in_review",
          first_seen_at: "2026-07-10T10:00:00Z",
          role_title: "Platform Engineer",
          source: "application",
        }]}
        onOpenApplication={onOpenApplication}
        onOpenEmail={vi.fn()}
      />,
    );

    expect(screen.getByText("Acme Labs")).toBeTruthy();
    expect(screen.getByText("Platform Engineer")).toBeTruthy();
    expect(screen.getByText("in review")).toBeTruthy();
    expect(screen.queryByText("Application record")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "View application" }));
    expect(onOpenApplication).toHaveBeenCalledWith("app-1");
  });

  it("renders a safe external web card and suppresses non-HTTPS links", () => {
    const { rerender } = render(
      <ChatCitationCards
        citations={[{
          citation_id: "web:1",
          snippet: "A current hiring update.",
          source: "web",
          web_domain: "example.com",
          web_title: "Hiring update",
          web_url: "https://example.com/jobs",
        }]}
        onOpenApplication={vi.fn()}
        onOpenEmail={vi.fn()}
      />,
    );

    const link = screen.getByRole("link", { name: "Open source" });
    expect(link.getAttribute("href")).toBe("https://example.com/jobs");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");

    rerender(
      <ChatCitationCards
        citations={[{
          citation_id: "web:2",
          source: "web",
          web_title: "Unsafe source",
          web_url: "javascript:alert(1)",
        }]}
        onOpenApplication={vi.fn()}
        onOpenEmail={vi.fn()}
      />,
    );
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("identifies an application card even when legacy citations lack metadata", () => {
    render(
      <ChatCitationCards
        citations={[{
          application_id: "app-legacy",
          citation_id: "application:app-legacy",
          source: "application",
        }]}
        onOpenApplication={vi.fn()}
        onOpenEmail={vi.fn()}
      />,
    );

    expect(screen.getByText("Application app-legacy")).toBeTruthy();
  });
});
