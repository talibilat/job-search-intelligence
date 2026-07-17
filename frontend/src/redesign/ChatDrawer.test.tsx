import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { loadChatHistory, sendChatTurn } from "../api";
import { ChatDrawer } from "./ChatDrawer";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    loadChatHistory: vi.fn(),
    sendChatTurn: vi.fn(),
    syncEmailContentSyncEmailsPublicIdContentGet: vi.fn(),
  };
});

const loadHistoryMock = vi.mocked(loadChatHistory);
const sendTurnMock = vi.mocked(sendChatTurn);

function renderDrawer() {
  const onClose = vi.fn();
  const onOpenApplication = vi.fn();
  const onOpenSettings = vi.fn();
  render(
    <ChatDrawer
      onClose={onClose}
      onOpenApplication={onOpenApplication}
      onOpenSettings={onOpenSettings}
    />,
  );
  return { onClose, onOpenApplication, onOpenSettings };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ChatDrawer", () => {
  it("loads persisted history and navigates its application citation", async () => {
    loadHistoryMock.mockResolvedValue([
      {
        citations: [],
        content: "Who am I waiting on?",
        conversation_id: "conversation-1",
        created_at: "2026-07-15T10:00:00Z",
        id: 1,
        role: "user",
        tool_outputs_json: [],
      },
      {
        citations: [
          {
            application_id: "app-acme",
            citation_id: "application:app-acme",
            source: "application",
          },
        ],
        content: "You are waiting on Acme.",
        conversation_id: "conversation-1",
        created_at: "2026-07-15T10:00:01Z",
        id: 2,
        role: "assistant",
        tool_outputs_json: [],
      },
    ]);
    const { onOpenApplication } = renderDrawer();

    expect(await screen.findByText("You are waiting on Acme.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View application" }));

    expect(onOpenApplication).toHaveBeenCalledWith("app-acme");
  });

  it("posts a question and progressively renders a dashboard-consistent cited answer", async () => {
    loadHistoryMock.mockResolvedValue([]);
    sendTurnMock.mockImplementation((_request, onEvent) => {
      onEvent?.({
        conversation_id: "conversation-2",
        route: "quantitative",
        type: "route",
      });
      onEvent?.({
        conversation_id: "conversation-2",
        tool: "structured_query",
        type: "tool",
      });
      return Promise.resolve({
      answer: "You have 23 applications.",
      citations: [
        {
          citation_id: "metric:summary_counts",
          metric_template: "summary_counts",
          source: "metric",
        },
      ],
      conversation_id: "conversation-2",
      increments: [
        { content: "quantitative", type: "route" },
        { content: "structured_query", type: "tool" },
        { content: "You have 23 applications.", type: "answer" },
      ],
      route: "quantitative",
      tool_outputs: [],
      });
    });
    renderDrawer();

    const message = await screen.findByRole("textbox", { name: "Message" });
    fireEvent.change(message, { target: { value: "How many applications?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(screen.getByText("Reconciling the answer with dashboard metrics…")).toBeTruthy();
    expect(await screen.findByText("You have 23 applications.")).toBeTruthy();
    expect(screen.getByText("Dashboard metric · summary_counts")).toBeTruthy();
    expect(sendTurnMock).toHaveBeenCalledWith(
      {
        conversation_id: null,
        message: "How many applications?",
      },
      expect.any(Function),
    );
  });

  it("labels an unsupported uncited answer as a grounded refusal", async () => {
    loadHistoryMock.mockResolvedValue([
      {
        citations: [],
        content: "I cannot answer that from the retained job-search evidence.",
        conversation_id: "conversation-refusal",
        created_at: "2026-07-15T10:00:00Z",
        id: 3,
        role: "assistant",
        tool_outputs_json: [],
      },
    ]);
    renderDrawer();

    const refusal = await screen.findByText("Grounded refusal");
    expect(within(refusal.closest("article")!).getByText(/cannot answer/)).toBeTruthy();
  });

  it("shows provider recovery and retries without duplicating the user question", async () => {
    loadHistoryMock.mockResolvedValue([]);
    sendTurnMock
      .mockRejectedValueOnce({
        response: {
          data: {
            error: {
              code: "llm_provider_unavailable",
              details: [],
              message: "The local model is not running.",
            },
          },
          status: 503,
        },
      })
      .mockResolvedValueOnce({
        answer: "You have 23 applications.",
        citations: [{ citation_id: "metric:summary_counts", source: "metric" }],
        conversation_id: "conversation-retry",
        increments: [{ content: "You have 23 applications.", type: "answer" }],
        route: "quantitative",
        tool_outputs: [],
      });
    const { onOpenSettings } = renderDrawer();

    const message = await screen.findByRole("textbox", { name: "Message" });
    fireEvent.change(message, { target: { value: "How many applications?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("AI provider unavailable")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open Settings" }));
    expect(onOpenSettings).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Retry answer" }));

    expect(await screen.findByText("You have 23 applications.")).toBeTruthy();
    await waitFor(() => expect(sendTurnMock).toHaveBeenCalledTimes(2));
    expect(screen.getAllByText("How many applications?")).toHaveLength(1);
  });
});
