import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApplicationDetailPage } from "./ApplicationDetailPage";

type MockResponseBody = Record<string, unknown> | unknown[];

type MockResponse =
  | MockResponseBody
  | {
      body: MockResponseBody;
      status: number;
    };

type MockResponseConfig = MockResponse | MockResponse[];

const applicationRecord = {
  company: "Acme Corp",
  created_at: "2026-07-01T09:00:00Z",
  currency: null,
  current_status: "applied",
  first_seen_at: "2026-07-01T09:00:00Z",
  id: "app-1",
  last_activity_at: "2026-07-01T09:00:00Z",
  location: null,
  manual_lock: false,
  role_title: "Software Engineer",
  salary_max: null,
  salary_min: null,
  seniority: null,
  source: "other",
  sponsorship: "unknown",
  tech_stack: ["Python"],
  updated_at: "2026-07-01T09:00:00Z",
  work_mode: null,
};

const applicationEvent = {
  application_id: "app-1",
  email_id: "email-1",
  event_at: "2026-07-01T09:00:00Z",
  event_type: "applied",
  extract_note: "Application confirmation received.",
  extracted_status: "applied",
  id: "event-1",
};

const secondApplicationEvent = {
  ...applicationEvent,
  email_id: "email-2",
  event_at: "2026-07-02T09:00:00Z",
  id: "event-2",
};

function correctionRecord(correctionType: string) {
  return {
    after_json: {},
    application_id: "app-1",
    before_json: {},
    correction_type: correctionType,
    created_at: "2026-07-06T09:30:00Z",
    id: 1,
    reason: "Corrected from the detail screen.",
  };
}

function isMockResponseConfig(
  value: MockResponse,
): value is { body: MockResponseBody; status: number } {
  return !Array.isArray(value) && "body" in value && "status" in value;
}

function mockFetchResponses(responses: Record<string, MockResponseConfig>) {
  const responseQueues = new Map<string, MockResponse[]>();

  for (const [path, response] of Object.entries(responses)) {
    responseQueues.set(
      path,
      Array.isArray(response) ? [...(response as MockResponse[])] : [response],
    );
  }

  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    const path = url.startsWith("http") ? new URL(url).pathname : url;
    const config = responseQueues.get(path);

    if (!config) {
      throw new Error(`Unhandled fetch request: ${path}`);
    }

    const nextConfig = config.length > 1 ? config.shift() : config[0];

    if (!nextConfig) {
      throw new Error(`No mock fetch responses left for: ${path}`);
    }

    const body = isMockResponseConfig(nextConfig)
      ? nextConfig.body
      : nextConfig;
    const status = isMockResponseConfig(nextConfig) ? nextConfig.status : 200;

    return Promise.resolve(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status,
      }),
    );
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function mockFetchImplementation(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
) {
  const fetchMock = vi.fn(handler);

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function requestJson(fetchMock: ReturnType<typeof vi.fn>, path: string) {
  const call = fetchMock.mock.calls.find(([input]) => input === path);
  const init = call?.[1] as RequestInit | undefined;

  return typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ApplicationDetailPage", () => {
  it("explains the application event timeline data source", async () => {
    mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByRole("heading", {
      level: 1,
      name: "Acme Corp - Software Engineer",
    });

    const infoButton = screen.getByRole("button", {
      name: "About Event timeline",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("GET /applications/{id}/events")).toBeTruthy();
    expect(screen.getByText("application_events")).toBeTruthy();
    expect(
      screen.getByText(/Run Gmail sync, classification, and aggregation/),
    ).toBeTruthy();
    expect(
      screen.getByText(/If the timeline is empty, confirm classification produced job-related evidence/),
    ).toBeTruthy();
  });

  it("explains the status correction data source", async () => {
    mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByRole("heading", {
      level: 1,
      name: "Acme Corp - Software Engineer",
    });

    const infoButton = screen.getByRole("button", {
      name: "About Status correction",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("PATCH /applications/{application_id}/status")).toBeTruthy();
    expect(screen.getByText("applications, application_corrections")).toBeTruthy();
    expect(screen.getByText(/writes an audited status_edit correction/)).toBeTruthy();
    expect(
      screen.getByText(/If the status looks wrong, inspect the event timeline/),
    ).toBeTruthy();
  });

  it("explains the merge correction data source", async () => {
    mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByRole("heading", {
      level: 1,
      name: "Acme Corp - Software Engineer",
    });

    const infoButton = screen.getByRole("button", {
      name: "About Merge correction",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("POST /applications/{application_id}/merge")).toBeTruthy();
    expect(screen.getByText("applications, application_events, application_corrections")).toBeTruthy();
    expect(screen.getByText(/Moves events from a duplicate source application/)).toBeTruthy();
    expect(screen.getByText(/If the source application ID is missing/)).toBeTruthy();
  });

  it("disables merge when the source is the current application", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByRole("heading", {
      level: 1,
      name: "Acme Corp - Software Engineer",
    });

    fireEvent.change(screen.getByLabelText("Source application ID"), {
      target: { value: "app-1" },
    });

    expect(
      screen.getByText(
        "Choose a different source application. An application cannot be merged into itself.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Merge source application" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(requestJson(fetchMock, "/applications/app-1/merge")).toBeNull();
  });

  it("disables merge until a source application ID is entered", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Source application ID");

    expect(
      screen.getByText("Enter the duplicate source application ID before merging."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Merge source application" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.submit(screen.getByRole("button", { name: "Merge source application" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/merge")).toBeNull();
  });

  it("explains the split correction data source", async () => {
    mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByRole("heading", {
      level: 1,
      name: "Acme Corp - Software Engineer",
    });

    const infoButton = screen.getByRole("button", {
      name: "About Split correction",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("POST /applications/{application_id}/split")).toBeTruthy();
    expect(screen.getByText("applications, application_events, application_corrections")).toBeTruthy();
    expect(screen.getByText(/source application and selectable events come from local Gmail sync/)).toBeTruthy();
    expect(screen.getByText(/moves selected timeline events into a new manually locked application/)).toBeTruthy();
    expect(screen.getByText(/If no events are available to split/)).toBeTruthy();

    fireEvent.click(infoButton);
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoButton);
    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
  });

  it("explains the reset manual lock data source", async () => {
    mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByRole("heading", {
      level: 1,
      name: "Acme Corp - Software Engineer",
    });

    const infoButton = screen.getByRole("button", {
      name: "About Manual lock reset",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("POST /applications/{application_id}/reset-lock")).toBeTruthy();
    expect(screen.getByText("applications, application_corrections")).toBeTruthy();
    expect(screen.getByText(/allows future aggregation reruns to update/)).toBeTruthy();
    expect(screen.getByText(/Manual status, event, merge, or split corrections create the lock/)).toBeTruthy();
    expect(screen.getByText(/If the manual lock is not enabled/)).toBeTruthy();

    fireEvent.click(infoButton);
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(infoButton);
    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
  });

  it("disables manual lock reset when automatic updates are already allowed", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    expect(await screen.findByText("Automatic updates allowed")).toBeTruthy();
    expect(
      screen.getByText(
        "Manual lock reset is only available after a manual correction has locked this application.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reset manual lock" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(screen.getByLabelText("Reset reason")).toHaveProperty("disabled", true);

    fireEvent.submit(screen.getByRole("button", { name: "Reset manual lock" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/reset-lock")).toBeNull();
  });

  it("explains the event correction data source", async () => {
    mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByRole("heading", {
      level: 1,
      name: "Acme Corp - Software Engineer",
    });

    const infoButton = screen.getByRole("button", {
      name: "About Event correction",
    });
    expect(infoButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.focus(infoButton);

    expect(infoButton.getAttribute("aria-expanded")).toBe("true");
    expect(
      screen.getByText("PATCH /applications/{application_id}/events/{event_id}"),
    ).toBeTruthy();
    expect(screen.getByText("application_events, application_corrections")).toBeTruthy();
    expect(screen.getByText(/writes an audited event_edit correction/)).toBeTruthy();
    expect(screen.getByText(/Run Gmail sync, classification, and aggregation/)).toBeTruthy();
    expect(screen.getByText(/If event details look wrong, compare them with the source email/)).toBeTruthy();
  });

  it("explains the disabled event correction state when no events exist", async () => {
    mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByRole("heading", {
      level: 1,
      name: "Acme Corp - Software Engineer",
    });

    expect(screen.getByText("No timeline events are available to edit.")).toBeTruthy();
    expect(
      screen.getByText(/Run Gmail sync, classification, and aggregation from Feature Status/),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save event correction" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("disables event correction until at least one event field changes", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Event to edit");

    expect(
      screen.getByText("Change at least one event field before saving an event correction."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save event correction" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.click(screen.getByRole("button", { name: "Save event correction" }));

    expect(requestJson(fetchMock, "/applications/app-1/events/event-1")).toBeNull();
  });

  it("disables event correction when the event time is blank", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Event to edit");
    fireEvent.change(screen.getByLabelText("Event time"), {
      target: { value: "" },
    });

    expect(screen.getByText("Enter an event time before saving an event correction.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save event correction" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.submit(screen.getByRole("button", { name: "Save event correction" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/events/event-1")).toBeNull();
  });

  it("disables event correction when the event time is not an ISO datetime", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Event to edit");
    fireEvent.change(screen.getByLabelText("Event time"), {
      target: { value: "tomorrow afternoon" },
    });

    expect(screen.getByText("Enter an ISO datetime before saving an event correction.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save event correction" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.submit(screen.getByRole("button", { name: "Save event correction" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/events/event-1")).toBeNull();
  });

  it("disables event correction when the event time is an impossible calendar date", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Event to edit");
    fireEvent.change(screen.getByLabelText("Event time"), {
      target: { value: "2026-02-30T09:00:00Z" },
    });

    expect(screen.getByText("Enter an ISO datetime before saving an event correction.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save event correction" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.submit(screen.getByRole("button", { name: "Save event correction" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/events/event-1")).toBeNull();
  });

  it("disables event correction when the event time has no timezone offset", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Event to edit");
    fireEvent.change(screen.getByLabelText("Event time"), {
      target: { value: "2026-07-01T10:00:00" },
    });

    expect(screen.getByText("Enter an ISO datetime with a timezone before saving an event correction.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save event correction" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.submit(screen.getByRole("button", { name: "Save event correction" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/events/event-1")).toBeNull();
  });

  it("disables event correction when a non-inferred event would lose its source email", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
      "/applications/app-1/events/event-1": {
        application: applicationRecord,
        correction: correctionRecord("event_edit"),
        event: {
          ...applicationEvent,
          email_id: null,
        },
      },
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Event to edit");
    fireEvent.change(screen.getByLabelText("Source email"), {
      target: { value: "" },
    });

    expect(
      screen.getByText(
        "Keep a source email unless the event is a ghost inference with no source message.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save event correction" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.submit(screen.getByRole("button", { name: "Save event correction" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/events/event-1")).toBeNull();
  });

  it("disables event correction when a ghost inference keeps a source email", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
      "/applications/app-1/events/event-1": {
        application: applicationRecord,
        correction: correctionRecord("event_edit"),
        event: {
          ...applicationEvent,
          event_type: "ghost_inferred",
        },
      },
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Event to edit");
    fireEvent.change(screen.getByLabelText("Event type"), {
      target: { value: "ghost_inferred" },
    });

    expect(
      screen.getByText("Clear the source email before saving a ghost-inferred event."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save event correction" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.submit(screen.getByRole("button", { name: "Save event correction" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/events/event-1")).toBeNull();
  });

  it("loads application detail and saves a manual status correction", async () => {
    const rejectedApplication = {
      ...applicationRecord,
      current_status: "rejected",
      manual_lock: true,
    };
    const fetchMock = mockFetchResponses({
      "/applications/app-1": [applicationRecord, rejectedApplication],
      "/applications/app-1/events": [[applicationEvent], [applicationEvent]],
      "/applications/app-1/status": {
        application: rejectedApplication,
        correction: correctionRecord("status_edit"),
      },
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Acme Corp - Software Engineer",
      }),
    ).toBeTruthy();
    expect(screen.getByRole("region", { name: "Correction tools" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Correct status"), {
      target: { value: "rejected" },
    });
    fireEvent.change(screen.getByLabelText("Status correction reason"), {
      target: { value: "The rejection email was missed." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save status correction" }));

    expect(await screen.findByText("Status correction saved"));
    expect(requestJson(fetchMock, "/applications/app-1/status")).toEqual({
      current_status: "rejected",
      reason: "The rejection email was missed.",
    });
    expect(await screen.findByText("Status: Rejected")).toBeTruthy();
  });

  it("disables status correction until the selected status changes", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Correct status");

    expect(
      screen.getByText("Choose a different status before saving a status correction."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save status correction" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.submit(screen.getByRole("button", { name: "Save status correction" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/status")).toBeNull();
  });

  it("shows a public-safe error and releases the submit button when a correction request fails", async () => {
    mockFetchImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const path = url.startsWith("http") ? new URL(url).pathname : url;

      if (path === "/applications/app-1") {
        return Promise.resolve(new Response(JSON.stringify(applicationRecord), { status: 200 }));
      }

      if (path === "/applications/app-1/events") {
        return Promise.resolve(new Response(JSON.stringify([applicationEvent]), { status: 200 }));
      }

      return Promise.reject(new TypeError("Network request failed"));
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Correct status");
    fireEvent.change(screen.getByLabelText("Correct status"), {
      target: { value: "rejected" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save status correction" }));

    expect(await screen.findByText("Status correction failed.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save status correction" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("saves a manual event correction from the detail screen", async () => {
    const updatedEvent = {
      ...applicationEvent,
      event_at: "2026-07-07T14:00:00Z",
      event_type: "interview_scheduled",
      extract_note: "Recruiter scheduled a phone screen.",
      id: "event-2",
    };
    const updatedApplication = {
      ...applicationRecord,
      current_status: "interview",
      manual_lock: true,
    };
    const fetchMock = mockFetchResponses({
      "/applications/app-1": [applicationRecord, updatedApplication],
      "/applications/app-1/events": [[applicationEvent], [updatedEvent]],
      "/applications/app-1/events/event-1": {
        application: updatedApplication,
        correction: correctionRecord("event_edit"),
        event: updatedEvent,
      },
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Event to edit");
    fireEvent.change(screen.getByLabelText("Event type"), {
      target: { value: "interview_scheduled" },
    });
    fireEvent.change(screen.getByLabelText("Event time"), {
      target: { value: "2026-07-07T14:00:00Z" },
    });
    fireEvent.change(screen.getByLabelText("Event note"), {
      target: { value: "Recruiter scheduled a phone screen." },
    });
    fireEvent.change(screen.getByLabelText("Event correction reason"), {
      target: { value: "The event type was classified incorrectly." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save event correction" }));

    expect(await screen.findByText("Event correction saved")).toBeTruthy();
    expect(requestJson(fetchMock, "/applications/app-1/events/event-1")).toEqual({
      email_id: "email-1",
      event_at: "2026-07-07T14:00:00Z",
      event_type: "interview_scheduled",
      extract_note: "Recruiter scheduled a phone screen.",
      reason: "The event type was classified incorrectly.",
    });
    expect((await screen.findAllByText("Interview scheduled")).length).toBeGreaterThan(0);
  });

  it("merges and splits applications from the detail screen", async () => {
    const lockedApplication = {
      ...applicationRecord,
      manual_lock: true,
    };
    const fetchMock = mockFetchResponses({
      "/applications/app-1": [
        applicationRecord,
        lockedApplication,
        lockedApplication,
      ],
      "/applications/app-1/events": [
        [applicationEvent],
        [applicationEvent, secondApplicationEvent],
        [],
      ],
      "/applications/app-1/merge": {
        application: lockedApplication,
        correction: correctionRecord("merge"),
        moved_event_count: 1,
        source_application_id: "duplicate-app",
        target_application_id: "app-1",
      },
      "/applications/app-1/split": {
        correction: correctionRecord("split"),
        moved_events: [applicationEvent],
        new_application: {
          ...applicationRecord,
          company: "Beta Corp",
          id: "app-2",
          role_title: "Backend Engineer",
        },
        source_application: lockedApplication,
      },
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    await screen.findByLabelText("Source application ID");
    fireEvent.change(screen.getByLabelText("Source application ID"), {
      target: { value: "duplicate-app" },
    });
    fireEvent.change(screen.getByLabelText("Merge reason"), {
      target: { value: "These rows are duplicates." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Merge source application" }));

    expect(await screen.findByText("Merge correction saved")).toBeTruthy();
    expect(requestJson(fetchMock, "/applications/app-1/merge")).toEqual({
      reason: "These rows are duplicates.",
      source_application_id: "duplicate-app",
    });

    fireEvent.click(await screen.findByRole("checkbox", { name: /event-1/ }));
    fireEvent.change(screen.getByLabelText("New application company"), {
      target: { value: "Beta Corp" },
    });
    fireEvent.change(screen.getByLabelText("New application role"), {
      target: { value: "Backend Engineer" },
    });
    fireEvent.change(screen.getByLabelText("Split reason"), {
      target: { value: "This event belongs to a different application." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Split selected events" }));

    expect(await screen.findByText("Split correction saved")).toBeTruthy();
    expect(requestJson(fetchMock, "/applications/app-1/split")).toEqual({
      event_ids: ["event-1"],
      new_application: {
        company: "Beta Corp",
        role_title: "Backend Engineer",
      },
      reason: "This event belongs to a different application.",
    });
  });

  it("resets the manual correction lock from the detail screen", async () => {
    const lockedApplication = {
      ...applicationRecord,
      manual_lock: true,
    };
    const unlockedApplication = {
      ...applicationRecord,
      manual_lock: false,
    };
    const fetchMock = mockFetchResponses({
      "/applications/app-1": [lockedApplication, unlockedApplication],
      "/applications/app-1/events": [[applicationEvent], [applicationEvent]],
      "/applications/app-1/reset-lock": {
        application: unlockedApplication,
        correction: correctionRecord("reset_lock"),
      },
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    expect(await screen.findByText("Manual lock enabled")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Reset reason"), {
      target: { value: "Let automatic aggregation update this row again." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reset manual lock" }));

    expect(await screen.findByText("Manual lock reset saved")).toBeTruthy();
    expect(requestJson(fetchMock, "/applications/app-1/reset-lock")).toEqual({
      reason: "Let automatic aggregation update this row again.",
    });
    expect(await screen.findByText("Automatic updates allowed")).toBeTruthy();
  });

  it("selects an available event after refresh removes the previously selected event", async () => {
    const lockedApplication = {
      ...applicationRecord,
      manual_lock: true,
    };
    mockFetchResponses({
      "/applications/app-1": [applicationRecord, lockedApplication],
      "/applications/app-1/events": [
        [applicationEvent, secondApplicationEvent],
        [secondApplicationEvent],
      ],
      "/applications/app-1/split": {
        correction: correctionRecord("split"),
        moved_events: [applicationEvent],
        new_application: {
          ...applicationRecord,
          company: "Beta Corp",
          id: "app-2",
          role_title: "Backend Engineer",
        },
        source_application: lockedApplication,
      },
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    fireEvent.click(await screen.findByRole("checkbox", { name: /event-1/ }));
    fireEvent.change(screen.getByLabelText("New application company"), {
      target: { value: "Beta Corp" },
    });
    fireEvent.change(screen.getByLabelText("New application role"), {
      target: { value: "Backend Engineer" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Split selected events" }));

    expect(await screen.findByText("Split correction saved")).toBeTruthy();
    expect(screen.getByLabelText("Event to edit")).toHaveProperty("value", "event-2");
    expect(screen.getByLabelText("Source email")).toHaveProperty("value", "email-2");
  });

  it("disables split when every source event is selected", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    fireEvent.click(await screen.findByRole("checkbox", { name: /event-1/ }));
    fireEvent.change(screen.getByLabelText("New application company"), {
      target: { value: "Beta Corp" },
    });
    fireEvent.change(screen.getByLabelText("New application role"), {
      target: { value: "Backend Engineer" },
    });

    expect(
      screen.getByText(
        "Leave at least one event on the source application. Move only the events that belong to the new application.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Split selected events" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.submit(screen.getByRole("button", { name: "Split selected events" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/split")).toBeNull();
  });

  it("disables split when the new application identity is missing", async () => {
    const fetchMock = mockFetchResponses({
      "/applications/app-1": applicationRecord,
      "/applications/app-1/events": [[applicationEvent, secondApplicationEvent]],
    });

    render(<ApplicationDetailPage applicationId="app-1" />);

    fireEvent.click(await screen.findByRole("checkbox", { name: /event-1/ }));

    expect(
      screen.getByText("Enter the new application company and role before splitting events."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Split selected events" })).toHaveProperty(
      "disabled",
      true,
    );

    fireEvent.submit(screen.getByRole("button", { name: "Split selected events" }).closest("form")!);

    expect(requestJson(fetchMock, "/applications/app-1/split")).toBeNull();
  });
});
