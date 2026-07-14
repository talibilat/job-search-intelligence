import {
  getChatHistoryChatHistoryGet,
  postChatChatPost,
  type ChatCitation,
  type ChatMessageRecord,
  type ChatRequest,
  type ChatResponse,
} from "./generated";

export interface ChatHistoryMessage
  extends Omit<ChatMessageRecord, "citations_json"> {
  citations: ChatCitation[];
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
      citation.source === "metric")
  );
}

function chatCitations(values: unknown[]): ChatCitation[] {
  const citations: ChatCitation[] = [];
  for (const value of values) {
    if (isChatCitation(value)) citations.push(value);
  }
  return citations;
}

export async function loadChatHistory(): Promise<ChatHistoryMessage[]> {
  const response = await getChatHistoryChatHistoryGet({ limit: 500 });
  if (response.status !== 200) {
    throw new ChatApiError(response);
  }
  return response.data.messages.map(({ citations_json, ...message }) => ({
    ...message,
    citations: chatCitations(citations_json),
  }));
}

export async function sendChatTurn(
  request: ChatRequest,
): Promise<ChatResponse> {
  const response = await postChatChatPost(request);
  if (response.status !== 200) {
    throw new ChatApiError(response);
  }
  return response.data;
}
