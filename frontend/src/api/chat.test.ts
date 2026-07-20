import { afterEach, describe, expect, it, vi } from "vitest";

import { sendChatTurn, type ChatClientStreamEvent } from "./chat";

const completeResponse = {
  answer: "You have 23 applications.",
  answer_kind: "grounded" as const,
  citations: [{ citation_id: "metric:summary_counts", source: "metric" as const }],
  conversation_id: "conversation-1",
  follow_up_prompts: [{ label: "See recent roles", message: "Show my recent roles" }],
  increments: [
    { content: "quantitative", type: "route" as const },
    { content: "structured_query", type: "tool" as const },
    { content: "You have 23 applications.", type: "answer" as const },
  ],
  route: "quantitative" as const,
  tool_outputs: [],
};

function streamingResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
    { headers: { "Content-Type": "text/event-stream" }, status: 200 },
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("sendChatTurn", () => {
  it("parses fragmented SSE frames and exposes progress before completion", async () => {
    const route = JSON.stringify({
      conversation_id: "conversation-1",
      route: "quantitative",
      type: "route",
    });
    const tool = JSON.stringify({
      conversation_id: "conversation-1",
      tool: "structured_query",
      type: "tool",
    });
    const answerDelta = JSON.stringify({
      answer_delta: "You have ",
      conversation_id: "conversation-1",
      type: "answer_delta",
    });
    const complete = JSON.stringify({
      conversation_id: "conversation-1",
      response: completeResponse,
      type: "complete",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamingResponse([
          `event: route\ndata: ${route.slice(0, 20)}`,
          `${route.slice(20)}\n\nevent: tool\ndata: ${tool}\n\nevent: answer_delta\ndata: ${answerDelta}\n\nevent: complete\ndata: `,
          `${complete}\n\n`,
        ]),
      ),
    );
    const events: ChatClientStreamEvent[] = [];

    const response = await sendChatTurn(
      { message: "How many applications?", turn_id: "turn-1" },
      (event) => events.push(event),
    );

    expect(events.map((event) => event.type)).toEqual([
      "route",
      "tool",
      "answer_delta",
      "complete",
    ]);
    expect(events[2]).toMatchObject({ answer_delta: "You have ", type: "answer_delta" });
    expect(response).toEqual(completeResponse);
    const [, request] = vi.mocked(fetch).mock.calls[0];
    if (typeof request?.body !== "string") throw new Error("Expected a JSON request body.");
    expect(JSON.parse(request.body)).toMatchObject({
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      turn_id: "turn-1",
    });
  });

  it("accepts conversational and web progress contracts", async () => {
    const conversationResponse = {
      ...completeResponse,
      answer: "Hello. What would you like to explore?",
      answer_kind: "conversation" as const,
      citations: [],
      route: "conversation" as const,
    };
    const events = [
      { conversation_id: "conversation-1", route: "conversation", type: "route" },
      { conversation_id: "conversation-1", route: "web", type: "route" },
      { conversation_id: "conversation-1", tool: "web_search", type: "tool" },
    ];
    const complete = {
      conversation_id: "conversation-1",
      response: conversationResponse,
      type: "complete",
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamingResponse([
      [...events, complete]
        .map((event) => `data: ${JSON.stringify(event)}\n\n`)
        .join(""),
    ])));
    const received: ChatClientStreamEvent[] = [];

    const response = await sendChatTurn(
      { message: "Hello", turn_id: "turn-web" },
      (event) => received.push(event),
    );

    expect(received.map((event) => event.type)).toEqual(["route", "route", "tool", "complete"]);
    expect(received[2]).toMatchObject({ tool: "web_search" });
    expect(response.answer_kind).toBe("conversation");
  });

  it("accepts cached insight tool progress events", async () => {
    const tool = JSON.stringify({
      conversation_id: "conversation-1",
      tool: "cached_insight",
      type: "tool",
    });
    const complete = JSON.stringify({
      conversation_id: "conversation-1",
      response: completeResponse,
      type: "complete",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamingResponse([
          `event: tool\ndata: ${tool}\n\nevent: complete\ndata: ${complete}\n\n`,
        ]),
      ),
    );
    const events: ChatClientStreamEvent[] = [];

    await sendChatTurn(
      { message: "Why am I getting rejected?", turn_id: "turn-2" },
      (event) => events.push(event),
    );

    expect(events[0]).toMatchObject({ tool: "cached_insight", type: "tool" });
  });

  it("turns an in-stream provider failure into the existing public API error shape", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamingResponse([
          'event: error\ndata: {"type":"error","error_code":"llm_provider_unavailable",' +
            '"error_message":"The local model is not running."}\n\n',
        ]),
      ),
    );

    await expect(sendChatTurn({ message: "What did Acme say?", turn_id: "turn-3" })).rejects.toMatchObject({
      response: {
        data: {
          error: {
            code: "llm_provider_unavailable",
            message: "The local model is not running.",
          },
        },
        status: 503,
      },
    });
  });

  it("passes an abort signal to the streaming fetch", async () => {
    const complete = JSON.stringify({
      conversation_id: "conversation-1",
      response: completeResponse,
      type: "complete",
    });
    const fetchMock = vi.fn().mockResolvedValue(
      streamingResponse([`event: complete\ndata: ${complete}\n\n`]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await sendChatTurn({ message: "How many?", turn_id: "turn-4" }, undefined, controller.signal);

    expect(fetchMock).toHaveBeenCalledWith("/chat", expect.objectContaining({ signal: controller.signal }));
  });
});
