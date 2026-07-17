import { afterEach, describe, expect, it, vi } from "vitest";

import { sendChatTurn, type ChatClientStreamEvent } from "./chat";

const completeResponse = {
  answer: "You have 23 applications.",
  citations: [{ citation_id: "metric:summary_counts", source: "metric" as const }],
  conversation_id: "conversation-1",
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
          `${route.slice(20)}\n\nevent: tool\ndata: ${tool}\n\nevent: complete\ndata: `,
          `${complete}\n\n`,
        ]),
      ),
    );
    const events: ChatClientStreamEvent[] = [];

    const response = await sendChatTurn(
      { message: "How many applications?" },
      (event) => events.push(event),
    );

    expect(events.map((event) => event.type)).toEqual(["route", "tool", "complete"]);
    expect(response).toEqual(completeResponse);
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

    await sendChatTurn({ message: "Why am I getting rejected?" }, (event) => events.push(event));

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

    await expect(sendChatTurn({ message: "What did Acme say?" })).rejects.toMatchObject({
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
});
