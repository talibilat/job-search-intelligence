import {
  ApplicationEventType,
  ApplicationStatus,
  type ApplicationEventRecord,
  type ApplicationEventType as ApplicationEventTypeValue,
  type ApplicationRecord,
  type ApplicationStatus as ApplicationStatusValue,
} from "../api";
import { Button, DataTable, FormField, TextInput } from "../components/ui";

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
  isSubmitting: boolean;
  onReasonChange: (value: string) => void;
  onStatusChange: (value: ApplicationStatusValue) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  reason: string;
  statusValue: ApplicationStatusValue;
}

interface MergeCorrectionFormProps {
  isSubmitting: boolean;
  onReasonChange: (value: string) => void;
  onSourceIdChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  reason: string;
  sourceId: string;
}

interface TimelineTableProps {
  events: ApplicationEventRecord[];
}

interface EventCorrectionFormProps {
  eventForm: EventEditFormState;
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

export function toTitle(value: string) {
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

export function StatusCorrectionForm({
  isSubmitting,
  onReasonChange,
  onStatusChange,
  onSubmit,
  reason,
  statusValue,
}: StatusCorrectionFormProps) {
  return (
    <article className="application-detail-card">
      <div>
        <p className="eyebrow">Status</p>
        <h2>Edit current status</h2>
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
        <Button disabled={isSubmitting} type="submit">
          Save status correction
        </Button>
      </form>
    </article>
  );
}

export function MergeCorrectionForm({
  isSubmitting,
  onReasonChange,
  onSourceIdChange,
  onSubmit,
  reason,
  sourceId,
}: MergeCorrectionFormProps) {
  return (
    <article className="application-detail-card">
      <div>
        <p className="eyebrow">Merge</p>
        <h2>Merge duplicate application</h2>
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
        <Button disabled={isSubmitting || sourceId.trim().length === 0} type="submit">
          Merge source application
        </Button>
      </form>
    </article>
  );
}

export function TimelineTable({ events }: TimelineTableProps) {
  return (
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
  );
}

export function EventCorrectionForm({
  eventForm,
  events,
  isSubmitting,
  onEventFormChange,
  onSelectEvent,
  onSubmit,
  selectedEventId,
}: EventCorrectionFormProps) {
  return (
    <article className="application-detail-card">
      <div>
        <p className="eyebrow">Event edit</p>
        <h2>Edit timeline event</h2>
      </div>
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
        <Button disabled={isSubmitting || !selectedEventId} type="submit">
          Save event correction
        </Button>
      </form>
    </article>
  );
}

export function SplitCorrectionForm({
  company,
  events,
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
  return (
    <article className="application-detail-card">
      <div>
        <p className="eyebrow">Split</p>
        <h2>Split selected events</h2>
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
