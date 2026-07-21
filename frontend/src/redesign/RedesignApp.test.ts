import { describe, expect, it } from "vitest";

import type { EmailSyncStatus } from "../api";
import { syncFlowStageForStatus, syncPortionProgressPercent } from "./RedesignApp";

function syncStatus(overrides: Partial<EmailSyncStatus>): EmailSyncStatus {
  return {
    account_id: "me@example.com",
    filtered_candidate_count: 0,
    finished_at: null,
    last_error: null,
    message_count: 0,
    mode: "full_backfill",
    page_count: 0,
    progress: 0,
    provider: "gmail",
    raw_email_count: 0,
    recovered_from_expired_cursor: false,
    retained_body_count: 0,
    retained_body_failure_count: 0,
    stage: "counting",
    started_at: "2026-07-20T12:00:00Z",
    state: "running",
    target_message_count: null,
    ...overrides,
  };
}

describe("RedesignApp sync progress", () => {
  it("completes counting when the backend moves to retrieving", () => {
    const counting = syncStatus({ stage: "counting", target_message_count: null });
    const retrieving = syncStatus({
      stage: "retrieving",
      target_message_count: 25,
    });

    expect(syncFlowStageForStatus(counting)).toBe("syncing");
    expect(syncFlowStageForStatus(retrieving)).toBe("filtering");
  });

  it("maps live backend progress into the sync portion of the bar", () => {
    const status = syncStatus({
      filtered_candidate_count: 7,
      message_count: 10,
      progress: 0.4,
      retained_body_count: 5,
      stage: "retrieving",
      target_message_count: 25,
    });

    expect(syncPortionProgressPercent(status)).toBe(22);
    expect(status.filtered_candidate_count).toBe(7);
    expect(status.retained_body_count).toBe(5);
  });

  it("keeps progress indeterminate until the backend provides a target", () => {
    expect(syncPortionProgressPercent(syncStatus({ stage: "counting" }))).toBeNull();
    expect(
      syncPortionProgressPercent(
        syncStatus({ stage: "retrieving", target_message_count: null }),
      ),
    ).toBeNull();
  });
});
