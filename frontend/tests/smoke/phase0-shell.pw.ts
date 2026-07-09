import { expect, test } from "@playwright/test";

const baseApplication = {
  created_at: "2026-07-01T09:01:00Z",
  currency: "USD",
  first_seen_at: "2026-07-01T09:00:00Z",
  last_activity_at: "2026-07-01T09:00:00Z",
  location: "Remote",
  manual_lock: false,
  salary_max: 180000,
  salary_min: 140000,
  seniority: "senior",
  sponsorship: "unknown",
  tech_stack: ["Python", "TypeScript"],
  updated_at: "2026-07-01T09:01:00Z",
  work_mode: "remote",
};

const applications = [
  {
    ...baseApplication,
    company: "Example Analytics",
    current_status: "offer",
    id: "app-analytics",
    last_activity_at: "2026-07-04T09:00:00Z",
    role_title: "Senior Data Engineer",
    source: "linkedin",
  },
  {
    ...baseApplication,
    company: "Fixture Systems",
    current_status: "rejected",
    id: "app-fixture",
    last_activity_at: "2026-07-03T09:00:00Z",
    role_title: "Platform Engineer",
    source: "company_site",
  },
  {
    ...baseApplication,
    company: "Example Analytics",
    current_status: "applied",
    id: "app-applied",
    last_activity_at: "2026-07-02T09:00:00Z",
    role_title: "Backend Engineer",
    source: "linkedin",
  },
];

const applicationEvents = [
  {
    application_id: "app-analytics",
    event_at: "2026-07-01T09:00:00Z",
    event_type: "applied",
  },
  {
    application_id: "app-analytics",
    event_at: "2026-07-03T09:00:00Z",
    event_type: "interview_scheduled",
  },
  {
    application_id: "app-analytics",
    event_at: "2026-07-04T09:00:00Z",
    event_type: "offer",
  },
  {
    application_id: "app-fixture",
    event_at: "2026-07-01T09:00:00Z",
    event_type: "applied",
  },
  {
    application_id: "app-fixture",
    event_at: "2026-07-03T09:00:00Z",
    event_type: "rejection",
  },
  {
    application_id: "app-applied",
    event_at: "2026-07-02T09:00:00Z",
    event_type: "applied",
  },
];

const responseEventTypes = new Set([
  "assessment",
  "feedback",
  "interview_scheduled",
  "offer",
  "rejection",
  "response",
]);

function applicationsWithEvent(eventType: string) {
  return new Set(
    applicationEvents
      .filter((event) => event.event_type === eventType)
      .map((event) => event.application_id),
  );
}

function responseApplicationIds() {
  return new Set(
    applicationEvents
      .filter((event) => responseEventTypes.has(event.event_type))
      .map((event) => event.application_id),
  );
}

function metricRate(numerator: number, denominator: number) {
  return {
    denominator,
    numerator,
    rate: denominator === 0 ? null : numerator / denominator,
  };
}

function averageFirstResponseHours() {
  const firstResponseHours = applications.flatMap((application) => {
    const responses = applicationEvents
      .filter(
        (event) =>
          event.application_id === application.id &&
          responseEventTypes.has(event.event_type),
      )
      .sort((left, right) => left.event_at.localeCompare(right.event_at));
    const firstResponse = responses[0];
    if (!firstResponse) {
      return [];
    }

    return [
      (Date.parse(firstResponse.event_at) - Date.parse(application.first_seen_at)) /
        3_600_000,
    ];
  });

  if (firstResponseHours.length === 0) {
    return null;
  }

  return (
    firstResponseHours.reduce((total, hours) => total + hours, 0) /
    firstResponseHours.length
  );
}

function sourceBreakdownRows() {
  const responseIds = responseApplicationIds();
  const interviewIds = applicationsWithEvent("interview_scheduled");
  const offerIds = applicationsWithEvent("offer");
  const bySource = new Map<
    string,
    {
      application_count: number;
      dimension: "source";
      interview_count: number;
      offer_count: number;
      response_count: number;
      value: string;
    }
  >();

  for (const application of applications) {
    const row = bySource.get(application.source) ?? {
      application_count: 0,
      dimension: "source",
      interview_count: 0,
      offer_count: 0,
      response_count: 0,
      value: application.source,
    };
    row.application_count += 1;
    row.response_count += responseIds.has(application.id) ? 1 : 0;
    row.interview_count += interviewIds.has(application.id) ? 1 : 0;
    row.offer_count += offerIds.has(application.id) ? 1 : 0;
    bySource.set(application.source, row);
  }

  return [...bySource.values()].sort((left, right) =>
    left.value.localeCompare(right.value),
  );
}

test("renders setup, sync, and fixture-backed dashboard metrics", async ({
  page,
}) => {
  await page.route("**/setup/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        classification_mode: "hybrid",
        email_provider: "gmail",
        gmail_connected: false,
        llm_configured: true,
        llm_provider: "azure_openai",
        recommended_classification_mode: "hybrid",
        setup_complete: false,
      },
      status: 200,
    });
  });
  await page.route("**/sync/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        account_id: "talib@example.test",
        finished_at: "2026-07-05T09:45:30Z",
        last_error: null,
        message_count: 2500,
        mode: "full_backfill",
        page_count: 12,
        provider: "gmail",
        raw_email_count: 1240,
        recovered_from_expired_cursor: true,
        started_at: "2026-07-05T09:15:00Z",
        state: "succeeded",
      },
      status: 200,
    });
  });
  await page.route("**/sync", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        account_id: "talib@example.test",
        finished_at: null,
        last_error: null,
        message_count: 2600,
        mode: "incremental",
        page_count: 13,
        provider: "gmail",
        raw_email_count: 1305,
        recovered_from_expired_cursor: false,
        started_at: "2026-07-05T10:00:00Z",
        state: "running",
      },
      status: 200,
    });
  });
  await page.route("**/applications**", async (route) => {
    const requestUrl = new URL(route.request().url());
    const status = requestUrl.searchParams.get("status");
    const body = status
      ? applications.filter((application) => application.current_status === status)
      : applications;

    await route.fulfill({
      contentType: "application/json",
      json: body,
      status: 200,
    });
  });
  await page.route("**/metrics/summary", async (route) => {
    const responseIds = responseApplicationIds();
    const averageHours = averageFirstResponseHours();
    await route.fulfill({
      contentType: "application/json",
      json: {
        application_windows: [],
        average_time_to_first_response: {
          application_count: responseIds.size,
          average_hours: averageHours,
        },
        distinct_company_count: new Set(
          applications.map((application) => application.company.toLowerCase()),
        ).size,
        evaluated_at: "2026-07-05T12:00:00Z",
        ghost_threshold_days: 30,
        ghosted_applications: applications.filter(
          (application) => application.current_status === "ghosted",
        ).length,
        interview_invitation_count: applicationsWithEvent("interview_scheduled").size,
        offers_received: applicationsWithEvent("offer").size,
        rejected_applications: applications.filter(
          (application) => application.current_status === "rejected",
        ).length,
        total_applications: applications.length,
      },
      status: 200,
    });
  });
  await page.route("**/metrics/rates", async (route) => {
    const responseCount = responseApplicationIds().size;
    const interviewCount = applicationsWithEvent("interview_scheduled").size;
    const offerCount = applicationsWithEvent("offer").size;
    const rejectionCount = applications.filter(
      (application) => application.current_status === "rejected",
    ).length;
    const ghostCount = applications.filter(
      (application) => application.current_status === "ghosted",
    ).length;
    await route.fulfill({
      contentType: "application/json",
      json: {
        application_to_interview_rate: metricRate(
          interviewCount,
          applications.length,
        ),
        ghost_rate: metricRate(ghostCount, applications.length),
        interview_to_offer_rate: metricRate(offerCount, interviewCount),
        overall_response_rate: metricRate(responseCount, applications.length),
        rejection_rate: metricRate(rejectionCount, applications.length),
      },
      status: 200,
    });
  });
  await page.route("**/metrics/breakdown**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        dimension: "source",
        rows: sourceBreakdownRows(),
      },
      status: 200,
    });
  });

  await page.goto("/");

  await expect(page).toHaveTitle("JobTracker");
  await expect(
    page.getByRole("heading", {
      name: "JobTracker turns your inbox into job-search intelligence.",
    }),
  ).toBeVisible();

  await expect(
    page.getByRole("heading", {
      name: "Frontend foundation ready for Phase 0 pages",
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Connect Gmail through a local-only setup flow"),
  ).toBeVisible();

  const syncPanel = page.getByRole("region", { name: "Gmail sync progress" });

  await expect(syncPanel).toBeVisible();
  await expect(syncPanel.getByText("Last sync succeeded")).toBeVisible();
  await expect(syncPanel.getByText("1,240 raw emails")).toBeVisible();
  await expect(syncPanel.getByText("2,500 messages")).toBeVisible();
  await expect(syncPanel.getByText("12 pages")).toBeVisible();
  await expect(syncPanel.getByText("Recovered expired cursor")).toBeVisible();
  await expect(syncPanel.getByText("talib@example.test")).toBeVisible();

  await syncPanel.getByRole("button", { name: "Sync now" }).click();
  await expect(syncPanel.getByText("Sync is running")).toBeVisible();
  await expect(syncPanel.getByText("1,305 raw emails")).toBeVisible();

  await expect(
    page.getByRole("region", { name: "Chart foundation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("status", { name: "Dashboard data pending" }),
  ).toContainText(
    "Future deterministic dashboard metrics will render here after the metrics API exists.",
  );

  await page.getByRole("link", { name: "Dashboard" }).click();

  await expect(page).toHaveURL("/dashboard");
  await expect(
    page.getByRole("heading", { exact: true, name: "Dashboard" }),
  ).toBeVisible();

  const metricsOverview = page.getByRole("region", {
    name: "Metrics overview",
  });
  await expect(
    metricsOverview.locator("article", { hasText: "Total applications" }),
  ).toContainText("3");
  await expect(
    metricsOverview.locator("article", { hasText: "Distinct companies" }),
  ).toContainText("2");
  await expect(
    metricsOverview.locator("article", { hasText: "Interview invitations" }),
  ).toContainText("1");
  await expect(
    metricsOverview.locator("article", { hasText: "Offers received" }),
  ).toContainText("1");
  await expect(
    metricsOverview.locator("article", {
      hasText: "Avg time to first response",
    }),
  ).toContainText("2 days");
  await expect(page.getByLabel("Response rate metric")).toContainText("66.7%");
  await expect(page.getByLabel("Rejection rate metric")).toContainText("33.3%");
  await expect(page.getByLabel("Ghost rate metric")).toContainText("0%");
  await expect(page.getByLabel("Application to interview rate metric")).toContainText(
    "33.3%",
  );
  await expect(page.getByLabel("Interview to offer rate metric")).toContainText(
    "100%",
  );

  const statusTable = page.getByRole("table", {
    name: "Application current statuses",
  });
  await expect(statusTable).toBeVisible();
  await expect(
    statusTable.getByRole("link", { name: "Example Analytics" }).first(),
  ).toBeVisible();
  await expect(statusTable.getByText("Platform Engineer")).toBeVisible();

  const breakdown = page.getByRole("region", { name: "Source breakdown" });
  await expect(breakdown.getByText("Linkedin").first()).toBeVisible();
  await expect(breakdown.getByText("2 applications")).toBeVisible();
  await expect(breakdown.getByText("1 response, 1 interview, 1 offer")).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Source metric breakdown" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Setup" }).click();

  await expect(page).toHaveURL("/setup");
  await expect(
    page.getByRole("heading", { name: "Set up JobTracker locally" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "The wizard must make each privacy and provider choice explicit.",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Choose your LLM provider" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Connect Gmail read-only" }),
  ).toBeVisible();
  await expect(page.getByText("Preselected from Azure OpenAI setup")).toBeVisible();
  await expect(page.getByText("Waiting for Gmail callback")).toBeVisible();
  await expect(page.getByText("No telemetry")).toBeVisible();
});
