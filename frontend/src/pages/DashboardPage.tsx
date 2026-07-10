import { useEffect, useState, type FormEvent } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  ApplicationSource,
  ApplicationStatus,
  MetricsBreakdownDimension,
  SponsorshipStatus,
  WorkMode,
  getMetricsBreakdownMetricsBreakdownGet,
  getMetricsDiagnosticsMetricsDiagnosticsGet,
  getMetricsFunnelMetricsFunnelGet,
  getMetricsRatesMetricsRatesGet,
  getMetricsResponseRateTrendMetricsResponseRateTrendGet,
  getMetricsSummaryMetricsSummaryGet,
  getMetricsTimeseriesMetricsTimeseriesGet,
  pipelineStatusPipelineStatusGet,
  type ApiErrorResponse,
  type PipelineStatus,
  type ApplicationSource as ApplicationSourceValue,
  type ApplicationStatus as ApplicationStatusValue,
  type DiagnosticSegmentComparison,
  type GetMetricsSummaryMetricsSummaryGetParams,
  type MetricBreakdownRow,
  type MetricFunnelStage,
  type MetricRate,
  type MetricResponseRateTrendPoint,
  type MetricTimeseriesPoint,
  type MetricsBreakdownDimension as MetricsBreakdownDimensionValue,
  type MetricsDiagnosticsResponse,
  type MetricsSummaryResponse,
  type SilenceAgeBucketMetric,
  type SponsorshipStatus as SponsorshipStatusValue,
  type WorkMode as WorkModeValue,
} from "../api";
import { ChartPanel } from "../components/charts";
import { Alert, Button, FormField, TextInput } from "../components/ui";

type BreakdownLoadState = "loading" | "loaded" | "error";
type DiagnosticsLoadState = "loading" | "loaded" | "error";
type FunnelLoadState = "loading" | "loaded" | "error";
type ResponseRateLoadState = "loading" | "loaded" | "error";
type TimeseriesLoadState = "loading" | "loaded" | "error";

interface DashboardFilters {
  firstSeenFrom: string;
  firstSeenTo: string;
  role: string;
  salaryMax: string;
  salaryMin: string;
  source: ApplicationSourceValue | "";
  sponsorship: SponsorshipStatusValue | "";
  status: ApplicationStatusValue | "";
  workMode: WorkModeValue | "";
}

type DashboardFilterErrors = Partial<
  Record<"firstSeenFrom" | "firstSeenTo" | "salaryMax" | "salaryMin", string>
>;

const emptyFilters: DashboardFilters = {
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

const statusOptions = Object.values(ApplicationStatus);
const sourceOptions = Object.values(ApplicationSource);
const sponsorshipOptions = Object.values(SponsorshipStatus);
const workModeOptions = Object.values(WorkMode);
const breakdownDimensionOptions = Object.values(MetricsBreakdownDimension);
const numberFormatter = new Intl.NumberFormat("en-US");
function titleize(value: string) {
  return value
    .split("_")
    .map((part, index) =>
      index === 0 ? `${part.charAt(0).toUpperCase()}${part.slice(1)}` : part,
    )
    .join(" ");
}

function filterValue<TValue extends string>(
  params: URLSearchParams,
  key: string,
  allowedValues: readonly TValue[],
) {
  const value = params.get(key);
  return value && allowedValues.includes(value as TValue)
    ? (value as TValue)
    : "";
}

function numericFilterText(value: string | null) {
  const trimmed = value?.trim() ?? "";
  if (trimmed.length === 0) {
    return "";
  }

  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? trimmed : "";
}

function validateSalaryFilter(value: string, label: string) {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }

  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0
    ? null
    : `${label} must be a non-negative number.`;
}

function validateDashboardFilters(filters: DashboardFilters) {
  const errors: DashboardFilterErrors = {};
  const firstSeenFrom = Date.parse(filters.firstSeenFrom.trim());
  const firstSeenTo = Date.parse(filters.firstSeenTo.trim());
  const salaryMinError = validateSalaryFilter(filters.salaryMin, "Salary min");
  const salaryMaxError = validateSalaryFilter(filters.salaryMax, "Salary max");
  const salaryMin = Number(filters.salaryMin.trim());
  const salaryMax = Number(filters.salaryMax.trim());

  if (
    filters.firstSeenFrom.trim().length > 0 &&
    filters.firstSeenTo.trim().length > 0 &&
    Number.isFinite(firstSeenFrom) &&
    Number.isFinite(firstSeenTo) &&
    firstSeenFrom > firstSeenTo
  ) {
    errors.firstSeenFrom =
      "First seen from must be less than or equal to first seen to.";
  }
  if (salaryMinError) {
    errors.salaryMin = salaryMinError;
  }
  if (salaryMaxError) {
    errors.salaryMax = salaryMaxError;
  }
  if (
    !salaryMinError &&
    !salaryMaxError &&
    filters.salaryMin.trim().length > 0 &&
    filters.salaryMax.trim().length > 0 &&
    salaryMin > salaryMax
  ) {
    errors.salaryMin = "Salary min must be less than or equal to salary max.";
  }

  return errors;
}

function filtersFromSearch(search: string): DashboardFilters {
  const params = new URLSearchParams(search);

  return {
    firstSeenFrom: params.get("first_seen_from") ?? "",
    firstSeenTo: params.get("first_seen_to") ?? "",
    role: params.get("role") ?? "",
    salaryMax: numericFilterText(params.get("salary_max")),
    salaryMin: numericFilterText(params.get("salary_min")),
    source: filterValue(params, "source", sourceOptions),
    sponsorship: filterValue(params, "sponsorship", sponsorshipOptions),
    status: filterValue(params, "status", statusOptions),
    workMode: filterValue(params, "work_mode", workModeOptions),
  };
}

function canonicalFilters(filters: DashboardFilters): DashboardFilters {
  return {
    ...filters,
    salaryMax: numericFilterText(filters.salaryMax),
    salaryMin: numericFilterText(filters.salaryMin),
  };
}

function optionalText(value: string) {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function optionalNumber(value: string) {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return undefined;
  }

  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function queryParamsFromFilters(
  filters: DashboardFilters,
): GetMetricsSummaryMetricsSummaryGetParams {
  return {
    first_seen_from: optionalText(filters.firstSeenFrom),
    first_seen_to: optionalText(filters.firstSeenTo),
    role: optionalText(filters.role),
    salary_max: optionalNumber(filters.salaryMax),
    salary_min: optionalNumber(filters.salaryMin),
    source: filters.source || undefined,
    sponsorship: filters.sponsorship || undefined,
    status: filters.status || undefined,
    work_mode: filters.workMode || undefined,
  };
}

function queryStringFromFilters(filters: DashboardFilters) {
  const params = new URLSearchParams();
  const apiParams = queryParamsFromFilters(filters);

  for (const [key, value] of Object.entries(apiParams)) {
    if (value !== undefined) {
      params.set(key, String(value));
    }
  }

  const query = params.toString();
  return query.length > 0 ? `?${query}` : "";
}

function replaceUrlWithFilters(filters: DashboardFilters) {
  const nextPath = `${window.location.pathname}${queryStringFromFilters(filters)}`;
  const currentPath = `${window.location.pathname}${window.location.search}`;
  if (nextPath !== currentPath) {
    window.history.replaceState({}, "", nextPath);
  }
}

function publicError(data: unknown, fallback: string) {
  if (
    typeof data === "object" &&
    data !== null &&
    "error" in data &&
    typeof (data as ApiErrorResponse).error?.message === "string"
  ) {
    return (data as ApiErrorResponse).error.message;
  }

  return fallback;
}

function silenceBucketLabel(bucket: SilenceAgeBucketMetric) {
  if (bucket.max_days === null || bucket.max_days === undefined) {
    return `${numberFormatter.format(bucket.min_days)}+ days`;
  }
  return `${numberFormatter.format(bucket.min_days)} to ${numberFormatter.format(
    bucket.max_days,
  )} days`;
}

function formatTrendDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  }).format(new Date(value));
}

function sortedBreakdownRows(rows: MetricBreakdownRow[]) {
  return [...rows].sort((left, right) => {
    const applicationOrder = right.application_count - left.application_count;
    if (applicationOrder !== 0) {
      return applicationOrder;
    }
    return left.value.localeCompare(right.value);
  });
}

function interviewConversionRate(row: MetricBreakdownRow) {
  if (row.application_count === 0) {
    return null;
  }
  return row.interview_count / row.application_count;
}

function sortedRoleConversionRows(rows: MetricBreakdownRow[]) {
  return [...rows].sort((left, right) => {
    const rateOrder =
      (interviewConversionRate(right) ?? -1) - (interviewConversionRate(left) ?? -1);
    if (rateOrder !== 0) {
      return rateOrder;
    }
    const interviewOrder = right.interview_count - left.interview_count;
    if (interviewOrder !== 0) {
      return interviewOrder;
    }
    return right.application_count - left.application_count;
  });
}

function sortedTimeseriesPoints(points: MetricTimeseriesPoint[]) {
  return [...points].sort((left, right) =>
    left.period_start.localeCompare(right.period_start),
  );
}

const funnelStageOrder = ["applied", "screen", "interview", "final", "offer"] as const;

function sortedFunnelStages(stages: MetricFunnelStage[]) {
  return [...stages].sort(
    (left, right) =>
      funnelStageOrder.indexOf(left.stage) - funnelStageOrder.indexOf(right.stage),
  );
}

function diagnosticSegmentTitle(segment: DiagnosticSegmentComparison) {
  return `${titleize(segment.value)} (${titleize(segment.dimension)})`;
}

export function DashboardPage() {
  const [summary, setSummary] = useState<MetricsSummaryResponse | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(true);
  const [responseRate, setResponseRate] = useState<MetricRate | null>(null);
  const [rejectionRate, setRejectionRate] = useState<MetricRate | null>(null);
  const [ghostRate, setGhostRate] = useState<MetricRate | null>(null);
  const [applicationToInterviewRate, setApplicationToInterviewRate] =
    useState<MetricRate | null>(null);
  const [interviewToOfferRate, setInterviewToOfferRate] =
    useState<MetricRate | null>(null);
  const [responseRateLoadState, setResponseRateLoadState] =
    useState<ResponseRateLoadState>("loading");
  const [funnelStages, setFunnelStages] = useState<MetricFunnelStage[]>([]);
  const [funnelLoadState, setFunnelLoadState] =
    useState<FunnelLoadState>("loading");
  const [funnelError, setFunnelError] = useState<string | null>(null);
  const [breakdownDimension, setBreakdownDimension] =
    useState<MetricsBreakdownDimensionValue>(MetricsBreakdownDimension.source);
  const [breakdownRows, setBreakdownRows] = useState<MetricBreakdownRow[]>([]);
  const [breakdownLoadState, setBreakdownLoadState] =
    useState<BreakdownLoadState>("loading");
  const [breakdownError, setBreakdownError] = useState<string | null>(null);
  const [roleConversionRows, setRoleConversionRows] = useState<MetricBreakdownRow[]>([]);
  const [roleConversionLoadState, setRoleConversionLoadState] =
    useState<BreakdownLoadState>("loading");
  const [roleConversionError, setRoleConversionError] = useState<string | null>(null);
  const [companyTypeRows, setCompanyTypeRows] = useState<MetricBreakdownRow[]>([]);
  const [companyTypeLoadState, setCompanyTypeLoadState] =
    useState<BreakdownLoadState>("loading");
  const [companyTypeError, setCompanyTypeError] = useState<string | null>(null);
  const [timeseriesPoints, setTimeseriesPoints] = useState<
    MetricTimeseriesPoint[]
  >([]);
  const [timeseriesLoadState, setTimeseriesLoadState] =
    useState<TimeseriesLoadState>("loading");
  const [timeseriesError, setTimeseriesError] = useState<string | null>(null);
  const [responseRateTrendPoints, setResponseRateTrendPoints] = useState<
    MetricResponseRateTrendPoint[]
  >([]);
  const [responseRateTrendLoadState, setResponseRateTrendLoadState] =
    useState<TimeseriesLoadState>("loading");
  const [responseRateTrendError, setResponseRateTrendError] = useState<
    string | null
  >(null);
  const [diagnostics, setDiagnostics] = useState<MetricsDiagnosticsResponse | null>(
    null,
  );
  const [diagnosticsLoadState, setDiagnosticsLoadState] =
    useState<DiagnosticsLoadState>("loading");
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);
  const [filters, setFilters] = useState<DashboardFilters>(() =>
    filtersFromSearch(window.location.search),
  );
  const [appliedFilters, setAppliedFilters] =
    useState<DashboardFilters>(filters);
  const [filterErrors, setFilterErrors] = useState<DashboardFilterErrors>({});
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(
    null,
  );

  useEffect(() => {
    let ignore = false;

    async function loadPipelineStatus() {
      try {
        const response = await pipelineStatusPipelineStatusGet();
        if (response.status === 200 && !ignore) {
          setPipelineStatus(response.data);
        }
      } catch {
        if (!ignore) {
          setPipelineStatus(null);
        }
      }
    }

    void loadPipelineStatus();

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    let ignore = false;

    async function loadSummary() {
      setIsLoadingSummary(true);
      try {
        const response = await getMetricsSummaryMetricsSummaryGet(
          queryParamsFromFilters(appliedFilters),
        );
        if (response.status === 200 && !ignore) {
          setSummary(response.data);
        }
      } catch {
        if (!ignore) {
          setSummary(null);
        }
      } finally {
        if (!ignore) {
          setIsLoadingSummary(false);
        }
      }
    }

    void loadSummary();

    return () => {
      ignore = true;
    };
  }, [appliedFilters]);

  useEffect(() => {
    let isCancelled = false;

    async function loadCompanyTypes() {
      setCompanyTypeLoadState("loading");
      setCompanyTypeError(null);
      setCompanyTypeRows([]);

      const response = await getMetricsBreakdownMetricsBreakdownGet({
        dimension: MetricsBreakdownDimension.company_type,
        ...queryParamsFromFilters(appliedFilters),
      });

      if (isCancelled) {
        return;
      }

      if (response.status !== 200) {
        setCompanyTypeRows([]);
        setCompanyTypeError(
          publicError(response.data, "Company type outcomes are unavailable."),
        );
        setCompanyTypeLoadState("error");
        return;
      }

      setCompanyTypeRows(sortedBreakdownRows(response.data.rows));
      setCompanyTypeLoadState("loaded");
    }

    void loadCompanyTypes().catch(() => {
      if (!isCancelled) {
        setCompanyTypeRows([]);
        setCompanyTypeError(
          "Company type outcomes are unavailable. Start the local backend to load Q-24.",
        );
        setCompanyTypeLoadState("error");
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [appliedFilters]);

  useEffect(() => {
    let isCancelled = false;

    async function loadResponseRateTrend() {
      setResponseRateTrendLoadState("loading");
      setResponseRateTrendError(null);
      setResponseRateTrendPoints([]);

      const response = await getMetricsResponseRateTrendMetricsResponseRateTrendGet(
        queryParamsFromFilters(appliedFilters),
      );

      if (isCancelled) {
        return;
      }

      if (response.status !== 200) {
        setResponseRateTrendPoints([]);
        setResponseRateTrendError(
          publicError(response.data, "Response rate trend is unavailable."),
        );
        setResponseRateTrendLoadState("error");
        return;
      }

      setResponseRateTrendPoints(
        [...response.data.points].sort((left, right) =>
          left.period_start.localeCompare(right.period_start),
        ),
      );
      setResponseRateTrendLoadState("loaded");
    }

    void loadResponseRateTrend().catch(() => {
      if (!isCancelled) {
        setResponseRateTrendPoints([]);
        setResponseRateTrendError(
          "Response rate trend is unavailable. Start the local backend to load Q-21.",
        );
        setResponseRateTrendLoadState("error");
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [appliedFilters]);

  useEffect(() => {
    replaceUrlWithFilters(appliedFilters);

    function handlePopState() {
      const nextFilters = filtersFromSearch(window.location.search);
      replaceUrlWithFilters(nextFilters);
      setFilters(nextFilters);
      setAppliedFilters(nextFilters);
    }

    window.addEventListener("popstate", handlePopState);
    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, [appliedFilters]);

  useEffect(() => {
    let isCancelled = false;

    async function loadFunnel() {
      setFunnelLoadState("loading");
      setFunnelError(null);
      setFunnelStages([]);

      const response = await getMetricsFunnelMetricsFunnelGet(
        queryParamsFromFilters(appliedFilters),
      );

      if (isCancelled) {
        return;
      }

      if (response.status !== 200) {
        setFunnelStages([]);
        setFunnelError(publicError(response.data, "Application funnel is unavailable."));
        setFunnelLoadState("error");
        return;
      }

      setFunnelStages(sortedFunnelStages(response.data.stages));
      setFunnelLoadState("loaded");
    }

    void loadFunnel().catch(() => {
      if (!isCancelled) {
        setFunnelStages([]);
        setFunnelError(
          "Application funnel is unavailable. Start the local backend to load Q-16.",
        );
        setFunnelLoadState("error");
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [appliedFilters]);

  useEffect(() => {
    let isCancelled = false;

    async function loadBreakdown() {
      setBreakdownLoadState("loading");
      setBreakdownError(null);
      setBreakdownRows([]);

      const response = await getMetricsBreakdownMetricsBreakdownGet({
        dimension: breakdownDimension,
        ...queryParamsFromFilters(appliedFilters),
      });

      if (isCancelled) {
        return;
      }

      if (response.status !== 200) {
        setBreakdownRows([]);
        setBreakdownError(
          publicError(response.data, "Metric breakdowns are unavailable."),
        );
        setBreakdownLoadState("error");
        return;
      }

      setBreakdownRows(sortedBreakdownRows(response.data.rows));
      setBreakdownLoadState("loaded");
    }

    void loadBreakdown().catch(() => {
      if (!isCancelled) {
        setBreakdownRows([]);
        setBreakdownError(
          "Metric breakdowns are unavailable. Start the local backend to load segmentation metrics.",
        );
        setBreakdownLoadState("error");
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [appliedFilters, breakdownDimension]);

  useEffect(() => {
    let isCancelled = false;

    async function loadRoleConversion() {
      setRoleConversionLoadState("loading");
      setRoleConversionError(null);
      setRoleConversionRows([]);

      const response = await getMetricsBreakdownMetricsBreakdownGet({
        dimension: MetricsBreakdownDimension.role,
        ...queryParamsFromFilters(appliedFilters),
      });

      if (isCancelled) {
        return;
      }

      if (response.status !== 200) {
        setRoleConversionRows([]);
        setRoleConversionError(
          publicError(response.data, "Role conversion metrics are unavailable."),
        );
        setRoleConversionLoadState("error");
        return;
      }

      setRoleConversionRows(sortedRoleConversionRows(response.data.rows));
      setRoleConversionLoadState("loaded");
    }

    void loadRoleConversion().catch(() => {
      if (!isCancelled) {
        setRoleConversionRows([]);
        setRoleConversionError(
          "Role conversion metrics are unavailable. Start the local backend to load Q-23.",
        );
        setRoleConversionLoadState("error");
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [appliedFilters]);

  useEffect(() => {
    let isCancelled = false;

    async function loadTimeseries() {
      setTimeseriesLoadState("loading");
      setTimeseriesError(null);
      setTimeseriesPoints([]);

      const response = await getMetricsTimeseriesMetricsTimeseriesGet(
        queryParamsFromFilters(appliedFilters),
      );

      if (isCancelled) {
        return;
      }

      if (response.status !== 200) {
        setTimeseriesPoints([]);
        setTimeseriesError(
          publicError(response.data, "Application volume trend is unavailable."),
        );
        setTimeseriesLoadState("error");
        return;
      }

      setTimeseriesPoints(sortedTimeseriesPoints(response.data.points));
      setTimeseriesLoadState("loaded");
    }

    void loadTimeseries().catch(() => {
      if (!isCancelled) {
        setTimeseriesPoints([]);
        setTimeseriesError(
          "Application volume trend is unavailable. Start the local backend to load Q-20.",
        );
        setTimeseriesLoadState("error");
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [appliedFilters]);

  useEffect(() => {
    let isCancelled = false;

    async function loadDiagnostics() {
      setDiagnosticsLoadState("loading");
      setDiagnosticsError(null);
      setDiagnostics(null);

      const response = await getMetricsDiagnosticsMetricsDiagnosticsGet(
        queryParamsFromFilters(appliedFilters),
      );

      if (isCancelled) {
        return;
      }

      if (response.status !== 200) {
        setDiagnostics(null);
        setDiagnosticsError(
          publicError(response.data, "Diagnostic comparisons are unavailable."),
        );
        setDiagnosticsLoadState("error");
        return;
      }

      setDiagnostics(response.data);
      setDiagnosticsLoadState("loaded");
    }

    void loadDiagnostics().catch(() => {
      if (!isCancelled) {
        setDiagnostics(null);
        setDiagnosticsError(
          "Diagnostic comparisons are unavailable. Start the local backend to load Tier 4 diagnostics.",
        );
        setDiagnosticsLoadState("error");
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [appliedFilters]);

  useEffect(() => {
    let isCancelled = false;

    async function loadResponseRate() {
      try {
        const response = await getMetricsRatesMetricsRatesGet(
          queryParamsFromFilters(appliedFilters),
        );
        if (!isCancelled) {
          if (response.status !== 200) {
            setResponseRateLoadState("error");
            return;
          }

          setResponseRate(response.data.overall_response_rate);
          setRejectionRate(response.data.rejection_rate);
          setGhostRate(response.data.ghost_rate);
          setApplicationToInterviewRate(response.data.application_to_interview_rate);
          setInterviewToOfferRate(response.data.interview_to_offer_rate);
          setResponseRateLoadState("loaded");
        }
      } catch {
        if (!isCancelled) {
          setResponseRateLoadState("error");
        }
      }
    }

    void loadResponseRate();

    return () => {
      isCancelled = true;
    };
  }, [appliedFilters]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationErrors = validateDashboardFilters(filters);
    setFilterErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    const nextFilters = canonicalFilters(filters);
    const nextQuery = queryStringFromFilters(nextFilters);
    window.history.pushState({}, "", `${window.location.pathname}${nextQuery}`);
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
  }

  function clearFilters() {
    window.history.pushState({}, "", window.location.pathname);
    setFilterErrors({});
    setFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
  }

  const foundationalCountRows = summary
    ? [
        { count: summary.total_applications ?? 0, metric: "Applications" },
        { count: summary.distinct_company_count ?? 0, metric: "Companies" },
        { count: summary.interview_invitation_count ?? 0, metric: "Interviews" },
        { count: summary.offers_received ?? 0, metric: "Offers" },
        { count: summary.rejected_applications ?? 0, metric: "Rejections" },
        { count: summary.ghosted_applications ?? 0, metric: "Ghosts" },
      ]
    : [];
  const outcomeRateRows =
    responseRateLoadState === "loaded"
      ? [
          { metric: "Response", rate: responseRate?.rate },
          { metric: "Rejection", rate: rejectionRate?.rate },
          { metric: "Ghost", rate: ghostRate?.rate },
          { metric: "Application to interview", rate: applicationToInterviewRate?.rate },
          { metric: "Interview to offer", rate: interviewToOfferRate?.rate },
        ]
          .filter((row) => row.rate !== null && row.rate !== undefined)
          .map((row) => ({ ...row, rate: Number(row.rate) * 100 }))
      : [];
  const responseTimingRows = summary
    ? [
        {
          hours: summary.average_time_to_first_response?.average_hours,
          metric: "First response",
        },
        {
          hours: summary.average_time_to_rejection?.average_hours,
          metric: "Rejection",
        },
      ]
        .filter((row) => row.hours !== null && row.hours !== undefined)
        .map((row) => ({ ...row, hours: Number(row.hours) }))
    : [];
  const silenceAgeBuckets =
    summary?.personal_ghost_threshold?.silence_age_distribution ?? [];
  const strongestResponseCorrelate = diagnostics?.strongest_response_correlate;
  const bestRoiSource = diagnostics?.best_roi_source;
  const sponsorshipImpact = diagnostics?.sponsorship_response_impact;
  const sellingSkill = diagnostics?.selling_skill_segments[0];
  const deadWeightSkill = diagnostics?.dead_weight_skill_segments[0];
  const diagnosticBaselineRows =
    diagnosticsLoadState === "loaded" &&
    !diagnosticsError &&
    diagnostics?.baseline_response_rate !== null &&
    diagnostics?.baseline_response_rate !== undefined
      ? [
          {
            metric: "Baseline response",
            rate: diagnostics.baseline_response_rate * 100,
          },
        ]
      : [];
  const strongestResponseCorrelateRows =
    diagnosticsLoadState === "loaded" && !diagnosticsError && strongestResponseCorrelate
      ? [
          {
            lift: Number(strongestResponseCorrelate.response_rate_lift ?? 0) * 100,
            segment: "Strongest correlate",
          },
        ]
      : [];
  const strongestResponseSignalRows =
    diagnosticsLoadState === "loaded" && !diagnosticsError
      ? (diagnostics?.strongest_response_segments ?? []).map((segment) => ({
          lift: Number(segment.response_rate_lift ?? 0) * 100,
          segment: diagnosticSegmentTitle(segment),
        }))
      : [];
  const weakestResponseSignalRows =
    diagnosticsLoadState === "loaded" && !diagnosticsError
      ? (diagnostics?.weakest_response_segments ?? []).map((segment) => ({
          lift: Number(segment.response_rate_lift ?? 0) * 100,
          segment: diagnosticSegmentTitle(segment),
        }))
      : [];
  const successfulApplicationTraitRows =
    diagnosticsLoadState === "loaded" && !diagnosticsError
      ? (diagnostics?.successful_application_segments ?? []).map((segment) => ({
          lift: Number(segment.success_rate_lift ?? 0) * 100,
          segment: diagnosticSegmentTitle(segment),
        }))
      : [];
  const rejectedOrGhostedTraitRows =
    diagnosticsLoadState === "loaded" && !diagnosticsError
      ? (diagnostics?.negative_outcome_segments ?? []).map((segment) => ({
          lift: Number(segment.negative_rate_lift ?? 0) * 100,
          segment: diagnosticSegmentTitle(segment),
        }))
      : [];
  const wastedEffortRows =
    diagnosticsLoadState === "loaded" && !diagnosticsError
      ? (diagnostics?.wasted_effort_segments ?? []).map((segment) => ({
          lift: Number(segment.response_rate_lift ?? 0) * 100,
          segment: titleize(segment.dimension),
        }))
      : [];
  const bestRoiSourceRows =
    diagnosticsLoadState === "loaded" && !diagnosticsError && bestRoiSource
      ? [
          {
            rate: Number(bestRoiSource.interview_rate ?? 0) * 100,
            source: "Best ROI source",
          },
        ]
      : [];
  const sponsorshipImpactRows =
    diagnosticsLoadState === "loaded" && !diagnosticsError && sponsorshipImpact
      ? [
          {
            lift: Number(sponsorshipImpact.response_rate_lift ?? 0) * 100,
            segment: "Sponsorship impact",
          },
        ]
      : [];
  const skillSignalRows =
    diagnosticsLoadState === "loaded" && !diagnosticsError
      ? [
          ...(sellingSkill
            ? [
                {
                  rate: Number(sellingSkill.interview_rate ?? 0) * 100,
                  segment: "Selling skill",
                },
              ]
            : []),
          ...(deadWeightSkill
            ? [
                {
                  rate: Number(deadWeightSkill.interview_rate ?? 0) * 100,
                  segment: "Dead-weight skill",
                },
              ]
            : []),
        ]
      : [];
  const adjacentRoleRows =
    diagnosticsLoadState === "loaded" && !diagnosticsError
      ? (diagnostics?.adjacent_role_suggestions ?? []).map((segment) => ({
          rate: Number(segment.interview_rate ?? 0) * 100,
          role: titleize(segment.value),
        }))
      : [];

  return (
    <main
      aria-labelledby="dashboard-page-title"
      className="app-shell dashboard-shell"
    >
      <section
        className="dashboard-hero"
        aria-labelledby="dashboard-page-title"
      >
        <p className="eyebrow">Phase 3 deterministic dashboard</p>
        <h1 id="dashboard-page-title">Dashboard</h1>
        <p className="hero-copy">
          Q-01, Q-03, Q-07, Q-08, Q-11, Q-12, Q-13, Q-14, and
          Q-15, Q-16, Q-17, Q-18, Q-19, Q-20, Q-21, and Tier 3 breakdowns now render from deterministic application and metrics
          endpoints, while remaining dashboard questions stay clearly marked as
          pending.
        </p>
      </section>

      {!isLoadingSummary &&
      summary?.total_applications === 0 &&
      pipelineStatus ? (
        pipelineStatus.next_action === "review_dashboard" ? (
          <Alert title="Zero applications is a real zero" tone="info">
            <p>{pipelineStatus.next_action_reason}</p>
          </Alert>
        ) : (
          <Alert
            title="These zeros mean the pipeline has not finished, not that you applied to zero jobs"
            tone="warning"
          >
            <p>{pipelineStatus.next_action_reason}</p>
            <p>
              {pipelineStatus.counts.raw_email_count > 0
                ? `${new Intl.NumberFormat("en-US").format(pipelineStatus.counts.raw_email_count)} synced emails are waiting on the ${
                    pipelineStatus.next_action === "run_classification"
                      ? "classification"
                      : "sync"
                  } step. `
                : ""}
              Go to <a href="/features">Feature Status</a> to run the next step.
            </p>
          </Alert>
        )
      ) : null}

      <div className="dashboard-layout">
        <section
          aria-labelledby="dashboard-filters-title"
          className="dashboard-filter-panel"
        >
          <div>
            <p className="eyebrow">Route-backed controls</p>
            <h2 id="dashboard-filters-title">Dashboard filters</h2>
          </div>
          <p>
            Filter state lives in the URL query string and is passed directly to
            the deterministic applications API.
          </p>
          <form className="dashboard-filter-form" onSubmit={handleSubmit}>
            <div className="dashboard-filter-grid">
              <FormField htmlFor="dashboard-status" label="Status">
                <select
                  className="ui-input"
                  id="dashboard-status"
                  onChange={(event) =>
                    setFilters({
                      ...filters,
                      status: event.target.value as ApplicationStatusValue | "",
                    })
                  }
                  value={filters.status}
                >
                  <option value="">All statuses</option>
                  {statusOptions.map((status) => (
                    <option key={status} value={status}>
                      {titleize(status)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField htmlFor="dashboard-role" label="Role">
                <TextInput
                  id="dashboard-role"
                  onChange={(event) =>
                    setFilters({ ...filters, role: event.target.value })
                  }
                  placeholder="Backend"
                  value={filters.role}
                />
              </FormField>
              <FormField htmlFor="dashboard-source" label="Source">
                <select
                  className="ui-input"
                  id="dashboard-source"
                  onChange={(event) =>
                    setFilters({
                      ...filters,
                      source: event.target.value as ApplicationSourceValue | "",
                    })
                  }
                  value={filters.source}
                >
                  <option value="">All sources</option>
                  {sourceOptions.map((source) => (
                    <option key={source} value={source}>
                      {titleize(source)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField htmlFor="dashboard-sponsorship" label="Sponsorship">
                <select
                  className="ui-input"
                  id="dashboard-sponsorship"
                  onChange={(event) =>
                    setFilters({
                      ...filters,
                      sponsorship: event.target.value as
                        SponsorshipStatusValue | "",
                    })
                  }
                  value={filters.sponsorship}
                >
                  <option value="">All sponsorship</option>
                  {sponsorshipOptions.map((sponsorship) => (
                    <option key={sponsorship} value={sponsorship}>
                      {titleize(sponsorship)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField htmlFor="dashboard-work-mode" label="Work mode">
                <select
                  className="ui-input"
                  id="dashboard-work-mode"
                  onChange={(event) =>
                    setFilters({
                      ...filters,
                      workMode: event.target.value as WorkModeValue | "",
                    })
                  }
                  value={filters.workMode}
                >
                  <option value="">All work modes</option>
                  {workModeOptions.map((workMode) => (
                    <option key={workMode} value={workMode}>
                      {titleize(workMode)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField
                error={filterErrors.firstSeenFrom}
                htmlFor="dashboard-first-seen-from"
                label="First seen from"
              >
                <TextInput
                  id="dashboard-first-seen-from"
                  onChange={(event) => {
                    setFilters({
                      ...filters,
                      firstSeenFrom: event.target.value,
                    });
                    setFilterErrors((currentErrors) => ({
                      ...currentErrors,
                      firstSeenFrom: undefined,
                    }));
                  }}
                  placeholder="2026-07-01T00:00:00Z"
                  value={filters.firstSeenFrom}
                />
              </FormField>
              <FormField
                error={filterErrors.firstSeenTo}
                htmlFor="dashboard-first-seen-to"
                label="First seen to"
              >
                <TextInput
                  id="dashboard-first-seen-to"
                  onChange={(event) => {
                    setFilters({ ...filters, firstSeenTo: event.target.value });
                    setFilterErrors((currentErrors) => ({
                      ...currentErrors,
                      firstSeenTo: undefined,
                    }));
                  }}
                  placeholder="2026-07-31T23:59:59Z"
                  value={filters.firstSeenTo}
                />
              </FormField>
              <FormField
                error={filterErrors.salaryMin}
                htmlFor="dashboard-salary-min"
                label="Salary min"
              >
                <TextInput
                  id="dashboard-salary-min"
                  inputMode="numeric"
                  onChange={(event) => {
                    setFilters({ ...filters, salaryMin: event.target.value });
                    setFilterErrors((currentErrors) => ({
                      ...currentErrors,
                      salaryMin: undefined,
                    }));
                  }}
                  placeholder="120000"
                  value={filters.salaryMin}
                />
              </FormField>
              <FormField
                error={filterErrors.salaryMax}
                htmlFor="dashboard-salary-max"
                label="Salary max"
              >
                <TextInput
                  id="dashboard-salary-max"
                  inputMode="numeric"
                  onChange={(event) => {
                    setFilters({ ...filters, salaryMax: event.target.value });
                    setFilterErrors((currentErrors) => ({
                      ...currentErrors,
                      salaryMax: undefined,
                    }));
                  }}
                  placeholder="180000"
                  value={filters.salaryMax}
                />
              </FormField>
            </div>
            <div className="dashboard-filter-actions">
              <Button type="submit">Apply filters</Button>
              <Button onClick={clearFilters} type="button" variant="secondary">
                Clear filters
              </Button>
            </div>
          </form>
        </section>

        <div className="dashboard-chart-stack">
          <ChartPanel
            description="Q-01, Q-03, Q-05, Q-06, Q-07, and Q-08 counts come from deterministic /metrics/summary fields over local applications and application_events."
            emptyState={{
              title: isLoadingSummary ? "Loading foundational counts" : "No count data yet",
              description: isLoadingSummary
                ? "Loading deterministic summary counts from the local backend."
                : "No summary counts are available yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={260}
            info={{
              dataSource: "GET /metrics/summary",
              dataTable: "applications",
              howItWorks:
                "Counts reconstructed applications and outcome events deterministically from local SQLite. No LLM produces these values.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application records.",
              missingData:
                "If values are zero or missing, inspect Feature Status for the next missing pipeline stage: Gmail connection, sync, classification, or aggregation.",
            }}
            title="Foundational counts"
          >
            {foundationalCountRows.length > 0 ? (
              <BarChart
                data={foundationalCountRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="metric" stroke="#c9d8ce" />
                <YAxis allowDecimals={false} stroke="#c9d8ce" />
                <Tooltip />
                <Bar dataKey="count" fill="#b8e2af" name="Count" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Q-11 through Q-15 rates come from deterministic /metrics/rates numerators and denominators over local applications and application_events."
            emptyState={{
              title:
                responseRateLoadState === "loading"
                  ? "Loading outcome rates"
                  : "No rate data yet",
              description:
                responseRateLoadState === "loading"
                  ? "Loading deterministic rate metrics from the local backend."
                  : "No rate denominators are available yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={260}
            info={{
              dataSource: "GET /metrics/rates",
              dataTable: "applications and application_events",
              howItWorks:
                "Calculates response, rejection, ghost, interview, and offer rates from deterministic numerators and denominators in local SQLite. No LLM produces these rates.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so application timelines have the events needed for each rate denominator.",
              missingData:
                "If rates are zero or missing, check whether applications have response, rejection, interview, or offer events after classification and aggregation.",
            }}
            title="Outcome rates"
          >
            {outcomeRateRows.length > 0 ? (
              <BarChart
                data={outcomeRateRows}
                layout="vertical"
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid horizontal={false} stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis allowDecimals={false} stroke="#c9d8ce" type="number" unit="%" />
                <YAxis
                  dataKey="metric"
                  stroke="#c9d8ce"
                  tick={{ fontSize: 12 }}
                  type="category"
                  width={132}
                />
                <Tooltip />
                <Bar dataKey="rate" fill="#b8e2af" name="Rate" radius={[0, 8, 8, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Q-17 and Q-18 response timing comes from deterministic /metrics/summary average_time_to_first_response and average_time_to_rejection fields."
            emptyState={{
              title: isLoadingSummary ? "Loading response timing" : "No timing data yet",
              description: isLoadingSummary
                ? "Loading deterministic timing metrics from the local backend."
                : "No applications have response or rejection timing evidence yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={260}
            info={{
              dataSource: "GET /metrics/summary",
              dataTable: "applications and application_events",
              howItWorks:
                "Calculates average hours from application timestamps to first response and rejection events using deterministic local timeline data. No LLM produces these timing values.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so application timelines include applied, response, and rejection events with timestamps.",
              missingData:
                "If timing values are zero or missing, check whether application timelines contain response or rejection events with timestamps after aggregation.",
            }}
            title="Response timing"
          >
            {responseTimingRows.length > 0 ? (
              <BarChart
                data={responseTimingRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="metric" stroke="#c9d8ce" />
                <YAxis allowDecimals={false} stroke="#c9d8ce" unit="h" />
                <Tooltip />
                <Bar dataKey="hours" fill="#b8e2af" name="Hours" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>
        </div>
      </div>

      <ChartPanel
        description="Q-19 silence-age buckets come from deterministic /metrics/summary personal_ghost_threshold data over local application timelines, then reload with the active dashboard filters."
        emptyState={{
          title: isLoadingSummary
            ? "Loading personal ghost threshold"
            : "No silence-age buckets yet",
          description: isLoadingSummary
            ? "Loading deterministic ghost-threshold distribution from the local backend."
            : "No applications have enough timeline history for a personal ghost-threshold distribution yet. Run sync, classification, and aggregation from Feature Status first.",
        }}
        height={300}
        info={{
          dataSource: "GET /metrics/summary",
          dataTable: "applications and application_events",
          howItWorks:
            "Buckets applications by silence age from deterministic local application timelines to show when unanswered applications typically become ghosted. No LLM produces these values.",
          howToGenerate:
            "Run sync, classification, and aggregation from Feature Status so application timelines include applied events, response events, and ghost inference evidence.",
          missingData:
            "If silence-age buckets are zero or missing, check whether applications have applied events, later response events, and enough elapsed time for ghost inference after aggregation.",
        }}
        title="Personal ghost threshold"
      >
        {silenceAgeBuckets.length > 0 ? (
          <BarChart
            data={silenceAgeBuckets.map((bucket) => ({
              applications: bucket.application_count,
              bucket: silenceBucketLabel(bucket),
            }))}
          >
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="bucket" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="applications" fill="var(--color-accent)" name="Applications" />
          </BarChart>
        ) : undefined}
      </ChartPanel>

      {funnelError ? (
        <Alert title="Application funnel unavailable" tone="danger">
          <p>{funnelError}</p>
        </Alert>
      ) : null}
      <ChartPanel
        description="Q-16 funnel stages come from deterministic /metrics/funnel rows over local applications and application_events, then reload with the active dashboard filters."
        emptyState={{
          title:
            funnelLoadState === "loading"
              ? "Loading application funnel"
              : "No funnel rows yet",
          description:
            funnelLoadState === "loading"
              ? "Loading deterministic funnel stages from the local backend."
              : "No applications exist for the funnel yet. Run sync, classification, and aggregation from Feature Status first.",
        }}
        height={300}
        info={{
          dataSource: "GET /metrics/funnel",
          dataTable: "applications and application_events",
          howItWorks:
            "Counts each application once through deterministic funnel stages built from local application statuses and timeline events. No LLM produces these funnel counts.",
          howToGenerate:
            "Run sync, classification, and aggregation from Feature Status so retained job-search emails become applications with ordered timeline events.",
          missingData:
            "If funnel rows are zero or missing, check whether classified emails have been aggregated into applications with ordered timeline events.",
        }}
        title="Application funnel"
      >
        {funnelStages.length > 0 ? (
          <BarChart
            data={funnelStages.map((stage) => ({
              applications: stage.count,
              stage: titleize(stage.stage),
            }))}
            margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
          >
            <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
            <XAxis dataKey="stage" stroke="#c9d8ce" />
            <YAxis allowDecimals={false} stroke="#c9d8ce" />
            <Tooltip />
            <Bar dataKey="applications" fill="#b8e2af" name="Applications" radius={[8, 8, 0, 0]} />
          </BarChart>
        ) : undefined}
      </ChartPanel>

      <section
        aria-labelledby="dashboard-breakdown-title"
        className="dashboard-card dashboard-breakdown-card"
      >
        <div className="dashboard-breakdown-header">
          <div>
            <p className="eyebrow">Tier 3 segmentation</p>
            <h2 id="dashboard-breakdown-title">
              {titleize(breakdownDimension)} breakdown
            </h2>
            <p className="dashboard-card__meta">
              Grouped metrics come from deterministic SQLite breakdown rows over
              applications and application_events.
            </p>
          </div>
          <FormField htmlFor="dashboard-breakdown-dimension" label="Dimension">
            <select
              className="ui-input"
              id="dashboard-breakdown-dimension"
              onChange={(event) =>
                setBreakdownDimension(
                  event.target.value as MetricsBreakdownDimensionValue,
                )
              }
              value={breakdownDimension}
            >
              {breakdownDimensionOptions.map((dimension) => (
                <option key={dimension} value={dimension}>
                  {titleize(dimension)}
                </option>
              ))}
            </select>
          </FormField>
        </div>

        {breakdownError ? (
          <Alert title="Metric breakdowns unavailable" tone="danger">
            <p>{breakdownError}</p>
          </Alert>
        ) : null}

        <ChartPanel
          description={`Application counts grouped by ${titleize(
            breakdownDimension,
          ).toLowerCase()} from deterministic /metrics/breakdown data.`}
          emptyState={{
            title:
              breakdownLoadState === "loading"
                ? "Loading breakdown"
                : "No breakdown rows yet",
            description:
              breakdownLoadState === "loading"
                ? "Loading deterministic grouped metrics from the local backend."
                : "No applications exist for this breakdown dimension yet.",
          }}
          height={260}
          info={{
            dataSource: `GET /metrics/breakdown?dimension=${breakdownDimension}`,
            dataTable: "applications and application_events",
            howItWorks: `Groups filtered applications by ${titleize(
              breakdownDimension,
            ).toLowerCase()} and counts each local application deterministically from SQLite. No LLM produces these breakdown values.`,
            howToGenerate:
              "Run sync, classification, and aggregation from Feature Status so retained job-search emails become applications with segmentation fields.",
            missingData:
              "If breakdown rows are zero or missing, check whether aggregated applications have the selected segmentation field populated for the active filters.",
          }}
          title={`${titleize(breakdownDimension)} applications`}
        >
          {breakdownRows.length > 0 ? (
            <BarChart
              data={breakdownRows.map((row) => ({
                applications: row.application_count,
                group: titleize(row.value),
              }))}
              layout="vertical"
              margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
            >
              <CartesianGrid horizontal={false} stroke="rgba(255, 250, 240, 0.16)" />
              <XAxis allowDecimals={false} stroke="#c9d8ce" type="number" />
              <YAxis
                dataKey="group"
                stroke="#c9d8ce"
                tick={{ fontSize: 12 }}
                type="category"
                width={96}
              />
              <Tooltip />
              <Bar dataKey="applications" fill="#b8e2af" radius={[0, 8, 8, 0]} />
            </BarChart>
          ) : undefined}
        </ChartPanel>
      </section>

      <section
        aria-labelledby="best-converting-titles-title"
        className="dashboard-card dashboard-breakdown-card"
      >
        <div>
          <p className="eyebrow">Q-23</p>
          <h2 id="best-converting-titles-title">Best-converting titles</h2>
          <p className="dashboard-card__meta">
            Roles are ranked by deterministic interview conversion from role breakdown rows.
          </p>
        </div>

        {roleConversionError ? (
          <Alert title="Best-converting titles unavailable" tone="danger">
            <p>{roleConversionError}</p>
          </Alert>
        ) : null}

        <ChartPanel
          description="Q-23 interview conversion rates are calculated deterministically from role breakdown rows over local applications and application_events."
          emptyState={{
            title:
              roleConversionLoadState === "loading"
                ? "Loading title conversions"
                : "No title conversion rows yet",
            description:
              roleConversionLoadState === "loading"
                ? "Loading deterministic role conversion metrics from the local backend."
                : "No applications have role breakdown data yet. Run sync, classification, and aggregation from Feature Status first.",
          }}
          height={280}
          info={{
            dataSource: "GET /metrics/breakdown?dimension=role",
            dataTable: "applications and application_events",
            howItWorks:
              "Ranks role titles by deterministic interview conversion from local application counts and interview events. No LLM produces these conversion rates.",
            howToGenerate:
              "Run sync, classification, and aggregation from Feature Status so retained job-search emails become applications with role titles and interview timeline events.",
            missingData:
              "If role conversion rows are zero or missing, check whether aggregated applications have role titles and interview events for the active filters.",
          }}
          title="Role interview conversion"
        >
          {roleConversionRows.length > 0 ? (
            <BarChart
              data={roleConversionRows.slice(0, 5).map((row) => ({
                interviewRate: (interviewConversionRate(row) ?? 0) * 100,
                role: titleize(row.value),
              }))}
              layout="vertical"
              margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
            >
              <CartesianGrid horizontal={false} stroke="rgba(255, 250, 240, 0.16)" />
              <XAxis allowDecimals={false} stroke="#c9d8ce" type="number" unit="%" />
              <YAxis
                dataKey="role"
                stroke="#c9d8ce"
                tick={{ fontSize: 12 }}
                type="category"
                width={124}
              />
              <Tooltip />
              <Bar dataKey="interviewRate" fill="#b8e2af" name="Interview rate" radius={[0, 8, 8, 0]} />
            </BarChart>
          ) : undefined}
        </ChartPanel>
      </section>

      <section
        aria-labelledby="company-type-outcomes-title"
        className="dashboard-card dashboard-breakdown-card"
      >
        <div>
          <p className="eyebrow">Q-24</p>
          <h2 id="company-type-outcomes-title">Company type outcomes</h2>
          <p className="dashboard-card__meta">
            Company type outcomes come from deterministic company profile metadata joined to applications.
          </p>
        </div>

        {companyTypeError ? (
          <Alert title="Company type outcomes unavailable" tone="danger">
            <p>{companyTypeError}</p>
          </Alert>
        ) : null}

        <ChartPanel
          description="Q-24 response conversion by company type is calculated deterministically from company_type breakdown rows over local applications and application_events."
          emptyState={{
            title:
              companyTypeLoadState === "loading"
                ? "Loading company types"
                : "No company type rows yet",
            description:
              companyTypeLoadState === "loading"
                ? "Loading deterministic company type outcomes from the local backend."
                : "No applications have company type metadata yet. Run sync, classification, and aggregation from Feature Status first.",
          }}
          height={280}
          info={{
            dataSource: "GET /metrics/breakdown?dimension=company_type",
            dataTable: "applications and application_events",
            howItWorks:
              "Groups filtered applications by company type and calculates response conversion from deterministic local application and response-event data. No LLM produces these conversion rates.",
            howToGenerate:
              "Run sync, classification, and aggregation from Feature Status so retained job-search emails become applications with company type metadata and response timeline events.",
            missingData:
              "If company type rows are zero or missing, check whether aggregated applications have company type metadata for the active filters.",
          }}
          title="Company type response conversion"
        >
          {companyTypeRows.length > 0 ? (
            <BarChart
              data={companyTypeRows.slice(0, 5).map((row) => ({
                companyType: titleize(row.value),
                responseRate: (row.response_rate ?? 0) * 100,
              }))}
              layout="vertical"
              margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
            >
              <CartesianGrid horizontal={false} stroke="rgba(255, 250, 240, 0.16)" />
              <XAxis allowDecimals={false} stroke="#c9d8ce" type="number" unit="%" />
              <YAxis
                dataKey="companyType"
                stroke="#c9d8ce"
                tick={{ fontSize: 12 }}
                type="category"
                width={124}
              />
              <Tooltip />
              <Bar dataKey="responseRate" fill="#b8e2af" name="Response rate" radius={[0, 8, 8, 0]} />
            </BarChart>
          ) : undefined}
        </ChartPanel>
      </section>

      <section
        aria-labelledby="application-volume-trend-title"
        className="dashboard-card dashboard-breakdown-card"
      >
        <div>
          <p className="eyebrow">Q-20</p>
          <h2 id="application-volume-trend-title">
            Application volume trend
          </h2>
          <p className="dashboard-card__meta">
            Daily application counts come from deterministic /metrics/timeseries
            points over canonical applications.first_seen_at values.
          </p>
        </div>

        {timeseriesError ? (
          <Alert title="Application volume trend unavailable" tone="danger">
            <p>{timeseriesError}</p>
          </Alert>
        ) : null}

        <div className="dashboard-breakdown-layout">
          <div className="dashboard-breakdown-chart-card">
            <ChartPanel
              description="Application counts grouped over time from the local SQLite applications table."
              emptyState={{
                title:
                  timeseriesLoadState === "loading"
                    ? "Loading application volume"
                    : "No application volume yet",
                description:
                  timeseriesLoadState === "loading"
                    ? "Loading deterministic application-volume points from the local backend."
                    : "No applications exist for the volume trend yet.",
              }}
              height={260}
              info={{
                dataSource: "GET /metrics/timeseries",
                dataTable: "applications",
                howItWorks:
                  "Groups filtered local applications by first_seen_at date and counts application volume deterministically from SQLite. No LLM produces these trend points.",
                howToGenerate:
                  "Run sync, classification, and aggregation from Feature Status so retained job-search emails become canonical application rows with first_seen_at dates.",
                missingData:
                  "If application-volume points are zero or missing, check whether aggregation has created application rows with first_seen_at dates for the active filters.",
              }}
              title="Daily application count"
            >
              {timeseriesPoints.length > 0 ? (
                <LineChart
                  data={timeseriesPoints.map((point) => ({
                    applications: point.application_count,
                    period: formatTrendDate(point.period_start),
                  }))}
                  margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
                >
                  <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                  <XAxis dataKey="period" stroke="#c9d8ce" />
                  <YAxis allowDecimals={false} stroke="#c9d8ce" />
                  <Tooltip />
                  <Line
                    dataKey="applications"
                    dot={{ fill: "#b8e2af", r: 4 }}
                    name="Applications"
                    stroke="#b8e2af"
                    strokeWidth={3}
                    type="monotone"
                  />
                </LineChart>
              ) : undefined}
            </ChartPanel>
          </div>
        </div>
      </section>

      <section
        aria-labelledby="response-rate-trend-title"
        className="dashboard-card dashboard-breakdown-card"
      >
        <div>
          <p className="eyebrow">Q-21</p>
          <h2 id="response-rate-trend-title">Response rate trend</h2>
          <p className="dashboard-card__meta">
            Response-rate trend points come from deterministic response evidence
            over canonical applications grouped by first_seen_at date.
          </p>
        </div>

        {responseRateTrendError ? (
          <Alert title="Response rate trend unavailable" tone="danger">
            <p>{responseRateTrendError}</p>
          </Alert>
        ) : null}

        <div className="dashboard-breakdown-layout">
          <div className="dashboard-breakdown-chart-card">
            <ChartPanel
              description="Response rates grouped over time from local application and response-event evidence."
              emptyState={{
                title:
                  responseRateTrendLoadState === "loading"
                    ? "Loading response rate trend"
                    : "No response rate trend yet",
                description:
                  responseRateTrendLoadState === "loading"
                    ? "Loading deterministic response-rate trend points from the local backend."
                    : "No applications exist for the response-rate trend yet.",
              }}
              height={260}
              info={{
                dataSource: "GET /metrics/response-rate-trend",
                dataTable: "applications and application_events",
                howItWorks:
                  "Groups filtered local applications by first_seen_at date and calculates each period's response rate from deterministic response-event evidence. No LLM produces these trend points.",
                howToGenerate:
                  "Run sync, classification, and aggregation from Feature Status so retained job-search emails become canonical applications with response timeline events.",
                missingData:
                  "If response-rate points are zero or missing, check whether aggregated applications have response events for the active filters.",
              }}
              title="Daily response rate"
            >
              {responseRateTrendPoints.length > 0 ? (
                <LineChart
                  data={responseRateTrendPoints.map((point) => ({
                    period: formatTrendDate(point.period_start),
                    responseRate:
                      point.response_rate === null ? null : point.response_rate * 100,
                  }))}
                  margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
                >
                  <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                  <XAxis dataKey="period" stroke="#c9d8ce" />
                  <YAxis allowDecimals={false} stroke="#c9d8ce" unit="%" />
                  <Tooltip />
                  <Line
                    dataKey="responseRate"
                    dot={{ fill: "#b8e2af", r: 4 }}
                    name="Response rate"
                    stroke="#b8e2af"
                    strokeWidth={3}
                    type="monotone"
                  />
                </LineChart>
              ) : undefined}
            </ChartPanel>
          </div>
        </div>
      </section>

      <section
        aria-labelledby="diagnostic-comparisons-title"
        className="dashboard-card dashboard-breakdown-card"
      >
        <div>
          <p className="eyebrow">Phase 3.5 diagnostics</p>
          <h2 id="diagnostic-comparisons-title">Diagnostic comparisons</h2>
          <p className="dashboard-card__meta">
            Winners, losers, and response-rate lift come from deterministic
            diagnostics over local applications and application_events.
          </p>
        </div>

        {diagnosticsError ? (
          <Alert title="Diagnostic comparisons unavailable" tone="danger">
            <p>{diagnosticsError}</p>
          </Alert>
        ) : null}

        <div className="dashboard-breakdown-layout">
          <ChartPanel
            description="Filtered baseline response rate comes from deterministic /metrics/diagnostics response counts over the currently included local applications."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading diagnostic baseline"
                  : "No diagnostic baseline yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic diagnostic baseline from the local backend."
                  : "No applications are available for the diagnostic baseline yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Calculates the filtered baseline response rate from deterministic local application counts and response events. No LLM produces this diagnostic baseline.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with response evidence.",
              missingData:
                "If the baseline rate is zero or missing, check whether aggregated applications have response events for the active filters.",
            }}
            title="Diagnostic baseline response rate"
          >
            {diagnosticBaselineRows.length > 0 ? (
              <BarChart
                data={diagnosticBaselineRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="metric" stroke="#c9d8ce" />
                <YAxis allowDecimals={false} stroke="#c9d8ce" type="number" unit="%" />
                <Tooltip />
                <Bar dataKey="rate" fill="#b8e2af" name="Response rate" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Strongest response signals use deterministic /metrics/diagnostics response-rate lift to chart segments above the filtered response baseline."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading strongest response signals"
                  : "No strongest response signals yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic response-lift diagnostics from the local backend."
                  : "No segment is above the filtered response baseline yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Compares deterministic segment response rates against the filtered baseline and charts the strongest positive response-rate lift from local SQLite. No LLM produces these diagnostic values.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with response evidence and segmentation fields.",
              missingData:
                "If strongest response signals are zero or missing, check whether aggregated applications have populated segmentation fields and response events for the active filters.",
            }}
            title="Strongest response signals"
          >
            {strongestResponseSignalRows.length > 0 ? (
              <BarChart
                data={strongestResponseSignalRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="segment" stroke="#c9d8ce" />
                <YAxis stroke="#c9d8ce" type="number" unit=" pp" />
                <Tooltip />
                <Bar dataKey="lift" fill="#9ed8ff" name="Response-rate lift" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Q-32 successful application traits use deterministic /metrics/diagnostics success-rate lift to chart segments above the filtered success baseline."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading successful application traits"
                  : "No successful application traits yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic success-lift diagnostics from the local backend."
                  : "No segment is above the filtered success baseline yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Compares deterministic segment success rates against the filtered success baseline and charts positive success-rate lift from local SQLite. No LLM produces these diagnostic values.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with interview or offer outcomes and segmentation fields.",
              missingData:
                "If successful application traits are zero or missing, check whether aggregated applications have interview or offer outcomes plus populated segmentation fields for the active filters.",
            }}
            title="Q-32 successful application traits"
          >
            {successfulApplicationTraitRows.length > 0 ? (
              <BarChart
                data={successfulApplicationTraitRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="segment" stroke="#c9d8ce" />
                <YAxis stroke="#c9d8ce" type="number" unit=" pp" />
                <Tooltip />
                <Bar dataKey="lift" fill="#b8e2af" name="Success-rate lift" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Weakest response signals use deterministic /metrics/diagnostics response-rate lift to chart segments below the filtered response baseline."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading weakest response signals"
                  : "No weakest response signals yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic response-lift diagnostics from the local backend."
                  : "No segment is below the filtered response baseline yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Compares deterministic segment response rates against the filtered baseline and charts the weakest negative response-rate lift from local SQLite. No LLM produces these diagnostic values.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with response evidence and segmentation fields.",
              missingData:
                "If weakest response signals are zero or missing, check whether aggregated applications have populated segmentation fields and response events for the active filters.",
            }}
            title="Weakest response signals"
          >
            {weakestResponseSignalRows.length > 0 ? (
              <BarChart
                data={weakestResponseSignalRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="segment" stroke="#c9d8ce" />
                <YAxis stroke="#c9d8ce" type="number" unit=" pp" />
                <Tooltip />
                <Bar dataKey="lift" fill="#ffb86c" name="Response-rate lift" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Q-33 rejected or ghosted traits use deterministic /metrics/diagnostics negative-outcome lift to chart segments above the filtered negative-outcome baseline."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading rejected or ghosted traits"
                  : "No rejected or ghosted traits yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic negative-outcome diagnostics from the local backend."
                  : "No segment is above the filtered negative-outcome baseline yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Compares deterministic segment negative-outcome rates against the filtered negative-outcome baseline and charts rejected or ghosted trait lift from local SQLite. No LLM produces these diagnostic values.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with rejected or ghosted outcomes and segmentation fields.",
              missingData:
                "If rejected or ghosted trait values are zero or missing, check whether aggregated applications have rejected or ghosted outcomes plus populated segmentation fields for the active filters.",
            }}
            title="Q-33 rejected or ghosted traits"
          >
            {rejectedOrGhostedTraitRows.length > 0 ? (
              <BarChart
                data={rejectedOrGhostedTraitRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="segment" stroke="#c9d8ce" />
                <YAxis stroke="#c9d8ce" type="number" unit=" pp" />
                <Tooltip />
                <Bar dataKey="lift" fill="#ff8f70" name="Negative-outcome lift" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Q-34 uses deterministic /metrics/diagnostics response-rate lift to chart the strongest segment above the filtered baseline."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading strongest correlate"
                  : "No strongest response correlate yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic response-lift diagnostics from the local backend."
                  : "No segment is above the filtered response baseline yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Compares deterministic segment response rates against the filtered baseline and charts the highest response-rate lift from local SQLite. No LLM produces this diagnostic value.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with response events and segmentation fields.",
              missingData:
                "If the strongest response correlate is zero or missing, check whether aggregated applications have populated segmentation fields and response events for the active filters.",
            }}
            title="Q-34 strongest response correlate"
          >
            {strongestResponseCorrelateRows.length > 0 ? (
              <BarChart
                data={strongestResponseCorrelateRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="segment" stroke="#c9d8ce" />
                <YAxis stroke="#c9d8ce" type="number" unit=" pp" />
                <Tooltip />
                <Bar dataKey="lift" fill="#9ed8ff" name="Response-rate lift" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Q-35 uses deterministic /metrics/diagnostics response-rate lift to chart segments that are below the filtered response baseline."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading wasted-effort segments"
                  : "No wasted-effort segment yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic wasted-effort diagnostics from the local backend."
                  : "No segment is below the filtered response baseline yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Compares deterministic segment response rates against the filtered baseline and charts the segments with negative response-rate lift from local SQLite. No LLM produces this diagnostic value.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with response events and segmentation fields.",
              missingData:
                "If wasted-effort segment values are zero or missing, check whether aggregated applications have populated segmentation fields and response events for the active filters.",
            }}
            title="Q-35 wasted-effort segments"
          >
            {wastedEffortRows.length > 0 ? (
              <BarChart
                data={wastedEffortRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="segment" stroke="#c9d8ce" />
                <YAxis stroke="#c9d8ce" type="number" unit=" pp" />
                <Tooltip />
                <Bar dataKey="lift" fill="#f4a6b8" name="Response-rate lift" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Q-36 uses deterministic /metrics/diagnostics interview-rate data to chart the source with the strongest interview ROI."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading best ROI source"
                  : "No best ROI source yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic source ROI diagnostics from the local backend."
                  : "No source has interview evidence yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Compares deterministic interview rates by application source and charts the source with the strongest interview conversion from local SQLite. No LLM produces this diagnostic value.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with source fields and interview events.",
              missingData:
                "If best ROI source values are zero or missing, check whether aggregated applications have populated source fields and interview events for the active filters.",
            }}
            title="Q-36 best ROI source"
          >
            {bestRoiSourceRows.length > 0 ? (
              <BarChart
                data={bestRoiSourceRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="source" stroke="#c9d8ce" />
                <YAxis allowDecimals={false} stroke="#c9d8ce" type="number" unit="%" />
                <Tooltip />
                <Bar dataKey="rate" fill="#f7c873" name="Interview rate" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Q-37 uses deterministic /metrics/diagnostics response-rate lift to chart how the sponsorship segment compares with the filtered baseline."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading sponsorship impact"
                  : "No sponsorship comparison yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic sponsorship response diagnostics from the local backend."
                  : "No sponsorship segment can be compared yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Compares deterministic response rates for sponsorship segments against the filtered baseline and charts the response-rate lift from local SQLite. No LLM produces this diagnostic value.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with sponsorship fields and response events.",
              missingData:
                "If sponsorship impact values are zero or missing, check whether aggregated applications have populated sponsorship fields and response events for the active filters.",
            }}
            title="Q-37 sponsorship response impact"
          >
            {sponsorshipImpactRows.length > 0 ? (
              <BarChart
                data={sponsorshipImpactRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="segment" stroke="#c9d8ce" />
                <YAxis stroke="#c9d8ce" type="number" unit=" pp" />
                <Tooltip />
                <Bar dataKey="lift" fill="#f4a6b8" name="Response-rate lift" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Q-38 uses deterministic /metrics/diagnostics interview-rate data to chart the strongest selling and dead-weight skill signals."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading skill signals"
                  : "No skill conversion signal yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic skill diagnostics from the local backend."
                  : "No skill has interview evidence yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Compares deterministic interview rates for selling and dead-weight skill segments from local SQLite application timelines. No LLM produces this diagnostic value.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with tech stack fields and interview events.",
              missingData:
                "If skill signal values are zero or missing, check whether aggregated applications have populated tech stack fields and interview events for the active filters.",
            }}
            title="Q-38 selling vs dead-weight skills"
          >
            {skillSignalRows.length > 0 ? (
              <BarChart
                data={skillSignalRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="segment" stroke="#c9d8ce" />
                <YAxis allowDecimals={false} stroke="#c9d8ce" type="number" unit="%" />
                <Tooltip />
                <Bar dataKey="rate" fill="#8bd3dd" name="Interview rate" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>

          <ChartPanel
            description="Q-39 uses deterministic /metrics/diagnostics adjacent-role conversion data to chart roles with interview evidence that may be worth exploring."
            emptyState={{
              title:
                diagnosticsLoadState === "loading"
                  ? "Loading adjacent role signals"
                  : "No adjacent role signal yet",
              description:
                diagnosticsLoadState === "loading"
                  ? "Loading deterministic adjacent-role diagnostics from the local backend."
                  : "No adjacent role has interview evidence yet. Run sync, classification, and aggregation from Feature Status first.",
            }}
            height={220}
            info={{
              dataSource: "GET /metrics/diagnostics",
              dataTable: "applications and application_events",
              howItWorks:
                "Compares deterministic interview rates for adjacent role-title segments from local SQLite application timelines. No LLM produces this diagnostic value.",
              howToGenerate:
                "Run sync, classification, and aggregation from Feature Status so retained job-search emails become application timelines with role titles and interview events.",
              missingData:
                "If adjacent role suggestion values are zero or missing, check whether aggregated applications have populated role titles and interview events for the active filters.",
            }}
            title="Q-39 adjacent role suggestions"
          >
            {adjacentRoleRows.length > 0 ? (
              <BarChart
                data={adjacentRoleRows}
                margin={{ bottom: 8, left: 12, right: 24, top: 8 }}
              >
                <CartesianGrid stroke="rgba(255, 250, 240, 0.16)" />
                <XAxis dataKey="role" stroke="#c9d8ce" />
                <YAxis allowDecimals={false} stroke="#c9d8ce" type="number" unit="%" />
                <Tooltip />
                <Bar dataKey="rate" fill="#d0b3ff" name="Interview rate" radius={[8, 8, 0, 0]} />
              </BarChart>
            ) : undefined}
          </ChartPanel>
        </div>

      </section>

    </main>
  );
}
