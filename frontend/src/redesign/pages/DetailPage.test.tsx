import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  ApplicationEventTimelineRecord,
  ApplicationRecord,
  ApplicationStatus,
} from "../../api";
import { DetailPage } from "./DetailPage";

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

function timelineEvent(
  id: string,
  eventAt: string,
  overrides: Partial<ApplicationEventTimelineRecord> = {},
): ApplicationEventTimelineRecord {
  return {
    application_id: "app-1",
    email_id: `email-${id}`,
    email_subject: "Source evidence",
    event_at: eventAt,
    event_type: "response",
    extract_note: id,
    id,
    ...overrides,
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

type FetchHandler = Response | Promise<Response> | ((init?: RequestInit) => Response | Promise<Response>);

function stubDetailFetch(
  currentApplication: ApplicationRecord,
  initialEvents: ApplicationEventTimelineRecord[],
  mutations: Record<string, FetchHandler> = {},
) {
  let loadedApplication = currentApplication;
  let loadedEvents = initialEvents;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const handler = mutations[path];
    if (!handler) {
      if (path === "/applications/app-1") return jsonResponse(loadedApplication);
      if (path === "/applications/app-1/events") return jsonResponse(loadedEvents);
      if (path === "/applications/app-1/correction-conflicts") return jsonResponse([]);
      if (path === "/applications/app-1/corrections") return jsonResponse([]);
    }
    if (!handler) {
      throw new Error(`Unhandled fetch request: ${path}`);
    }
    const response = await Promise.resolve(typeof handler === "function" ? handler(init) : handler);
    const body = await response.clone().json() as {
        application?: ApplicationRecord;
        event?: ApplicationEventTimelineRecord;
        source_application?: ApplicationRecord;
      };
    if (body.application || body.source_application || body.event) {
      loadedApplication = body.application ?? body.source_application ?? loadedApplication;
      if (body.event) {
        loadedEvents = loadedEvents.map((event) => event.id === body.event?.id ? body.event : event);
      }
    }
    return response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function correction(applicationId: string, type: "status_edit" | "event_edit") {
  return {
    after_json: {},
    application_id: applicationId,
    before_json: {},
    correction_type: type,
    created_at: "2026-07-11T12:00:00Z",
    id: 1,
    reason: null,
  };
}

function renderDetail(onChanged = vi.fn()) {
  render(
    <DetailPage
      applicationId="app-1"
      go={() => undefined}
      onChanged={onChanged}
    />,
  );
  return onChanged;
}

function startEventEdit(note: string, reason = "Correcting the source event.") {
  fireEvent.click(screen.getByRole("button", { name: "Fix a mistake" }));
  fireEvent.change(screen.getByLabelText("Event note"), { target: { value: note } });
  fireEvent.change(screen.getByLabelText("Correction reason"), { target: { value: reason } });
}

function expectBefore(firstText: string, secondText: string) {
  const first = screen.getByText(new RegExp(firstText));
  const second = screen.getByText(new RegExp(secondText));
  expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DetailPage corrections", () => {
  it("shows the lock, conflicting evidence, and visible correction audit", async () => {
    stubDetailFetch(application({ manual_lock: true }), [], {
      "/applications/app-1/correction-conflicts": jsonResponse([{
        application_id: "app-1",
        conflict_key: "application_summary:app-1:email-2",
        conflict_type: "application_summary",
        created_at: "2026-07-12T12:00:00Z",
        evidence_email_id: "email-2",
        existing_json: { application: { current_status: "interview" } },
        id: 3,
        proposed_json: { application: { current_status: "rejected" } },
      }]),
      "/applications/app-1/corrections": jsonResponse([{
        ...correction("app-1", "status_edit"),
        after_json: { current_status: "interview" },
        before_json: { current_status: "applied" },
        reason: "The interview email confirms progress.",
      }]),
    });
    renderDetail();

    expect(await screen.findByText("Manual correction lock is on")).toBeTruthy();
    expect(screen.getByText("New evidence conflicts with your correction")).toBeTruthy();
    expect(screen.getByText(/application summary from email email-2/)).toBeTruthy();
    expect(screen.getByText(/status edit/)).toBeTruthy();
    fireEvent.click(screen.getByText(/status edit/));
    expect(screen.getByText(/The interview email confirms progress/)).toBeTruthy();
  });

  it("merges a duplicate and refreshes detail, events, conflicts, history, and metrics", async () => {
    const fetchMock = stubDetailFetch(application(), [], {
      "/applications/app-1/merge": jsonResponse({ application: application({ manual_lock: true }), correction: correction("app-1", "status_edit"), moved_events: [] }),
    });
    const onChanged = renderDetail();

    await screen.findByText("Repair grouping mistakes");
    fireEvent.change(screen.getByLabelText("Duplicate application ID"), { target: { value: "app-2" } });
    fireEvent.change(screen.getByLabelText("Reason", { selector: "input#merge-reason" }), { target: { value: "Duplicate evidence" } });
    fireEvent.click(screen.getByRole("button", { name: "Merge into this record" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    for (const path of [
      "/applications/app-1",
      "/applications/app-1/events",
      "/applications/app-1/correction-conflicts",
      "/applications/app-1/corrections",
    ]) {
      expect(fetchMock.mock.calls.filter(([input]) => input === path)).toHaveLength(2);
    }
  });

  it("splits selected evidence and can reset the resulting manual lock", async () => {
    const first = timelineEvent("event-1", "2026-07-01T12:00:00Z");
    const second = timelineEvent("event-2", "2026-07-02T12:00:00Z");
    const fetchMock = stubDetailFetch(application({ manual_lock: true }), [first, second], {
      "/applications/app-1/split": jsonResponse({ source_application: application({ manual_lock: true }), new_application: application({ id: "split-1", manual_lock: true }), moved_events: [first], correction: correction("app-1", "status_edit") }),
      "/applications/app-1/reset-lock": jsonResponse({ application: application(), correction: correction("app-1", "status_edit") }),
    });
    const onChanged = renderDetail();

    await screen.findByText("Split timeline events");
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.change(screen.getByLabelText("New company"), { target: { value: "Beta" } });
    fireEvent.change(screen.getByLabelText("New role"), { target: { value: "Engineer" } });
    fireEvent.click(screen.getByRole("button", { name: "Create split application" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Reset lock" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls.some(([input]) => input === "/applications/app-1/split")).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => input === "/applications/app-1/reset-lock")).toBe(true);
  });

  it("keeps the saved status until the audited correction succeeds and disables duplicates", async () => {
    const pending = deferredResponse();
    const saved = application({ current_status: "offer", manual_lock: true });
    const fetchMock = stubDetailFetch(application(), [], {
      "/applications/app-1/status": pending.promise,
    });
    renderDetail();

    const status = await screen.findByLabelText<HTMLSelectElement>("Application status");
    expect(Array.from(status.options, (option) => option.value)).toEqual([
      "applied",
      "in_review",
      "assessment",
      "interview",
      "offer",
      "rejected",
      "ghosted",
      "withdrawn",
    ] satisfies ApplicationStatus[]);
    fireEvent.change(status, { target: { value: "offer" } });
    fireEvent.change(status, { target: { value: "interview" } });

    expect(status.value).toBe("applied");
    expect(status.disabled).toBe(true);
    expect(
      fetchMock.mock.calls.filter(([input]) => input === "/applications/app-1/status"),
    ).toHaveLength(1);

    pending.resolve(
      jsonResponse({ application: saved, correction: correction("app-1", "status_edit") }),
    );
    await waitFor(() => expect(status.value).toBe("offer"));
    expect(screen.getByText("Edited by you - protected from auto-updates")).toBeTruthy();
  });

  it("preserves status and shows a typed status-correction failure", async () => {
    stubDetailFetch(application(), [], {
      "/applications/app-1/status": jsonResponse(
        {
          error: {
            code: "invalid_status_correction",
            details: [],
            message: "That status cannot follow the current timeline.",
          },
        },
        422,
      ),
    });
    renderDetail();

    const status = await screen.findByLabelText<HTMLSelectElement>("Application status");
    fireEvent.change(status, { target: { value: "offer" } });

    expect((await screen.findByRole("alert")).textContent).toContain(
      "That status cannot follow the current timeline.",
    );
    expect(status.value).toBe("applied");
  });

  it("edits an event in its card through the audited endpoint", async () => {
    const original = timelineEvent("event-1", "2026-07-03T12:00:00Z", {
      classification_confidence: 0.91,
      email_subject: "Your interview",
      event_type: "interview_scheduled",
      extract_note: "Initial interview",
    });
    const saved = application({ current_status: "in_review", manual_lock: true });
    const fetchMock = stubDetailFetch(application({ current_status: "interview" }), [original], {
      "/applications/app-1/events/event-1": jsonResponse({
        application: saved,
        correction: correction("app-1", "event_edit"),
        event: { ...original, event_type: "response", extract_note: "Recruiter screen" },
      }),
    });
    renderDetail();

    await screen.findByText(/Initial interview/);
    startEventEdit("Recruiter screen", "The email describes a recruiter screen.");
    fireEvent.change(screen.getByLabelText("Event type"), { target: { value: "response" } });
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));

    expect(await screen.findByText(/Recruiter screen/)).toBeTruthy();
    const call = fetchMock.mock.calls.find(
      ([input]) => input === "/applications/app-1/events/event-1",
    );
    expect(JSON.parse(call?.[1]?.body as string)).toMatchObject({
      event_type: "response",
      extract_note: "Recruiter screen",
      reason: "The email describes a recruiter screen.",
    });
    expect(screen.getByText(/Your interview/).closest("button")).toBeNull();
  });

  it("shows a typed event-edit failure without changing application or event state", async () => {
    const original = timelineEvent("event-1", "2026-07-03T12:00:00Z", {
      extract_note: "Original note",
    });
    stubDetailFetch(application({ current_status: "interview" }), [original], {
      "/applications/app-1/events/event-1": jsonResponse(
        {
          error: {
            code: "invalid_event_correction",
            details: [],
            message: "That event correction conflicts with its source.",
          },
        },
        422,
      ),
    });
    renderDetail();

    await screen.findByText(/Original note/);
    startEventEdit("Unsaved note");
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "That event correction conflicts with its source.",
    );
    expect(screen.getByLabelText<HTMLSelectElement>("Application status").value).toBe("interview");
    expect(screen.getByText(/Original note/)).toBeTruthy();
  });

  it("turns duplicate rapid event submissions into one request", async () => {
    const original = timelineEvent("event-1", "2026-07-03T12:00:00Z");
    const pending = deferredResponse();
    const fetchMock = stubDetailFetch(application(), [original], {
      "/applications/app-1/events/event-1": pending.promise,
    });
    renderDetail();

    await screen.findByText(/event-1/);
    startEventEdit("Changed once");
    const save = screen.getByRole("button", { name: "Save correction" });
    fireEvent.click(save);
    fireEvent.click(save);

    expect(save).toHaveProperty("disabled", true);
    expect(
      fetchMock.mock.calls.filter(([input]) => input === "/applications/app-1/events/event-1"),
    ).toHaveLength(1);
  });
});

describe("DetailPage timeline evidence", () => {
  it("distinguishes detail transport failure from a missing application and supports retry", async () => {
    let detailCalls = 0;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (path === "/applications/app-1") {
        detailCalls += 1;
        return Promise.resolve(detailCalls === 1
          ? jsonResponse({ error: { code: "service_unavailable", details: [], message: "Database is temporarily unavailable." } }, 503)
          : jsonResponse(application()));
      }
      if (path === "/applications/app-1/events") return Promise.resolve(jsonResponse([]));
      return Promise.reject(new Error(`Unhandled fetch request: ${path}`));
    }));
    renderDetail();

    expect((await screen.findByRole("alert")).textContent).toContain("Database is temporarily unavailable.");
    expect(screen.queryByText("Application unavailable")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/Platform Engineer/)).toBeTruthy();
  });

  it("shows a timeline request failure instead of an empty timeline", async () => {
    stubDetailFetch(application(), [], {
      "/applications/app-1/events": jsonResponse(
        { error: { code: "timeline_failed", details: [], message: "Timeline storage is unavailable." } },
        503,
      ),
    });
    renderDetail();

    expect((await screen.findByRole("alert")).textContent).toContain("Timeline storage is unavailable.");
    expect(screen.queryByText(/No source emails are attached/)).toBeNull();
  });
  it("sorts initial events newest first with stable ties", async () => {
    stubDetailFetch(application(), [
      timelineEvent("oldest", "2026-07-01T12:00:00Z"),
      timelineEvent("tie-first", "2026-07-03T12:00:00Z"),
      timelineEvent("tie-second", "2026-07-03T12:00:00Z"),
      timelineEvent("newest", "2026-07-05T12:00:00Z"),
    ]);
    renderDetail();

    await screen.findByText(/newest/);
    expectBefore("newest", "tie-first");
    expectBefore("tie-first", "tie-second");
    expectBefore("tie-second", "oldest");
  });

  it("sorts offset-bearing timestamps by chronological instant on initial load", async () => {
    stubDetailFetch(application(), [
      timelineEvent("lexically-later", "2026-07-01T10:00:00+02:00"),
      timelineEvent("chronologically-later", "2026-07-01T09:30:00Z"),
    ]);
    renderDetail();

    await screen.findByText(/chronologically-later/);
    expectBefore("chronologically-later", "lexically-later");
  });

  it("reorders an offset-bearing timestamp edit by chronological instant", async () => {
    const older = timelineEvent("older", "2026-07-01T08:00:00Z");
    const newer = timelineEvent("newer", "2026-07-01T09:30:00Z");
    stubDetailFetch(application(), [older, newer], {
      "/applications/app-1/events/older": jsonResponse({
        application: application({ manual_lock: true }),
        correction: correction("app-1", "event_edit"),
        event: { ...older, event_at: "2026-07-01T08:45:00-01:00" },
      }),
    });
    renderDetail();

    await screen.findByText(/newer/);
    expectBefore("newer", "older");
    const editButtons = screen.getAllByRole("button", { name: "Fix a mistake" });
    fireEvent.click(editButtons[1]);
    fireEvent.change(screen.getByLabelText("Event time"), {
      target: { value: "2026-07-01T08:45:00-01:00" },
    });
    fireEvent.change(screen.getByLabelText("Correction reason"), {
      target: { value: "The event happened later." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));

    await waitFor(() => expect(screen.queryByLabelText("Event time")).toBeNull());
    await waitFor(() => expectBefore("older", "newer"));
  });

  it("counts only events with source emails", async () => {
    stubDetailFetch(application(), [
      timelineEvent("source", "2026-07-03T12:00:00Z"),
      timelineEvent("inferred", "2026-07-04T12:00:00Z", {
        email_id: null,
        email_subject: null,
        event_type: "ghost_inferred",
      }),
    ]);
    renderDetail();

    expect(await screen.findByText(/1 source email in your inbox/)).toBeTruthy();
    expect(screen.queryByText(/2 source emails in your inbox/)).toBeNull();
  });

  it("describes an all-inferred timeline without calling events inbox emails", async () => {
    stubDetailFetch(application(), [
      timelineEvent("inferred-one", "2026-07-03T12:00:00Z", {
        email_id: null,
        email_subject: null,
        event_type: "ghost_inferred",
      }),
      timelineEvent("inferred-two", "2026-07-04T12:00:00Z", {
        email_id: null,
        email_subject: null,
        event_type: "ghost_inferred",
      }),
    ]);
    renderDetail();

    expect((await screen.findByText(/2 timeline events/)).textContent).toContain(
      "No source emails are attached",
    );
    expect(screen.queryByText(/emails in your inbox/)).toBeNull();
  });
});
