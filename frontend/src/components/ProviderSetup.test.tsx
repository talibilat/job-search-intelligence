import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProviderSetup } from "./ProviderSetup";

const config = {
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
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ProviderSetup", () => {
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
