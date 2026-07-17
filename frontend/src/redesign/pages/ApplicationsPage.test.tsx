import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApplicationEventTimelineRecord, ApplicationRecord } from "../../api";
import { ApplicationsPage } from "./ApplicationsPage";

function application(overrides: Partial<ApplicationRecord> = {}): ApplicationRecord {
  return {
    company: "Acme",
    created_at: "2026-07-01T12:00:00Z",
    currency: null,
    current_status: "applied",
    first_seen_at: "2026-07-01T12:00:00Z",
    id: "app-1",
    last_activity_at: "2026-07-03T12:00:00Z",
    location: "Remote",
    manual_lock: false,
    role_title: "Platform Engineer",
    salary_max: null,
    salary_min: null,
    seniority: "senior",
    source: "linkedin",
    sponsorship: "unknown",
    tech_stack: [],
    updated_at: "2026-07-03T12:00:00Z",
    work_mode: "remote",
    ...overrides,
  };
}

function event(id: string, eventType: ApplicationEventTimelineRecord["event_type"]): ApplicationEventTimelineRecord {
  return {
    application_id: "app-1",
    email_id: null,
    event_at: "2026-07-03T12:00:00Z",
    event_type: eventType,
    extract_note: null,
    id,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });
}

function deferredResponse() {
  let resolve: (response: Response) => void = () => undefined;
  const promise = new Promise<Response>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

function renderApplications(reloadKey: number) {
  return (
    <ApplicationsPage
      openApp={() => undefined}
      reloadKey={reloadKey}
      setStatusFilter={() => undefined}
      statusFilter="all"
    />
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/applications");
});

describe("ApplicationsPage timeline refresh", () => {
  it("applies active URL filters to both rows and status totals", async () => {
    window.history.replaceState(null, "", "/applications?role=Platform&work_mode=remote");
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      requests.push(path);
      if (path.startsWith("/applications/status-counts?")) {
        return Promise.resolve(jsonResponse({ counts: { interview: 1 }, total: 1 }));
      }
      if (path.startsWith("/applications?")) {
        return Promise.resolve(jsonResponse([application({ current_status: "interview" })]));
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    render(renderApplications(0));

    expect(await screen.findByRole("button", { name: "All 1" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Interview 1" })).toBeTruthy();
    const applicationRequests = requests.filter((request) => request.startsWith("/applications"));
    expect(applicationRequests).toHaveLength(2);
    for (const request of applicationRequests) {
      const params = new URL(request, "http://localhost").searchParams;
      expect(params.get("role")).toBe("Platform");
      expect(params.get("work_mode")).toBe("remote");
    }
  });

  it("explains that totals are partial when refreshed status counts fail", async () => {
    let applicationRequestCount = 0;
    let countRequestCount = 0;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/applications") {
        applicationRequestCount += 1;
        return Promise.resolve(
          jsonResponse(
            applicationRequestCount === 1
              ? [application()]
              : [
                  application({ company: "New One", current_status: "offer", id: "app-2" }),
                  application({ company: "New Two", current_status: "offer", id: "app-3" }),
                ],
          ),
        );
      }
      if (path === "/applications/status-counts") {
        countRequestCount += 1;
        return Promise.resolve(
          countRequestCount === 1
            ? jsonResponse({ counts: { applied: 7, offer: 2 }, total: 9 })
            : jsonResponse(
                { error: { code: "counts_failed", details: [], message: "Counts failed." } },
                503,
              ),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    const { rerender } = render(renderApplications(0));
    expect(await screen.findByRole("button", { name: "Applied 7" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "All 9" })).toBeTruthy();

    rerender(renderApplications(1));
    await screen.findByText("New Two");
    expect((await screen.findByRole("alert")).textContent).toContain("Counts failed.");
    expect(screen.getByRole("button", { name: "All 2" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Applied 0" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Offer 2" })).toBeTruthy();
  });

  it.each([
    ["screening", ["assessment-new", "review-new", "assessment-old"]],
    ["closed", ["rejected-new", "withdrawn-new", "ghost-old"]],
  ] as const)("globally sorts merged %s responses by first seen date and ID", async (statusFilter, expected) => {
    const fixtures: Record<string, ApplicationRecord[]> = {
      assessment: [
        application({ id: "assessment-new", company: "assessment-new", current_status: "assessment", first_seen_at: "2026-07-05T12:00:00Z" }),
        application({ id: "assessment-old", company: "assessment-old", current_status: "assessment", first_seen_at: "2026-07-01T12:00:00Z" }),
      ],
      in_review: [application({ id: "review-new", company: "review-new", current_status: "in_review", first_seen_at: "2026-07-05T12:00:00Z" })],
      rejected: [application({ id: "rejected-new", company: "rejected-new", current_status: "rejected", first_seen_at: "2026-07-06T12:00:00Z" })],
      ghosted: [application({ id: "ghost-old", company: "ghost-old", current_status: "ghosted", first_seen_at: "2026-06-01T12:00:00Z" })],
      withdrawn: [application({ id: "withdrawn-new", company: "withdrawn-new", current_status: "withdrawn", first_seen_at: "2026-07-06T12:00:00Z" })],
    };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const status = new URL(path, "http://localhost").searchParams.get("status") ?? "";
      if (path.startsWith("/applications?")) return Promise.resolve(jsonResponse(fixtures[status] ?? []));
      if (path === "/applications/status-counts") return Promise.resolve(jsonResponse({ counts: {}, total: 3 }));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    const { container } = render(
      <ApplicationsPage openApp={() => undefined} reloadKey={0} setStatusFilter={() => undefined} statusFilter={statusFilter} />,
    );
    await screen.findByText(expected[0]);
    const rows = [...container.querySelectorAll(".rd-hover-row")].map((row) => row.textContent ?? "");
    expect(rows.map((row) => expected.find((id) => row.includes(id)))).toEqual([...expected]);
  });

  it("re-enters loading on reload and replaces a prior success", async () => {
    const refreshedTimeline = deferredResponse();
    let eventRequestCount = 0;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/applications") return Promise.resolve(jsonResponse([application()]));
      if (path === "/applications/app-1/events") {
        eventRequestCount += 1;
        return eventRequestCount === 1
          ? Promise.resolve(jsonResponse([event("event-1", "applied")]))
          : refreshedTimeline.promise;
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    const { rerender } = render(renderApplications(0));
    await screen.findByText("Acme");
    fireEvent.click(screen.getByRole("button", { name: "Timeline" }));
    expect(await screen.findByText("1 step")).toBeTruthy();

    rerender(renderApplications(1));
    expect(await screen.findByText("Loading…")).toBeTruthy();
    refreshedTimeline.resolve(
      jsonResponse([event("event-1", "applied"), event("event-2", "response")]),
    );
    expect(await screen.findByText("2 steps")).toBeTruthy();
  });

  it("retries and replaces a prior timeline error after reload", async () => {
    const refreshedTimeline = deferredResponse();
    let eventRequestCount = 0;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/applications") return Promise.resolve(jsonResponse([application()]));
      if (path === "/applications/app-1/events") {
        eventRequestCount += 1;
        return eventRequestCount === 1
          ? Promise.resolve(
              jsonResponse(
                { error: { code: "timeline_failed", details: [], message: "Timeline failed." } },
                503,
              ),
            )
          : refreshedTimeline.promise;
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    const { rerender } = render(renderApplications(0));
    await screen.findByText("Acme");
    fireEvent.click(screen.getByRole("button", { name: "Timeline" }));
    expect(await screen.findByText("Timeline failed.")).toBeTruthy();

    rerender(renderApplications(1));
    expect(await screen.findByText("Loading…")).toBeTruthy();
    refreshedTimeline.resolve(jsonResponse([]));
    expect(await screen.findByText("No timeline events")).toBeTruthy();
  });

  it("keeps loading visible for pending events and ignores a stale generation", async () => {
    const staleTimeline = deferredResponse();
    const currentTimeline = deferredResponse();
    let eventRequestCount = 0;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/applications") return Promise.resolve(jsonResponse([application()]));
      if (path === "/applications/app-1/events") {
        eventRequestCount += 1;
        return eventRequestCount === 1 ? staleTimeline.promise : currentTimeline.promise;
      }
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));

    const { rerender } = render(renderApplications(0));
    await screen.findByText("Acme");
    fireEvent.click(screen.getByRole("button", { name: "Timeline" }));
    expect(await screen.findByText("Loading…")).toBeTruthy();

    rerender(renderApplications(1));
    await waitFor(() => expect(eventRequestCount).toBe(2));
    expect(screen.getByText("Loading…")).toBeTruthy();
    currentTimeline.resolve(
      jsonResponse([event("event-1", "applied"), event("event-2", "response")]),
    );
    expect(await screen.findByText("2 steps")).toBeTruthy();

    staleTimeline.resolve(jsonResponse([event("stale-event", "applied")]));
    await waitFor(() => expect(screen.getByText("2 steps")).toBeTruthy());
    expect(screen.queryByText("1 step")).toBeNull();
  });
});
