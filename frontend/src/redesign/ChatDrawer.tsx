import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";

import {
  loadChatHistory,
  sendChatTurn,
  type ChatCitation,
  type ChatHistoryMessage,
} from "../api";
import { publicApiError } from "./apiError";
import { EmailReaderDialog } from "./components/EmailReaderDialog";

const SUGGESTIONS = [
  "How many applications have I submitted?",
  "What exactly did the latest recruiter say?",
  "Who am I waiting on and who is overdue?",
];

type VisibleMessage = Pick<ChatHistoryMessage, "content" | "conversation_id"> & {
  citations: ChatCitation[];
  id: number | string;
  role: "assistant" | "user";
};

type ChatFailure = "history" | "provider" | "request" | null;

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

function isProviderUnavailable(error: unknown): boolean {
  if (typeof error !== "object" || error === null || !("response" in error)) return false;
  const response = (error as { response?: { data?: unknown; status?: number } }).response;
  if (response?.status === 503) return true;
  if (typeof response?.data !== "object" || response.data === null || !("error" in response.data)) {
    return false;
  }
  const detail = (response.data as { error?: { code?: unknown } }).error;
  return detail?.code === "llm_provider_unavailable";
}

function citationTitle(citation: ChatCitation): string {
  if (citation.subject?.trim()) return citation.subject;
  if (citation.source === "application") return "Application record";
  if (citation.source === "metric") return "Deterministic dashboard metric";
  return "Email evidence";
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
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [failure, setFailure] = useState<ChatFailure>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [emailPublicId, setEmailPublicId] = useState<string | null>(null);
  const emailCitationTriggerRef = useRef<HTMLButtonElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const requestSequence = useRef(0);

  const fetchHistory = async () => {
    const sequence = ++requestSequence.current;
    setHistoryLoading(true);
    setFailure(null);
    setErrorMessage(null);
    try {
      const history = await loadChatHistory();
      if (sequence !== requestSequence.current) return;
      const visible = history.filter(
        (message): message is ChatHistoryMessage & { role: "assistant" | "user" } =>
          message.role === "assistant" || message.role === "user",
      );
      setMessages(
        visible.map((message) => ({
          citations: message.citations,
          content: message.content,
          conversation_id: message.conversation_id,
          id: message.id,
          role: message.role,
        })),
      );
      setConversationId(visible.at(-1)?.conversation_id ?? null);
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
    };
  }, []);

  useEffect(() => {
    const log = logRef.current;
    if (!log) return;
    if (typeof log.scrollTo === "function") {
      log.scrollTo({ behavior: "smooth", top: log.scrollHeight });
    } else {
      log.scrollTop = log.scrollHeight;
    }
  }, [messages, progress]);

  const ask = async (question: string, appendUser = true) => {
    const trimmed = question.trim();
    if (!trimmed || sending) return;
    const optimisticId = `user-${Date.now()}`;
    if (appendUser) {
      setMessages((current) => [
        ...current,
        {
          citations: [],
          content: trimmed,
          conversation_id: conversationId ?? "pending",
          id: optimisticId,
          role: "user",
        },
      ]);
    }
    setDraft("");
    setLastQuestion(trimmed);
    setFailure(null);
    setErrorMessage(null);
    setSending(true);
    setProgress("Routing your question through local job-search data…");
    try {
      const response = await sendChatTurn(
        {
          conversation_id: conversationId,
          message: trimmed,
        },
        (event) => {
          if (event.type === "route") {
            const routeLabel = event.route === "quantitative"
              ? "Checking deterministic dashboard facts…"
              : event.route === "mixed"
                ? "Checking metrics and cited email evidence…"
                : "Searching cited email evidence…";
            setProgress(routeLabel);
          } else if (event.type === "tool") {
            setProgress(
              event.tool === "structured_query"
                ? "Reconciling the answer with dashboard metrics…"
                : "Reviewing safe retained email evidence…",
            );
          }
        },
      );
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        {
          citations: response.citations,
          content: response.answer,
          conversation_id: response.conversation_id,
          id: `assistant-${Date.now()}`,
          role: "assistant",
        },
      ]);
      setProgress(null);
    } catch (error) {
      setProgress(null);
      setFailure(isProviderUnavailable(error) ? "provider" : "request");
      setErrorMessage(
        publicApiError(
          error,
          isProviderUnavailable(error)
            ? "The configured AI provider is unavailable."
            : "The grounded answer could not be completed.",
        ),
      );
    } finally {
      setSending(false);
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
            const refusal = message.role === "assistant" && message.citations.length === 0;
            return (
              <article key={message.id} style={messageStyle(message.role)}>
                {refusal ? <div className="rd-chat-refusal-label">Grounded refusal</div> : null}
                <div className="rd-chat-message">{message.content}</div>
                {message.citations.length > 0 ? (
                  <div aria-label="Sources" className="rd-chat-citations">
                    {message.citations.map((citation) => (
                      <div className="rd-chat-citation" key={citation.citation_id}>
                        <strong>{citationTitle(citation)}</strong>
                        {citation.sent_at ? <span>{new Date(citation.sent_at).toLocaleDateString()}</span> : null}
                        {citation.snippet ? <q>{citation.snippet}</q> : null}
                        <div className="rd-chat-citation-actions">
                          {citation.application_id ? (
                            <button onClick={() => onOpenApplication(citation.application_id!)} type="button">
                              View application
                            </button>
                          ) : null}
                          {citation.source === "email" && citation.email_public_id ? (
                            <button
                              onClick={(event) => {
                                emailCitationTriggerRef.current = event.currentTarget;
                                setEmailPublicId(citation.email_public_id!);
                              }}
                              type="button"
                            >
                              Open email evidence
                            </button>
                          ) : null}
                          {citation.source === "metric" ? (
                            <span>Dashboard metric · {citation.metric_template ?? "verified query"}</span>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}

          {progress ? <div className="rd-chat-progress" role="status"><span />{progress}</div> : null}
          {failure === "provider" || failure === "request" ? (
            <div className="rd-chat-error" role="alert">
              <strong>{failure === "provider" ? "AI provider unavailable" : "Answer interrupted"}</strong>
              <span>{errorMessage}</span>
              <div>
                <button disabled={sending} onClick={() => lastQuestion && void ask(lastQuestion, false)} type="button">Retry answer</button>
                {failure === "provider" ? <button onClick={onOpenSettings} type="button">Open Settings</button> : null}
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
