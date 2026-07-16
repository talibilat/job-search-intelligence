import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

import {
  syncEmailContentSyncEmailsPublicIdContentGet,
  type RawEmailDetail,
} from "../../api";

interface EmailReaderDialogProps {
  publicId: string | null;
  triggerRef?: RefObject<HTMLElement | null>;
  onClose: () => void;
}

type LoadState =
  | { publicId: string; status: "loading" }
  | { publicId: string; status: "success"; email: RawEmailDetail }
  | { publicId: string; status: "error" };

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function formattedSentDate(sentAt: string): string | null {
  const date = new Date(sentAt);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function emailSubject(subject: string | null | undefined): string {
  const trimmedSubject = subject?.trim();
  if (!trimmedSubject) {
    return "Email";
  }
  return trimmedSubject;
}

function restoreFocus(triggerRef?: RefObject<HTMLElement | null>) {
  const trigger = triggerRef?.current;
  if (trigger && document.contains(trigger)) {
    trigger.focus();
  }
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    error.name === "AbortError"
  );
}

export function EmailReaderDialog({
  publicId,
  triggerRef,
  onClose,
}: EmailReaderDialogProps) {
  const headingId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const wasOpenRef = useRef(false);
  const [loadState, setLoadState] = useState<LoadState | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useLayoutEffect(() => {
    if (!publicId) {
      return;
    }
    // Invalidate prior content before paint, including when reopening the same email.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoadState({ publicId, status: "loading" });
  }, [publicId, retryToken]);

  useEffect(() => {
    if (!publicId) {
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    const load = async () => {
      try {
        const response =
          await syncEmailContentSyncEmailsPublicIdContentGet(publicId, {
            signal: controller.signal,
          });
        if (response.status !== 200) {
          throw new Error("Email content request failed");
        }
        if (!cancelled) {
          setLoadState({ email: response.data, publicId, status: "success" });
        }
      } catch (error) {
        if (!cancelled && !isAbortError(error)) {
          setLoadState({ publicId, status: "error" });
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [publicId, retryToken]);

  useEffect(() => {
    if (publicId) {
      wasOpenRef.current = true;
      dialogRef.current?.focus();
      return;
    }
    if (wasOpenRef.current) {
      wasOpenRef.current = false;
      restoreFocus(triggerRef);
    }
  }, [publicId, triggerRef]);

  useEffect(
    () => () => {
      if (wasOpenRef.current) {
        restoreFocus(triggerRef);
      }
    },
    [triggerRef],
  );

  useEffect(() => {
    if (!publicId) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const dialog = dialogRef.current;
      if (!dialog) {
        return;
      }
      const focusableElements = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      );
      if (focusableElements.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      const activeElement = document.activeElement;
      if (!dialog.contains(activeElement)) {
        event.preventDefault();
        (event.shiftKey ? lastElement : firstElement)?.focus();
        return;
      }
      if (
        focusableElements.length === 1 ||
        (event.shiftKey &&
          (activeElement === firstElement || activeElement === dialog)) ||
        (!event.shiftKey &&
          (activeElement === lastElement || activeElement === dialog))
      ) {
        event.preventDefault();
        (event.shiftKey ? lastElement : firstElement)?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, publicId]);

  if (!publicId) {
    return null;
  }

  const currentState = loadState?.publicId === publicId ? loadState : null;
  const email = currentState?.status === "success" ? currentState.email : null;
  const subject = emailSubject(email?.subject);
  const sentDate = email?.sent_at ? formattedSentDate(email.sent_at) : null;

  return (
    <div
      className="email-reader-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        aria-labelledby={headingId}
        aria-modal="true"
        className="email-reader-dialog"
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="email-reader-header">
          <div className="email-reader-heading-group">
            <h2 id={headingId}>{subject}</h2>
            {email && (email.from_domain || sentDate) ? (
              <p className="email-reader-metadata">
                {email.from_domain ? <span>{email.from_domain}</span> : null}
                {sentDate ? <span>{sentDate}</span> : null}
              </p>
            ) : null}
          </div>
          <button
            aria-label="Close email"
            className="email-reader-close"
            onClick={onClose}
            type="button"
          >
            &times;
          </button>
        </header>
        <div className="email-reader-content">
          {!currentState || currentState.status === "loading" ? (
            <p className="email-reader-message" role="status">
              Loading email
            </p>
          ) : null}
          {currentState?.status === "error" ? (
            <div className="email-reader-error">
              <p role="alert">Email content could not be loaded</p>
              <button
                onClick={() => {
                  setRetryToken((current) => current + 1);
                }}
                type="button"
              >
                Retry
              </button>
            </div>
          ) : null}
          {email ? <div className="email-reader-body">{email.body_text}</div> : null}
        </div>
      </section>
    </div>
  );
}
