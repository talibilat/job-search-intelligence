import { useState, type FormEvent } from "react";

import { Button, FormField, TextInput } from "../../components/ui";
import {
  EMPTY_DASHBOARD_FILTERS,
  dashboardFilterOptions,
  titleize,
  type DashboardFilters,
} from "../dashboardFilters";

interface DashboardFilterPanelProps {
  filters: DashboardFilters;
  onApply: (filters: DashboardFilters) => void;
}

export function DashboardFilterPanel({ filters, onApply }: DashboardFilterPanelProps) {
  const [draft, setDraft] = useState(filters);
  const invalidSalary = Boolean(
    draft.salaryMin && draft.salaryMax && Number(draft.salaryMin) > Number(draft.salaryMax),
  );
  const invalidDate = Boolean(
    draft.firstSeenFrom && draft.firstSeenTo && draft.firstSeenFrom > draft.firstSeenTo,
  );
  const update = (key: keyof DashboardFilters, value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!invalidSalary && !invalidDate) onApply(draft);
  };

  return (
    <details className="rd-filter-panel">
      <summary>Filter dashboard and applications</summary>
      <form onSubmit={submit}>
        <div className="rd-filter-grid">
          <FormField htmlFor="rd-filter-status" label="Status">
            <select className="ui-input" onChange={(event) => update("status", event.target.value)} value={draft.status}>
              <option value="">All statuses</option>
              {dashboardFilterOptions.status.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
            </select>
          </FormField>
          <FormField htmlFor="rd-filter-source" label="Source">
            <select className="ui-input" onChange={(event) => update("source", event.target.value)} value={draft.source}>
              <option value="">All sources</option>
              {dashboardFilterOptions.source.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
            </select>
          </FormField>
          <FormField htmlFor="rd-filter-sponsorship" label="Sponsorship">
            <select className="ui-input" onChange={(event) => update("sponsorship", event.target.value)} value={draft.sponsorship}>
              <option value="">All sponsorship</option>
              {dashboardFilterOptions.sponsorship.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
            </select>
          </FormField>
          <FormField htmlFor="rd-filter-work-mode" label="Work mode">
            <select className="ui-input" onChange={(event) => update("workMode", event.target.value)} value={draft.workMode}>
              <option value="">All work modes</option>
              {dashboardFilterOptions.workMode.map((value) => <option key={value} value={value}>{titleize(value)}</option>)}
            </select>
          </FormField>
          <FormField htmlFor="rd-filter-role" label="Role">
            <TextInput onChange={(event) => update("role", event.target.value)} placeholder="Platform engineer" value={draft.role} />
          </FormField>
          <FormField error={invalidDate ? "Start date must not be after end date." : undefined} htmlFor="rd-filter-from" label="From">
            <TextInput onChange={(event) => update("firstSeenFrom", event.target.value)} type="date" value={draft.firstSeenFrom} />
          </FormField>
          <FormField htmlFor="rd-filter-to" label="To">
            <TextInput onChange={(event) => update("firstSeenTo", event.target.value)} type="date" value={draft.firstSeenTo} />
          </FormField>
          <FormField error={invalidSalary ? "Minimum must not exceed maximum." : undefined} htmlFor="rd-filter-salary-min" label="Salary minimum">
            <TextInput inputMode="numeric" min="0" onChange={(event) => update("salaryMin", event.target.value)} type="number" value={draft.salaryMin} />
          </FormField>
          <FormField htmlFor="rd-filter-salary-max" label="Salary maximum">
            <TextInput inputMode="numeric" min="0" onChange={(event) => update("salaryMax", event.target.value)} type="number" value={draft.salaryMax} />
          </FormField>
        </div>
        <div className="rd-filter-actions">
          <Button disabled={invalidDate || invalidSalary} type="submit">Apply filters</Button>
          <Button onClick={() => { setDraft(EMPTY_DASHBOARD_FILTERS); onApply(EMPTY_DASHBOARD_FILTERS); }} type="button" variant="secondary">Clear</Button>
        </div>
      </form>
    </details>
  );
}
