import { useEffect, useState, type FormEvent } from "react";

import {
  editApplicationEventApplicationsApplicationIdEventsEventIdPatch,
  editApplicationStatusApplicationsApplicationIdStatusPatch,
  getApplicationDetailApplicationsIdGet,
  getApplicationEventsApplicationsIdEventsGet,
  mergeApplicationApplicationsApplicationIdMergePost,
  resetApplicationLockApplicationsApplicationIdResetLockPost,
  splitApplicationApplicationsApplicationIdSplitPost,
  type ApiErrorResponse,
  type ApplicationEventRecord,
  type ApplicationRecord,
  type ApplicationStatus as ApplicationStatusValue,
} from "../api";
import { Alert } from "../components/ui";
import {
  ApplicationSummary,
  EventCorrectionForm,
  MergeCorrectionForm,
  ResetLockForm,
  SplitCorrectionForm,
  StatusCorrectionForm,
  TimelineTable,
  type EventEditFormState,
} from "./ApplicationCorrectionForms";

interface ApplicationDetailPageProps {
  applicationId: string;
}

type LoadState = "loading" | "loaded" | "error";

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

function eventFormHasChanges(
  eventForm: EventEditFormState,
  event: ApplicationEventRecord | undefined,
) {
  if (!event) {
    return false;
  }

  return (
    eventForm.emailId.trim() !== (event.email_id ?? "") ||
    eventForm.eventAt !== event.event_at ||
    eventForm.eventType !== event.event_type ||
    eventForm.extractNote.trim() !== (event.extract_note ?? "")
  );
}

function eventFormHasSourceEmailForEventType(eventForm: EventEditFormState) {
  return eventForm.eventType === "ghost_inferred" || eventForm.emailId.trim().length > 0;
}

function isIsoDatetime(value: string) {
  const trimmedValue = value.trim();

  return trimmedValue.includes("T") && !Number.isNaN(Date.parse(trimmedValue));
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
  const [resetReason, setResetReason] = useState("");
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
      const nextSelectedEventId = nextEvents.some((event) => event.id === selectedEventId)
        ? selectedEventId
        : nextEvents[0]?.id ?? "";
      const nextSelectedEvent = nextEvents.find(
        (event) => event.id === nextSelectedEventId,
      );

      setEvents(nextEvents);
      setSelectedEventId(nextSelectedEventId);
      setEventForm(eventFormFromEvent(nextSelectedEvent));
    }
  }

  async function handleStatusSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (application === null || statusValue === application.current_status) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    let response: Awaited<ReturnType<typeof editApplicationStatusApplicationsApplicationIdStatusPatch>>;

    try {
      response = await editApplicationStatusApplicationsApplicationIdStatusPatch(
        applicationId,
        {
          current_status: statusValue,
          reason: statusReason.trim() || null,
        },
      );
    } catch {
      setIsSubmitting(false);
      setErrorMessage("Status correction failed.");
      return;
    }

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

    const selectedEvent = events.find((item) => item.id === selectedEventId);
    if (
      !eventFormHasChanges(eventForm, selectedEvent) ||
      eventForm.eventAt.trim().length === 0 ||
      !isIsoDatetime(eventForm.eventAt) ||
      !eventFormHasSourceEmailForEventType(eventForm)
    ) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    let response: Awaited<ReturnType<typeof editApplicationEventApplicationsApplicationIdEventsEventIdPatch>>;

    try {
      response = await editApplicationEventApplicationsApplicationIdEventsEventIdPatch(
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
    } catch {
      setIsSubmitting(false);
      setErrorMessage("Event correction failed.");
      return;
    }

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

    const trimmedMergeSourceId = mergeSourceId.trim();

    if (trimmedMergeSourceId.length === 0 || trimmedMergeSourceId === applicationId) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    let response: Awaited<ReturnType<typeof mergeApplicationApplicationsApplicationIdMergePost>>;

    try {
      response = await mergeApplicationApplicationsApplicationIdMergePost(applicationId, {
        reason: mergeReason.trim() || null,
        source_application_id: trimmedMergeSourceId,
      });
    } catch {
      setIsSubmitting(false);
      setErrorMessage("Merge correction failed.");
      return;
    }

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

  async function handleResetSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (application?.manual_lock !== true) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    let response: Awaited<ReturnType<typeof resetApplicationLockApplicationsApplicationIdResetLockPost>>;

    try {
      response = await resetApplicationLockApplicationsApplicationIdResetLockPost(applicationId, {
        reason: resetReason.trim() || null,
      });
    } catch {
      setIsSubmitting(false);
      setErrorMessage("Manual lock reset failed.");
      return;
    }

    setIsSubmitting(false);

    if (response.status !== 200) {
      setErrorMessage(publicError(response.data, "Manual lock reset failed."));
      return;
    }

    setApplication(response.data.application);
    setResetReason("");
    setSuccessMessage("Manual lock reset saved");
  }

  async function handleSplitSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (
      splitEventIds.length === 0 ||
      splitEventIds.length === events.length ||
      splitCompany.trim().length === 0 ||
      splitRole.trim().length === 0
    ) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    let response: Awaited<ReturnType<typeof splitApplicationApplicationsApplicationIdSplitPost>>;

    try {
      response = await splitApplicationApplicationsApplicationIdSplitPost(applicationId, {
        event_ids: splitEventIds,
        new_application: {
          company: splitCompany.trim(),
          role_title: splitRole.trim(),
        },
        reason: splitReason.trim() || null,
      });
    } catch {
      setIsSubmitting(false);
      setErrorMessage("Split correction failed.");
      return;
    }

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

  const selectedEvent = events.find((event) => event.id === selectedEventId);
  const hasEventFieldChanges = eventFormHasChanges(eventForm, selectedEvent);
  const hasEventTime = eventForm.eventAt.trim().length > 0;
  const hasValidEventTime = !hasEventTime || isIsoDatetime(eventForm.eventAt);
  const hasSourceEmailForEventType = eventFormHasSourceEmailForEventType(eventForm);
  const hasStatusChange = statusValue !== application?.current_status;

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
        <ApplicationSummary application={application} />
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
        <StatusCorrectionForm
          hasStatusChange={hasStatusChange}
          isSubmitting={isSubmitting}
          onReasonChange={setStatusReason}
          onStatusChange={setStatusValue}
          onSubmit={(event) => {
            void handleStatusSubmit(event);
          }}
          reason={statusReason}
          statusValue={statusValue}
        />

        <MergeCorrectionForm
          isSubmitting={isSubmitting}
          onReasonChange={setMergeReason}
          onSourceIdChange={setMergeSourceId}
          onSubmit={(event) => {
            void handleMergeSubmit(event);
          }}
          reason={mergeReason}
          sourceId={mergeSourceId}
          targetId={applicationId}
        />

        <ResetLockForm
          isSubmitting={isSubmitting}
          manualLock={application.manual_lock}
          onReasonChange={setResetReason}
          onSubmit={(event) => {
            void handleResetSubmit(event);
          }}
          reason={resetReason}
        />

        <TimelineTable events={events} />

        <EventCorrectionForm
          eventForm={eventForm}
          hasEventFieldChanges={hasEventFieldChanges}
          hasEventTime={hasEventTime}
          hasValidEventTime={hasValidEventTime}
          hasSourceEmailForEventType={hasSourceEmailForEventType}
          events={events}
          isSubmitting={isSubmitting}
          onEventFormChange={setEventForm}
          onSelectEvent={handleSelectEvent}
          onSubmit={(event) => {
            void handleEventSubmit(event);
          }}
          selectedEventId={selectedEventId}
        />

        <SplitCorrectionForm
          company={splitCompany}
          events={events}
          isSubmitting={isSubmitting}
          onCompanyChange={setSplitCompany}
          onReasonChange={setSplitReason}
          onRoleChange={setSplitRole}
          onSubmit={(event) => {
            void handleSplitSubmit(event);
          }}
          onToggleEvent={toggleSplitEvent}
          reason={splitReason}
          role={splitRole}
          selectedEventIds={splitEventIds}
        />
      </section>
    </main>
  );
}
