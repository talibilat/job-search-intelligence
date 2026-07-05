import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import styles from "./index.css?raw";

function renderAtPath(pathname: string) {
  window.history.pushState({}, "", pathname);
  return render(<App />);
}

type MockResponseBody = Record<string, unknown>;

type MockResponse =
  | MockResponseBody
  | {
      body: MockResponseBody;
      status: number;
    };

type MockResponseConfig = MockResponse | MockResponse[];

function isMockResponseConfig(
  value: MockResponse,
): value is { body: object; status: number } {
  return "body" in value && "status" in value;
}

function mockFetchResponses(responses: Record<string, MockResponseConfig>) {
  const responseQueues = new Map<string, MockResponse[]>();

  for (const [path, response] of Object.entries(responses)) {
    responseQueues.set(
      path,
      Array.isArray(response) ? [...response] : [response],
    );
  }

  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    const path = url.startsWith("http") ? new URL(url).pathname : url;
    const config = responseQueues.get(path);

    if (!config) {
      throw new Error(`Unhandled fetch request: ${path}`);
    }

    const nextConfig = config.length > 1 ? config.shift() : config[0];

    if (!nextConfig) {
      throw new Error(`No mock fetch responses left for: ${path}`);
    }

    const body = isMockResponseConfig(nextConfig)
      ? nextConfig.body
      : nextConfig;
    const status = isMockResponseConfig(nextConfig) ? nextConfig.status : 200;

    return Promise.resolve(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status,
      }),
    );
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

describe("App", () => {
  it("renders the insights page shell on the insights route", () => {
    window.history.pushState({}, "", "/insights");

    render(<App />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Insights" }),
    ).toBeTruthy();
    expect(
      screen.getByText("Narrative insights are not generated yet."),
    ).toBeTruthy();
  });

  it("shows a chart foundation empty state without implementing dashboard metrics", () => {
    renderAtPath("/");

    expect(
      screen.getByRole("region", { name: "Chart foundation" }),
    ).toBeTruthy();

    const emptyState = screen.getByRole("status", {
      name: "Dashboard data pending",
    });

    expect(emptyState.textContent).toContain(
      "Future deterministic dashboard metrics will render here after the metrics API exists.",
    );
  });

  it("starts manual sync from the overview page and renders the returned status", async () => {
    const fetchMock = mockFetchResponses({
      "/sync/status": {
        state: "idle",
      },
      "/sync": {
        account_id: "me@example.com",
        finished_at: "2026-07-05T12:00:00Z",
        last_error: null,
        message_count: 2,
        mode: "full_backfill",
        page_count: 1,
        provider: "gmail",
        raw_email_count: 2,
        recovered_from_expired_cursor: false,
        started_at: "2026-07-05T12:00:00Z",
        state: "succeeded",
      },
    });

    renderAtPath("/");

    expect(await screen.findByText("Current sync state: Idle")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    expect(await screen.findByText("Last sync succeeded")).toBeTruthy();
    expect(screen.getByText("2 messages")).toBeTruthy();
    expect(screen.getByText("2 raw emails")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/sync",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows typed sync API errors when manual sync cannot start", async () => {
    mockFetchResponses({
      "/sync/status": {
        state: "idle",
      },
      "/sync": {
        body: {
          error: {
            code: "bad_request",
            details: [],
            message: "Gmail connection is not configured yet.",
          },
        },
        status: 400,
      },
    });

    renderAtPath("/");

    fireEvent.click(await screen.findByRole("button", { name: "Sync now" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Gmail connection is not configured yet.",
    );
  });

  it("refreshes running sync status until the sync action is available again", async () => {
    mockFetchResponses({
      "/sync/status": [
        {
          message_count: 1,
          raw_email_count: 1,
          state: "running",
        },
        {
          finished_at: "2026-07-05T12:00:00Z",
          message_count: 3,
          raw_email_count: 3,
          state: "succeeded",
        },
      ],
    });

    renderAtPath("/");

    expect(await screen.findByText("Sync is running")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Syncing" })).toHaveProperty(
      "disabled",
      true,
    );

    expect(
      await screen.findByText("Last sync succeeded", {}, { timeout: 4000 }),
    ).toBeTruthy();
    expect(screen.getByText("3 messages")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sync now" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("renders the first-run setup shell at /setup", () => {
    window.history.pushState({}, "", "/setup");

    render(<App />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Set up JobTracker locally",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("navigation", { name: "Primary" }).textContent,
    ).toContain("Setup");
    expect(
      screen.getByRole("region", { name: "Setup checklist" }),
    ).toBeTruthy();
    expect(screen.getByText("Choose provider")).toBeTruthy();
    expect(screen.getByText("Connect Gmail read-only")).toBeTruthy();
  });

  it("starts Gmail OAuth from the setup page and exposes the read-only authorization link", async () => {
    const fetchMock = mockFetchResponses({
      "/setup/status": {
        classification_mode: "local",
        email_provider: "gmail",
        gmail_connected: false,
        llm_configured: false,
        llm_provider: "ollama",
        setup_complete: false,
      },
      "/auth/gmail": {
        authorization_url:
          "https://accounts.google.com/o/oauth2/v2/auth?state=issued-state",
        provider: "gmail",
        requested_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
        state: "issued-state",
      },
    });

    renderAtPath("/setup");

    fireEvent.click(
      await screen.findByRole("button", { name: "Start Gmail OAuth" }),
    );

    const googleLink = await screen.findByRole("link", {
      name: "Continue to Google",
    });

    expect(googleLink.getAttribute("href")).toBe(
      "https://accounts.google.com/o/oauth2/v2/auth?state=issued-state",
    );
    expect(
      screen.getByText(
        "Requested scope: https://www.googleapis.com/auth/gmail.readonly",
      ),
    ).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/auth/gmail",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("shows Gmail callback completion when setup status reports a connection", async () => {
    mockFetchResponses({
      "/setup/status": {
        classification_mode: "local",
        email_provider: "gmail",
        gmail_connected: true,
        llm_configured: false,
        llm_provider: "ollama",
        setup_complete: false,
      },
    });

    renderAtPath("/setup");

    expect(await screen.findByText("Gmail callback complete")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Gmail connected" }),
    ).toHaveProperty("disabled", true);
  });

  it("renders the empty chat shell at the chat route", () => {
    window.history.pushState({}, "", "/chat");

    render(<App />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /ask your job search history/i,
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("main", { name: /ask your job search history/i }),
    ).toBeTruthy();
    expect(screen.getByRole("textbox", { name: /message/i })).toHaveProperty(
      "disabled",
      true,
    );
    expect(
      screen.getByText(/chat agent work arrives in phase 5/i),
    ).toBeTruthy();
  });

  it("keeps the chat shell constrained on narrow mobile viewports", () => {
    expect(styles).toContain(".chat-hero h1");
    expect(styles).toContain("font-size: clamp(2rem, 9vw, 2.45rem)");
    expect(styles).toContain("width: min(100%, 390px)");
    expect(styles).toContain("margin: 0 auto 0 0");
    expect(styles).toContain(".chat-panel");
    expect(styles).toContain("padding: 18px");
    expect(styles).toContain(".chat-card");
    expect(styles).toContain("padding: 20px");
  });

  it("renders an empty dashboard page shell at the dashboard route", () => {
    renderAtPath("/dashboard");

    expect(screen.getByRole("main", { name: "Dashboard" })).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 1, name: "Dashboard" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("region", { name: "Dashboard filters" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("region", { name: "Metrics overview" }),
    ).toBeTruthy();

    const emptyState = screen.getByRole("status", {
      name: "Dashboard metrics pending",
    });

    expect(emptyState.textContent).toContain(
      "Deterministic metrics will appear here after the metrics API is available.",
    );
  });
});
