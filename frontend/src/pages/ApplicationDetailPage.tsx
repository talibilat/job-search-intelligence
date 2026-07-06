import { useEffect, useState, type FormEvent } from "react";

import {
  ApplicationEventType,
  ApplicationStatus,
  editApplicationEventApplicationsApplicationIdEventsEventIdPatch,
  editApplicationStatusApplicationsApplicationIdStatusPatch,
  getApplicationDetailApplicationsIdGet,
  getApplicationEventsApplicationsIdEventsGet,
  mergeApplicationApplicationsApplicationIdMergePost,
  splitApplicationApplicationsApplicationIdSplitPost,
  type ApiErrorResponse,
  type ApplicationEventRecord,
  type ApplicationEventType as ApplicationEventTypeValue,
  type ApplicationRecord,
  type ApplicationStatus as ApplicationStatusValue,
} from "../api";
import { Alert, Button, DataTable, FormField, TextInput } from "../components/ui";

interface ApplicationDetailPageProps {
  applicationId: string;
}

type LoadState = "loading" | "loaded" | "error";

interface EventEditFormState {
  emailId: string;
  eventAt: string;
  eventType: ApplicationEventTypeValue;
  extractNote: string;
  reason: string;
}

const statusOptions = Object.values(ApplicationStatus) as ApplicationStatusValue[];
const eventTypeOptions = Object.values(ApplicationEventType) as ApplicationEventTypeValue[];

function toTitle(value: string) {
  const label = value.replaceAll("_", " ");

  return label.charAt(0).toUpperCase() + label.slice(1);
}

function publicError(data: unknown, fallback: string) {
  if (
    typeof data === "object" &&
    data !== null &&
    "error" in data &&
    typeof (data as ApiErrorResponse).error?.message === "string"
  ) {
    return (data as ApiErrorResponse).error.message;
  }

  return fallback;
}

function eventFormFromEvent(event: ApplicationEventRecord | undefined): EventEditFormState {
  return {
    emailId: event?.email_id ?? "",
    eventAt: event?.event_at ?? "",
    eventType: event?.event_type ?? "applied",
    extractNote: event?.extract_note ?? "",
    reason: "",
  };
}

function sortEvents(events: ApplicationEventRecord[]) {
  return [...events].sort((left, right) => left.event_at.localeCompare(right.event_at));
}

export function ApplicationDetailPage({ applicationId }: ApplicationDetailPageProps) {
  const [application, setApplication] = useState<ApplicationRecord | null>(null);
  const [events, setEvents] = useState<ApplicationEventRecord[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [statusValue, setStatusValue] = useState<ApplicationStatusValue>("applied");
  const [statusReason, setStatusReason] = useState("");
  const [selectedEventId, setSelectedEventId] = useState("");
  const [eventForm, setEventForm] = useState<EventEditFormState>(() =>
    eventFormFromEvent(undefined),
  );
  const [mergeSourceId, setMergeSourceId] = useState("");
  const [mergeReason, setMergeReason] = useState("");
  const [splitEventIds, setSplitEventIds] = useState<string[]>([]);
  const [splitCompany, setSplitCompany] = useState("");
  const [splitRole, setSplitRole] = useState("");
  const [splitReason, setSplitReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let isCancelled = false;

    async function loadApplication() {
      setLoadState("loading");
      setErrorMessage(null);

      const [applicationResponse, eventsResponse] = await Promise.all([
        getApplicationDetailApplicationsIdGet(applicationId),
        getApplicationEventsApplicationsIdEventsGet(applicationId),
      ]);

      if (isCancelled) {
        return;
      }

      if (applicationResponse.status !== 200) {
        setErrorMessage(
          publicError(applicationResponse.data, "Application detail is unavailable."),
        );
        setLoadState("error");
        return;
      }

      if (eventsResponse.status !== 200) {
        setErrorMessage(
          publicError(eventsResponse.data, "Application events are unavailable."),
        );
        setLoadState("error");
        return;
      }

      const nextEvents = sortEvents(eventsResponse.data);
      const firstEvent = nextEvents[0];
      setApplication(applicationResponse.data);
      setEvents(nextEvents);
      setStatusValue(applicationResponse.data.current_status);
      setSelectedEventId(firstEvent?.id ?? "");
      setEventForm(eventFormFromEvent(firstEvent));
      setLoadState("loaded");
    }

    void loadApplication().catch(() => {
      if (!isCancelled) {
        setErrorMessage("Application detail is unavailable. Start the local backend to edit corrections.");
        setLoadState("error");
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [applicationId]);

  async function refreshEvents() {
    const eventsResponse = await getApplicationEventsApplicationsIdEventsGet(applicationId);

    if (eventsResponse.status === 200) {
      const nextEvents = sortEvents(eventsResponse.data);
      setEvents(nextEvents);
      if (nextEvents.length === 0) {
        setSelectedEventId("");
        setEventForm(eventFormFromEvent(undefined));
      }
    }
  }

  async function handleStatusSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    const response = await editApplicationStatusApplicationsApplicationIdStatusPatch(
      applicationId,
      {
        current_status: statusValue,
        reason: statusReason.trim() || null,
      },
    );

    setIsSubmitting(false);

    if (response.status !== 200) {
      setErrorMessage(publicError(response.data, "Status correction failed."));
      return;
    }

    setApplication(response.data.application);
    setStatusValue(response.data.application.current_status);
    setStatusReason("");
    setSuccessMessage("Status correction saved");
  }

  async function handleEventSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedEventId) {
      setErrorMessage("Select an event before saving an event correction.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    const response = await editApplicationEventApplicationsApplicationIdEventsEventIdPatch(
      applicationId,
      selectedEventId,
      {
        email_id: eventForm.emailId.trim() || null,
        event_at: eventForm.eventAt,
        event_type: eventForm.eventType,
        extract_note: eventForm.extractNote.trim() || null,
        reason: eventForm.reason.trim() || null,
      },
    );

    setIsSubmitting(false);

    if (response.status !== 200) {
      setErrorMessage(publicError(response.data, "Event correction failed."));
      return;
    }

    setApplication(response.data.application);
    setEvents((currentEvents) =>
      sortEvents(
        currentEvents.map((currentEvent) =>
          currentEvent.id === selectedEventId ? response.data.event : currentEvent,
        ),
      ),
    );
    setSelectedEventId(response.data.event.id);
    setEventForm(eventFormFromEvent(response.data.event));
    setSuccessMessage("Event correction saved");
  }

  async function handleMergeSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    const response = await mergeApplicationApplicationsApplicationIdMergePost(applicationId, {
      reason: mergeReason.trim() || null,
      source_application_id: mergeSourceId.trim(),
    });

    setIsSubmitting(false);

    if (response.status !== 200) {
      setErrorMessage(publicError(response.data, "Merge correction failed."));
      return;
    }

    setApplication(response.data.application);
    setMergeSourceId("");
    setMergeReason("");
    await refreshEvents();
    setSuccessMessage("Merge correction saved");
  }

  async function handleSplitSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    const response = await splitApplicationApplicationsApplicationIdSplitPost(applicationId, {
      event_ids: splitEventIds,
      new_application: {
        company: splitCompany.trim(),
        role_title: splitRole.trim(),
        source: application?.source ?? "other",
        sponsorship: application?.sponsorship ?? "unknown",
      },
      reason: splitReason.trim() || null,
    });

    setIsSubmitting(false);

    if (response.status !== 200) {
      setErrorMessage(publicError(response.data, "Split correction failed."));
      return;
    }

    setApplication(response.data.source_application);
    setSplitEventIds([]);
    setSplitCompany("");
    setSplitRole("");
    setSplitReason("");
    await refreshEvents();
    setSuccessMessage("Split correction saved");
  }

  function handleSelectEvent(eventId: string) {
    const event = events.find((item) => item.id === eventId);
    setSelectedEventId(eventId);
    setEventForm(eventFormFromEvent(event));
  }

  function toggleSplitEvent(eventId: string, checked: boolean) {
    setSplitEventIds((currentIds) =>
      checked
        ? Array.from(new Set([...currentIds, eventId]))
        : currentIds.filter((currentId) => currentId !== eventId),
    );
  }

  if (loadState === "loading") {
    return (
      <main aria-labelledby="application-detail-title" className="app-shell application-detail-shell">
        <section className="dashboard-hero" aria-labelledby="application-detail-title">
          <p className="eyebrow">Application detail</p>
          <h1 id="application-detail-title">Loading application</h1>
        </section>
      </main>
    );
  }

  if (loadState === "error" || application === null) {
    return (
      <main aria-labelledby="application-detail-title" className="app-shell application-detail-shell">
        <section className="dashboard-hero" aria-labelledby="application-detail-title">
          <p className="eyebrow">Application detail</p>
          <h1 id="application-detail-title">Application unavailable</h1>
          <Alert title="Application detail unavailable" tone="danger">
            <p>{errorMessage ?? "Application detail is unavailable."}</p>
          </Alert>
        </section>
      </main>
    );
  }

  return (
    <main aria-labelledby="application-detail-title" className="app-shell application-detail-shell">
      <section className="application-detail-hero" aria-labelledby="application-detail-title">
        <p className="eyebrow">Application correction workspace</p>
        <h1 id="application-detail-title">
          {application.company} - {application.role_title}
        </h1>
        <div className="application-detail-summary" aria-label="Application summary">
          <span>Status: {toTitle(application.current_status)}</span>
          <span>{application.manual_lock ? "Manual lock enabled" : "Automatic updates allowed"}</span>
          <span>{toTitle(application.source)}</span>
        </div>
      </section>

      {successMessage ? (
        <Alert role="status" title={successMessage} tone="success">
          <p>The local SQLite source of truth has been updated and audited.</p>
        </Alert>
      ) : null}
      {errorMessage ? (
        <Alert title="Correction failed" tone="danger">
          <p>{errorMessage}</p>
        </Alert>
      ) : null}

      <section className="application-detail-grid" aria-label="Correction tools">
        <article className="application-detail-card">
          <div>
            <p className="eyebrow">Status</p>
            <h2>Edit current status</h2>
          </div>
          <form
            className="application-detail-form"
            onSubmit={(event) => {
              void handleStatusSubmit(event);
            }}
          >
            <FormField htmlFor="status-value" label="Correct status">
              <select
                className="ui-input"
                id="status-value"
                onChange={(event) => setStatusValue(event.target.value as ApplicationStatusValue)}
                value={statusValue}
              >
                {statusOptions.map((status) => (
                  <option key={status} value={status}>
                    {toTitle(status)}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField htmlFor="status-reason" label="Status correction reason">
              <TextInput
                id="status-reason"
                onChange={(event) => setStatusReason(event.target.value)}
                value={statusReason}
              />
            </FormField>
            <Button disabled={isSubmitting} type="submit">
              Save status correction
            </Button>
          </form>
        </article>

        <article className="application-detail-card">
          <div>
            <p className="eyebrow">Merge</p>
            <h2>Merge duplicate application</h2>
          </div>
          <form
            className="application-detail-form"
            onSubmit={(event) => {
              void handleMergeSubmit(event);
            }}
          >
            <FormField htmlFor="merge-source-id" label="Source application ID">
              <TextInput
                id="merge-source-id"
                onChange={(event) => setMergeSourceId(event.target.value)}
                required
                value={mergeSourceId}
              />
            </FormField>
            <FormField htmlFor="merge-reason" label="Merge reason">
              <TextInput
                id="merge-reason"
                onChange={(event) => setMergeReason(event.target.value)}
                value={mergeReason}
              />
            </FormField>
            <Button disabled={isSubmitting || mergeSourceId.trim().length === 0} type="submit">
              Merge source application
            </Button>
          </form>
        </article>

        <article className="application-detail-card application-detail-card--wide">
          <div>
            <p className="eyebrow">Timeline</p>
            <h2>Event timeline</h2>
          </div>
          <DataTable
            caption="Application event timeline"
            columns={[
              { key: "event_type", header: "Event", render: (row) => toTitle(row.event_type) },
              { key: "event_at", header: "When" },
              { key: "email_id", header: "Source email" },
              { key: "extract_note", header: "Note" },
            ]}
            emptyMessage="No events recorded for this application."
            rowKey={(row) => row.id}
            rows={events}
          />
        </article>

        <article className="application-detail-card">
          <div>
            <p className="eyebrow">Event edit</p>
            <h2>Edit timeline event</h2>
          </div>
          <form
            className="application-detail-form"
            onSubmit={(event) => {
              void handleEventSubmit(event);
            }}
          >
            <FormField htmlFor="event-id" label="Event to edit">
              <select
                className="ui-input"
                disabled={events.length === 0}
                id="event-id"
                onChange={(event) => handleSelectEvent(event.target.value)}
                value={selectedEventId}
              >
                {events.map((event) => (
                  <option key={event.id} value={event.id}>
                    {event.id}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField htmlFor="event-type" label="Event type">
              <select
                className="ui-input"
                disabled={!selectedEventId}
                id="event-type"
                onChange={(event) =>
                  setEventForm((current) => ({
                    ...current,
                    eventType: event.target.value as ApplicationEventTypeValue,
                  }))
                }
                value={eventForm.eventType}
              >
                {eventTypeOptions.map((eventType) => (
                  <option key={eventType} value={eventType}>
                    {toTitle(eventType)}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField htmlFor="event-time" label="Event time">
              <TextInput
                disabled={!selectedEventId}
                id="event-time"
                onChange={(event) =>
                  setEventForm((current) => ({ ...current, eventAt: event.target.value }))
                }
                value={eventForm.eventAt}
              />
            </FormField>
            <FormField htmlFor="event-email" label="Source email">
              <TextInput
                disabled={!selectedEventId}
                id="event-email"
                onChange={(event) =>
                  setEventForm((current) => ({ ...current, emailId: event.target.value }))
                }
                value={eventForm.emailId}
              />
            </FormField>
            <FormField htmlFor="event-note" label="Event note">
              <TextInput
                disabled={!selectedEventId}
                id="event-note"
                onChange={(event) =>
                  setEventForm((current) => ({ ...current, extractNote: event.target.value }))
                }
                value={eventForm.extractNote}
              />
            </FormField>
            <FormField htmlFor="event-reason" label="Event correction reason">
              <TextInput
                disabled={!selectedEventId}
                id="event-reason"
                onChange={(event) =>
                  setEventForm((current) => ({ ...current, reason: event.target.value }))
                }
                value={eventForm.reason}
              />
            </FormField>
            <Button disabled={isSubmitting || !selectedEventId} type="submit">
              Save event correction
            </Button>
          </form>
        </article>

        <article className="application-detail-card">
          <div>
            <p className="eyebrow">Split</p>
            <h2>Split selected events</h2>
          </div>
          <form
            className="application-detail-form"
            onSubmit={(event) => {
              void handleSplitSubmit(event);
            }}
          >
            <fieldset className="application-detail-fieldset">
              <legend>Events to move</legend>
              {events.length > 0 ? (
                events.map((event) => (
                  <label className="application-detail-checkbox" key={event.id}>
                    <input
                      checked={splitEventIds.includes(event.id)}
                      onChange={(inputEvent) =>
                        toggleSplitEvent(event.id, inputEvent.target.checked)
                      }
                      type="checkbox"
                    />
                    <span>{event.id}</span>
                  </label>
                ))
              ) : (
                <p>No events are available to split.</p>
              )}
            </fieldset>
            <FormField htmlFor="split-company" label="New application company">
              <TextInput
                id="split-company"
                onChange={(event) => setSplitCompany(event.target.value)}
                required
                value={splitCompany}
              />
            </FormField>
            <FormField htmlFor="split-role" label="New application role">
              <TextInput
                id="split-role"
                onChange={(event) => setSplitRole(event.target.value)}
                required
                value={splitRole}
              />
            </FormField>
            <FormField htmlFor="split-reason" label="Split reason">
              <TextInput
                id="split-reason"
                onChange={(event) => setSplitReason(event.target.value)}
                value={splitReason}
              />
            </FormField>
            <Button
              disabled={
                isSubmitting ||
                splitEventIds.length === 0 ||
                splitCompany.trim().length === 0 ||
                splitRole.trim().length === 0
              }
              type="submit"
            >
              Split selected events
            </Button>
          </form>
        </article>
      </section>
    </main>
  );
}
