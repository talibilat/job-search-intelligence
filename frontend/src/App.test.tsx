import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
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

  it("shows sync status progress, counts, last run, and starts manual sync", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const path = url.startsWith("http") ? new URL(url).pathname : url;
      const body =
        path === "/sync"
          ? {
              account_id: "talib@example.test",
              finished_at: null,
              last_error: null,
              message_count: 2600,
              mode: "incremental",
              page_count: 13,
              provider: "gmail",
              raw_email_count: 1305,
              recovered_from_expired_cursor: false,
              started_at: "2026-07-05T10:00:00Z",
              state: "running",
            }
          : path === "/sync/status"
            ? {
                account_id: "talib@example.test",
                finished_at: "2026-07-05T09:45:30Z",
                last_error: null,
                message_count: 2500,
                mode: "full_backfill",
                page_count: 12,
                provider: "gmail",
                raw_email_count: 1240,
                recovered_from_expired_cursor: true,
                started_at: "2026-07-05T09:15:00Z",
                state: "succeeded",
              }
            : null;

      if (!body) {
        throw new Error(`Unhandled fetch request: ${path}`);
      }

      expect(path === "/sync" ? init?.method : "GET").toBe(
        path === "/sync" ? "POST" : "GET",
      );

      return Promise.resolve(
        new Response(JSON.stringify(body), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/");

    expect(await screen.findByText("Last sync succeeded")).toBeTruthy();
    expect(screen.getByText("1,240 raw emails")).toBeTruthy();
    expect(screen.getByText("2,500 messages")).toBeTruthy();
    expect(screen.getByText("12 pages")).toBeTruthy();
    expect(screen.getByText("Finished Jul 5, 2026, 9:45 AM UTC")).toBeTruthy();
    expect(screen.getByText("Recovered expired cursor")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/sync/status",
      expect.objectContaining({ method: "GET" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    expect(await screen.findByText("Sync is running")).toBeTruthy();
    expect(screen.getByText("1,305 raw emails")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/sync",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows public sync status API errors instead of idle progress", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const path = url.startsWith("http") ? new URL(url).pathname : url;

      expect(path).toBe("/sync/status");
      expect(init?.method).toBe("GET");

      return Promise.resolve(
        new Response(
          JSON.stringify({
            error: {
              code: "email_authorization_required",
              details: [],
              message: "Reconnect Gmail before syncing.",
            },
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 401,
          },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/");

    expect(
      await screen.findByText("Reconnect Gmail before syncing."),
    ).toBeTruthy();
    expect(screen.queryByText("No sync run yet")).toBeNull();
  });

  it("refreshes running sync status until the latest run completes", async () => {
    vi.useFakeTimers();
    const runningStatus = {
      account_id: "talib@example.test",
      finished_at: null,
      last_error: null,
      message_count: 2600,
      mode: "incremental",
      page_count: 13,
      provider: "gmail",
      raw_email_count: 1305,
      recovered_from_expired_cursor: false,
      started_at: "2026-07-05T10:00:00Z",
      state: "running",
    };
    const completedStatus = {
      ...runningStatus,
      finished_at: "2026-07-05T10:05:00Z",
      message_count: 2700,
      page_count: 14,
      raw_email_count: 1325,
      state: "succeeded",
    };
    const statusResponses = [runningStatus, completedStatus];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const path = url.startsWith("http") ? new URL(url).pathname : url;

      expect(path).toBe("/sync/status");
      expect(init?.method).toBe("GET");

      return Promise.resolve(
        new Response(JSON.stringify(statusResponses.shift()), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAtPath("/");

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("Sync is running")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sync running" })).toHaveProperty(
      "disabled",
      true,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(screen.getByText("Last sync succeeded")).toBeTruthy();
    expect(screen.getByText("1,325 raw emails")).toBeTruthy();
    expect(screen.getByText("2,700 messages")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sync now" })).toHaveProperty(
      "disabled",
      false,
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
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
        recommended_classification_mode: "local",
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
        recommended_classification_mode: "local",
        setup_complete: false,
      },
    });

    renderAtPath("/setup");

    expect(await screen.findByText("Gmail callback complete")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Gmail connected" }),
    ).toHaveProperty("disabled", true);
  });

  it("preselects the recommended classification mode in setup", async () => {
    mockFetchResponses({
      "/setup/status": {
        classification_mode: "llm",
        email_provider: "gmail",
        gmail_connected: false,
        llm_configured: false,
        llm_provider: "azure_openai",
        recommended_classification_mode: "hybrid",
        setup_complete: false,
      },
    });

    renderAtPath("/setup");

    const hybridMode = await screen.findByRole("radio", {
      name: /hybrid/i,
    });

    await waitFor(() => {
      expect(hybridMode).toHaveProperty("checked", true);
    });
    expect(
      screen.getByText("Preselected from Azure OpenAI setup"),
    ).toBeTruthy();
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
