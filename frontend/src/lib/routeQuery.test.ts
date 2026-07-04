import { describe, expect, it } from "vitest";
import {
  enumQueryParam,
  parseRouteQuery,
  routeQueryString,
  stringListQueryParam,
  stringQueryParam,
  updateRouteQuery,
} from "./routeQuery";

const dashboardQuerySchema = {
  statuses: stringListQueryParam("status"),
  role: stringQueryParam("role"),
  workMode: enumQueryParam("work_mode", ["remote", "hybrid", "onsite"] as const),
} as const;

describe("route query helpers", () => {
  it("parses URL query strings into typed filter values", () => {
    const result = parseRouteQuery(
      "?status=applied&status=interview&role=frontend&work_mode=remote",
      dashboardQuerySchema,
    );

    expect(result).toEqual({
      statuses: ["applied", "interview"],
      role: "frontend",
      workMode: "remote",
    });
  });

  it("falls back to defaults for absent or invalid values", () => {
    const result = parseRouteQuery("?work_mode=spaceship", dashboardQuerySchema);

    expect(result).toEqual({
      statuses: [],
      role: "",
      workMode: undefined,
    });
  });

  it("serializes typed filter values with stable ordering and without defaults", () => {
    const result = routeQueryString(
      {
        statuses: ["applied", "interview"],
        role: "frontend engineer",
        workMode: undefined,
      },
      dashboardQuerySchema,
    );

    expect(result).toBe("?status=applied&status=interview&role=frontend+engineer");
  });

  it("updates an existing query string while removing default values", () => {
    const result = updateRouteQuery(
      "?status=applied&role=frontend&work_mode=hybrid",
      {
        statuses: [],
        workMode: "remote",
      },
      dashboardQuerySchema,
    );

    expect(result).toBe("?role=frontend&work_mode=remote");
  });
});
