import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ClassificationPreRunEstimate, ProviderConfigResponse } from "../../api";
import { SettingsPage } from "./SettingsPage";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });
}

function providerConfig(): ProviderConfigResponse {
  return {
    email_providers: [
      { config_requirements: [], display_name: "Gmail", name: "gmail", secret_requirements: [] },
    ],
    llm_providers: [
      {
        config_requirements: [],
        display_name: "Ollama",
        is_local: true,
        name: "ollama",
        secret_requirements: [],
      },
    ],
    recommended_classification_mode: "local",
    selection: { classification_mode: "local", email_provider: "gmail", llm_provider: "ollama" },
    settings: {
      azure_openai_api_version: "",
      azure_openai_chat_deployment: "",
      azure_openai_embedding_deployment: "",
      azure_openai_endpoint: "",
      gmail_scopes: ["gmail.readonly"],
      ollama_base_url: "http://localhost:11434",
      ollama_chat_model: "llama3.1",
      ollama_embedding_model: "nomic-embed-text",
      sync_interval_seconds: 3600,
      sync_on_open: false,
    },
  };
}

function classificationEstimate(overrides: Partial<ClassificationPreRunEstimate> = {}): ClassificationPreRunEstimate {
  return {
    candidate_count: 42,
    classification_mode: "local",
    cost_estimate_available: true,
    currency: "USD",
    estimated_completion_tokens: 500,
    estimated_cost_usd: 0,
    estimated_prompt_tokens: 12000,
    estimated_total_tokens: 12500,
    llm_provider: "ollama",
    model: "llama3.1",
    prompt_version: "current",
    token_estimate_method: "heuristic per-candidate token budget",
    ...overrides,
  };
}

function renderSettings() {
  render(
    <SettingsPage
      connections={[]}
      connectionsError={null}
      connectionsLoadState="ready"
      onChanged={vi.fn()}
      onRetryConnections={vi.fn()}
      syncStats={null}
    />,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SettingsPage cost control", () => {
  it("reveals the real cost-estimate math behind the scan cost figure instead of a fabricated explanation", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/config/providers") return Promise.resolve(jsonResponse(providerConfig()));
      if (path === "/classification/estimate") return Promise.resolve(jsonResponse(classificationEstimate()));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    renderSettings();

    const seeTheMath = await screen.findByRole("button", { name: "see the math" });
    expect(screen.queryByText(/12,000 prompt/)).toBeNull();

    fireEvent.click(seeTheMath);
    expect(screen.getByText(/12,000 prompt \+ 500 completion/)).toBeTruthy();
    expect(screen.getByText(/42 candidate emails × llama3.1 \(ollama\)/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "hide the math" })).toBeTruthy();
  });

  it("does not offer to reveal the math when there is no estimate yet", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/config/providers") return Promise.resolve(jsonResponse(providerConfig()));
      if (path === "/classification/estimate") return Promise.reject(new Error("estimate unavailable"));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    renderSettings();

    await screen.findByText("Cost control");
    expect(screen.queryByRole("button", { name: "see the math" })).toBeNull();
  });
});
