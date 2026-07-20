import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProviderConfigResponse } from "../api";
import { ProviderSetup } from "./ProviderSetup";

const config: ProviderConfigResponse = {
  email_providers: [],
  llm_providers: [],
  recommended_classification_mode: "local",
  selection: {
    classification_mode: "local",
    email_provider: "gmail",
    llm_provider: "ollama",
  },
  settings: {
    azure_openai_api_version: "2024-06-01",
    azure_openai_chat_deployment: "",
    azure_openai_embedding_deployment: "",
    azure_openai_endpoint: "",
    gmail_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
    ollama_base_url: "http://127.0.0.1:11434",
    ollama_chat_model: "llama3.1",
    ollama_embedding_model: "nomic-embed-text",
    sync_interval_seconds: 900,
    sync_on_open: true,
    tavily_base_url: "https://api.tavily.com",
    web_search_enabled: false,
    web_search_max_results: 5,
    web_search_provider: "tavily",
    web_search_timeout_seconds: 15,
  },
};

const readiness = {
  chat_generation: { action: null, message: "Not implemented.", state: "not_implemented" },
  classification_generation: {
    action: "Start Ollama.",
    message: "Classification unavailable.",
    state: "unavailable",
  },
  embedding_generation: {
    action: "Pull the model.",
    message: "Embedding unavailable.",
    state: "unavailable",
  },
  gmail_sync: {
    action: "Enter the downloaded Desktop OAuth client JSON.",
    message: "Google Desktop OAuth client JSON is required.",
    state: "missing_credential",
  },
  ready_to_classify: false,
  ready_to_sync: false,
  web_search: {
    action: "Enable web search and enter a Tavily API key.",
    message: "Web search is disabled.",
    state: "missing_config",
  },
};

const healthyProvider = {
  checks: [
    { detail: null, kind: "chat", model: "llama3.1", status: "available" },
    { detail: null, kind: "embedding", model: "nomic-embed-text", status: "available" },
  ],
  provider_name: "ollama",
  status: "available",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ProviderSetup", () => {
  it("keeps Azure API endpoints and credentials out of frontend settings", () => {
    const azureConfig: ProviderConfigResponse = {
      ...config,
      recommended_classification_mode: "hybrid",
      selection: {
        ...config.selection,
        classification_mode: "hybrid",
        llm_provider: "azure_openai",
      },
    };

    render(<ProviderSetup autoLoad={false} initialConfig={azureConfig} />);

    expect(screen.queryByLabelText("Azure endpoint")).toBeNull();
    expect(screen.queryByLabelText("Azure API key")).toBeNull();
    expect(screen.getByText(/AI API endpoints and credentials are configured in the backend/)).toBeTruthy();
  });

  it("checks provider health after saving and confirms the API connection", async () => {
    const requests: { method: string; path: string }[] = [];
    const timeoutSpy = vi.spyOn(window, "setTimeout");
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      requests.push({ method: init?.method ?? "GET", path });
      if (path === "/config/providers/llm/health") {
        return Promise.resolve(new Response(JSON.stringify(healthyProvider), { status: 200 }));
      }
      if (path === "/config/providers/readiness") {
        return Promise.resolve(new Response(JSON.stringify(readiness), { status: 200 }));
      }
      if (path === "/config/providers") {
        return Promise.resolve(new Response(JSON.stringify(config), { status: 200 }));
      }
      throw new Error(`Unexpected request: ${path}`);
    }));

    render(<ProviderSetup autoLoad={false} initialConfig={config} />);
    fireEvent.click(screen.getByRole("button", { name: "Save provider setup" }));

    expect(
      (await screen.findByRole("status", { name: "API connection status" })).textContent,
    ).toBe("API connected");
    expect(requests.map(({ method, path }) => `${method} ${path}`)).toContain(
      "POST /config/providers/llm/health",
    );
    const dismiss = timeoutSpy.mock.calls.find((call) => call[1] === 3000)?.[0];
    expect(dismiss).toBeTypeOf("function");
    act(() => dismiss?.());
    expect(screen.queryByRole("status", { name: "API connection status" })).toBeNull();
  });

  it("shows actionable readiness and submits credentials only in the write request", async () => {
    const requests: { body: string | null; path: string }[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      requests.push({ body: typeof init?.body === "string" ? init.body : null, path });
      if (path === "/config/providers") {
        return Promise.resolve(new Response(JSON.stringify(config), { status: 200 }));
      }
      if (path === "/config/providers/readiness") {
        return Promise.resolve(new Response(JSON.stringify(readiness), { status: 200 }));
      }
      if (path === "/config/providers/llm/health") {
        return Promise.resolve(new Response(JSON.stringify(healthyProvider), { status: 200 }));
      }
      throw new Error(`Unexpected request: ${path}`);
    }));

    render(<ProviderSetup />);

    expect(await screen.findByText("Needs credential")).toBeTruthy();
    expect(screen.getByText("Enter the downloaded Desktop OAuth client JSON.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Google Desktop OAuth client JSON"), {
      target: { value: '{"installed":{"client_id":"id"}}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save provider setup" }));

    await waitFor(() => {
      const update = requests.find((request) => request.body !== null);
      expect(update?.path).toBe("/config/providers");
      expect(update?.body).toContain("gmail_oauth_client_json");
    });
    expect(screen.queryByDisplayValue('{"installed":{"client_id":"id"}}')).toBeNull();
  });

  it("saves Tavily enablement and a write-only key, then clears the field", async () => {
    const requestBodies: string[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (typeof init?.body === "string") requestBodies.push(init.body);
      if (path === "/config/providers/llm/health") {
        return Promise.resolve(new Response(JSON.stringify(healthyProvider), { status: 200 }));
      }
      if (path === "/config/providers/readiness") {
        return Promise.resolve(new Response(JSON.stringify(readiness), { status: 200 }));
      }
      if (path === "/config/providers") {
        return Promise.resolve(new Response(JSON.stringify({
          ...config,
          settings: { ...config.settings, web_search_enabled: true },
        }), { status: 200 }));
      }
      throw new Error(`Unexpected request: ${path}`);
    }));

    render(<ProviderSetup autoLoad={false} initialConfig={config} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Enable Tavily web search" }));
    fireEvent.change(screen.getByLabelText("Tavily API key"), {
      target: { value: "tvly-write-only" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save provider setup" }));

    await screen.findByText("API connected");
    expect(JSON.parse(requestBodies[0])).toMatchObject({
      tavily_api_key: "tvly-write-only",
      web_search_enabled: true,
    });
    expect(screen.queryByDisplayValue("tvly-write-only")).toBeNull();
    expect(screen.getByText("Web search is disabled.")).toBeTruthy();
  });

  it("renders a public API error instead of a generic failure", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (init?.method === "PUT") {
        return Promise.resolve(new Response(
          JSON.stringify({ error: { code: "bad_request", details: [], message: "Pull the configured Ollama model." } }),
          { status: 400 },
        ));
      }
      return Promise.resolve(
        new Response(JSON.stringify(path.includes("readiness") ? readiness : config), {
          status: 200,
        }),
      );
    }));

    render(<ProviderSetup />);
    await screen.findByText("Needs credential");
    fireEvent.click(screen.getByRole("button", { name: "Save provider setup" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Pull the configured Ollama model.",
    );
  });
});

function requestPath(input: RequestInfo | URL): string {
  return typeof input === "string"
    ? input
    : input instanceof URL
      ? input.href
      : input.url;
}
