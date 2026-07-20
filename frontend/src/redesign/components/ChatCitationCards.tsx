import type { ChatCitation } from "../../api";

interface ChatCitationCardsProps {
  citations: ChatCitation[];
  onOpenApplication: (id: string) => void;
  onOpenEmail: (publicId: string, trigger: HTMLButtonElement) => void;
}

function safeWebUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function displayDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? null : date.toLocaleDateString();
}

function nonEmpty(value: string | null | undefined): string | null {
  const trimmed = value?.trim();
  if (!trimmed) return null;
  return trimmed;
}

function ApplicationCitationCard({
  citation,
  onOpenApplication,
}: {
  citation: ChatCitation;
  onOpenApplication: (id: string) => void;
}) {
  const company = nonEmpty(citation.company);
  const roleTitle = nonEmpty(citation.role_title);
  const hasMetadata = company !== null || roleTitle !== null;
  const fallbackTitle = citation.application_id
    ? `Application ${citation.application_id}`
    : "Application";
  const date = displayDate(citation.first_seen_at ?? citation.sent_at);
  return (
    <article className="rd-chat-citation rd-chat-application-citation">
      <div className="rd-chat-application-heading">
        <strong>{company ?? (hasMetadata ? "Unknown company" : fallbackTitle)}</strong>
        {roleTitle ? <span>{roleTitle}</span> : null}
      </div>
      {citation.current_status || date ? (
        <div className="rd-chat-citation-meta">
          {citation.current_status ? <span>{citation.current_status.replaceAll("_", " ")}</span> : null}
          {date ? <time dateTime={citation.first_seen_at ?? citation.sent_at ?? undefined}>{date}</time> : null}
        </div>
      ) : null}
      {citation.snippet ? <p>{citation.snippet}</p> : null}
      {citation.application_id ? (
        <div className="rd-chat-citation-actions">
          <button onClick={() => onOpenApplication(citation.application_id!)} type="button">
            View application
          </button>
        </div>
      ) : null}
    </article>
  );
}

function WebCitationCard({ citation }: { citation: ChatCitation }) {
  const href = safeWebUrl(citation.web_url);
  const domain = nonEmpty(citation.web_domain);
  const title = nonEmpty(citation.web_title) ?? domain ?? "Web source";
  return (
    <article className="rd-chat-citation rd-chat-web-citation">
      <strong>{title}</strong>
      {domain ? <span>{domain}</span> : null}
      {citation.snippet ? <p>{citation.snippet}</p> : null}
      {href ? (
        <div className="rd-chat-citation-actions">
          <a href={href} rel="noopener noreferrer" target="_blank">Open source</a>
        </div>
      ) : null}
    </article>
  );
}

function EvidenceCitationCard({
  citation,
  onOpenApplication,
  onOpenEmail,
}: {
  citation: ChatCitation;
  onOpenApplication: (id: string) => void;
  onOpenEmail: (publicId: string, trigger: HTMLButtonElement) => void;
}) {
  const date = displayDate(citation.sent_at);
  return (
    <article className="rd-chat-citation">
      <strong>
        {nonEmpty(citation.subject) ??
          (citation.source === "metric" ? "Deterministic dashboard metric" : "Email evidence")}
      </strong>
      {date ? <time dateTime={citation.sent_at ?? undefined}>{date}</time> : null}
      {citation.snippet ? <q>{citation.snippet}</q> : null}
      <div className="rd-chat-citation-actions">
        {citation.application_id ? (
          <button onClick={() => onOpenApplication(citation.application_id!)} type="button">
            View application
          </button>
        ) : null}
        {citation.source === "email" && citation.email_public_id ? (
          <button
            onClick={(event) => onOpenEmail(citation.email_public_id!, event.currentTarget)}
            type="button"
          >
            Open email evidence
          </button>
        ) : null}
        {citation.source === "metric" ? (
          <span>Dashboard metric · {citation.metric_template ?? "verified query"}</span>
        ) : null}
      </div>
    </article>
  );
}

export function ChatCitationCards({
  citations,
  onOpenApplication,
  onOpenEmail,
}: ChatCitationCardsProps) {
  if (citations.length === 0) return null;
  return (
    <div aria-label="Sources" className="rd-chat-citations">
      {citations.map((citation) => {
        if (citation.source === "application") {
          return (
            <ApplicationCitationCard
              citation={citation}
              key={citation.citation_id}
              onOpenApplication={onOpenApplication}
            />
          );
        }
        if (citation.source === "web") {
          return <WebCitationCard citation={citation} key={citation.citation_id} />;
        }
        return (
          <EvidenceCitationCard
            citation={citation}
            key={citation.citation_id}
            onOpenApplication={onOpenApplication}
            onOpenEmail={onOpenEmail}
          />
        );
      })}
    </div>
  );
}
