import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RawEmailPreviewPage, RawEmailPreviewRecord } from "../../api";
import { SyncedEmailList } from "./SyncedEmailList";

function email(index: number): RawEmailPreviewRecord {
  return {
    body_retention_state: "metadata_only",
    classification_category: null,
    classification_is_job_related: null,
    filter_outcome: null,
    filter_reason: null,
    from_domain: `sender-${index}.example`,
    has_retained_body: false,
    ingested_at: "2026-07-12T12:00:00Z",
    provider: "gmail",
    public_id: `email-${index}`,
    sent_at: `2026-07-${String((index % 9) + 1).padStart(2, "0")}T12:00:00Z`,
    subject: `Subject ${index}`,
    subject_present: true,
    to_domains: ["recipient.example"],
  };
}

function page(pageNumber: number, totalItems = 23): RawEmailPreviewPage {
  const firstIndex = (pageNumber - 1) * 10 + 1;
  const itemCount = Math.min(10, Math.max(0, totalItems - firstIndex + 1));
  return {
    items: Array.from({ length: itemCount }, (_, index) =>
      email(firstIndex + index),
    ),
    page: pageNumber,
    page_size: 10,
    total_items: totalItems,
    total_pages: Math.ceil(totalItems / 10),
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });
}

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === "string"
    ? input
    : input instanceof URL
      ? input.href
      : input.url;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SyncedEmailList", () => {
  it("renders ten email rows and three-page navigation", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(page(1)))));

    render(
      <SyncedEmailList
        onOpenEmail={() => undefined}
        refreshToken={0}
      />,
    );

    const list = await screen.findByLabelText("Synced emails");
    expect(within(list).getAllByRole("button")).toHaveLength(10);
    expect(screen.getByRole("button", { name: "1" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "2" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "3" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Previous" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(screen.getByRole("button", { name: "Next" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("requests page two with the page size and selected period", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(requestUrl(input), "http://localhost");
      return Promise.resolve(
        jsonResponse(page(Number(url.searchParams.get("page") ?? "1"))),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <SyncedEmailList
        onOpenEmail={() => undefined}
        refreshToken={0}
        sentAfter="2026-07-05T00:00:00Z"
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "2" }));
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map(([input]) =>
        new URL(requestUrl(input), "http://localhost"),
      );
      expect(
        urls.some(
          (url) =>
            url.searchParams.get("page") === "2" &&
            url.searchParams.get("page_size") === "10" &&
            url.searchParams.get("sent_after") === "2026-07-05T00:00:00Z",
        ),
      ).toBe(true);
    });
  });

  it("renders the selected-period empty state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(page(1, 0)))));

    render(
      <SyncedEmailList
        onOpenEmail={() => undefined}
        refreshToken={0}
      />,
    );

    expect(
      await screen.findByText("No emails found in the selected period."),
    ).toBeTruthy();
  });

  it("shows a neutral error and retries the current page", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: "unavailable" }, 503))
      .mockResolvedValueOnce(jsonResponse(page(1)));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <SyncedEmailList
        onOpenEmail={() => undefined}
        refreshToken={0}
      />,
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent?.toLowerCase()).not.toContain("disconnected");
    expect(alert.textContent?.toLowerCase()).not.toContain("reconnect");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Subject 1")).toBeTruthy();
  });

  it("resets to page one when the refresh token changes", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(requestUrl(input), "http://localhost");
      return Promise.resolve(
        jsonResponse(page(Number(url.searchParams.get("page") ?? "1"))),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(
      <SyncedEmailList
        onOpenEmail={() => undefined}
        refreshToken={0}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "2" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "2" }).getAttribute("aria-current")).toBe(
        "page",
      ),
    );
    const callsBeforeRefresh = fetchMock.mock.calls.length;

    rerender(
      <SyncedEmailList
        onOpenEmail={() => undefined}
        refreshToken={1}
      />,
    );

    await waitFor(() => {
      const refreshUrls = fetchMock.mock.calls
        .slice(callsBeforeRefresh)
        .map(([input]) => new URL(requestUrl(input), "http://localhost"));
      expect(
        refreshUrls.some((url) => url.searchParams.get("page") === "1"),
      ).toBe(true);
      expect(screen.getByRole("button", { name: "1" }).getAttribute("aria-current")).toBe(
        "page",
      );
    });
  });
});
