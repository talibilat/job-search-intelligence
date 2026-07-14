import {
  ApplicationSource,
  ApplicationStatus,
  SponsorshipStatus,
  WorkMode,
  type GetMetricsSummaryMetricsSummaryGetParams,
} from "../api";

export interface DashboardFilters {
  firstSeenFrom: string;
  firstSeenTo: string;
  role: string;
  salaryMax: string;
  salaryMin: string;
  source: string;
  sponsorship: string;
  status: string;
  workMode: string;
}

export const EMPTY_DASHBOARD_FILTERS: DashboardFilters = {
  firstSeenFrom: "",
  firstSeenTo: "",
  role: "",
  salaryMax: "",
  salaryMin: "",
  source: "",
  sponsorship: "",
  status: "",
  workMode: "",
};

export const dashboardFilterOptions = {
  source: Object.values(ApplicationSource),
  sponsorship: Object.values(SponsorshipStatus),
  status: Object.values(ApplicationStatus),
  workMode: Object.values(WorkMode),
};

export function filtersFromSearch(search: string): DashboardFilters {
  const params = new URLSearchParams(search);
  const allowed = (key: keyof typeof dashboardFilterOptions, value: string | null) =>
    value && dashboardFilterOptions[key].includes(value as never) ? value : "";
  const number = (value: string | null) =>
    value !== null && /^\d+$/u.test(value) ? value : "";

  return {
    firstSeenFrom: params.get("first_seen_from") ?? "",
    firstSeenTo: params.get("first_seen_to") ?? "",
    role: params.get("role") ?? "",
    salaryMax: number(params.get("salary_max")),
    salaryMin: number(params.get("salary_min")),
    source: allowed("source", params.get("source")),
    sponsorship: allowed("sponsorship", params.get("sponsorship")),
    status: allowed("status", params.get("status")),
    workMode: allowed("workMode", params.get("work_mode")),
  };
}

export function apiParamsFromFilters(
  filters: DashboardFilters,
): GetMetricsSummaryMetricsSummaryGetParams {
  const text = (value: string) => value.trim() || undefined;
  const date = (value: string, end = false) => value ? `${value}T${end ? "23:59:59.999" : "00:00:00"}Z` : undefined;
  const number = (value: string) => value ? Number(value) : undefined;
  return {
    first_seen_from: date(filters.firstSeenFrom),
    first_seen_to: date(filters.firstSeenTo, true),
    role: text(filters.role),
    salary_max: number(filters.salaryMax),
    salary_min: number(filters.salaryMin),
    source: (filters.source || undefined) as GetMetricsSummaryMetricsSummaryGetParams["source"],
    sponsorship: (filters.sponsorship || undefined) as GetMetricsSummaryMetricsSummaryGetParams["sponsorship"],
    status: (filters.status || undefined) as GetMetricsSummaryMetricsSummaryGetParams["status"],
    work_mode: (filters.workMode || undefined) as GetMetricsSummaryMetricsSummaryGetParams["work_mode"],
  };
}

export function searchFromFilters(filters: DashboardFilters): string {
  const params = new URLSearchParams();
  const values = {
    first_seen_from: filters.firstSeenFrom,
    first_seen_to: filters.firstSeenTo,
    role: filters.role.trim(),
    salary_max: filters.salaryMax,
    salary_min: filters.salaryMin,
    source: filters.source,
    sponsorship: filters.sponsorship,
    status: filters.status,
    work_mode: filters.workMode,
  };
  for (const [key, value] of Object.entries(values)) {
    if (value) params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function titleize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./u, (letter) => letter.toUpperCase());
}
