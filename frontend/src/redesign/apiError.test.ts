import { describe, expect, it } from "vitest";

import { publicApiError } from "./apiError";

describe("publicApiError", () => {
  it("returns only the standard public API message", () => {
    expect(
      publicApiError(
        {
          response: {
            data: {
              error: {
                code: "busy",
                message: "Sync is already running.",
                details: [],
              },
            },
          },
        },
        "Sync failed.",
      ),
    ).toBe("Sync is already running.");
  });

  it("does not expose arbitrary exception text", () => {
    expect(publicApiError(new Error("token=secret"), "Request failed.")).toBe(
      "Request failed.",
    );
  });

  it("falls back when the standard API message is not a string", () => {
    expect(
      publicApiError(
        {
          response: {
            data: {
              error: {
                code: "busy",
                message: { token: "secret" },
                details: [],
              },
            },
          },
        },
        "Request failed.",
      ),
    ).toBe("Request failed.");
  });
});
