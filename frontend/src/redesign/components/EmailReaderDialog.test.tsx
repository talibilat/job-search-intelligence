import { createRef } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiErrorResponse, RawEmailDetail } from "../../api";
import { EmailReaderDialog } from "./EmailReaderDialog";

function email(overrides: Partial<RawEmailDetail> = {}): RawEmailDetail {
  return {
    body_retention_state: "retained",
    body_text: "Email body",
    from_addr: "Jobs Team <jobs@jobs.example>",
    from_domain: "jobs.example",
    ingested_at: "2026-07-12T12:05:00Z",
    labels: ["INBOX", "CATEGORY_UPDATES"],
    provider: "gmail",
    public_id: "email-1",
    sent_at: "2026-07-12T12:00:00Z",
    subject: "Application update",
    to_addr: "Me <me@example.com>",
    ...overrides,
  };
}

function apiError(): ApiErrorResponse {
  return {
    error: {
      code: "email_provider_request_failed",
      details: [],
      message: "Unavailable",
    },
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("EmailReaderDialog", () => {
  it("shows loading before rendering successful email content as literal text", async () => {
    let resolveFetch: (response: Response) => void = () => undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolveFetch = resolve;
          }),
      ),
    );

    const { container } = render(
      <EmailReaderDialog onClose={() => undefined} publicId="email-1" />,
    );

    expect(screen.getByText("Loading email")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Email" })).toBeTruthy();

    resolveFetch(
      jsonResponse(
        email({ body_text: "<strong>Private body</strong>" }),
      ),
    );

    expect(
      await screen.findByText("<strong>Private body</strong>"),
    ).toBeTruthy();
    expect(container.querySelector("strong")).toBeNull();
    expect(
      screen.getByRole("heading", { name: "Application update" }),
    ).toBeTruthy();
    expect(screen.getByText("From: Jobs Team <jobs@jobs.example>")).toBeTruthy();
    expect(screen.getByText("To: Me <me@example.com>")).toBeTruthy();
    expect(screen.getByText("Jul 12, 2026")).toBeTruthy();
    expect(screen.getByText("Gmail")).toBeTruthy();
    expect(screen.getByText("retained")).toBeTruthy();
    expect(screen.getByText("INBOX, CATEGORY_UPDATES")).toBeTruthy();
  });

  it("calls onClose from the labelled close button", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(email()))),
    );
    const onClose = vi.fn();
    render(<EmailReaderDialog onClose={onClose} publicId="email-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Close email" }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("shows loading instead of stale content when reopening the same email", async () => {
    let resolveSecondFetch: (response: Response) => void = () => undefined;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(email({ body_text: "Previously loaded body" })),
      )
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveSecondFetch = resolve;
          }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(
      <EmailReaderDialog onClose={() => undefined} publicId="email-1" />,
    );
    expect(await screen.findByText("Previously loaded body")).toBeTruthy();

    rerender(<EmailReaderDialog onClose={() => undefined} publicId={null} />);
    rerender(
      <EmailReaderDialog onClose={() => undefined} publicId="email-1" />,
    );

    expect(screen.queryByText("Previously loaded body")).toBeNull();
    expect(screen.getByText("Loading email")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);

    resolveSecondFetch(
      jsonResponse(email({ body_text: "Freshly loaded body" })),
    );
    expect(await screen.findByText("Freshly loaded body")).toBeTruthy();
  });

  it("aborts obsolete requests without showing a failure", async () => {
    const signals: AbortSignal[] = [];
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      const signal = init?.signal;
      if (signal) {
        signals.push(signal);
      }
      return new Promise<Response>((_resolve, reject) => {
        signal?.addEventListener("abort", () => {
          reject(new DOMException("The request was aborted", "AbortError"));
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(
      <EmailReaderDialog onClose={() => undefined} publicId="email-1" />,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(signals).toHaveLength(1);

    rerender(
      <EmailReaderDialog onClose={() => undefined} publicId="email-2" />,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(signals[0]?.aborted).toBe(true);
    expect(screen.queryByText("Email content could not be loaded")).toBeNull();
    expect(screen.getByText("Loading email")).toBeTruthy();

    rerender(<EmailReaderDialog onClose={() => undefined} publicId={null} />);
    expect(signals[1]?.aborted).toBe(true);
  });

  it("calls onClose when Escape is pressed", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(email()))),
    );
    const onClose = vi.fn();
    render(<EmailReaderDialog onClose={onClose} publicId="email-1" />);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("keeps focus on the only focusable control", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(email()))),
    );
    render(<EmailReaderDialog onClose={() => undefined} publicId="email-1" />);
    await screen.findByText("Email body");
    const closeButton = screen.getByRole("button", { name: "Close email" });
    closeButton.focus();

    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(closeButton);

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(closeButton);
  });

  it("wraps focus in both directions and recovers focus from outside", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(apiError(), 503))),
    );
    render(
      <>
        <button type="button">Outside</button>
        <EmailReaderDialog onClose={() => undefined} publicId="email-1" />
      </>,
    );
    await screen.findByText("Email content could not be loaded");
    const closeButton = screen.getByRole("button", { name: "Close email" });
    const retryButton = screen.getByRole("button", { name: "Retry" });
    const outsideButton = screen.getByRole("button", { name: "Outside" });

    retryButton.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(closeButton);

    closeButton.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(retryButton);

    outsideButton.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(closeButton);
  });

  it("moves focus into the dialog and restores the trigger when closed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(email()))),
    );
    const triggerRef = createRef<HTMLButtonElement>();
    const onClose = vi.fn();
    const { rerender } = render(
      <>
        <button ref={triggerRef} type="button">
          Open email
        </button>
        <EmailReaderDialog
          onClose={onClose}
          publicId={null}
          triggerRef={triggerRef}
        />
      </>,
    );
    triggerRef.current?.focus();

    rerender(
      <>
        <button ref={triggerRef} type="button">
          Open email
        </button>
        <EmailReaderDialog
          onClose={onClose}
          publicId="email-1"
          triggerRef={triggerRef}
        />
      </>,
    );

    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));

    rerender(
      <>
        <button ref={triggerRef} type="button">
          Open email
        </button>
        <EmailReaderDialog
          onClose={onClose}
          publicId={null}
          triggerRef={triggerRef}
        />
      </>,
    );

    expect(triggerRef.current).toBe(document.activeElement);
  });

  it("shows a failure and retries successfully after a non-200 response", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(apiError(), 503))
      .mockResolvedValueOnce(
        jsonResponse(email({ body_text: "Loaded after retry" })),
      );
    vi.stubGlobal("fetch", fetchMock);
    render(<EmailReaderDialog onClose={() => undefined} publicId="email-1" />);

    expect(
      await screen.findByText("Email content could not be loaded"),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Email" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Loaded after retry")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("closes from the overlay but not from inside the panel", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(email()))),
    );
    const onClose = vi.fn();
    render(<EmailReaderDialog onClose={onClose} publicId="email-1" />);
    const dialog = screen.getByRole("dialog");

    fireEvent.click(dialog);
    expect(onClose).not.toHaveBeenCalled();

    const overlay = dialog.parentElement;
    expect(overlay).not.toBeNull();
    fireEvent.click(overlay!);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("renders nothing while publicId is null", () => {
    const { container } = render(
      <EmailReaderDialog onClose={() => undefined} publicId={null} />,
    );

    expect(container.childElementCount).toBe(0);
  });

  it("uses the fallback heading for an empty subject", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(email({ subject: "  " })))),
    );
    render(<EmailReaderDialog onClose={() => undefined} publicId="email-1" />);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Email" })).toBeTruthy();
  });

  it("ignores stale responses when the selected email changes", async () => {
    const resolvers = new Map<string, (response: Response) => void>();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        return new Promise<Response>((resolve) => {
          resolvers.set(url, resolve);
        });
      }),
    );
    const { rerender } = render(
      <EmailReaderDialog onClose={() => undefined} publicId="email-1" />,
    );
    rerender(
      <EmailReaderDialog onClose={() => undefined} publicId="email-2" />,
    );

    const emailTwoRequest = [...resolvers.entries()].find(([url]) =>
      url.includes("email-2"),
    );
    const emailOneRequest = [...resolvers.entries()].find(([url]) =>
      url.includes("email-1"),
    );
    expect(emailTwoRequest).toBeTruthy();
    expect(emailOneRequest).toBeTruthy();

    emailTwoRequest?.[1](
      jsonResponse(
        email({
          body_text: "Newest body",
          public_id: "email-2",
          subject: "Newest subject",
        }),
      ),
    );
    expect(await screen.findByText("Newest body")).toBeTruthy();

    emailOneRequest?.[1](jsonResponse(email({ body_text: "Stale body" })));
    await waitFor(() => expect(screen.queryByText("Stale body")).toBeNull());
    expect(screen.getByText("Newest body")).toBeTruthy();
  });
});
