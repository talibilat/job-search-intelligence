import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";

import {
  loadChatHistory,
  sendChatTurn,
  type ChatAnswerKind,
  type ChatCitation,
  type ChatFollowUpPrompt,
  type ChatHistoryMessage,
} from "../api";
import { publicApiError } from "./apiError";
import { ChatCitationCards } from "./components/ChatCitationCards";
import { EmailReaderDialog } from "./components/EmailReaderDialog";

const SUGGESTIONS = [
  "How many applications have I submitted?",
  "Show me every rejection email that mentioned experience.",
  "Who am I waiting on and who is overdue?",
];

type VisibleMessage = Pick<ChatHistoryMessage, "content" | "conversation_id" | "created_at"> & {
  answerKind?: ChatAnswerKind;
  citations: ChatCitation[];
  followUpPrompts: ChatFollowUpPrompt[];
  id: number | string;
  role: "assistant" | "user";
};

type ChatFailure = "history" | "provider" | "request" | "web" | null;

interface PendingTurn {
  assistantId: string;
  question: string;
  turnId: string;
}

interface ConversationSummary {
  id: string;
  label: string;
  lastActivity: string;
}

function visibleMessages(history: ChatHistoryMessage[]): VisibleMessage[] {
  return history
    .filter(
      (message): message is ChatHistoryMessage & { role: "assistant" | "user" } =>
        message.role === "assistant" || message.role === "user",
    )
    .map((message) => ({
      answerKind: message.answer_kind,
      citations: message.citations,
      content: message.content,
      conversation_id: message.conversation_id,
      created_at: message.created_at,
      followUpPrompts: message.follow_up_prompts ?? [],
      id: message.id,
      role: message.role,
    }));
}

function conversationSummaries(messages: VisibleMessage[]): ConversationSummary[] {
  const summaries = new Map<string, ConversationSummary>();
  for (const message of messages) {
    const current = summaries.get(message.conversation_id);
    const label = message.role === "user" && (!current || current.label === "Saved conversation")
      ? message.content.trim().slice(0, 60)
      : current?.label ?? "Saved conversation";
    summaries.set(message.conversation_id, {
      id: message.conversation_id,
      label,
      lastActivity: current?.lastActivity && current.lastActivity > message.created_at
        ? current.lastActivity
        : message.created_at,
    });
  }
  return [...summaries.values()].sort((left, right) =>
    right.lastActivity.localeCompare(left.lastActivity),
  );
}

function messageStyle(role: "assistant" | "user"): CSSProperties {
  return role === "user"
    ? {
        alignSelf: "flex-end",
        maxWidth: "85%",
        padding: "10px 14px",
        borderRadius: "14px 14px 4px 14px",
        background: "#1B201C",
        color: "#F6F4EC",
      }
    : {
        alignSelf: "flex-start",
        maxWidth: "94%",
        padding: "12px 14px",
        borderRadius: "14px 14px 14px 4px",
        background: "#F4F2FB",
        border: "1px solid #E9E5F7",
        color: "#2B2833",
      };
}

function chatErrorCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("response" in error)) return null;
  const response = (error as { response?: { data?: unknown; status?: number } }).response;
  if (typeof response?.data !== "object" || response.data === null || !("error" in response.data)) {
    return response?.status === 503 ? "llm_provider_unavailable" : null;
  }
  const detail = (response.data as { error?: { code?: unknown } }).error;
  return typeof detail?.code === "string" ? detail.code : null;
}

export function ChatDrawer({
  onClose,
  onOpenApplication,
  onOpenSettings,
}: {
  onClose: () => void;
  onOpenApplication: (id: string) => void;
  onOpenSettings: () => void;
}) {
  const [messages, setMessages] = useState<VisibleMessage[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [failure, setFailure] = useState<ChatFailure>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastTurn, setLastTurn] = useState<PendingTurn | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [emailPublicId, setEmailPublicId] = useState<string | null>(null);
  const emailCitationTriggerRef = useRef<HTMLButtonElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const requestSequence = useRef(0);
  const activeTurn = useRef<AbortController | null>(null);

  const fetchHistory = async (selectedConversationId?: string) => {
    const sequence = ++requestSequence.current;
    setHistoryLoading(true);
    setFailure(null);
    setErrorMessage(null);
    try {
      const history = await loadChatHistory(selectedConversationId);
      if (sequence !== requestSequence.current) return;
      const visible = visibleMessages(history);
      if (selectedConversationId) {
        setMessages(visible);
        setConversationId(selectedConversationId);
      } else {
        const summaries = conversationSummaries(visible);
        const latestConversationId = summaries[0]?.id ?? null;
        setConversations(summaries);
        setMessages(
          latestConversationId
            ? visible.filter((message) => message.conversation_id === latestConversationId)
            : [],
        );
        setConversationId(latestConversationId);
      }
    } catch (error) {
      if (sequence !== requestSequence.current) return;
      setFailure("history");
      setErrorMessage(publicApiError(error, "Saved chat history could not be loaded."));
    } finally {
      if (sequence === requestSequence.current) setHistoryLoading(false);
    }
  };

  useEffect(() => {
    queueMicrotask(() => void fetchHistory());
    return () => {
      requestSequence.current += 1;
      activeTurn.current?.abort();
    };
  }, []);

  const startNewChat = () => {
    activeTurn.current?.abort();
    requestSequence.current += 1;
    setMessages([]);
    setConversationId(null);
    setHistoryLoading(false);
    setFailure(null);
    setErrorMessage(null);
    setLastTurn(null);
    setProgress(null);
  };

  useEffect(() => {
    const log = logRef.current;
    if (!log) return;
    if (typeof log.scrollTo === "function") {
      log.scrollTo({ behavior: "smooth", top: log.scrollHeight });
    } else {
      log.scrollTop = log.scrollHeight;
    }
  }, [messages, progress]);

  const ask = async (question: string, retryTurn?: PendingTurn) => {
    const trimmed = question.trim();
    if (!trimmed || sending) return;
    const turnId = retryTurn?.turnId ?? crypto.randomUUID();
    const assistantId = retryTurn?.assistantId ?? `assistant-${turnId}`;
    const requestedAt = new Date().toISOString();
    if (retryTurn) {
      setMessages((current) => current.map((message) =>
        message.id === assistantId
          ? { ...message, answerKind: undefined, citations: [], content: "", followUpPrompts: [] }
          : message,
      ));
    } else {
      setMessages((current) => [
        ...current,
        {
          citations: [],
          content: trimmed,
          conversation_id: conversationId ?? "pending",
          created_at: requestedAt,
          id: `user-${turnId}`,
          followUpPrompts: [],
          role: "user",
        },
        {
          citations: [],
          content: "",
          conversation_id: conversationId ?? "pending",
          created_at: requestedAt,
          followUpPrompts: [],
          id: assistantId,
          role: "assistant",
        },
      ]);
    }
    const pendingTurn = { assistantId, question: trimmed, turnId };
    const controller = new AbortController();
    activeTurn.current?.abort();
    activeTurn.current = controller;
    setDraft("");
    setLastTurn(pendingTurn);
    setFailure(null);
    setErrorMessage(null);
    setSending(true);
    setProgress("Planning the best way to answer…");
    try {
      const response = await sendChatTurn(
        {
          conversation_id: conversationId,
          message: trimmed,
          turn_id: turnId,
        },
        (event) => {
          if (event.type === "route") {
            const routeLabel = event.route === "quantitative"
              ? "Checking deterministic local dashboard facts…"
              : event.route === "web"
                ? "Searching the web for current information…"
              : event.route === "mixed"
                ? "Searching web and local job-search evidence…"
                : event.route === "conversation"
                  ? "Preparing a conversational response…"
                  : "Searching cited local email evidence…";
            setProgress(routeLabel);
          } else if (event.type === "tool") {
            const toolLabel = event.tool === "structured_query"
              ? "Reconciling the answer with local dashboard metrics…"
              : event.tool === "web_search"
                ? "Reviewing current web results…"
              : event.tool === "cached_insight"
                ? "Reading your cached local insight…"
                : "Reviewing safe retained local email evidence…";
            setProgress(toolLabel);
          } else if (event.type === "answer_delta") {
            setProgress(null);
            setMessages((current) => current.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    content: message.content + event.answer_delta,
                    conversation_id: event.conversation_id,
                  }
                : message,
            ));
          }
        },
        controller.signal,
      );
      setConversationId(response.conversation_id);
      setConversations((current) => {
        const existing = current.find((conversation) => conversation.id === response.conversation_id);
        const summary = {
          id: response.conversation_id,
          label: existing?.label === "Saved conversation" || !existing
            ? trimmed.slice(0, 60)
            : existing.label,
          lastActivity: new Date().toISOString(),
        };
        return [summary, ...current.filter((conversation) => conversation.id !== response.conversation_id)];
      });
      setMessages((current) => current.map((message) =>
        message.id === assistantId
          ? {
              ...message,
              answerKind: response.answer_kind,
              citations: response.citations,
              content: response.answer,
              conversation_id: response.conversation_id,
              created_at: new Date().toISOString(),
              followUpPrompts: response.follow_up_prompts ?? [],
            }
          : message,
      ));
      setProgress(null);
    } catch (error) {
      if (controller.signal.aborted) return;
      setProgress(null);
      setMessages((current) => current.map((message) =>
        message.id === assistantId
          ? { ...message, answerKind: undefined, citations: [], content: "", followUpPrompts: [] }
          : message,
      ));
      const errorCode = chatErrorCode(error);
      const nextFailure = errorCode === "web_search_unavailable"
        ? "web"
        : errorCode === "llm_provider_unavailable"
          ? "provider"
          : "request";
      setFailure(nextFailure);
      setErrorMessage(
        publicApiError(
          error,
          nextFailure === "provider"
            ? "The configured AI provider is unavailable."
            : nextFailure === "web"
              ? "Web search is not configured or is currently unavailable."
            : "The grounded answer could not be completed.",
        ),
      );
    } finally {
      if (activeTurn.current === controller) {
        activeTurn.current = null;
        setSending(false);
      }
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void ask(draft);
  };

  return (
    <>
      <aside aria-label="Ask AI drawer" className="rd-chat-drawer">
        <header className="rd-chat-header">
          <div>
            <div className="rd-chat-title">
              <span aria-hidden="true" className="rd-chat-status-dot" />
              Ask your job search
            </div>
            <div className="rd-chat-subtitle">Grounded in local metrics and cited email evidence</div>
          </div>
          <button aria-label="Close chat" className="rd-chat-close" onClick={onClose} type="button">
            &times;
          </button>
        </header>

        {!historyLoading && conversations.length > 0 ? (
          <div className="rd-chat-conversation-bar">
            <label htmlFor="chat-conversation">Conversation</label>
            <select
              disabled={sending}
              id="chat-conversation"
              onChange={(event) => {
                if (event.target.value === "new") startNewChat();
                else void fetchHistory(event.target.value);
              }}
              value={conversationId ?? "new"}
            >
              {conversationId === null ? <option value="new">New conversation</option> : null}
              {conversations.map((conversation) => (
                <option key={conversation.id} value={conversation.id}>
                  {conversation.label}
                </option>
              ))}
            </select>
            <button disabled={sending} onClick={startNewChat} type="button">New chat</button>
          </div>
        ) : null}

        <div aria-live="polite" aria-relevant="additions text" className="rd-chat-log" ref={logRef} role="log">
          {historyLoading ? <div className="rd-chat-state" role="status">Loading saved conversation…</div> : null}
          {!historyLoading && failure === "history" ? (
            <div className="rd-chat-error" role="alert">
              <strong>History unavailable</strong>
              <span>{errorMessage}</span>
              <button onClick={() => void fetchHistory()} type="button">Retry history</button>
            </div>
          ) : null}
          {!historyLoading && failure !== "history" && messages.length === 0 ? (
            <div className="rd-chat-empty">
              <strong>Ask from your actual search history</strong>
              <span>Counts reconcile with the dashboard. Content answers link to retained evidence.</span>
            </div>
          ) : null}

          {messages.map((message) => {
            const refusal = message.role === "assistant" && message.answerKind === "refusal";
            return (
              <article key={message.id} style={messageStyle(message.role)}>
                {refusal ? <div className="rd-chat-refusal-label">Grounded refusal</div> : null}
                <div className="rd-chat-message">{message.content}</div>
                <ChatCitationCards
                  citations={message.citations}
                  onOpenApplication={onOpenApplication}
                  onOpenEmail={(publicId, trigger) => {
                    emailCitationTriggerRef.current = trigger;
                    setEmailPublicId(publicId);
                  }}
                />
                {message.role === "assistant" && message.followUpPrompts.length > 0 ? (
                  <div aria-label="Follow-up prompts" className="rd-chat-follow-ups">
                    {message.followUpPrompts.map((prompt) => (
                      <button
                        disabled={sending}
                        key={`${message.id}-${prompt.message}`}
                        onClick={() => void ask(prompt.message)}
                        type="button"
                      >
                        {prompt.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}

          {progress ? <div className="rd-chat-progress" role="status"><span />{progress}</div> : null}
          {failure === "provider" || failure === "request" || failure === "web" ? (
            <div className="rd-chat-error" role="alert">
              <strong>
                {failure === "provider"
                  ? "AI provider unavailable"
                  : failure === "web"
                    ? "Web search unavailable"
                    : "Answer interrupted"}
              </strong>
              <span>{errorMessage}</span>
              <div>
                <button disabled={sending} onClick={() => lastTurn && void ask(lastTurn.question, lastTurn)} type="button">Retry answer</button>
                {failure === "provider" || failure === "web" ? (
                  <button onClick={onOpenSettings} type="button">Open Settings</button>
                ) : null}
              </div>
            </div>
          ) : null}

          {!historyLoading && messages.length === 0 ? (
            <div className="rd-chat-suggestions">
              {SUGGESTIONS.map((suggestion) => (
                <button disabled={sending} key={suggestion} onClick={() => void ask(suggestion)} type="button">
                  {suggestion}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <form className="rd-chat-composer" onSubmit={onSubmit}>
          <label className="rd-sr-only" htmlFor="chat-message">Message</label>
          <textarea
            disabled={sending || historyLoading}
            id="chat-message"
            maxLength={4000}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Ask about your applications or email evidence"
            rows={2}
            value={draft}
          />
          <button disabled={sending || historyLoading || !draft.trim()} type="submit">
            {sending ? "Working…" : "Ask"}
          </button>
          <small>Only configured providers receive the evidence needed for this question.</small>
        </form>
      </aside>
      <EmailReaderDialog
        onClose={() => setEmailPublicId(null)}
        publicId={emailPublicId}
        triggerRef={emailCitationTriggerRef}
      />
    </>
  );
}
