import { describe, expect, it } from "vitest";
import {
  enumQueryParam,
  parseRouteQuery,
  routeQueryString,
  stringListQueryParam,
  stringQueryParam,
  updateRouteQuery,
} from "./routeQuery";
import {
  pathForRoute,
  redesignRouteFromLocation,
} from "../redesign/RedesignApp";

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

  it("preserves unrelated query params when updating schema values", () => {
    const result = updateRouteQuery(
      "?page=2&status=applied&tab=activity&status=interview&sort=recent",
      {
        statuses: ["rejected"],
      },
      dashboardQuerySchema,
    );

    expect(result).toBe("?page=2&tab=activity&sort=recent&status=rejected");
  });
});

describe("redesign application status query", () => {
  it("parses a valid status filter and falls back to all for invalid values", () => {
    expect(
      redesignRouteFromLocation("/applications", "?status=interview").statusFilter,
    ).toBe("interview");
    expect(
      redesignRouteFromLocation("/applications", "?status=not-real").statusFilter,
    ).toBe("all");
  });

  it("serializes non-default filters and omits all", () => {
    expect(
      pathForRoute({ page: "applications", detailId: null, statusFilter: "offer" }),
    ).toBe("/applications?status=offer");
    expect(
      pathForRoute({ page: "applications", detailId: null, statusFilter: "all" }),
    ).toBe("/applications");
  });

  it("preserves unrelated query parameters while changing status", () => {
    expect(
      pathForRoute(
        { page: "applications", detailId: null, statusFilter: "closed" },
        "?sort=recent&debug=1&status=offer",
      ),
    ).toBe("/applications?sort=recent&debug=1&status=closed");
  });
});
