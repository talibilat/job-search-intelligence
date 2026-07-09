import { expect, test } from "@playwright/test";

test("renders the Phase 0 setup, sync, and dashboard shell", async ({
  page,
}) => {
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
        retained_body_failure_count: 1,
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
        retained_body_failure_count: 2,
        started_at: "2026-07-05T10:00:00Z",
        state: "running",
      },
      status: 200,
    });
  });
  await page.route("**/pipeline/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        account_display: "talib@example.test",
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
      },
      status: 200,
    });
  });
  await page.route("**/sync/recent-emails?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: [
        {
          body_retention_state: "retained",
          classification_category: null,
          classification_is_job_related: null,
          filter_outcome: "candidate",
          filter_reason: "sender_domain:example.com",
          from_addr: "jobs@example.com",
          has_retained_body: true,
          id: "gmail-msg-1",
          ingested_at: "2026-07-05T09:45:30Z",
          labels: ["INBOX"],
          provider: "gmail",
          sent_at: "2026-07-05T08:30:00Z",
          subject: "Application received",
          thread_id: "thread-1",
          to_addr: "talib@example.test",
        },
      ],
      status: 200,
    });
  });

  await page.goto("/");

  await expect(page).toHaveTitle("JobTracker");
  await expect(
    page.getByRole("heading", {
      name: "Your job search, from inbox to insight.",
    }),
  ).toBeVisible();

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
  await expect(syncPanel.getByText("talib@example.test")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Newest synced mailbox messages" }),
  ).toBeVisible();
  await expect(page.getByText("Application received")).toBeVisible();

  await syncPanel.getByRole("button", { name: "Sync now" }).click();
  await expect(syncPanel.getByText("Sync is running")).toBeVisible();
  await expect(syncPanel.getByText("1,305 raw emails")).toBeVisible();
  await expect(syncPanel.getByText("2 body fetch issues")).toBeVisible();

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
  await expect(page.getByText("No telemetry")).toBeVisible();
});
