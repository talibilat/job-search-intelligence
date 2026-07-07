import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";

const baseApplication = {
  company: "Acme Corp",
  created_at: "2026-07-01T09:00:00Z",
  currency: null,
  current_status: "interview",
  first_seen_at: "2026-07-01T09:00:00Z",
  id: "app-1",
  last_activity_at: "2026-07-03T10:00:00Z",
  location: "Remote",
  manual_lock: false,
  role_title: "Backend Engineer",
  salary_max: 150000,
  salary_min: 120000,
  seniority: "senior",
  source: "linkedin",
  sponsorship: "unknown",
  tech_stack: ["Python", "FastAPI"],
  updated_at: "2026-07-03T10:01:00Z",
  work_mode: "remote",
};

function mockApplicationResponses() {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? `${input.pathname}${input.search}`
          : input.url;

    if (url === "/metrics/summary") {
      return Promise.resolve(
        new Response(JSON.stringify({ distinct_company_count: 1 }), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    }

    if (url === "/applications") {
      return Promise.resolve(
        new Response(JSON.stringify([baseApplication]), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    }

    if (url === "/applications?status=rejected") {
      return Promise.resolve(
        new Response(
          JSON.stringify([
            {
              ...baseApplication,
              company: "Globex",
              current_status: "rejected",
              id: "app-2",
              role_title: "Platform Engineer",
            },
          ]),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (url === "/applications?role=platform&status=rejected") {
      return Promise.resolve(
        new Response(
          JSON.stringify([
            {
              ...baseApplication,
              company: "Globex",
              current_status: "rejected",
              id: "app-2",
              role_title: "Platform Engineer",
            },
          ]),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      );
    }

    if (
      url === "/applications?status=applied" ||
      url === "/applications?status=in_review" ||
      url === "/applications?status=assessment" ||
      url === "/applications?status=interview"
    ) {
      return Promise.resolve(
        new Response(JSON.stringify([]), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    }

    throw new Error(`Unhandled fetch request: ${url}`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

describe("DashboardPage", () => {
  it("renders Q-09 application statuses and applies the status filter", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState({}, "", "/dashboard");

    render(<DashboardPage />);

    expect(await screen.findByText("Acme Corp")).toBeTruthy();
    const table = screen.getByRole("table", {
      name: "Application current statuses",
    });
    expect(table).toBeTruthy();
    expect(screen.getByText("Backend Engineer")).toBeTruthy();
    expect(within(table).getByText("Interview")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications",
      expect.objectContaining({ method: "GET" }),
    );

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "rejected" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    expect(await screen.findByText("Globex")).toBeTruthy();
    expect(within(table).getByText("Rejected")).toBeTruthy();
    expect(window.location.search).toBe("?status=rejected");
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications?status=rejected",
      expect.objectContaining({ method: "GET" }),
    );

    window.history.pushState({}, "", "/dashboard");
    window.dispatchEvent(new Event("popstate"));

    expect(await screen.findByText("Acme Corp")).toBeTruthy();
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "");
    expect(window.location.search).toBe("");
  });

  it("hydrates composed filters from the URL and clears them", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState(
      {},
      "",
      "/dashboard?status=rejected&role=platform",
    );

    render(<DashboardPage />);

    expect(await screen.findByText("Globex")).toBeTruthy();
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "rejected");
    expect(screen.getByLabelText("Role")).toHaveProperty("value", "platform");
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications?role=platform&status=rejected",
      expect.objectContaining({ method: "GET" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(await screen.findByText("Acme Corp")).toBeTruthy();
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "");
    expect(screen.getByLabelText("Role")).toHaveProperty("value", "");
    expect(window.location.search).toBe("");
  });

  it("canonicalizes invalid salary and enum query filters before loading", async () => {
    const fetchMock = mockApplicationResponses();
    window.history.pushState(
      {},
      "",
      "/dashboard?status=not-a-status&salary_min=abc",
    );

    render(<DashboardPage />);

    expect(await screen.findByText("Acme Corp")).toBeTruthy();
    expect(window.location.search).toBe("");
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "");
    expect(screen.getByLabelText("Salary min")).toHaveProperty("value", "");
    expect(fetchMock).toHaveBeenCalledWith(
      "/applications",
      expect.objectContaining({ method: "GET" }),
    );
  });
});
