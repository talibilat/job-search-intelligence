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

  if (process.env.NO_MISTAKES_EVIDENCE_DIR) {
    await syncPanel.screenshot({
      path: `${process.env.NO_MISTAKES_EVIDENCE_DIR}/sync-status-panel-succeeded.png`,
    });
  }

  await syncPanel.getByRole("button", { name: "Sync now" }).click();
  await expect(syncPanel.getByText("Sync is running")).toBeVisible();
  await expect(syncPanel.getByText("1,305 raw emails")).toBeVisible();

  if (process.env.NO_MISTAKES_EVIDENCE_DIR) {
    await syncPanel.screenshot({
      path: `${process.env.NO_MISTAKES_EVIDENCE_DIR}/sync-status-panel-running.png`,
    });
  }

  await expect(
    page.getByRole("region", { name: "Chart foundation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("status", { name: "Dashboard data pending" }),
  ).toContainText(
    "Future deterministic dashboard metrics will render here after the metrics API exists.",
  );

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
