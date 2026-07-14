import { useEffect, useRef, useState, type FormEvent } from "react";

import {
  ApplicationEventType,
  editApplicationEventApplicationsApplicationIdEventsEventIdPatch,
  editApplicationStatusApplicationsApplicationIdStatusPatch,
  getApplicationCorrectionConflictsApplicationsIdCorrectionConflictsGet,
  getApplicationCorrectionHistoryApplicationsIdCorrectionsGet,
  getApplicationDetailApplicationsIdGet,
  getApplicationEventsApplicationsIdEventsGet,
  mergeApplicationApplicationsApplicationIdMergePost,
  resetApplicationLockApplicationsApplicationIdResetLockPost,
  splitApplicationApplicationsApplicationIdSplitPost,
  type ApiErrorResponse,
  type ApplicationCorrectionConflictRecord,
  type ApplicationCorrectionRecord,
  type ApplicationEventTimelineRecord,
  type ApplicationEventType as ApplicationEventTypeValue,
  type ApplicationRecord,
  type ApplicationStatus,
} from "../../api";
import { Alert, Button, FormField, TextInput } from "../../components/ui";
import type { RedesignPage, StatusChipKey } from "../RedesignApp";
import { EVENT_LABELS, formatShortDate, logoStyle } from "../theme";
import { publicApiError } from "../apiError";

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

const compactInputStyle = {
  width: "100%",
  minHeight: "38px",
  padding: "8px 10px",
  border: "1px solid #D9D6CC",
  borderRadius: "8px",
  background: "#fff",
  boxSizing: "border-box" as const,
};

interface EventEditState {
  emailId: string;
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
    emailId: event.email_id ?? "",
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
  const [conflicts, setConflicts] = useState<ApplicationCorrectionConflictRecord[]>([]);
  const [corrections, setCorrections] = useState<ApplicationCorrectionRecord[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [correctionDataError, setCorrectionDataError] = useState<string | null>(null);
  const [loadKey, setLoadKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingEventId, setEditingEventId] = useState<string | null>(null);
  const [eventEdit, setEventEdit] = useState<EventEditState | null>(null);
  const [mergeSourceId, setMergeSourceId] = useState("");
  const [mergeReason, setMergeReason] = useState("");
  const [splitEventIds, setSplitEventIds] = useState<string[]>([]);
  const [splitCompany, setSplitCompany] = useState("");
  const [splitRole, setSplitRole] = useState("");
  const [splitReason, setSplitReason] = useState("");
  const [resetReason, setResetReason] = useState("");
  const savingRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setNotFound(false);
      setLoadError(null);
      setEventsError(null);
      setCorrectionDataError(null);
      const [detailResponse, eventsResponse, conflictsResponse, correctionsResponse] = await Promise.all([
        getApplicationDetailApplicationsIdGet(applicationId).catch((requestError: unknown) => ({ error: requestError })),
        getApplicationEventsApplicationsIdEventsGet(applicationId).catch((requestError: unknown) => ({ error: requestError })),
        getApplicationCorrectionConflictsApplicationsIdCorrectionConflictsGet(applicationId).catch((requestError: unknown) => ({ error: requestError })),
        getApplicationCorrectionHistoryApplicationsIdCorrectionsGet(applicationId).catch((requestError: unknown) => ({ error: requestError })),
      ]);
      if (cancelled) {
        return;
      }
      if ("status" in detailResponse && detailResponse.status === 200) {
        setApplication(detailResponse.data);
      } else if ("status" in detailResponse && detailResponse.status === 404) {
        setApplication(null);
        setNotFound(true);
      } else {
        setApplication(null);
        setLoadError(publicApiError("status" in detailResponse ? { response: detailResponse } : detailResponse.error, "Application could not be loaded."));
      }
      if ("status" in eventsResponse && eventsResponse.status === 200) {
        setEvents(sortEventsNewestFirst(eventsResponse.data));
      } else {
        setEvents([]);
        setEventsError(publicApiError("status" in eventsResponse ? { response: eventsResponse } : eventsResponse.error, "Timeline could not be loaded."));
      }
      setConflicts("status" in conflictsResponse && conflictsResponse.status === 200 ? conflictsResponse.data : []);
      setCorrections("status" in correctionsResponse && correctionsResponse.status === 200 ? correctionsResponse.data : []);
      if (!("status" in conflictsResponse && conflictsResponse.status === 200) || !("status" in correctionsResponse && correctionsResponse.status === 200)) {
        setCorrectionDataError("Correction conflicts or audit history could not be loaded. Retry before assuming this record has no unresolved evidence.");
      }
      setLoading(false);
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [applicationId, loadKey]);

  const refreshAfterCorrection = () => {
    setLoadKey((value) => value + 1);
    onChanged();
  };

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
        refreshAfterCorrection();
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
      eventEdit.emailId.trim() !== (original.email_id ?? "") ||
      eventEdit.eventAt.trim() !== original.event_at ||
      eventEdit.eventType !== original.event_type ||
      eventEdit.extractNote.trim() !== (original.extract_note ?? "");
    const sourceIsValid = eventEdit.eventType === "ghost_inferred"
      ? !eventEdit.emailId.trim()
      : Boolean(eventEdit.emailId.trim());
    if (!changed || !eventEdit.reason.trim() || !sourceIsValid) {
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
          email_id: eventEdit.emailId.trim() || null,
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
      setEditingEventId(null);
      setEventEdit(null);
      refreshAfterCorrection();
    } catch {
      setError("Event correction failed. Check that the local backend is running.");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const runRepair = async (operation: () => Promise<{ status: number; data: unknown }>) => {
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      const response = await operation();
      if (response.status !== 200) {
        setError(publicError(response.data, "Correction failed."));
        return;
      }
      setMergeSourceId("");
      setMergeReason("");
      setSplitEventIds([]);
      setSplitCompany("");
      setSplitRole("");
      setSplitReason("");
      setResetReason("");
      refreshAfterCorrection();
    } catch {
      setError("Correction failed. Check that the local backend is running.");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const submitMerge = (submitEvent: FormEvent<HTMLFormElement>) => {
    submitEvent.preventDefault();
    const sourceId = mergeSourceId.trim();
    if (!sourceId || sourceId === application?.id) return;
    void runRepair(() =>
      mergeApplicationApplicationsApplicationIdMergePost(applicationId, {
        source_application_id: sourceId,
        reason: mergeReason.trim() || null,
      }),
    );
  };

  const submitSplit = (submitEvent: FormEvent<HTMLFormElement>) => {
    submitEvent.preventDefault();
    if (!splitEventIds.length || splitEventIds.length === events.length || !splitCompany.trim() || !splitRole.trim()) return;
    void runRepair(() =>
      splitApplicationApplicationsApplicationIdSplitPost(applicationId, {
        event_ids: splitEventIds,
        new_application: { company: splitCompany.trim(), role_title: splitRole.trim() },
        reason: splitReason.trim() || null,
      }),
    );
  };

  const submitReset = (submitEvent: FormEvent<HTMLFormElement>) => {
    submitEvent.preventDefault();
    if (!application?.manual_lock) return;
    void runRepair(() =>
      resetApplicationLockApplicationsApplicationIdResetLockPost(applicationId, {
        reason: resetReason.trim() || null,
      }),
    );
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

  if (loadError) {
    return (
      <section style={{ maxWidth: "860px", margin: "0 auto", padding: "24px 32px 60px", display: "flex", flexDirection: "column", gap: "18px" }}>
        <Alert tone="danger">{loadError}</Alert>
        <Button onClick={() => setLoadKey((value) => value + 1)} variant="secondary">Retry</Button>
      </section>
    );
  }

  if (!application) {
    return (
      <section style={{ maxWidth: "860px", margin: "0 auto", padding: "24px 32px 60px" }}>
        {loading ? <p style={{ margin: 0, color: "#9A9F96", fontSize: "13px" }}>Loading application…</p> : null}
      </section>
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

      {eventsError ? (
        <Alert tone="danger">{eventsError}</Alert>
      ) : null}
      {correctionDataError ? <Alert tone="danger">{correctionDataError}</Alert> : null}

      {!eventsError ? <div
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
      </div> : null}

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
          padding: "18px 20px",
          border: application.manual_lock ? "1px solid #D9D2EE" : "1px solid #DDE5DE",
          borderRadius: "14px",
          background: application.manual_lock ? "#F8F7FC" : "#F6FAF7",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "18px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <strong style={{ display: "block", fontSize: "13.5px" }}>
            {application.manual_lock ? "Manual correction lock is on" : "Automatic updates are on"}
          </strong>
          <span style={{ display: "block", marginTop: "3px", color: "#666D66", fontSize: "12.5px", maxWidth: "590px" }}>
            {application.manual_lock
              ? "Your corrected grouping and status stay protected when new email evidence is processed. Conflicting evidence is recorded below instead of replacing your correction."
              : "Future aggregation runs may update this record from source-email evidence. A manual correction turns protection back on."}
          </span>
        </div>
        {application.manual_lock ? (
          <form onSubmit={submitReset} style={{ display: "flex", alignItems: "flex-end", gap: "8px", flexWrap: "wrap" }}>
            <FormField htmlFor="reset-lock-reason" label="Why resume automatic updates?">
              <TextInput
                id="reset-lock-reason"
                disabled={saving}
                onChange={(event) => setResetReason(event.target.value)}
                style={{ ...compactInputStyle, minWidth: "220px" }}
                value={resetReason}
              />
            </FormField>
            <Button disabled={saving} type="submit" variant="secondary">
              Reset lock
            </Button>
          </form>
        ) : null}
      </div>

      {conflicts.length > 0 ? (
        <div
          role="alert"
          style={{ padding: "18px 20px", border: "1px solid #E8C8C2", borderRadius: "14px", background: "#FFF7F5" }}
        >
          <h2 style={{ margin: 0, fontSize: "15px" }}>New evidence conflicts with your correction</h2>
          <p style={{ margin: "5px 0 14px", color: "#725049", fontSize: "12.5px" }}>
            Nothing was overwritten. Review the proposed source evidence, then edit the record or reset its lock if the new evidence should take precedence.
          </p>
          <div style={{ display: "grid", gap: "9px" }}>
            {conflicts.map((conflict) => (
              <details key={conflict.id} style={{ padding: "10px 12px", border: "1px solid #EEDBD7", borderRadius: "9px", background: "#fff" }}>
                <summary style={{ cursor: "pointer", fontSize: "12.5px", fontWeight: 700 }}>
                  {conflict.conflict_type.replaceAll("_", " ")}
                  {conflict.evidence_email_id ? ` from email ${conflict.evidence_email_id}` : " from inferred evidence"}
                </summary>
                <div style={{ marginTop: "9px", display: "grid", gap: "7px", fontSize: "12px", color: "#4A5049" }}>
                  <div><strong>Protected value:</strong> <code>{JSON.stringify(conflict.existing_json)}</code></div>
                  <div><strong>Proposed value:</strong> <code>{JSON.stringify(conflict.proposed_json)}</code></div>
                </div>
              </details>
            ))}
          </div>
        </div>
      ) : null}

      <div style={{ padding: "22px 24px", border: "1px solid #E4E2DA", borderRadius: "16px", background: "#fff" }}>
        <h2 style={{ margin: "0 0 4px", fontSize: "15px", fontWeight: 700 }}>Repair grouping mistakes</h2>
        <p style={{ margin: "0 0 16px", color: "#9A9F96", fontSize: "12.5px" }}>
          Merge a duplicate into this record, or move selected timeline events into a new application. Both actions are audited and protected from automatic overwrite.
        </p>
        <div className="rd-repair-grid" style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "18px" }}>
          <form onSubmit={submitMerge} style={{ padding: "14px", border: "1px solid #E8E5DC", borderRadius: "11px", display: "grid", gap: "10px" }}>
            <strong style={{ fontSize: "13px" }}>Merge duplicate</strong>
            <FormField htmlFor="merge-source-id" label="Duplicate application ID">
              <TextInput id="merge-source-id" disabled={saving} onChange={(event) => setMergeSourceId(event.target.value)} required style={compactInputStyle} value={mergeSourceId} />
            </FormField>
            <FormField htmlFor="merge-reason" label="Reason">
              <TextInput id="merge-reason" disabled={saving} onChange={(event) => setMergeReason(event.target.value)} style={compactInputStyle} value={mergeReason} />
            </FormField>
            {mergeSourceId.trim() === application.id ? <span style={{ color: "#8A3328", fontSize: "12px" }}>Choose a different application.</span> : null}
            <Button disabled={saving || !mergeSourceId.trim() || mergeSourceId.trim() === application.id} type="submit">Merge into this record</Button>
          </form>

          <form onSubmit={submitSplit} style={{ padding: "14px", border: "1px solid #E8E5DC", borderRadius: "11px", display: "grid", gap: "10px" }}>
            <strong style={{ fontSize: "13px" }}>Split timeline events</strong>
            <fieldset style={{ margin: 0, padding: "8px 10px", border: "1px solid #E4E2DA", borderRadius: "8px" }}>
              <legend style={{ padding: "0 4px", fontSize: "12px", color: "#666D66" }}>Events to move</legend>
              <div style={{ display: "grid", gap: "6px" }}>
                {events.map((event) => (
                  <label key={event.id} style={{ display: "flex", alignItems: "center", gap: "7px", fontSize: "12px" }}>
                    <input
                      checked={splitEventIds.includes(event.id)}
                      disabled={saving}
                      onChange={(inputEvent) => setSplitEventIds((current) => inputEvent.target.checked ? [...current, event.id] : current.filter((id) => id !== event.id))}
                      type="checkbox"
                    />
                    {EVENT_LABELS[event.event_type]} - {formatShortDate(event.event_at)}
                  </label>
                ))}
              </div>
            </fieldset>
            <FormField htmlFor="split-company" label="New company">
              <TextInput id="split-company" disabled={saving} onChange={(event) => setSplitCompany(event.target.value)} required style={compactInputStyle} value={splitCompany} />
            </FormField>
            <FormField htmlFor="split-role" label="New role">
              <TextInput id="split-role" disabled={saving} onChange={(event) => setSplitRole(event.target.value)} required style={compactInputStyle} value={splitRole} />
            </FormField>
            <FormField htmlFor="split-reason" label="Reason">
              <TextInput id="split-reason" disabled={saving} onChange={(event) => setSplitReason(event.target.value)} style={compactInputStyle} value={splitReason} />
            </FormField>
            {splitEventIds.length === events.length && events.length > 0 ? <span style={{ color: "#8A3328", fontSize: "12px" }}>Leave at least one event on this application.</span> : null}
            <Button disabled={saving || !splitEventIds.length || splitEventIds.length === events.length || !splitCompany.trim() || !splitRole.trim()} type="submit">Create split application</Button>
          </form>
        </div>
      </div>

      <div style={{ padding: "22px 24px", border: "1px solid #E4E2DA", borderRadius: "16px", background: "#fff" }}>
        <h2 style={{ margin: "0 0 4px", fontSize: "15px", fontWeight: 700 }}>Correction history</h2>
        <p style={{ margin: "0 0 14px", color: "#9A9F96", fontSize: "12.5px" }}>Newest first. Every manual change and lock reset remains reviewable.</p>
        {corrections.length === 0 ? <p style={{ margin: 0, fontSize: "12.5px", color: "#666D66" }}>No manual corrections yet.</p> : (
          <div style={{ display: "grid", gap: "8px" }}>
            {corrections.map((correction) => (
              <details key={correction.id} style={{ padding: "10px 12px", border: "1px solid #E8E5DC", borderRadius: "9px" }}>
                <summary style={{ cursor: "pointer", fontSize: "12.5px", fontWeight: 700 }}>
                  {correction.correction_type.replaceAll("_", " ")} - {formatShortDate(correction.created_at)}
                </summary>
                <div style={{ marginTop: "8px", display: "grid", gap: "6px", color: "#4A5049", fontSize: "12px" }}>
                  <div><strong>Reason:</strong> {correction.reason ?? "No reason recorded"}</div>
                  <div><strong>Before:</strong> <code>{JSON.stringify(correction.before_json)}</code></div>
                  <div><strong>After:</strong> <code>{JSON.stringify(correction.after_json)}</code></div>
                </div>
              </details>
            ))}
          </div>
        )}
      </div>

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
                    <FormField htmlFor={`${event.id}-email`} label="Source email ID">
                      <TextInput
                        disabled={saving}
                        onChange={(changeEvent) =>
                          setEventEdit({ ...eventEdit, emailId: changeEvent.target.value })
                        }
                        style={{
                          width: "auto",
                          minHeight: 0,
                          padding: "7px 9px",
                          border: "1px solid #D9D6CC",
                          borderRadius: "8px",
                          background: "#fff",
                        }}
                        value={eventEdit.emailId}
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
                          (eventEdit.eventType === "ghost_inferred" ? Boolean(eventEdit.emailId.trim()) : !eventEdit.emailId.trim()) ||
                          (eventEdit.emailId.trim() === (event.email_id ?? "") &&
                            eventEdit.eventAt.trim() === event.event_at &&
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
