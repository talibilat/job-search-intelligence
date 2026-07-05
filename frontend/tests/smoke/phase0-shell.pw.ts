import { expect, test } from "@playwright/test";

test("renders the Phase 0 setup, sync, and dashboard shell", async ({
  page,
}) => {
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

  await expect(
    page.getByRole("heading", { name: "Sync status ready for backend wiring" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Manual sync and last-run state will appear here once the sync API exists.",
    ),
  ).toBeVisible();

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
