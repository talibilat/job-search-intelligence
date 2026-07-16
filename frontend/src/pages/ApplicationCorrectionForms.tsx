import {
  ApplicationEventType,
  ApplicationStatus,
  type ApplicationEventRecord,
  type ApplicationEventType as ApplicationEventTypeValue,
  type ApplicationRecord,
  type ApplicationStatus as ApplicationStatusValue,
} from "../api";
import { Button, DataTable, FormField, InfoDisclosure, TextInput } from "../components/ui";

export interface EventEditFormState {
  emailId: string;
  eventAt: string;
  eventType: ApplicationEventTypeValue;
  extractNote: string;
  reason: string;
}

interface ApplicationSummaryProps {
  application: ApplicationRecord;
}

interface StatusCorrectionFormProps {
  hasStatusChange: boolean;
  isSubmitting: boolean;
  onReasonChange: (value: string) => void;
  onStatusChange: (value: ApplicationStatusValue) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  reason: string;
  statusValue: ApplicationStatusValue;
}

interface MergeCorrectionFormProps {
  hasSafeSourceId: boolean;
  isSubmitting: boolean;
  onReasonChange: (value: string) => void;
  onSourceIdChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  reason: string;
  sourceId: string;
  targetId: string;
}

interface ResetLockFormProps {
  isSubmitting: boolean;
  manualLock: boolean;
  onReasonChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  reason: string;
}

interface TimelineTableProps {
  events: ApplicationEventRecord[];
}

interface ApplicationSurfaceInfo {
  dataSource: string;
  dataTable: string;
  howItWorks: string;
  missingData: string;
}

interface EventCorrectionFormProps {
  eventForm: EventEditFormState;
  ghostInferenceHasSourceEmail: boolean;
  hasEventFieldChanges: boolean;
  hasEventTime: boolean;
  hasEventTimeZone: boolean;
  hasSafeSelectedEventId: boolean;
  hasValidEventTime: boolean;
  hasValidSourceEmailForEventType: boolean;
  events: ApplicationEventRecord[];
  isSubmitting: boolean;
  onEventFormChange: (form: EventEditFormState) => void;
  onSelectEvent: (eventId: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  selectedEventId: string;
}

interface SplitCorrectionFormProps {
  company: string;
  events: ApplicationEventRecord[];
  hasSafeSelectedEventIds: boolean;
  isSubmitting: boolean;
  onCompanyChange: (value: string) => void;
  onReasonChange: (value: string) => void;
  onRoleChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onToggleEvent: (eventId: string, checked: boolean) => void;
  reason: string;
  role: string;
  selectedEventIds: string[];
}

const statusOptions = Object.values(ApplicationStatus) as ApplicationStatusValue[];
const eventTypeOptions = Object.values(ApplicationEventType) as ApplicationEventTypeValue[];

function toTitle(value: string) {
  const label = value.replaceAll("_", " ");

  return label.charAt(0).toUpperCase() + label.slice(1);
}

export function ApplicationSummary({ application }: ApplicationSummaryProps) {
  return (
    <div className="application-detail-summary" aria-label="Application summary">
      <span>Status: {toTitle(application.current_status)}</span>
      <span>{application.manual_lock ? "Manual lock enabled" : "Automatic updates allowed"}</span>
      <span>{toTitle(application.source)}</span>
    </div>
  );
}

function ApplicationSurfaceInfoButton({
  info,
  label,
}: {
  info: ApplicationSurfaceInfo;
  label: string;
}) {
  return (
    <InfoDisclosure
      ariaLabel={`About ${label}`}
      buttonClassName="pipeline-panel__stage-info-button"
      className="pipeline-panel__stage-info"
      panelClassName="pipeline-panel__stage-info-panel"
      useButtonPrimitive
    >
      <p>{info.howItWorks}</p>
      <dl>
        <div>
          <dt>Data source</dt>
          <dd>{info.dataSource}</dd>
        </div>
        <div>
          <dt>Table</dt>
          <dd>{info.dataTable}</dd>
        </div>
        <div>
          <dt>If values are zero or missing</dt>
          <dd>{info.missingData}</dd>
        </div>
      </dl>
    </InfoDisclosure>
  );
}

export function StatusCorrectionForm({
  hasStatusChange,
  isSubmitting,
  onReasonChange,
  onStatusChange,
  onSubmit,
  reason,
  statusValue,
}: StatusCorrectionFormProps) {
  return (
    <article className="application-detail-card">
      <div className="pipeline-panel__stage-heading">
        <div>
          <p className="eyebrow">Status</p>
          <h2>Edit current status</h2>
        </div>
        <ApplicationSurfaceInfoButton
          info={{
            dataSource: "PATCH /applications/{application_id}/status",
            dataTable: "applications, application_corrections",
            howItWorks:
              "Updates the current status on the local application row, locks it from automatic overwrite, and writes an audited status_edit correction in SQLite.",
            missingData:
              "If the status looks wrong, inspect the event timeline first. Use this correction only when aggregation missed or misread local evidence, then add a reason so the audit trail explains the change.",
          }}
          label="Status correction"
        />
      </div>
      <form className="application-detail-form" onSubmit={onSubmit}>
        <FormField htmlFor="status-value" label="Correct status">
          <select
            className="ui-input"
            id="status-value"
            onChange={(event) => onStatusChange(event.target.value as ApplicationStatusValue)}
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
            onChange={(event) => onReasonChange(event.target.value)}
            value={reason}
          />
        </FormField>
        {!hasStatusChange ? (
          <p>Choose a different status before saving a status correction.</p>
        ) : null}
        <Button disabled={isSubmitting || !hasStatusChange} type="submit">
          Save status correction
        </Button>
      </form>
    </article>
  );
}

export function MergeCorrectionForm({
  hasSafeSourceId,
  isSubmitting,
  onReasonChange,
  onSourceIdChange,
  onSubmit,
  reason,
  sourceId,
  targetId,
}: MergeCorrectionFormProps) {
  const trimmedSourceId = sourceId.trim();
  const sourceIsTarget = trimmedSourceId.length > 0 && trimmedSourceId === targetId;

  return (
    <article className="application-detail-card">
      <div className="pipeline-panel__stage-heading">
        <div>
          <p className="eyebrow">Merge</p>
          <h2>Merge duplicate application</h2>
        </div>
        <ApplicationSurfaceInfoButton
          info={{
            dataSource: "POST /applications/{application_id}/merge",
            dataTable: "applications, application_events, application_corrections",
            howItWorks:
              "Moves events from a duplicate source application into this target application, recalculates the target summary, deletes the duplicate row, and writes an audited merge correction in SQLite.",
            missingData:
              "If the source application ID is missing, open the Applications feature list first and confirm sync, classification, and aggregation created both duplicate rows before merging. Add a reason so the audit trail explains why the rows belonged together.",
          }}
          label="Merge correction"
        />
      </div>
      <form className="application-detail-form" onSubmit={onSubmit}>
        <FormField htmlFor="merge-source-id" label="Source application ID">
          <TextInput
            id="merge-source-id"
            onChange={(event) => onSourceIdChange(event.target.value)}
            required
            value={sourceId}
          />
        </FormField>
        <FormField htmlFor="merge-reason" label="Merge reason">
          <TextInput
            id="merge-reason"
            onChange={(event) => onReasonChange(event.target.value)}
            value={reason}
          />
        </FormField>
        {sourceIsTarget ? (
          <p>Choose a different source application. An application cannot be merged into itself.</p>
        ) : null}
        {trimmedSourceId.length === 0 ? (
          <p>Enter the duplicate source application ID before merging.</p>
        ) : null}
        {trimmedSourceId.length > 0 && !hasSafeSourceId ? (
          <p>This source application ID is malformed or unsupported.</p>
        ) : null}
        <Button disabled={isSubmitting || trimmedSourceId.length === 0 || sourceIsTarget || !hasSafeSourceId} type="submit">
          Merge source application
        </Button>
      </form>
    </article>
  );
}

export function ResetLockForm({
  isSubmitting,
  manualLock,
  onReasonChange,
  onSubmit,
  reason,
}: ResetLockFormProps) {
  return (
    <article className="application-detail-card">
      <div className="pipeline-panel__stage-heading">
        <div>
          <p className="eyebrow">Reset</p>
          <h2>Reset manual lock</h2>
        </div>
        <ApplicationSurfaceInfoButton
          info={{
            dataSource: "POST /applications/{application_id}/reset-lock",
            dataTable: "applications, application_corrections",
            howItWorks:
              "Manual status, event, merge, or split corrections create the lock and audit records locally. This allows future aggregation reruns to update a manually locked application again and writes an audited reset_lock correction in SQLite.",
            missingData:
              "If the manual lock is not enabled, this action is usually unnecessary. Use it only after reviewing previous corrections and add a reason so the audit trail explains why automatic aggregation can resume.",
          }}
          label="Manual lock reset"
        />
      </div>
      {!manualLock ? (
        <p>
          Manual lock reset is only available after a manual correction has locked this application.
        </p>
      ) : null}
      <form className="application-detail-form" onSubmit={onSubmit}>
        <FormField htmlFor="reset-reason" label="Reset reason">
          <TextInput
            disabled={!manualLock}
            id="reset-reason"
            onChange={(event) => onReasonChange(event.target.value)}
            value={reason}
          />
        </FormField>
        <Button disabled={isSubmitting || !manualLock} type="submit" variant="secondary">
          Reset manual lock
        </Button>
      </form>
    </article>
  );
}

export function TimelineTable({ events }: TimelineTableProps) {
  return (
    <article className="application-detail-card application-detail-card--wide">
      <div className="pipeline-panel__stage-heading">
        <div>
          <p className="eyebrow">Timeline</p>
          <h2>Event timeline</h2>
        </div>
        <ApplicationSurfaceInfoButton
          info={{
            dataSource: "GET /applications/{id}/events",
            dataTable: "application_events",
            howItWorks:
              "Shows the ordered timeline events for this reconstructed application. Classification extracts candidate facts, aggregation groups them into an application, and this view reads the audited local timeline from SQLite.",
            missingData:
              "Run Gmail sync, classification, and aggregation from Feature Status. If the timeline is empty, confirm classification produced job-related evidence and aggregation created application events for this application.",
          }}
          label="Event timeline"
        />
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
  );
}

export function EventCorrectionForm({
  eventForm,
  ghostInferenceHasSourceEmail,
  hasEventFieldChanges,
  hasEventTime,
  hasEventTimeZone,
  hasSafeSelectedEventId,
  hasValidEventTime,
  hasValidSourceEmailForEventType,
  events,
  isSubmitting,
  onEventFormChange,
  onSelectEvent,
  onSubmit,
  selectedEventId,
}: EventCorrectionFormProps) {
  return (
    <article className="application-detail-card">
      <div className="pipeline-panel__stage-heading">
        <div>
          <p className="eyebrow">Event edit</p>
          <h2>Edit timeline event</h2>
        </div>
        <ApplicationSurfaceInfoButton
          info={{
            dataSource: "PATCH /applications/{application_id}/events/{event_id}",
            dataTable: "application_events, application_corrections",
            howItWorks:
              "Updates one local timeline event, recalculates the application status from the edited timeline, protects that source evidence from automatic overwrite, and writes an audited event_edit correction in SQLite.",
            missingData:
              "Run Gmail sync, classification, and aggregation from Feature Status to create timeline events. If event details look wrong, compare them with the source email and the event timeline first. Use this correction only when aggregation misread the local evidence, then add a reason so future reruns can surface conflicts instead of silently overwriting the edit.",
          }}
          label="Event correction"
        />
      </div>
      {events.length === 0 ? (
        <div>
          <p>No timeline events are available to edit.</p>
          <p>
            Run Gmail sync, classification, and aggregation from Feature Status, then confirm the event timeline
            has local evidence before editing.
          </p>
        </div>
      ) : null}
      {selectedEventId && !hasEventFieldChanges ? (
        <p>Change at least one event field before saving an event correction.</p>
      ) : null}
      {selectedEventId && !hasEventTime ? (
        <p>Enter an event time before saving an event correction.</p>
      ) : null}
      {selectedEventId && hasEventTime && !hasEventTimeZone ? (
        <p>Enter an ISO datetime with a timezone before saving an event correction.</p>
      ) : null}
      {selectedEventId && hasEventTime && hasEventTimeZone && !hasValidEventTime ? (
        <p>Enter an ISO datetime before saving an event correction.</p>
      ) : null}
      {selectedEventId && ghostInferenceHasSourceEmail ? (
        <p>Clear the source email before saving a ghost-inferred event.</p>
      ) : null}
      {selectedEventId && !ghostInferenceHasSourceEmail && !hasValidSourceEmailForEventType ? (
        <p>Keep a source email unless the event is a ghost inference with no source message.</p>
      ) : null}
      {selectedEventId && !hasSafeSelectedEventId ? (
        <p>This timeline event ID is malformed or unsupported.</p>
      ) : null}
      <form className="application-detail-form" onSubmit={onSubmit}>
        <FormField htmlFor="event-id" label="Event to edit">
          <select
            className="ui-input"
            disabled={events.length === 0}
            id="event-id"
            onChange={(event) => onSelectEvent(event.target.value)}
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
              onEventFormChange({
                ...eventForm,
                eventType: event.target.value as ApplicationEventTypeValue,
              })
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
            onChange={(event) => onEventFormChange({ ...eventForm, eventAt: event.target.value })}
            value={eventForm.eventAt}
          />
        </FormField>
        <FormField htmlFor="event-email" label="Source email">
          <TextInput
            disabled={!selectedEventId}
            id="event-email"
            onChange={(event) => onEventFormChange({ ...eventForm, emailId: event.target.value })}
            value={eventForm.emailId}
          />
        </FormField>
        <FormField htmlFor="event-note" label="Event note">
          <TextInput
            disabled={!selectedEventId}
            id="event-note"
            onChange={(event) => onEventFormChange({ ...eventForm, extractNote: event.target.value })}
            value={eventForm.extractNote}
          />
        </FormField>
        <FormField htmlFor="event-reason" label="Event correction reason">
          <TextInput
            disabled={!selectedEventId}
            id="event-reason"
            onChange={(event) => onEventFormChange({ ...eventForm, reason: event.target.value })}
            value={eventForm.reason}
          />
        </FormField>
        <Button
          disabled={
            isSubmitting ||
            !selectedEventId ||
            !hasEventFieldChanges ||
            !hasEventTime ||
            !hasEventTimeZone ||
            !hasValidEventTime ||
            !hasSafeSelectedEventId ||
            !hasValidSourceEmailForEventType
          }
          type="submit"
        >
          Save event correction
        </Button>
      </form>
    </article>
  );
}

export function SplitCorrectionForm({
  company,
  events,
  hasSafeSelectedEventIds,
  isSubmitting,
  onCompanyChange,
  onReasonChange,
  onRoleChange,
  onSubmit,
  onToggleEvent,
  reason,
  role,
  selectedEventIds,
}: SplitCorrectionFormProps) {
  const allSourceEventsSelected =
    events.length > 0 && selectedEventIds.length === events.length;

  return (
    <article className="application-detail-card">
      <div className="pipeline-panel__stage-heading">
        <div>
          <p className="eyebrow">Split</p>
          <h2>Split selected events</h2>
        </div>
        <ApplicationSurfaceInfoButton
          info={{
            dataSource: "POST /applications/{application_id}/split",
            dataTable: "applications, application_events, application_corrections",
            howItWorks:
              "The source application and selectable events come from local Gmail sync, classification, and deterministic aggregation. This moves selected timeline events into a new manually locked application, recalculates both application summaries, preserves source segmentation fields, and writes an audited split correction in SQLite.",
            missingData:
              "If no events are available to split, run Gmail sync, classification, and aggregation from Feature Status first. If the event belongs elsewhere, confirm the source timeline and enter the new application company and role before saving.",
          }}
          label="Split correction"
        />
      </div>
      <form className="application-detail-form" onSubmit={onSubmit}>
        <fieldset className="application-detail-fieldset">
          <legend>Events to move</legend>
          {events.length > 0 ? (
            events.map((event) => (
              <label className="application-detail-checkbox" key={event.id}>
                <input
                  checked={selectedEventIds.includes(event.id)}
                  onChange={(inputEvent) => onToggleEvent(event.id, inputEvent.target.checked)}
                  type="checkbox"
                />
                <span>{event.id}</span>
              </label>
            ))
          ) : (
            <p>No events are available to split.</p>
          )}
        </fieldset>
        {allSourceEventsSelected ? (
          <p>
            Leave at least one event on the source application. Move only the events that belong to the new application.
          </p>
        ) : null}
        {events.length > 0 && selectedEventIds.length === 0 ? (
          <p>Select at least one timeline event before splitting.</p>
        ) : null}
        {!hasSafeSelectedEventIds ? (
          <p>One or more selected event IDs are malformed or unsupported.</p>
        ) : null}
        {company.trim().length === 0 || role.trim().length === 0 ? (
          <p>Enter the new application company and role before splitting events.</p>
        ) : null}
        <FormField htmlFor="split-company" label="New application company">
          <TextInput
            id="split-company"
            onChange={(event) => onCompanyChange(event.target.value)}
            required
            value={company}
          />
        </FormField>
        <FormField htmlFor="split-role" label="New application role">
          <TextInput
            id="split-role"
            onChange={(event) => onRoleChange(event.target.value)}
            required
            value={role}
          />
        </FormField>
        <FormField htmlFor="split-reason" label="Split reason">
          <TextInput
            id="split-reason"
            onChange={(event) => onReasonChange(event.target.value)}
            value={reason}
          />
        </FormField>
        <Button
          disabled={
            isSubmitting ||
            selectedEventIds.length === 0 ||
            allSourceEventsSelected ||
            !hasSafeSelectedEventIds ||
            company.trim().length === 0 ||
            role.trim().length === 0
          }
          type="submit"
        >
          Split selected events
        </Button>
      </form>
    </article>
  );
}
