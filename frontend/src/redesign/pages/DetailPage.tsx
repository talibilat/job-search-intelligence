import { useEffect, useRef, useState, type FormEvent } from "react";

import {
  ApplicationEventType,
  editApplicationEventApplicationsApplicationIdEventsEventIdPatch,
  editApplicationStatusApplicationsApplicationIdStatusPatch,
  getApplicationDetailApplicationsIdGet,
  getApplicationEventsApplicationsIdEventsGet,
  type ApiErrorResponse,
  type ApplicationEventTimelineRecord,
  type ApplicationEventType as ApplicationEventTypeValue,
  type ApplicationRecord,
  type ApplicationStatus,
} from "../../api";
import { Alert, Button, FormField, TextInput } from "../../components/ui";
import type { RedesignPage, StatusChipKey } from "../RedesignApp";
import { EVENT_LABELS, formatShortDate, logoStyle } from "../theme";

interface DetailPageProps {
  applicationId: string;
  go: (page: RedesignPage, extra?: { statusFilter?: StatusChipKey }) => void;
  onChanged: () => void;
}

const STATUS_OPTIONS: { value: ApplicationStatus; label: string }[] = [
  { value: "applied", label: "Applied" },
  { value: "in_review", label: "In review" },
  { value: "assessment", label: "Assessment" },
  { value: "interview", label: "Interview" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
  { value: "ghosted", label: "No response" },
  { value: "withdrawn", label: "Withdrawn" },
];

const EVENT_TYPE_OPTIONS = Object.values(ApplicationEventType) as ApplicationEventTypeValue[];

interface EventEditState {
  eventAt: string;
  eventType: ApplicationEventTypeValue;
  extractNote: string;
  reason: string;
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

function eventEditState(event: ApplicationEventTimelineRecord): EventEditState {
  return {
    eventAt: event.event_at,
    eventType: event.event_type,
    extractNote: event.extract_note ?? "",
    reason: "",
  };
}

function sortEventsNewestFirst(events: ApplicationEventTimelineRecord[]) {
  return events
    .map((event, index) => ({ event, epochMs: Date.parse(event.event_at), index }))
    .sort(
      (left, right) =>
        right.epochMs - left.epochMs || left.index - right.index,
    )
    .map(({ event }) => event);
}

export function DetailPage({ applicationId, go, onChanged }: DetailPageProps) {
  const [application, setApplication] = useState<ApplicationRecord | null>(null);
  const [events, setEvents] = useState<ApplicationEventTimelineRecord[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingEventId, setEditingEventId] = useState<string | null>(null);
  const [eventEdit, setEventEdit] = useState<EventEditState | null>(null);
  const savingRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const [detailResponse, eventsResponse] = await Promise.all([
        getApplicationDetailApplicationsIdGet(applicationId).catch(() => null),
        getApplicationEventsApplicationsIdEventsGet(applicationId).catch(() => null),
      ]);
      if (cancelled) {
        return;
      }
      if (detailResponse?.status === 200) {
        setApplication(detailResponse.data);
      } else {
        setNotFound(true);
      }
      if (eventsResponse?.status === 200) {
        setEvents(sortEventsNewestFirst(eventsResponse.data));
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [applicationId]);

  const onStatusEdit = async (nextStatus: ApplicationStatus) => {
    if (!application || savingRef.current || nextStatus === application.current_status) {
      return;
    }
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      const response = await editApplicationStatusApplicationsApplicationIdStatusPatch(
        application.id,
        { current_status: nextStatus, reason: null },
      );
      if (response.status === 200) {
        setApplication(response.data.application);
        onChanged();
      } else {
        setError(publicError(response.data, "Status correction failed."));
      }
    } catch {
      setError("Status correction failed. Check that the local backend is running.");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const beginEventEdit = (event: ApplicationEventTimelineRecord) => {
    if (savingRef.current) {
      return;
    }
    setError(null);
    setEditingEventId(event.id);
    setEventEdit(eventEditState(event));
  };

  const saveEventEdit = async (submitEvent: FormEvent<HTMLFormElement>) => {
    submitEvent.preventDefault();
    const original = events.find((event) => event.id === editingEventId);
    if (!application || !original || !eventEdit || savingRef.current) {
      return;
    }
    const changed =
      eventEdit.eventAt.trim() !== original.event_at ||
      eventEdit.eventType !== original.event_type ||
      eventEdit.extractNote.trim() !== (original.extract_note ?? "");
    if (!changed || !eventEdit.reason.trim()) {
      return;
    }

    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      const response = await editApplicationEventApplicationsApplicationIdEventsEventIdPatch(
        application.id,
        original.id,
        {
          email_id: original.email_id,
          event_at: eventEdit.eventAt.trim(),
          event_type: eventEdit.eventType,
          extract_note: eventEdit.extractNote.trim() || null,
          reason: eventEdit.reason.trim(),
        },
      );
      if (response.status !== 200) {
        setError(publicError(response.data, "Event correction failed."));
        return;
      }
      setApplication(response.data.application);
      setEvents((current) =>
        sortEventsNewestFirst(
          current.map((event) =>
            event.id === original.id ? { ...event, ...response.data.event } : event,
          ),
        ),
      );
      setEditingEventId(null);
      setEventEdit(null);
      onChanged();
    } catch {
      setError("Event correction failed. Check that the local backend is running.");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  if (notFound) {
    return (
      <section
        style={{
          maxWidth: "860px",
          margin: "0 auto",
          padding: "24px 32px 60px",
          display: "flex",
          flexDirection: "column",
          gap: "18px",
        }}
      >
        <button
          onClick={() => go("applications")}
          style={{
            alignSelf: "flex-start",
            border: "none",
            background: "none",
            color: "#666D66",
            fontSize: "12.5px",
            fontWeight: 600,
            cursor: "pointer",
            padding: 0,
          }}
          type="button"
        >
          ← All applications
        </button>
        <div
          style={{
            padding: "22px 24px",
            border: "1px solid #E4E2DA",
            borderRadius: "16px",
            background: "#fff",
          }}
        >
          <h1 style={{ margin: 0, fontSize: "20px", fontWeight: 700 }}>
            Application unavailable
          </h1>
          <p style={{ margin: "6px 0 0", color: "#666D66", fontSize: "13.5px" }}>
            This application link is malformed or no longer exists.
          </p>
        </div>
      </section>
    );
  }

  if (!application) {
    return (
      <section style={{ maxWidth: "860px", margin: "0 auto", padding: "24px 32px 60px" }} />
    );
  }

  const sourceEmailCount = events.filter((event) => event.email_id).length;
  const sourceEvidenceCopy =
    sourceEmailCount > 0
      ? `This record was assembled by AI from ${sourceEmailCount} source ${sourceEmailCount === 1 ? "email" : "emails"} in your inbox. Source subjects are shown as metadata so you can identify the evidence used.`
      : `This record has ${events.length} timeline ${events.length === 1 ? "event" : "events"}. No source emails are attached to this timeline. Inferred events are timeline evidence, not inbox emails.`;

  return (
    <section
      style={{
        maxWidth: "860px",
        margin: "0 auto",
        padding: "24px 32px 60px",
        display: "flex",
        flexDirection: "column",
        gap: "18px",
      }}
    >
      <button
        onClick={() => go("applications")}
        style={{
          alignSelf: "flex-start",
          border: "none",
          background: "none",
          color: "#666D66",
          fontSize: "12.5px",
          fontWeight: 600,
          cursor: "pointer",
          padding: 0,
        }}
        type="button"
      >
        ← All applications
      </button>

      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "16px",
          padding: "22px 24px",
          border: "1px solid #E4E2DA",
          borderRadius: "16px",
          background: "#fff",
          boxShadow: "0 1px 2px rgba(20,25,20,0.04)",
        }}
      >
        <div style={{ display: "flex", gap: "14px", alignItems: "center" }}>
          <span
            style={{
              ...logoStyle(application.company),
              width: "44px",
              height: "44px",
              fontSize: "18px",
              borderRadius: "12px",
            }}
          >
            {application.company[0]}
          </span>
          <div>
            <h1 style={{ margin: 0, fontSize: "20px", fontWeight: 700, letterSpacing: "-0.02em" }}>
              {application.company}
            </h1>
            <div style={{ fontSize: "13.5px", color: "#666D66" }}>
              {application.role_title} · applied {formatShortDate(application.first_seen_at)}
            </div>
          </div>
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            gap: "6px",
          }}
        >
          <select
            aria-label="Application status"
            disabled={saving}
            onChange={(event) => void onStatusEdit(event.target.value as ApplicationStatus)}
            style={{
              padding: "8px 12px",
              border: "1px solid #E4E2DA",
              borderRadius: "10px",
              background: "#FAFAF7",
              fontSize: "13px",
              fontWeight: 600,
              color: "#1B201C",
              cursor: "pointer",
            }}
            value={application.current_status}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <span style={{ fontSize: "11px", color: "#9A9F96" }}>
            {application.manual_lock
              ? "Edited by you - protected from auto-updates"
              : "Kept in sync from your email"}
          </span>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          padding: "12px 16px",
          border: "1px solid #D9D2EE",
          borderRadius: "12px",
          background: "#F4F2FB",
          fontSize: "12.5px",
          color: "#4B3FA6",
        }}
      >
        <span
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: "#6C5FC7",
            flex: "none",
          }}
        />
        <span style={{ flex: 1 }}>{sourceEvidenceCopy}</span>
      </div>

      {error ? (
        <Alert
          tone="danger"
          style={{
            display: "block",
            padding: "11px 14px",
            border: "1px solid #E8C8C2",
            borderRadius: "10px",
            background: "#FFF4F2",
            color: "#8A3328",
            fontSize: "12.5px",
          }}
        >
          {error}
        </Alert>
      ) : null}

      <div
        style={{
          padding: "22px 24px",
          border: "1px solid #E4E2DA",
          borderRadius: "16px",
          background: "#fff",
        }}
      >
        <h2 style={{ margin: "0 0 4px", fontSize: "15px", fontWeight: 700 }}>
          What happened, step by step
        </h2>
        <p style={{ margin: "0 0 16px", fontSize: "12.5px", color: "#9A9F96" }}>
          Newest first. Something look wrong? Use Fix a mistake to make an audited correction that
          is protected after re-syncs.
        </p>
        <div style={{ display: "flex", flexDirection: "column" }}>
          {events.map((event, index) => (
            <div
              key={event.id}
              style={{ display: "grid", gridTemplateColumns: "20px 1fr", gap: "14px" }}
            >
              <span style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <span
                  style={{
                    width: "11px",
                    height: "11px",
                    borderRadius: "50%",
                    marginTop: "4px",
                    flex: "none",
                    background: index === 0 ? "#1E5136" : "#C7D3C9",
                    border: index === 0 ? "2px solid #1E5136" : "2px solid #C7D3C9",
                  }}
                />
                {index === events.length - 1 ? null : (
                  <span style={{ flex: 1, width: "2px", background: "#E8EDE8" }} />
                )}
              </span>
              <div style={{ paddingBottom: "20px" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: "10px",
                    flexWrap: "wrap",
                  }}
                >
                  <span style={{ fontWeight: 700, fontSize: "13.5px" }}>
                    {EVENT_LABELS[event.event_type]}
                  </span>
                  <span
                    style={{
                      fontSize: "12px",
                      color: "#9A9F96",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {formatShortDate(event.event_at)}
                  </span>
                </div>
                {event.extract_note ? (
                  <div
                    style={{
                      marginTop: "6px",
                      fontSize: "13px",
                      color: "#4A5049",
                      background: "#F7F6F2",
                      borderRadius: "8px",
                      padding: "8px 12px",
                    }}
                  >
                    “{event.extract_note}”
                  </div>
                ) : null}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    marginTop: "8px",
                    flexWrap: "wrap",
                  }}
                >
                  {event.email_subject ? (
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "6px",
                        fontSize: "11.5px",
                        color: "#666D66",
                        border: "1px solid #E4E2DA",
                        borderRadius: "999px",
                        padding: "3px 10px",
                        background: "#FAFAF7",
                      }}
                    >
                      ✉ {event.email_subject}
                    </span>
                  ) : null}
                  {event.classification_confidence !== null &&
                  event.classification_confidence !== undefined ? (
                    <span
                      style={{
                        fontSize: "11px",
                        color: "#8B84B8",
                        fontFamily: "'JetBrains Mono',monospace",
                      }}
                    >
                      AI-detected · {Math.round(event.classification_confidence * 100)}% sure
                    </span>
                  ) : null}
                  <Button
                    disabled={saving}
                    onClick={() => beginEventEdit(event)}
                    style={{
                      display: "inline-flex",
                      minHeight: 0,
                      minWidth: 0,
                      border: "none",
                      background: "none",
                      color: "#1E5136",
                      fontSize: "11.5px",
                      fontWeight: 600,
                      cursor: saving ? "wait" : "pointer",
                      lineHeight: "normal",
                      padding: 0,
                      transform: "none",
                      transition: "none",
                    }}
                    variant="ghost"
                  >
                    Fix a mistake
                  </Button>
                </div>
                {editingEventId === event.id && eventEdit ? (
                  <form
                    onSubmit={(submitEvent) => void saveEventEdit(submitEvent)}
                    className="rd-event-edit-form"
                    style={{
                      marginTop: "12px",
                      padding: "14px",
                      border: "1px solid #D9D2EE",
                      borderRadius: "10px",
                      background: "#F8F7FC",
                      display: "grid",
                      gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                      gap: "10px",
                    }}
                  >
                    <FormField htmlFor={`${event.id}-type`} label="Event type">
                      <select
                        disabled={saving}
                        onChange={(changeEvent) =>
                          setEventEdit({
                            ...eventEdit,
                            eventType: changeEvent.target.value as ApplicationEventTypeValue,
                          })
                        }
                        style={{ padding: "7px 9px", border: "1px solid #D9D6CC", borderRadius: "8px" }}
                        value={eventEdit.eventType}
                      >
                        {EVENT_TYPE_OPTIONS.map((eventType) => (
                          <option key={eventType} value={eventType}>
                            {EVENT_LABELS[eventType]}
                          </option>
                        ))}
                      </select>
                    </FormField>
                    <FormField htmlFor={`${event.id}-time`} label="Event time">
                      <TextInput
                        disabled={saving}
                        onChange={(changeEvent) =>
                          setEventEdit({ ...eventEdit, eventAt: changeEvent.target.value })
                        }
                        style={{
                          width: "auto",
                          minHeight: 0,
                          padding: "7px 9px",
                          border: "1px solid #D9D6CC",
                          borderRadius: "8px",
                          background: "#fff",
                        }}
                        value={eventEdit.eventAt}
                      />
                    </FormField>
                    <FormField htmlFor={`${event.id}-note`} label="Event note">
                      <TextInput
                        disabled={saving}
                        onChange={(changeEvent) =>
                          setEventEdit({ ...eventEdit, extractNote: changeEvent.target.value })
                        }
                        style={{
                          width: "auto",
                          minHeight: 0,
                          padding: "7px 9px",
                          border: "1px solid #D9D6CC",
                          borderRadius: "8px",
                          background: "#fff",
                        }}
                        value={eventEdit.extractNote}
                      />
                    </FormField>
                    <FormField htmlFor={`${event.id}-reason`} label="Correction reason">
                      <TextInput
                        disabled={saving}
                        onChange={(changeEvent) =>
                          setEventEdit({ ...eventEdit, reason: changeEvent.target.value })
                        }
                        required
                        style={{
                          width: "auto",
                          minHeight: 0,
                          padding: "7px 9px",
                          border: "1px solid #D9D6CC",
                          borderRadius: "8px",
                          background: "#fff",
                        }}
                        value={eventEdit.reason}
                      />
                    </FormField>
                    <div style={{ gridColumn: "1 / -1", display: "flex", gap: "8px" }}>
                      <Button
                        disabled={
                          saving ||
                          !eventEdit.reason.trim() ||
                          (eventEdit.eventAt.trim() === event.event_at &&
                            eventEdit.eventType === event.event_type &&
                            eventEdit.extractNote.trim() === (event.extract_note ?? ""))
                        }
                        style={{
                          minHeight: 0,
                          minWidth: 0,
                          border: "none",
                          borderRadius: "999px",
                          background: "#1E5136",
                          color: "#fff",
                          padding: "7px 13px",
                          fontSize: "11.5px",
                          fontWeight: 700,
                          lineHeight: "normal",
                          transform: "none",
                          transition: "none",
                        }}
                        type="submit"
                      >
                        {saving ? "Saving..." : "Save correction"}
                      </Button>
                      <Button
                        disabled={saving}
                        onClick={() => {
                          setEditingEventId(null);
                          setEventEdit(null);
                        }}
                        style={{
                          minHeight: 0,
                          minWidth: 0,
                          border: "none",
                          background: "none",
                          color: "#666D66",
                          fontSize: "11.5px",
                          fontWeight: 400,
                          lineHeight: "normal",
                          padding: 0,
                          transform: "none",
                          transition: "none",
                        }}
                        variant="ghost"
                      >
                        Cancel
                      </Button>
                    </div>
                  </form>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
