import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProcessingPanel } from "./ProcessingPanel";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });
}

function requestPath(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.pathname;
  return new URL(input.url).pathname;
}

const pipeline = {
  generated_at: "2026-07-14T12:00:00Z",
  gmail_connected: true,
  reauth_required: false,
  sync_running: false,
  backfill_state: "completed",
  backfill_pages_processed: 2,
  backfill_messages_processed: 50,
  backfill_complete: true,
  incremental_sync_ready: true,
  counts: {
    raw_email_count: 50,
    metadata_only_count: 48,
    retained_body_count: 2,
    filter_decision_count: 50,
    filter_candidate_count: 2,
    filter_rejected_count: 48,
    classified_email_count: 0,
    job_related_email_count: 0,
    application_count: 0,
    application_event_count: 0,
  },
  unclassified_retained_count: 2,
  next_action: "run_classification",
  next_action_reason: "Two candidates need classification.",
};

const processing = {
  state: "idle",
  pending_candidate_count: 2,
  candidate_count: 2,
  candidate_limit: 500,
  processed_count: 0,
  accepted_count: 0,
  malformed_count: 0,
  skipped_not_job_count: 0,
  applications_upserted: 0,
  events_upserted: 0,
  ghost_updates: 0,
  ghost_retractions: 0,
  manual_conflict_count: 0,
  prompt_tokens: 0,
  completion_tokens: 0,
  total_tokens: 0,
  estimated_cost_usd: 0,
  model: "llama3.1",
  prompt_version: "v1",
  llm_provider: "ollama",
  classification_mode: "local",
  limit_reached: false,
};

const readiness = {
  ready_to_sync: true,
  ready_to_classify: true,
  gmail_sync: { state: "ready", message: "Ready." },
  classification_generation: { state: "ready", message: "Ready." },
  embedding_generation: { state: "ready", message: "Ready." },
  chat_generation: { state: "not_implemented", message: "Later." },
};

const estimate = {
  candidate_count: 2,
  estimated_prompt_tokens: 100,
  estimated_completion_tokens: 50,
  estimated_total_tokens: 150,
  estimated_cost_usd: 0,
  currency: "USD",
  cost_estimate_available: true,
  classification_mode: "local",
  llm_provider: "ollama",
  model: "llama3.1",
  prompt_version: "v1",
  token_estimate_method: "fixture",
};

function installFetch(overrides: Record<string, unknown> = {}) {
  const bodies: Record<string, unknown> = {
    "/pipeline/status": pipeline,
    "/processing/status": processing,
    "/config/providers/readiness": readiness,
    "/classification/estimate": estimate,
    ...overrides,
  };
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const path = requestPath(input);
    if (!(path in bodies)) return Promise.reject(new Error(`Unhandled request: ${path}`));
    return Promise.resolve(response(bodies[path]));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ProcessingPanel", () => {
  it("shows sync as the next action and never starts classification automatically", async () => {
    const fetchMock = installFetch({
      "/pipeline/status": {
        ...pipeline,
        backfill_complete: false,
        next_action: "continue_backfill",
        next_action_reason: "Historical sync is still running.",
      },
    });

    render(<ProcessingPanel onProcessed={() => undefined} reloadKey={0} />);

    expect(await screen.findByText("Finish reading your inbox")).toBeTruthy();
    expect(screen.getByText("Historical sync is still running.")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/processing/run")).toBe(false);
  });

  it("shows processing state, runs only after click, and refreshes after completion", async () => {
    let finishRun: ((value: Response) => void) | undefined;
    const fetchMock = installFetch();
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === "/processing/run") {
        return new Promise<Response>((resolve) => {
          finishRun = resolve;
        });
      }
      const bodies: Record<string, unknown> = {
        "/pipeline/status": pipeline,
        "/processing/status": processing,
        "/config/providers/readiness": readiness,
        "/classification/estimate": estimate,
      };
      return Promise.resolve(response(bodies[path]));
    });
    const onProcessed = vi.fn();

    render(<ProcessingPanel onProcessed={onProcessed} reloadKey={0} />);
    const button = await screen.findByRole("button", { name: "Process 2 emails" });
    expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === "/processing/run")).toBe(false);

    fireEvent.click(button);
    expect(await screen.findByText("Building your application history")).toBeTruthy();
    finishRun?.(response({
      ...processing,
      state: "succeeded",
      run_id: "run-1",
      started_at: "2026-07-14T12:00:00Z",
      completed_at: "2026-07-14T12:01:00Z",
      processed_count: 2,
      accepted_count: 2,
      applications_upserted: 1,
      events_upserted: 2,
    }));

    expect(await screen.findByText(/Processed 2; accepted 2/)).toBeTruthy();
    expect(onProcessed).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["missing_config", "Configure classification first", "Setup needed"],
    ["unavailable", "Classification cannot start", "Provider unavailable"],
  ])("shows %s classification readiness", async (state, title, label) => {
    installFetch({
      "/config/providers/readiness": {
        ...readiness,
        ready_to_classify: false,
        classification_generation: {
          state,
          message: "Provider is not ready.",
          action: "Check Settings.",
        },
      },
    });

    render(<ProcessingPanel onProcessed={() => undefined} reloadKey={0} />);

    expect(await screen.findByText(title)).toBeTruthy();
    expect(screen.getByText(label)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Process/ })).toBeNull();
  });
});
