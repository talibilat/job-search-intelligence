import { useEffect, useState } from "react";

import {
  syncEmailsSyncEmailsGet,
  type RawEmailPreviewPage,
  type RawEmailPreviewRecord,
} from "../../api";

interface SyncedEmailListProps {
  refreshToken: number;
  sentAfter?: string;
  sentBefore?: string;
  onOpenEmail: (email: RawEmailPreviewRecord) => void;
}

const PAGE_SIZE = 10;
const PAGE_WINDOW_SIZE = 5;

function formattedSentDate(sentAt: string | null): string {
  if (!sentAt) {
    return "Unknown date";
  }
  const date = new Date(sentAt);
  if (Number.isNaN(date.getTime())) {
    return "Unknown date";
  }
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
  }).format(date);
}

function companyName(domain: string | null): string {
  if (!domain) return "Unknown company";
  const aliases: Record<string, string> = {
    "mail.tsenta.com": "Tsenta",
    "smartrecruiters.com": "SmartRecruiters",
  };
  if (aliases[domain]) return aliases[domain];
  const labels = domain.toLowerCase().split(".");
  const meaningful = labels.length > 2 && ["mail", "jobs", "careers", "www"].includes(labels[0] ?? "") ? labels[1] : labels[0];
  return (meaningful ?? domain).split("-").map((part) => part ? part[0]?.toUpperCase() + part.slice(1) : "").join(" ");
}

function visiblePages(currentPage: number, totalPages: number): number[] {
  const start = Math.max(
    1,
    Math.min(currentPage - 2, totalPages - PAGE_WINDOW_SIZE + 1),
  );
  const end = Math.min(totalPages, start + PAGE_WINDOW_SIZE - 1);
  return Array.from({ length: Math.max(0, end - start + 1) }, (_, index) =>
    start + index,
  );
}

export function SyncedEmailList({
  refreshToken,
  sentAfter,
  sentBefore,
  onOpenEmail,
}: SyncedEmailListProps) {
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<RawEmailPreviewPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    // The product contract requires this reset to be a separate prop-keyed effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPage(1);
  }, [refreshToken, sentAfter, sentBefore]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await syncEmailsSyncEmailsGet({
          page,
          page_size: PAGE_SIZE,
          sent_after: sentAfter,
          sent_before: sentBefore,
        });
        if (response.status !== 200) {
          throw new Error("Synced email request failed");
        }
        if (!cancelled) {
          setResult(response.data);
        }
      } catch {
        if (!cancelled) {
          setResult(null);
          setError("Emails could not be loaded.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [page, refreshToken, retryToken, sentAfter, sentBefore]);

  const totalPages = result?.total_pages ?? 0;

  return (
    <div className="synced-email-list-shell">
      {loading ? (
        <p className="synced-email-list-message" role="status">
          Loading emails…
        </p>
      ) : null}
      {!loading && error ? (
        <div className="synced-email-list-error">
          <p role="alert">{error}</p>
          <button
            className="rd-hover-green-border"
            onClick={() => setRetryToken((current) => current + 1)}
            type="button"
          >
            Retry
          </button>
        </div>
      ) : null}
      {!loading && !error && result?.items.length === 0 ? (
        <p className="synced-email-list-message">
          No emails found in the selected period.
        </p>
      ) : null}
      <ul aria-label="Synced emails" className="synced-email-list">
        {!error
          ? result?.items.map((item) => {
              const subject =
                item.subject_present && item.subject?.trim()
                  ? item.subject.trim()
                  : "(no subject)";
              return (
                <li key={item.public_id}>
                  <button
                    className="synced-email-list-row rd-hover-soft"
                    onClick={() => onOpenEmail(item)}
                    type="button"
                  >
                    <span className="synced-email-list-sender">
                      {companyName(item.from_domain)}
                    </span>
                    <span className="synced-email-list-subject">{subject}</span>
                    <span className="synced-email-list-date">
                      {formattedSentDate(item.sent_at)}
                    </span>
                  </button>
                </li>
              );
            })
          : null}
      </ul>
      {!loading && !error && result && result.items.length > 0 ? (
        <nav aria-label="Synced email pages" className="synced-email-pagination">
          <button
            className="rd-hover-green-border"
            disabled={page === 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            type="button"
          >
            Previous
          </button>
          <span className="synced-email-pagination-pages">
            {visiblePages(page, totalPages).map((pageNumber) => (
              <button
                aria-current={pageNumber === page ? "page" : undefined}
                className="rd-hover-green-border"
                key={pageNumber}
                onClick={() => setPage(pageNumber)}
                type="button"
              >
                {pageNumber}
              </button>
            ))}
          </span>
          <button
            className="rd-hover-green-border"
            disabled={totalPages === 0 || page >= totalPages}
            onClick={() =>
              setPage((current) => Math.min(totalPages, current + 1))
            }
            type="button"
          >
            Next
          </button>
        </nav>
      ) : null}
    </div>
  );
}
