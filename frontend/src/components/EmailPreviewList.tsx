import { useEffect, useState } from "react";

import {
  syncRecentEmailsSyncRecentEmailsGet,
  type RawEmailPreviewOrder,
  type RawEmailPreviewRecord,
} from "../api";
import { Alert, Button } from "./ui";

const fetchLimit = 50;
const defaultVisibleRows = 10;

const sentDateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
  year: "numeric",
});

const detailDateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  month: "short",
  timeZone: "UTC",
  timeZoneName: "short",
  year: "numeric",
});

function subjectLabel(email: RawEmailPreviewRecord) {
  return email.subject_present ? "Subject captured" : "No subject";
}

function sentLabel(email: RawEmailPreviewRecord) {
  return email.sent_at
    ? sentDateFormatter.format(new Date(email.sent_at))
    : "Unknown date";
}

function detailTimestamp(value: string | null | undefined) {
  return value ? detailDateFormatter.format(new Date(value)) : "Unknown";
}

function filterBadge(email: RawEmailPreviewRecord) {
  if (email.filter_outcome === "candidate") {
    return { className: "email-preview__badge--kept", label: "kept by filter" };
  }
  if (email.filter_outcome === "rejected") {
    return {
      className: "email-preview__badge--skipped",
      label: "skipped by filter",
    };
  }
  return { className: "", label: "not filtered yet" };
}

function processingBadge(email: RawEmailPreviewRecord) {
  if (email.classification_category) {
    return `classified: ${email.classification_category.replaceAll("_", " ")}`;
  }
  if (email.has_retained_body) {
    return "awaiting classification";
  }
  return null;
}

function formatEmailDomains(domains: string[]) {
  return domains.length > 0 ? domains.join(", ") : "Unknown recipient";
}

function emailRowKey(email: RawEmailPreviewRecord) {
  return [
    email.provider,
    email.ingested_at,
    email.sent_at,
    email.from_domain,
    email.subject_present ? "subject" : "no-subject",
    email.filter_outcome,
    email.filter_reason,
    email.classification_category,
  ]
    .filter(Boolean)
    .join(":");
}

function EmailRow({
  email,
  isExpanded,
  onToggle,
}: {
  email: RawEmailPreviewRecord;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const filter = filterBadge(email);
  const processing = processingBadge(email);

  return (
    <li className="email-preview__row">
      <button
        aria-expanded={isExpanded}
        className="email-preview__row-button"
        onClick={onToggle}
        type="button"
      >
        <span className="email-preview__sender">
          {email.from_domain ?? "Unknown sender"}
        </span>
        <span className="email-preview__subject">{subjectLabel(email)}</span>
        <span className="email-preview__badges">
          <span className={`email-preview__badge ${filter.className}`}>
            {filter.label}
          </span>
          <span className="email-preview__badge">
            {email.has_retained_body ? "body retained" : "metadata only"}
          </span>
          {processing ? (
            <span className="email-preview__badge">{processing}</span>
          ) : null}
        </span>
        <span className="email-preview__date">{sentLabel(email)}</span>
      </button>
      {isExpanded ? (
        <dl className="email-preview__detail">
          <div>
            <dt>Provider</dt>
            <dd>{email.provider}</dd>
          </div>
          <div>
            <dt>From domain</dt>
            <dd>{email.from_domain ?? "Unknown sender"}</dd>
          </div>
          <div>
            <dt>To domains</dt>
            <dd>{formatEmailDomains(email.to_domains)}</dd>
          </div>
          <div>
            <dt>Subject</dt>
            <dd>{subjectLabel(email)}</dd>
          </div>
          <div>
            <dt>Sent</dt>
            <dd>{detailTimestamp(email.sent_at)}</dd>
          </div>
          <div>
            <dt>Ingested locally</dt>
            <dd>{detailTimestamp(email.ingested_at)}</dd>
          </div>
          <div>
            <dt>Body retention</dt>
            <dd>
              {email.body_retention_state.replaceAll("_", " ")}
              {email.has_retained_body
                ? " (body text stored locally, never shown here)"
                : " (no body text stored)"}
            </dd>
          </div>
          <div>
            <dt>Filter decision</dt>
            <dd>
              {email.filter_outcome ?? "not evaluated"}
              {email.filter_reason ? ` - ${email.filter_reason}` : ""}
            </dd>
          </div>
          <div>
            <dt>Classification</dt>
            <dd>
              {email.classification_category
                ? `${email.classification_category.replaceAll("_", " ")}${
                    email.classification_is_job_related === false
                      ? " (not job-related)"
                      : ""
                  }`
                : "not classified yet"}
            </dd>
          </div>
        </dl>
      ) : null}
    </li>
  );
}

export function EmailPreviewList({ refreshToken = 0 }: { refreshToken?: number }) {
  const [emails, setEmails] = useState<RawEmailPreviewRecord[]>([]);
  const [order, setOrder] = useState<RawEmailPreviewOrder>("sent_at");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let ignore = false;

    async function loadEmails() {
      try {
        const response = await syncRecentEmailsSyncRecentEmailsGet({
          limit: fetchLimit,
          order,
        });
        if (ignore) {
          return;
        }
        if (response.status === 200) {
          setEmails(response.data);
          setErrorMessage(null);
        } else {
          setErrorMessage("Recent synced email metadata is unavailable.");
        }
      } catch {
        if (!ignore) {
          setErrorMessage("Recent synced email metadata is unavailable.");
        }
      }
    }

    void loadEmails();

    return () => {
      ignore = true;
    };
  }, [order, refreshToken]);

  const visibleEmails = showAll ? emails : emails.slice(0, defaultVisibleRows);

  return (
    <section aria-labelledby="email-preview-title" className="email-preview">
      <div className="email-preview__header">
        <div>
          <p className="eyebrow">Stored email metadata</p>
          <h3 id="email-preview-title">
            {order === "sent_at"
              ? "Newest synced mailbox messages"
              : "Recently ingested (diagnostic)"}
          </h3>
        </div>
        <p>
          Public-safe metadata from raw_emails. Body text and snippets stay
          hidden. Click a row for the full processing detail.
        </p>
        <div
          aria-label="Email preview ordering"
          className="email-preview__order-toggle"
          role="group"
        >
          <Button
            aria-pressed={order === "sent_at"}
            onClick={() => {
              setOrder("sent_at");
              setExpandedKey(null);
            }}
            variant={order === "sent_at" ? "primary" : "secondary"}
          >
            Newest in mailbox
          </Button>
          <Button
            aria-pressed={order === "ingested_at"}
            onClick={() => {
              setOrder("ingested_at");
              setExpandedKey(null);
            }}
            variant={order === "ingested_at" ? "primary" : "secondary"}
          >
            Recently ingested
          </Button>
        </div>
        {order === "ingested_at" ? (
          <p className="email-preview__order-note">
            This diagnostic view shows what the latest sync run wrote. During
            the historical backfill it fills with progressively older mailbox
            messages; that is expected, not a sync bug.
          </p>
        ) : null}
      </div>

      {errorMessage ? (
        <Alert title="Recent email metadata unavailable" tone="warning">
          <p>{errorMessage}</p>
        </Alert>
      ) : visibleEmails.length > 0 ? (
        <>
          <ul className="email-preview__list">
            {visibleEmails.map((email) => {
              const key = emailRowKey(email);
              return (
                <EmailRow
                  email={email}
                  isExpanded={expandedKey === key}
                  key={key}
                  onToggle={() =>
                    setExpandedKey((currentKey) =>
                      currentKey === key ? null : key,
                    )
                  }
                />
              );
            })}
          </ul>
          {emails.length > defaultVisibleRows ? (
            <Button
              onClick={() => setShowAll((current) => !current)}
              variant="secondary"
            >
              {showAll
                ? `Show first ${defaultVisibleRows}`
                : `Show all ${emails.length} loaded`}
            </Button>
          ) : null}
        </>
      ) : (
        <p className="email-preview__empty">
          No synced email metadata is stored yet. Run a sync to fill this list.
        </p>
      )}
    </section>
  );
}
