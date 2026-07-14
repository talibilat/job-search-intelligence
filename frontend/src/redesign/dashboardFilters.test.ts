import { describe, expect, it } from "vitest";

import { apiParamsFromFilters, filtersFromSearch, searchFromFilters } from "./dashboardFilters";

describe("redesign dashboard filters", () => {
  it("composes every supported filter in the route and deterministic API params", () => {
    const search = "?first_seen_from=2026-06-01&first_seen_to=2026-07-14&status=rejected&source=referral&sponsorship=offered&role=platform&salary_min=120000&salary_max=180000&work_mode=remote";
    const filters = filtersFromSearch(search);

    expect(Object.fromEntries(new URLSearchParams(searchFromFilters(filters)))).toEqual(
      Object.fromEntries(new URLSearchParams(search)),
    );
    expect(apiParamsFromFilters(filters)).toEqual({
      first_seen_from: "2026-06-01T00:00:00Z",
      first_seen_to: "2026-07-14T23:59:59.999Z",
      role: "platform",
      salary_max: 180000,
      salary_min: 120000,
      source: "referral",
      sponsorship: "offered",
      status: "rejected",
      work_mode: "remote",
    });
  });

  it("drops unsupported enum and numeric values instead of sending them", () => {
    expect(filtersFromSearch("?status=made_up&salary_min=-2&work_mode=somewhere")).toMatchObject({
      salaryMin: "",
      status: "",
      workMode: "",
    });
  });
});
