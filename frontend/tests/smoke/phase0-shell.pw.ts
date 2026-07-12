import { expect, test, type Page } from "@playwright/test";

import type {
  ApiErrorResponse,
  ApplicationEventEditRequest,
  ApplicationEventEditResponse,
  ApplicationEventTimelineRecord,
  ApplicationRecord,
  ApplicationStatusCountsResponse,
  ApplicationStatusEditRequest,
  ApplicationStatusEditResponse,
  ClassificationPreRunEstimate,
  EmailAuthorizationStartResult,
  EmailConnection,
  EmailSyncStatus,
  InsightListResponse,
  InsightRegenerateRequest,
  InsightRegenerateResponse,
  LLMProviderHealthCheckResponse,
  MetricsBreakdownResponse,
  MetricsFunnelResponse,
  MetricsRatesResponse,
  MetricsSummaryResponse,
  MetricsTimeseriesResponse,
  PipelineStatus,
  ProviderConfigResponse,
  ProviderConfigUpdateRequest,
  RawEmailPreviewRecord,
  RecentApplicationEventRecord,
  SetupStatusResponse,
  SyncLocalStats,
} from "../../src/api";

async function expectCategoricalTooltip(
  page: Page,
  chart: ReturnType<Page["getByRole"]>,
  options: {
    categoryIndex: number;
    label: string;
    mark?: "bar" | "line";
    markCount: number;
    value: string;
  },
) {
  const marks = chart.locator(
    options.mark === "line"
      ? ".recharts-line-dot"
      : ".recharts-bar-rectangle .recharts-rectangle",
  );
  await expect(marks).toHaveCount(options.markCount);
  const mark = marks.nth(options.categoryIndex);
  const tooltip = chart.locator(".recharts-tooltip-wrapper");
  const label = tooltip.locator(".recharts-tooltip-label");
  const value = tooltip.locator(".recharts-tooltip-item-value");
  await expect
    .poll(async () => {
      const box = await mark.boundingBox();
      return box !== null && box.width > 0 && box.height > 0;
    })
    .toBe(true);
  await mark.evaluate((element) => element.scrollIntoView({ block: "center" }));
  await expect
    .poll(async () => {
      const box = await mark.boundingBox();
      if (!box) {
        return null;
      }
      const eventInit = {
        bubbles: true,
        clientX: box.x + box.width / 2,
        clientY: box.y + box.height / 2,
      };
      await mark.dispatchEvent("mouseover", eventInit);
      await mark.dispatchEvent("mousemove", eventInit);
      await page.mouse.move(eventInit.clientX, eventInit.clientY, {
        steps: 1,
      });
      return label.textContent();
    })
    .toBe(options.label);
  await expect(label).toHaveText(options.label);
  await expect(value).toHaveText(options.value);
}

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
} satisfies Omit<
  ApplicationRecord,
  "company" | "current_status" | "id" | "role_title" | "source"
>;

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
] satisfies ApplicationRecord[];

const legacyMetricsSummary = {
  application_windows: [],
  average_time_to_first_response: { application_count: 2, average_hours: 48 },
  average_time_to_rejection: { application_count: 1, average_hours: 48 },
  distinct_company_count: 2,
  evaluated_at: "2026-07-05T12:00:00Z",
  ghost_threshold_days: 30,
  ghosted_applications: 0,
  interview_invitation_count: 1,
  live_applications: 2,
  offers_received: 1,
  personal_ghost_threshold: {
    response_sample_size: 2,
    silence_age_distribution: [
      { application_count: 1, bucket: "0_7", max_days: 7, min_days: 0 },
      { application_count: 0, bucket: "8_14", max_days: 14, min_days: 8 },
      { application_count: 0, bucket: "15_30", max_days: 30, min_days: 15 },
      { application_count: 0, bucket: "31_60", max_days: 60, min_days: 31 },
      { application_count: 0, bucket: "61_plus", max_days: null, min_days: 61 },
    ],
    silent_application_count: 1,
    threshold_days: 2,
    threshold_source: "response_percentile",
  },
  rejected_applications: 1,
  total_applications: 3,
} satisfies MetricsSummaryResponse;

const legacyMetricsRates = {
  application_to_interview_rate: {
    denominator: 3,
    numerator: 1,
    rate: 0.333333,
  },
  ghost_rate: { denominator: 3, numerator: 0, rate: 0 },
  interview_to_offer_rate: { denominator: 1, numerator: 1, rate: 1 },
  overall_response_rate: { denominator: 3, numerator: 2, rate: 0.666667 },
  rejection_rate: { denominator: 3, numerator: 1, rate: 0.333333 },
} satisfies MetricsRatesResponse;

const legacySourceBreakdown = {
  dimension: "source",
  rows: [
    {
      application_count: 1,
      dimension: "source",
      interview_count: 0,
      interview_rate: 0,
      offer_count: 0,
      offer_rate: 0,
      response_count: 1,
      response_rate: 1,
      value: "company_site",
    },
    {
      application_count: 2,
      dimension: "source",
      interview_count: 1,
      interview_rate: 0.5,
      offer_count: 1,
      offer_rate: 0.5,
      response_count: 1,
      response_rate: 0.5,
      value: "linkedin",
    },
  ],
} satisfies MetricsBreakdownResponse;

const legacyTimeseries = {
  points: [
    { application_count: 2, period_start: "2026-07-01" },
    { application_count: 1, period_start: "2026-07-02" },
  ],
} satisfies MetricsTimeseriesResponse;

const legacySetupStatus = {
  classification_mode: "hybrid",
  email_provider: "gmail",
  gmail_connected: false,
  llm_configured: true,
  llm_provider: "azure_openai",
  recommended_classification_mode: "hybrid",
  setup_complete: false,
} satisfies SetupStatusResponse;

const legacyRunnableFeatureStatus = {
  ...legacySetupStatus,
  gmail_connected: true,
} satisfies SetupStatusResponse;

const legacyCompletedSync = {
  account_id: "person@example.test",
  finished_at: "2026-07-05T09:45:30Z",
  last_error: null,
  message_count: 2500,
  mode: "full_backfill",
  page_count: 12,
  provider: "gmail",
  raw_email_count: 1240,
  recovered_from_expired_cursor: true,
  retained_body_failure_count: 1,
  started_at: "2026-07-05T09:15:00Z",
  state: "succeeded",
} satisfies EmailSyncStatus;

const legacyRunningSync = {
  account_id: "person@example.test",
  finished_at: null,
  last_error: null,
  message_count: 2600,
  mode: "incremental",
  page_count: 13,
  provider: "gmail",
  raw_email_count: 1305,
  recovered_from_expired_cursor: false,
  retained_body_failure_count: 2,
  started_at: "2026-07-05T10:00:00Z",
  state: "running",
} satisfies EmailSyncStatus;

const legacyPipelineStatus = {
  account_display: "person@example.test",
  backfill_complete: false,
  backfill_messages_processed: 2500,
  backfill_pages_processed: 12,
  backfill_state: "running",
  counts: {
    application_count: 0,
    application_event_count: 0,
    classified_email_count: 0,
    filter_candidate_count: 24,
    filter_decision_count: 1240,
    filter_rejected_count: 1216,
    job_related_email_count: 0,
    metadata_only_count: 1216,
    raw_email_count: 1240,
    retained_body_count: 24,
  },
  generated_at: "2026-07-05T09:45:30Z",
  gmail_connected: true,
  incremental_sync_ready: false,
  last_error: null,
  last_sync_finished_at: "2026-07-05T09:45:30Z",
  last_sync_started_at: "2026-07-05T09:15:00Z",
  next_action: "continue_backfill",
  next_action_reason: "The one-time historical backfill has not finished.",
  reauth_required: false,
  sync_mode: "full_backfill",
  sync_running: false,
  unclassified_retained_count: 24,
} satisfies PipelineStatus;

const legacyRecentEmails = [
  {
    body_retention_state: "retained",
    classification_category: null,
    classification_is_job_related: null,
    filter_outcome: "candidate",
    filter_reason: "sender_domain:example.com",
    from_domain: "example.com",
    has_retained_body: true,
    ingested_at: "2026-07-05T09:45:30Z",
    provider: "gmail",
    sent_at: "2026-07-05T08:30:00Z",
    subject_present: true,
    to_domains: ["example.test"],
  },
] satisfies RawEmailPreviewRecord[];

test("renders setup, sync, and fixture-backed dashboard metrics", async ({
  page,
}) => {
  await page.route("**/setup/status", async (route) => {
    const setupStatus =
      new URL(page.url()).pathname === "/setup"
        ? legacySetupStatus
        : legacyRunnableFeatureStatus;
    await route.fulfill({
      contentType: "application/json",
      json: setupStatus,
      status: 200,
    });
  });
  await page.route("**/sync/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: legacyCompletedSync,
      status: 200,
    });
  });
  await page.route("**/sync", async (route) => {
    expect(route.request().method()).toBe("POST");
    await route.fulfill({
      contentType: "application/json",
      json: legacyRunningSync,
      status: 200,
    });
  });
  await page.route("**/pipeline/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: legacyPipelineStatus,
      status: 200,
    });
  });
  await page.route("**/sync/recent-emails?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: legacyRecentEmails,
      status: 200,
    });
  });
  await page.route(/\/applications(?:\?.*)?$/, async (route) => {
    if (route.request().isNavigationRequest()) {
      await route.continue();
      return;
    }
    const requestUrl = new URL(route.request().url());
    if (
      requestUrl.pathname !== "/applications" ||
      route.request().method() !== "GET"
    ) {
      await route.continue();
      return;
    }
    const status = requestUrl.searchParams.get("status");
    const body = status
      ? applications.filter(
          (application) => application.current_status === status,
        )
      : applications;

    await route.fulfill({
      contentType: "application/json",
      json: body,
      status: 200,
    });
  });
  await page.route("**/metrics/summary", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: legacyMetricsSummary,
      status: 200,
    });
  });
  await page.route("**/metrics/rates", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: legacyMetricsRates,
      status: 200,
    });
  });
  await page.route("**/metrics/breakdown**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: legacySourceBreakdown,
      status: 200,
    });
  });
  await page.route("**/metrics/timeseries**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: legacyTimeseries,
      status: 200,
    });
  });

  await page.goto("/legacy");

  await expect(page).toHaveTitle("JobTracker");
  await expect(
    page.getByRole("heading", {
      name: "Your job search, from inbox to insight.",
    }),
  ).toBeVisible();

  await page.goto("/features");

  await expect(
    page.getByRole("heading", {
      name: "Pipeline status",
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Historical backfill is still in progress"),
  ).toBeVisible();

  const syncPanel = page.getByRole("region", { name: "Gmail sync progress" });

  await expect(syncPanel).toBeVisible();
  await expect(syncPanel.getByText("Last sync succeeded")).toBeVisible();
  await expect(syncPanel.getByText("1,240 raw emails")).toBeVisible();
  await expect(syncPanel.getByText("2,500 messages")).toBeVisible();
  await expect(syncPanel.getByText("12 pages")).toBeVisible();
  await expect(syncPanel.getByText("1 body fetch issue")).toBeVisible();
  await expect(syncPanel.getByText("Recovered expired cursor")).toBeVisible();
  await expect(syncPanel.getByText("person@example.test")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Newest synced mailbox messages" }),
  ).toBeVisible();
  await expect(page.getByText("Subject captured")).toBeVisible();
  await expect(page.getByText("example.com")).toBeVisible();

  const applicationTable = page.getByRole("table", {
    name: "Application current statuses",
  });
  await expect(applicationTable).toBeVisible();
  const applicationRows = applicationTable.locator("tbody tr");
  await expect(applicationRows).toHaveCount(3);
  for (const [rowIndex, expectedCells] of [
    [0, ["Example Analytics", "Senior Data Engineer", "Offer", "Jul 4, 2026"]],
    [1, ["Fixture Systems", "Platform Engineer", "Rejected", "Jul 3, 2026"]],
    [2, ["Example Analytics", "Backend Engineer", "Applied", "Jul 2, 2026"]],
  ] as const) {
    const cells = applicationRows.nth(rowIndex).getByRole("cell");
    await expect(cells).toHaveCount(4);
    for (const [cellIndex, expectedCell] of expectedCells.entries()) {
      await expect(cells.nth(cellIndex)).toHaveText(expectedCell);
    }
  }

  const refreshedSyncPanel = page.getByRole("region", {
    name: "Gmail sync progress",
  });
  await refreshedSyncPanel.getByRole("button", { name: "Sync now" }).click();
  await expect(refreshedSyncPanel.getByText("Sync is running")).toBeVisible();
  await expect(refreshedSyncPanel.getByText("1,305 raw emails")).toBeVisible();
  await expect(
    refreshedSyncPanel.getByText("2 body fetch issues"),
  ).toBeVisible();

  await page.getByRole("link", { name: "Dashboard" }).click();

  await expect(page).toHaveURL("/dashboard");
  await expect(
    page.getByRole("heading", { exact: true, name: "Dashboard" }),
  ).toBeVisible();

  const counts = page.getByRole("region", { name: "Foundational counts" });
  await expect(counts).toBeVisible();
  await expect(
    counts.getByRole("img", { name: "Foundational counts" }),
  ).toBeVisible();
  for (const metric of [
    "Applications",
    "Interviews",
    "Offers",
    "Rejections",
    "Ghosts",
  ]) {
    await expect(counts.getByText(metric, { exact: true })).toBeVisible();
  }
  const countsChart = counts.getByRole("img", { name: "Foundational counts" });
  for (const [categoryIndex, label, value] of [
    [0, "Applications", "3"],
    [1, "Companies", "2"],
    [2, "Interviews", "1"],
    [3, "Offers", "1"],
    [4, "Rejections", "1"],
  ] as const) {
    await expectCategoricalTooltip(page, countsChart, {
      categoryIndex,
      label,
      markCount: 5,
      value,
    });
  }
  await expect(countsChart.getByText("Ghosts", { exact: true })).toBeVisible();
  await expect(
    countsChart.locator(".recharts-bar-rectangle .recharts-rectangle"),
  ).toHaveCount(5);

  const rates = page.getByRole("region", { name: "Outcome rates" });
  await expect(rates).toBeVisible();
  const ratesChart = rates.getByRole("img", { name: "Outcome rates" });
  await expect(ratesChart).toBeVisible();
  for (const metric of [
    "Response",
    "Rejection",
    "Ghost",
    /Application to\s*interview/,
    "Interview to offer",
  ]) {
    await expect(
      ratesChart.getByText(metric, { exact: typeof metric === "string" }),
    ).toBeVisible();
  }
  for (const [categoryIndex, label, value] of [
    [0, "Response", "66.6667"],
    [1, "Rejection", "33.3333"],
    [2, "Application to interview", "33.3333"],
    [3, "Interview to offer", "100"],
  ] as const) {
    await expectCategoricalTooltip(page, ratesChart, {
      categoryIndex,
      label,
      markCount: 4,
      value,
    });
  }
  await expect(ratesChart.getByText("Ghost", { exact: true })).toBeVisible();
  await expect(
    ratesChart.locator(".recharts-bar-rectangle .recharts-rectangle"),
  ).toHaveCount(4);

  const timing = page.getByRole("region", { name: "Response timing" });
  await expect(timing).toBeVisible();
  await expect(
    timing.getByText("First response", { exact: true }),
  ).toBeVisible();
  await expect(timing.getByText("Rejection", { exact: true })).toBeVisible();
  const timingChart = timing.getByRole("img", { name: "Response timing" });
  await expectCategoricalTooltip(page, timingChart, {
    categoryIndex: 0,
    label: "First response",
    markCount: 2,
    value: "48",
  });
  await expectCategoricalTooltip(page, timingChart, {
    categoryIndex: 1,
    label: "Rejection",
    markCount: 2,
    value: "48",
  });

  await expect(
    page.getByRole("table", { name: "Application current statuses" }),
  ).toHaveCount(0);

  const breakdown = page.getByRole("region", { name: "Source breakdown" });
  await expect(
    breakdown.getByRole("img", { name: "Source applications" }),
  ).toBeVisible();
  const breakdownChart = breakdown.getByRole("img", {
    name: "Source applications",
  });
  await expect(
    breakdownChart.getByText("Linkedin", { exact: true }),
  ).toBeVisible();
  await expect(
    breakdownChart.getByText("Companysite", { exact: true }),
  ).toBeVisible();
  await expectCategoricalTooltip(page, breakdownChart, {
    categoryIndex: 0,
    label: "Linkedin",
    markCount: 2,
    value: "2",
  });
  await expectCategoricalTooltip(page, breakdownChart, {
    categoryIndex: 1,
    label: "Company site",
    markCount: 2,
    value: "1",
  });
  await expect(
    breakdown.getByRole("table", { name: "Source metric breakdown" }),
  ).toHaveCount(0);

  const trend = page.getByRole("region", { name: "Application volume trend" });
  await expect(trend.getByText("Application volume trend")).toBeVisible();
  const trendChart = trend.getByRole("img", {
    name: "Daily application count",
  });
  await expect(trendChart).toBeVisible();
  await expect(
    trendChart.getByText("Jul 1, 2026", { exact: true }),
  ).toBeVisible();
  await expect(
    trendChart.getByText("Jul 2, 2026", { exact: true }),
  ).toBeVisible();
  await expectCategoricalTooltip(page, trendChart, {
    categoryIndex: 0,
    label: "Jul 1, 2026",
    mark: "line",
    markCount: 2,
    value: "2",
  });
  await expectCategoricalTooltip(page, trendChart, {
    categoryIndex: 1,
    label: "Jul 2, 2026",
    mark: "line",
    markCount: 2,
    value: "1",
  });

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
  await expect(
    page.getByText("Preselected from Azure OpenAI setup"),
  ).toBeVisible();
  await expect(page.getByText("Waiting for Gmail callback")).toBeVisible();
  await expect(page.getByText("No telemetry")).toBeVisible();
});

const redesignApplication = {
  ...baseApplication,
  company: "Example Analytics",
  current_status: "interview",
  id: "app-analytics",
  last_activity_at: "2026-07-09T14:00:00Z",
  role_title: "Senior Data Engineer",
  source: "linkedin",
} satisfies ApplicationRecord;

const rejectedApplication = {
  ...baseApplication,
  company: "Fixture Systems",
  current_status: "rejected",
  id: "app-fixture",
  last_activity_at: "2026-07-10T16:00:00Z",
  role_title: "Platform Engineer",
  source: "company_site",
} satisfies ApplicationRecord;

const redesignEvents = [
  {
    application_id: "app-analytics",
    classification_classified_at: "2026-07-09T14:02:00Z",
    classification_confidence: 0.97,
    email_id: "email-interview-fixture",
    email_sent_at: "2026-07-09T14:00:00Z",
    email_subject: "Interview availability",
    event_at: "2026-07-09T14:00:00Z",
    event_type: "interview_scheduled",
    extract_note: "Technical interview scheduled for Thursday.",
    extracted_status: "interview",
    id: "event-interview-fixture",
  },
  {
    application_id: "app-analytics",
    classification_classified_at: "2026-07-08T11:02:00Z",
    classification_confidence: 0.95,
    email_id: "email-feedback-fixture",
    email_sent_at: "2026-07-08T11:00:00Z",
    email_subject: "Interview feedback",
    event_at: "2026-07-08T11:00:00Z",
    event_type: "feedback",
    extract_note: "Explain architecture tradeoffs more concisely.",
    extracted_status: "interview",
    id: "event-feedback-fixture",
  },
  {
    application_id: "app-analytics",
    classification_classified_at: "2026-07-01T09:02:00Z",
    classification_confidence: 0.99,
    email_id: "email-applied-fixture",
    email_sent_at: "2026-07-01T09:00:00Z",
    email_subject: "Application received",
    event_at: "2026-07-01T09:00:00Z",
    event_type: "applied",
    extract_note: "Application received for Senior Data Engineer.",
    extracted_status: "applied",
    id: "event-applied-fixture",
  },
] satisfies ApplicationEventTimelineRecord[];

const rejectionEvents = [
  {
    application_id: "app-fixture",
    classification_classified_at: "2026-07-10T16:02:00Z",
    classification_confidence: 0.98,
    email_id: "email-rejection-fixture",
    email_sent_at: "2026-07-10T16:00:00Z",
    email_subject: "Rejection decision",
    event_at: "2026-07-10T16:00:00Z",
    event_type: "rejection",
    extract_note:
      "The role requires deeper distributed-systems design experience.",
    extracted_status: "rejected",
    id: "event-rejection-fixture",
  },
] satisfies ApplicationEventTimelineRecord[];

const redesignMetricsSummary = {
  application_windows: [],
  average_time_to_first_response: { application_count: 13, average_hours: 28 },
  average_time_to_rejection: { application_count: 9, average_hours: 72 },
  distinct_company_count: 18,
  evaluated_at: "2026-07-11T10:00:00Z",
  ghost_threshold_days: 30,
  ghosted_applications: 4,
  interview_invitation_count: 7,
  live_applications: 8,
  offers_received: 2,
  personal_ghost_threshold: {
    response_sample_size: 13,
    silence_age_distribution: [],
    silent_application_count: 8,
    threshold_days: 12,
    threshold_source: "response_percentile",
  },
  rejected_applications: 9,
  total_applications: 23,
} satisfies MetricsSummaryResponse;

const redesignMetricsRates = {
  application_to_interview_rate: {
    denominator: 23,
    numerator: 7,
    rate: 0.3043,
  },
  ghost_rate: { denominator: 23, numerator: 4, rate: 0.1739 },
  interview_to_offer_rate: { denominator: 7, numerator: 2, rate: 0.2857 },
  overall_response_rate: { denominator: 23, numerator: 13, rate: 0.5652 },
  rejection_rate: { denominator: 23, numerator: 9, rate: 0.3913 },
} satisfies MetricsRatesResponse;

const redesignFunnel = {
  stages: [
    { count: 23, stage: "applied" },
    { count: 14, stage: "screen" },
    { count: 7, stage: "interview" },
    { count: 3, stage: "final" },
    { count: 2, stage: "offer" },
  ],
} satisfies MetricsFunnelResponse;

const redesignRecentEvents = [
  {
    application_id: "app-analytics",
    company: "Example Analytics",
    current_status: "interview",
    email_id: "email-interview-fixture",
    email_subject: "Interview availability",
    event_at: "2026-07-09T14:00:00Z",
    event_id: "event-interview-fixture",
    event_type: "interview_scheduled",
    role_title: "Senior Data Engineer",
  },
] satisfies RecentApplicationEventRecord[];

const redesignStatusCounts = {
  counts: {
    applied: 5,
    assessment: 2,
    ghosted: 4,
    in_review: 3,
    interview: 1,
    offer: 2,
    rejected: 5,
    withdrawn: 1,
  },
  total: 23,
} satisfies ApplicationStatusCountsResponse;

const providerConfig = {
  email_providers: [],
  llm_providers: [],
  recommended_classification_mode: "hybrid",
  selection: {
    classification_mode: "hybrid",
    email_provider: "gmail",
    llm_provider: "azure_openai",
  },
  settings: {
    azure_openai_api_version: "2026-01-01",
    azure_openai_chat_deployment: "fixture-chat",
    azure_openai_embedding_deployment: "fixture-embedding",
    azure_openai_endpoint: "https://example.invalid",
    gmail_client_config_file: "client-secret.fixture.json",
    gmail_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
    ollama_base_url: "http://127.0.0.1:11434",
    ollama_chat_model: "fixture-chat",
    ollama_embedding_model: "fixture-embedding",
    sync_interval_seconds: 1800,
    sync_on_open: true,
  },
} satisfies ProviderConfigResponse;

const ollamaProviderConfig = {
  ...providerConfig,
  recommended_classification_mode: "local",
  selection: {
    ...providerConfig.selection,
    classification_mode: "local",
    llm_provider: "ollama",
  },
} satisfies ProviderConfigResponse;

const hourlyOllamaProviderConfig = {
  ...ollamaProviderConfig,
  settings: { ...ollamaProviderConfig.settings, sync_interval_seconds: 3600 },
} satisfies ProviderConfigResponse;

const unavailableOllamaHealth = {
  checks: [
    {
      detail: "The private-data-free fixture model is not running.",
      kind: "chat",
      model: "fixture-chat",
      status: "unavailable",
    },
    {
      detail: "The private-data-free fixture embedding model is not running.",
      kind: "embedding",
      model: "fixture-embedding",
      status: "unavailable",
    },
  ],
  provider_name: "Ollama",
  status: "unavailable",
} satisfies LLMProviderHealthCheckResponse;

const redesignConnections = [
  {
    account: { account_id: "fixture-account", provider: "gmail" },
    connected_at: "2026-07-01T08:00:00Z",
    credential_expires_at: null,
    credential_ref: {
      kind: "oauth_token",
      name: "gmail.fixture-account",
      provider: "gmail",
    },
    display_email: {
      address: "person@example.test",
      display_name: "Fixture User",
    },
    granted_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
    reauth_required: false,
  },
] satisfies EmailConnection[];

const redesignSyncStats = {
  last_run_at: "2026-07-11T09:30:00Z",
  total_raw_emails: 2400,
} satisfies SyncLocalStats;

const classificationEstimate = {
  candidate_count: 12,
  classification_mode: "hybrid",
  cost_estimate_available: true,
  currency: "USD",
  estimated_completion_tokens: 1200,
  estimated_cost_usd: 0.12,
  estimated_prompt_tokens: 4800,
  estimated_total_tokens: 6000,
  llm_provider: "azure_openai",
  model: "fixture-chat",
  prompt_version: "fixture-v1",
  token_estimate_method: "private-data-free fixture",
} satisfies ClassificationPreRunEstimate;

const gmailAuthorization = {
  authorization_url: "http://127.0.0.1:4173/oauth-fixture-destination",
  provider: "gmail",
  requested_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
  state: "public-fixture-state",
} satisfies EmailAuthorizationStartResult;

const statusCorrectionRequest = {
  current_status: "offer",
  reason: null,
} satisfies ApplicationStatusEditRequest;

const statusCorrectionResponse = {
  application: {
    ...redesignApplication,
    current_status: "offer",
    manual_lock: true,
  },
  correction: {
    after_json: { current_status: "offer" },
    application_id: "app-analytics",
    before_json: { current_status: "interview" },
    correction_type: "status_edit",
    created_at: "2026-07-11T10:05:00Z",
    id: 41,
    reason: null,
  },
} satisfies ApplicationStatusEditResponse;

const eventCorrectionRequest = {
  email_id: "email-interview-fixture",
  event_at: "2026-07-09T14:00:00Z",
  event_type: "interview_scheduled",
  extract_note: "Technical interview moved to Friday.",
  reason: "Calendar invite was updated",
} satisfies ApplicationEventEditRequest;

const eventCorrectionResponse = {
  application: {
    ...redesignApplication,
    current_status: "offer",
    manual_lock: true,
  },
  correction: {
    after_json: { extract_note: "Technical interview moved to Friday." },
    application_id: "app-analytics",
    before_json: { extract_note: redesignEvents[0].extract_note },
    correction_type: "event_edit",
    created_at: "2026-07-11T10:06:00Z",
    id: 42,
    reason: "Calendar invite was updated",
  },
  event: {
    application_id: "app-analytics",
    classification_classified_at: "2026-07-09T14:02:00Z",
    email_id: "email-interview-fixture",
    email_sent_at: "2026-07-09T14:00:00Z",
    event_at: "2026-07-09T14:00:00Z",
    event_type: "interview_scheduled",
    extract_note: "Technical interview moved to Friday.",
    extracted_status: "interview",
    id: "event-interview-fixture",
  },
} satisfies ApplicationEventEditResponse;

const insightList = {
  insights: [
    {
      citations: [
        {
          application_id: "app-fixture",
          citation_id: "application:app-fixture:event:event-rejection-fixture",
          company: "Fixture Systems",
          email_id: "email-rejection-fixture",
          email_subject: "Rejection decision",
          event_at: "2026-07-10T16:00:00Z",
          event_id: "event-rejection-fixture",
          event_type: "rejection",
          role_title: "Platform Engineer",
        },
      ],
      content:
        "Rejections repeatedly cite system-design depth in the saved evidence.",
      generated_at: "2026-07-10T12:00:00Z",
      id: 40,
      inputs_hash: "fixture-q40-v1",
      is_stale: true,
      model: "fixture-model",
      type: "why_rejected",
    },
    {
      citations: [
        {
          application_id: "app-analytics",
          citation_id: "application:app-analytics:event:event-feedback-fixture",
          company: "Example Analytics",
          email_id: "email-feedback-fixture",
          email_subject: "Interview feedback",
          event_at: "2026-07-08T11:00:00Z",
          event_id: "event-feedback-fixture",
          event_type: "feedback",
          role_title: "Senior Data Engineer",
        },
      ],
      content:
        "Recruiter feedback consistently asks for more concise tradeoff explanations.",
      generated_at: "2026-07-10T12:00:00Z",
      id: 41,
      inputs_hash: "fixture-q41-v1",
      is_stale: false,
      model: "fixture-model",
      type: "recurring_feedback",
    },
  ],
  regeneration_cost_estimates: [
    {
      cost: {
        cost_estimate_available: true,
        currency: "USD",
        estimated_completion_tokens: 120,
        estimated_cost_usd: 0.004,
        estimated_prompt_tokens: 500,
        estimated_total_tokens: 620,
        token_estimate_method: "fixture estimate",
      },
      type: "why_rejected",
    },
  ],
} satisfies InsightListResponse;

const regenerateInsightRequest = {
  type: "why_rejected",
} satisfies InsightRegenerateRequest;

const regenerateInsightResponse = {
  cached: false,
  cost: {
    actual_completion_tokens: 100,
    actual_cost_usd: 0.003,
    actual_prompt_tokens: 450,
    actual_total_tokens: 550,
    cost_estimate_available: true,
    currency: "USD",
    estimated_completion_tokens: 120,
    estimated_cost_usd: 0.004,
    estimated_prompt_tokens: 500,
    estimated_total_tokens: 620,
    token_estimate_method: "fixture estimate",
  },
  evidence_citation_ids: [
    "application:app-fixture:event:event-rejection-fixture",
  ],
  insight: {
    citations: [
      {
        application_id: "app-fixture",
        citation_id: "application:app-fixture:event:event-rejection-fixture",
        company: "Fixture Systems",
        email_id: "email-rejection-fixture",
        email_subject: "Rejection decision",
        event_at: "2026-07-10T16:00:00Z",
        event_id: "event-rejection-fixture",
        event_type: "rejection",
        role_title: "Platform Engineer",
      },
    ],
    content: "Fresh cited evidence points to system-design tradeoff depth.",
    generated_at: "2026-07-11T10:10:00Z",
    id: 40,
    inputs_hash: "fixture-q40-v2",
    is_stale: false,
    model: "fixture-model",
    type: "why_rejected",
  },
} satisfies InsightRegenerateResponse;

const schedulerError = {
  error: {
    code: "conflict",
    details: [],
    message: "The scheduler rejected this fixture update.",
  },
} satisfies ApiErrorResponse;

async function installRedesignFixtures(page: Page) {
  const timelineRequestEvents: string[] = [];
  const chatRequestEvents: string[] = [];
  const mutationRequestEvents: string[] = [];
  let providerUpdateCount = 0;
  let currentProviderConfig: ProviderConfigResponse = providerConfig;

  await page.route("**/auth/connections", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: redesignConnections,
      status: 200,
    }),
  );
  await page.route("**/sync/stats", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: redesignSyncStats,
      status: 200,
    }),
  );
  await page.route("**/metrics/summary", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: redesignMetricsSummary,
      status: 200,
    }),
  );
  await page.route("**/metrics/rates", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: redesignMetricsRates,
      status: 200,
    }),
  );
  await page.route("**/metrics/funnel", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: redesignFunnel,
      status: 200,
    }),
  );
  await page.route("**/applications/events/recent?**", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: redesignRecentEvents,
      status: 200,
    }),
  );
  await page.route("**/applications/status-counts", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: redesignStatusCounts,
      status: 200,
    }),
  );
  await page.route("**/applications/app-analytics/status", async (route) => {
    expect(route.request().method()).toBe("PATCH");
    mutationRequestEvents.push("PATCH /applications/app-analytics/status");
    expect(route.request().postDataJSON()).toEqual(statusCorrectionRequest);
    await route.fulfill({
      contentType: "application/json",
      json: statusCorrectionResponse,
      status: 200,
    });
  });
  await page.route(
    "**/applications/app-analytics/events/event-interview-fixture",
    async (route) => {
      expect(route.request().method()).toBe("PATCH");
      mutationRequestEvents.push(
        "PATCH /applications/app-analytics/events/event-interview-fixture",
      );
      expect(route.request().postDataJSON()).toEqual(eventCorrectionRequest);
      await route.fulfill({
        contentType: "application/json",
        json: eventCorrectionResponse,
        status: 200,
      });
    },
  );
  await page.route("**/applications/app-analytics/events", async (route) => {
    timelineRequestEvents.push(
      `${route.request().method()} /applications/app-analytics/events`,
    );
    await route.fulfill({
      contentType: "application/json",
      json: redesignEvents,
      status: 200,
    });
  });
  await page.route("**/applications/app-fixture/events", async (route) => {
    timelineRequestEvents.push(
      `${route.request().method()} /applications/app-fixture/events`,
    );
    await route.fulfill({
      contentType: "application/json",
      json: rejectionEvents,
      status: 200,
    });
  });
  await page.route("**/applications/app-fixture", (route) => {
    if (route.request().isNavigationRequest()) {
      return route.continue();
    }
    return route.fulfill({
      contentType: "application/json",
      json: rejectedApplication,
      status: 200,
    });
  });
  await page.route("**/applications/app-analytics", (route) => {
    if (route.request().isNavigationRequest()) {
      return route.continue();
    }
    return route.fulfill({
      contentType: "application/json",
      json: redesignApplication,
      status: 200,
    });
  });
  await page.route("**/applications?**", (route) => {
    if (route.request().isNavigationRequest()) {
      return route.continue();
    }
    const requestUrl = new URL(route.request().url());
    expect(requestUrl.searchParams.get("status")).toBe("interview");
    return route.fulfill({
      contentType: "application/json",
      json: [redesignApplication],
      status: 200,
    });
  });
  await page.route("**/applications", (route) => {
    if (route.request().isNavigationRequest()) {
      return route.continue();
    }
    return route.fulfill({
      contentType: "application/json",
      json: [redesignApplication],
      status: 200,
    });
  });
  await page.route("**/insights", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: insightList,
      status: 200,
    }),
  );
  await page.route("**/insights/regenerate", async (route) => {
    expect(route.request().method()).toBe("POST");
    mutationRequestEvents.push("POST /insights/regenerate");
    expect(route.request().postDataJSON()).toEqual(regenerateInsightRequest);
    await route.fulfill({
      contentType: "application/json",
      json: regenerateInsightResponse,
      status: 200,
    });
  });
  await page.route("**/config/providers/llm/health", async (route) => {
    expect(route.request().method()).toBe("POST");
    mutationRequestEvents.push("POST /config/providers/llm/health");
    await route.fulfill({
      contentType: "application/json",
      json: unavailableOllamaHealth,
      status: 200,
    });
  });
  await page.route("**/config/providers", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        contentType: "application/json",
        json: currentProviderConfig,
        status: 200,
      });
      return;
    }
    expect(route.request().method()).toBe("PUT");
    mutationRequestEvents.push("PUT /config/providers");
    providerUpdateCount += 1;
    if (providerUpdateCount === 1) {
      const providerUpdate = {
        llm_provider: "ollama",
      } satisfies ProviderConfigUpdateRequest;
      expect(route.request().postDataJSON()).toEqual(providerUpdate);
      currentProviderConfig = ollamaProviderConfig;
      await route.fulfill({
        contentType: "application/json",
        json: currentProviderConfig,
        status: 200,
      });
      return;
    }
    if (providerUpdateCount === 2) {
      const schedulerUpdate = {
        sync_interval_seconds: 3600,
        sync_on_open: true,
      } satisfies ProviderConfigUpdateRequest;
      expect(route.request().postDataJSON()).toEqual({
        ...schedulerUpdate,
      });
      currentProviderConfig = hourlyOllamaProviderConfig;
      await route.fulfill({
        contentType: "application/json",
        json: currentProviderConfig,
        status: 200,
      });
      return;
    }
    const manualUpdate = {
      sync_on_open: false,
    } satisfies ProviderConfigUpdateRequest;
    expect(route.request().postDataJSON()).toEqual(manualUpdate);
    await route.fulfill({
      contentType: "application/json",
      json: schedulerError,
      status: 409,
    });
  });
  await page.route("**/classification/estimate", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: classificationEstimate,
      status: 200,
    }),
  );
  await page.route("**/auth/gmail", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: gmailAuthorization,
      status: 200,
    }),
  );
  await page.route("**/oauth-fixture-destination", (route) =>
    route.fulfill({
      body: "<!doctype html><title>Controlled OAuth fixture destination</title><h1>Controlled OAuth fixture destination</h1>",
      contentType: "text/html",
      status: 200,
    }),
  );
  await page.route("**/chat", async (route) => {
    chatRequestEvents.push(`${route.request().method()} /chat`);
    await route.abort();
  });

  return {
    chatRequestEvents,
    mutationRequestEvents,
    providerUpdateCount: () => providerUpdateCount,
    timelineRequestEvents,
  };
}

test("runs the critical private-data-free redesign journey", async ({
  page,
}) => {
  const requests = await installRedesignFixtures(page);
  const noRequestObservationMs = 150;

  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: /offer.*on the table/i }),
  ).toBeVisible();
  for (const [label, value] of [
    ["Applications", "23"],
    ["Response rate", "56.5%"],
    ["Interview rate", "30.4%"],
    ["Offers", "2"],
  ] as const) {
    const card = page
      .getByRole("main")
      .getByText(label, { exact: true })
      .locator(
        "xpath=ancestor::div[./div/button[normalize-space()='How?']][1]",
      );
    await expect(card.getByText(value, { exact: true })).toBeVisible();
  }
  const funnelHeading = page.getByRole("heading", {
    name: "Where applications stand",
  });
  const funnel = funnelHeading.locator("xpath=ancestor::div[.//button][1]");
  await expect(funnel.getByRole("button")).toHaveCount(5);
  for (const [label, count] of [
    ["Applied", "23"],
    ["Screen", "14"],
    ["Interview", "7"],
    ["Final", "3"],
    ["Offer", "2"],
  ]) {
    const stage = funnel.getByRole("button", {
      name: new RegExp(`^${label}\\s+${count}$`),
    });
    await expect(stage).toBeVisible();
    await expect(stage.getByText(count, { exact: true })).toBeVisible();
  }

  await page.goto("/applications?status=interview");
  await expect(page).toHaveURL("/applications?status=interview");
  await expect(page.getByText("1 of 23 applications")).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: /Example Analytics.*Senior Data Engineer/i,
    }),
  ).toBeVisible();
  const timelineRequestsBeforeViews = requests.timelineRequestEvents.length;
  await page.waitForTimeout(noRequestObservationMs);
  expect(requests.timelineRequestEvents).toHaveLength(
    timelineRequestsBeforeViews,
  );

  await page.getByRole("button", { name: "Board" }).click();
  await expect(
    page.getByRole("button", {
      name: /Example Analytics.*Senior Data Engineer/i,
    }),
  ).toBeVisible();
  await page.waitForTimeout(noRequestObservationMs);
  expect(requests.timelineRequestEvents).toHaveLength(
    timelineRequestsBeforeViews,
  );

  await page.getByRole("button", { name: "Timeline" }).click();
  await expect(page.getByText("3 steps")).toBeVisible();
  expect(requests.timelineRequestEvents).toEqual([
    "GET /applications/app-analytics/events",
  ]);

  await page.goto("/applications/app-analytics");
  await expect(
    page.getByRole("heading", { name: "Example Analytics" }),
  ).toBeVisible();
  await page.getByLabel("Application status").selectOption("offer");
  await expect(
    page.getByText("Edited by you - protected from auto-updates"),
  ).toBeVisible();
  expect(requests.mutationRequestEvents).toContain(
    "PATCH /applications/app-analytics/status",
  );

  await page.getByRole("button", { name: "Fix a mistake" }).first().click();
  await page
    .getByLabel("Event note")
    .fill("Technical interview moved to Friday.");
  await page
    .getByLabel("Correction reason")
    .fill("Calendar invite was updated");
  await page.getByRole("button", { name: "Save correction" }).click();
  await expect(
    page.getByText("“Technical interview moved to Friday.”"),
  ).toBeVisible();
  expect(requests.mutationRequestEvents).toContain(
    "PATCH /applications/app-analytics/events/event-interview-fixture",
  );

  await page.getByRole("button", { name: "Insights" }).click();
  await expect(
    page.getByText("Q-40 · Why am I getting rejected?"),
  ).toBeVisible();
  await expect(
    page.getByText("Q-41 · What feedback says to improve"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /Rewrite with latest data/ })
    .first()
    .click();
  await expect(
    page.getByText(
      "Fresh cited evidence points to system-design tradeoff depth.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Fixture Systems - Rejection decision",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Example Analytics - Interview feedback",
    }),
  ).toBeVisible();
  expect(requests.mutationRequestEvents).toContain("POST /insights/regenerate");

  await page
    .getByRole("button", { name: "Fixture Systems - Rejection decision" })
    .click();
  await expect(page).toHaveURL("/applications/app-fixture");
  await expect(
    page.getByRole("heading", { name: "Fixture Systems" }),
  ).toBeVisible();
  await expect(page.getByLabel("Application status")).toHaveValue("rejected");
  const rejectionTimeline = page
    .getByRole("heading", { name: "What happened, step by step" })
    .locator("xpath=ancestor::div[1]");
  await expect(
    rejectionTimeline.getByText("Rejected", { exact: true }),
  ).toBeVisible();
  await expect(
    rejectionTimeline.getByText("✉ Rejection decision", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Insights" }).click();
  await page
    .getByRole("button", { name: "Example Analytics - Interview feedback" })
    .click();
  await expect(page).toHaveURL("/applications/app-analytics");
  const feedbackTimeline = page
    .getByRole("heading", { name: "What happened, step by step" })
    .locator("xpath=ancestor::div[1]");
  await expect(
    feedbackTimeline.getByText("Feedback received", { exact: true }),
  ).toBeVisible();
  await expect(
    feedbackTimeline.getByText("✉ Interview feedback", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByRole("button", { name: /On this computer/ }).click();
  await expect(page.getByText("Ollama unavailable")).toBeVisible();
  expect(requests.mutationRequestEvents).toContain("PUT /config/providers");
  expect(requests.mutationRequestEvents).toContain(
    "POST /config/providers/llm/health",
  );
  await page.getByLabel("Auto-sync interval").selectOption("hour");
  await expect(page.getByLabel("Auto-sync interval")).toHaveValue("hour");
  await page.getByLabel("Auto-sync interval").selectOption("manual");
  await expect(page.getByRole("alert")).toContainText(
    "The scheduler rejected this fixture update.",
  );
  expect(requests.providerUpdateCount()).toBe(3);

  await page.getByRole("button", { name: "+ Add another inbox" }).click();
  await page.getByRole("button", { name: "Gmail" }).click();
  await expect(page).toHaveURL("/oauth-fixture-destination");
  await expect(
    page.getByRole("heading", { name: "Controlled OAuth fixture destination" }),
  ).toBeVisible();

  await page.goto("/");
  const chatRequestsBeforeOpen = requests.chatRequestEvents.length;
  await page.getByRole("button", { name: "Ask AI" }).click();
  const chatDrawer = page.getByRole("complementary", { name: "Ask AI drawer" });
  await expect(
    chatDrawer.getByText("Phase 5 unavailable - grounded chat is not active"),
  ).toBeVisible();
  await expect(
    chatDrawer.getByPlaceholder("e.g. Why am I getting rejected?"),
  ).toBeDisabled();
  await expect(
    chatDrawer.getByRole("button", { name: "Ask", exact: true }),
  ).toBeDisabled();
  await page.waitForTimeout(noRequestObservationMs);
  expect(requests.chatRequestEvents).toHaveLength(chatRequestsBeforeOpen);

  await page.goto("/dev");
  await expect(
    page.getByRole("heading", { name: "For developers" }),
  ).toBeVisible();
  const manualCorrectionsRow = page
    .getByText("Manual corrections", { exact: true })
    .locator("xpath=ancestor::div[span][1]");
  await expect(manualCorrectionsRow).toContainText("Completed");
  const chatStatusRow = page
    .getByText("Chat agent (RAG)", { exact: true })
    .locator("xpath=ancestor::div[span][1]");
  await expect(chatStatusRow).toContainText("Planned");
  await expect(chatStatusRow).toContainText("Phase 5");
  await expect(page.getByText("POST /chat")).toBeVisible();
});
