import { Alert, Button, DataTable, FormField, Tabs, TextInput } from "./primitives";

interface ApplicationSummary {
  company: string;
  applications: number;
  status: "applied" | "interview" | "rejected";
}

const summaries: ApplicationSummary[] = [
  { company: "Acme", applications: 2, status: "interview" },
];

export function UiPrimitiveContract() {
  return (
    <form aria-label="Application filters">
      <FormField
        htmlFor="company-filter"
        label="Company"
        hint="Filter by company name without changing source data."
      >
        <TextInput id="company-filter" name="company" placeholder="Acme" />
      </FormField>

      <Button type="submit">Apply filters</Button>

      <Alert title="Synced" tone="success">
        Dashboard numbers reconcile with local application data.
      </Alert>

      <Tabs
        label="Application views"
        items={[
          { id: "summary", label: "Summary", content: <p>Summary metrics</p> },
          { id: "events", label: "Events", content: <p>Application event timeline</p> },
        ]}
      />

      <DataTable
        caption="Applications by company"
        columns={[
          { key: "company", header: "Company" },
          { key: "applications", header: "Applications", align: "right" },
          { key: "status", header: "Current status" },
        ]}
        rows={summaries}
        rowKey={(row) => row.company}
      />
    </form>
  );
}
