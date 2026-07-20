import {
  getChatHistoryChatHistoryGet,
  type ChatAnswerKind,
  type ChatCitation,
  type ChatFollowUpPrompt,
  type ChatMessageRecord,
  type ChatRequest,
  type ChatResponse,
} from "./generated";

export type ChatTurnRequest = ChatRequest & { turn_id: string };
export type ChatTurnResponse = ChatResponse & { answer_kind: ChatAnswerKind };

export type ChatClientStreamEvent =
  | { conversation_id: string; route: ChatResponse["route"]; type: "route" }
  | { conversation_id: string; tool: "cached_insight" | "semantic_search" | "structured_query" | "web_search"; type: "tool" }
  | { answer_delta: string; conversation_id: string; type: "answer_delta" }
  | { conversation_id: string; response: ChatTurnResponse; type: "complete" };

export interface ChatHistoryMessage
  extends Omit<ChatMessageRecord, "answer_kind" | "citations_json" | "follow_up_prompts_json"> {
  answer_kind?: ChatAnswerKind;
  citations: ChatCitation[];
  follow_up_prompts?: ChatFollowUpPrompt[];
}

class ChatApiError extends Error {
  constructor(readonly response: { data: unknown; status: number }) {
    super("Chat API request failed");
  }
}

function isChatCitation(value: unknown): value is ChatCitation {
  if (typeof value !== "object" || value === null) return false;
  const citation = value as Record<string, unknown>;
  return (
    typeof citation.citation_id === "string" &&
    (citation.source === "application" ||
      citation.source === "email" ||
      citation.source === "metric" ||
      citation.source === "web")
  );
}

function isFollowUpPrompt(value: unknown): value is ChatFollowUpPrompt {
  if (typeof value !== "object" || value === null) return false;
  const prompt = value as Record<string, unknown>;
  return typeof prompt.label === "string" && typeof prompt.message === "string";
}

function chatCitations(values: unknown[]): ChatCitation[] {
  const citations: ChatCitation[] = [];
  for (const value of values) {
    if (isChatCitation(value)) citations.push(value);
  }
  return citations;
}

function chatFollowUpPrompts(values: unknown[]): ChatFollowUpPrompt[] {
  const prompts: ChatFollowUpPrompt[] = [];
  for (const value of values) {
    if (isFollowUpPrompt(value)) prompts.push(value);
  }
  return prompts;
}

export async function loadChatHistory(conversationId?: string): Promise<ChatHistoryMessage[]> {
  const response = await getChatHistoryChatHistoryGet({
    conversation_id: conversationId,
    limit: 500,
  });
  if (response.status !== 200) {
    throw new ChatApiError(response);
  }
  return response.data.messages.map(({ citations_json, follow_up_prompts_json = [], ...message }) => ({
    ...message,
    answer_kind: message.answer_kind ?? undefined,
    citations: chatCitations(citations_json),
    follow_up_prompts: chatFollowUpPrompts(follow_up_prompts_json),
  }));
}

export async function sendChatTurn(
  request: ChatTurnRequest,
  onEvent?: (event: ChatClientStreamEvent) => void,
  signal?: AbortSignal,
): Promise<ChatTurnResponse> {
  const response = await fetch("/chat", {
    body: JSON.stringify({
      ...request,
      timezone: request.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
    }),
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    method: "POST",
    signal,
  });
  if (!response.ok) {
    throw new ChatApiError({ data: await responseData(response), status: response.status });
  }
  if (!response.body) {
    throw new ChatApiError({ data: streamError("Chat response body was unavailable."), status: 502 });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: ChatTurnResponse | null = null;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    buffer = buffer.replaceAll("\r\n", "\n");
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = parseStreamFrame(frame);
      if (event.type === "error") {
        throw new ChatApiError({
          data: streamError(event.error_message, event.error_code),
          status: event.error_code === "llm_provider_unavailable" ? 503 : 502,
        });
      }
      onEvent?.(event);
      if (event.type === "complete") completed = event.response;
    }
    if (done) break;
  }
  if (!completed) {
    throw new ChatApiError({ data: streamError("Chat response ended before completion."), status: 502 });
  }
  return completed;
}

async function responseData(response: Response): Promise<unknown> {
  const body = await response.text();
  try {
    return body ? JSON.parse(body) : {};
  } catch {
    return {};
  }
}

function streamError(message: string, code = "chat_stream_interrupted") {
  return { error: { code, details: [], message } };
}

function parseStreamFrame(frame: string): ChatClientStreamEvent | ChatStreamError {
  const data = frame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data) {
    throw new ChatApiError({ data: streamError("Chat stream contained an empty event."), status: 502 });
  }
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    throw new ChatApiError({ data: streamError("Chat stream contained invalid JSON."), status: 502 });
  }
  if (typeof value !== "object" || value === null || !("type" in value)) {
    throw new ChatApiError({ data: streamError("Chat stream contained an invalid event."), status: 502 });
  }
  const event = value as Record<string, unknown>;
  if (event.type === "route" && typeof event.conversation_id === "string" &&
      (event.route === "conversation" || event.route === "quantitative" ||
        event.route === "content" || event.route === "web" || event.route === "mixed")) {
    return event as ChatClientStreamEvent;
  }
  if (event.type === "tool" && typeof event.conversation_id === "string" &&
      (event.tool === "structured_query" || event.tool === "semantic_search" ||
        event.tool === "cached_insight" || event.tool === "web_search")) {
    return event as ChatClientStreamEvent;
  }
  if (event.type === "answer_delta" && typeof event.conversation_id === "string" &&
      typeof event.answer_delta === "string") {
    return event as ChatClientStreamEvent;
  }
  if (event.type === "complete" && typeof event.conversation_id === "string" &&
      typeof event.response === "object" && event.response !== null &&
      "answer_kind" in event.response &&
       (event.response.answer_kind === "conversation" || event.response.answer_kind === "grounded" ||
         event.response.answer_kind === "refusal")) {
    return event as ChatClientStreamEvent;
  }
  if (event.type === "error" && typeof event.error_code === "string" &&
      typeof event.error_message === "string") {
    return event as unknown as ChatStreamError;
  }
  throw new ChatApiError({ data: streamError("Chat stream contained an invalid event."), status: 502 });
}

interface ChatStreamError {
  error_code: string;
  error_message: string;
  type: "error";
}
