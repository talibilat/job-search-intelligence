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
  type TimeToFirstResponseMetric,
  type TimeToRejectionMetric,
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

const metricPlaceholders: readonly { label: string; note: string }[] = [];

const statusOptions = Object.values(ApplicationStatus);
const sourceOptions = Object.values(ApplicationSource);
const sponsorshipOptions = Object.values(SponsorshipStatus);
const workModeOptions = Object.values(WorkMode);
const breakdownDimensionOptions = Object.values(MetricsBreakdownDimension);
const numberFormatter = new Intl.NumberFormat("en-US");
const percentageFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 1,
  style: "percent",
});
const percentagePointFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});
const durationFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});

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

function summaryMetricValue(isLoading: boolean, value: number | undefined) {
  if (isLoading) {
    return "Loading";
  }
  if (value === undefined) {
    return "Unavailable";
  }
  return numberFormatter.format(value);
}

function formatTimeToFirstResponseValue(
  isLoading: boolean,
  metric: TimeToFirstResponseMetric | undefined,
) {
  if (isLoading) {
    return "Loading";
  }
  if (metric === undefined) {
    return "Unavailable";
  }
  const averageHours = metric.average_hours;
  if (averageHours == null) {
    return "No data";
  }
  if (averageHours < 24) {
    return `${durationFormatter.format(averageHours)} hours`;
  }
  return `${durationFormatter.format(averageHours / 24)} days`;
}

function formatTimeToFirstResponseMeta(
  isLoading: boolean,
  metric: TimeToFirstResponseMetric | undefined,
) {
  if (isLoading || metric === undefined) {
    return "Loading deterministic response timing";
  }
  if (metric.application_count === 0) {
    return "No applications have response evidence yet";
  }
  const applicationLabel =
    metric.application_count === 1 ? "application" : "applications";
  return `Averaged across ${numberFormatter.format(
    metric.application_count,
  )} ${applicationLabel} with response evidence`;
}

function formatTimeToRejectionValue(
  isLoading: boolean,
  metric: TimeToRejectionMetric | undefined,
) {
  if (isLoading) {
    return "Loading";
  }
  if (metric === undefined) {
    return "Unavailable";
  }
  const averageHours = metric.average_hours;
  if (averageHours == null) {
    return "No data";
  }
  if (averageHours < 24) {
    return `${durationFormatter.format(averageHours)} hours`;
  }
  return `${durationFormatter.format(averageHours / 24)} days`;
}

function formatTimeToRejectionMeta(
  isLoading: boolean,
  metric: TimeToRejectionMetric | undefined,
) {
  if (isLoading || metric === undefined) {
    return "Loading deterministic rejection timing";
  }
  if (metric.application_count === 0) {
    return "No applications have rejection evidence yet";
  }
  const applicationLabel =
    metric.application_count === 1 ? "rejected application" : "rejected applications";
  return `Averaged across ${numberFormatter.format(
    metric.application_count,
  )} ${applicationLabel}`;
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

function countLabel(count: number, singular: string) {
  return `${numberFormatter.format(count)} ${singular}${count === 1 ? "" : "s"}`;
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

function formatResponseLift(lift: number | null | undefined) {
  if (lift == null) {
    return "No baseline";
  }
  const sign = lift > 0 ? "+" : "";
  return `${sign}${percentagePointFormatter.format(lift * 100)} pp vs baseline`;
}

function formatSuccessLift(lift: number | null | undefined) {
  if (lift == null) {
    return "No success baseline";
  }
  const sign = lift > 0 ? "+" : "";
  return `${sign}${percentagePointFormatter.format(lift * 100)} pp success lift`;
}

function formatNegativeLift(lift: number | null | undefined) {
  if (lift == null) {
    return "No negative baseline";
  }
  const sign = lift > 0 ? "+" : "";
  return `${sign}${percentagePointFormatter.format(lift * 100)} pp negative lift`;
}

function diagnosticSegmentTitle(segment: DiagnosticSegmentComparison) {
  return `${titleize(segment.value)} (${titleize(segment.dimension)})`;
}

function diagnosticSegmentEvidence(segment: DiagnosticSegmentComparison) {
  return `${countLabel(segment.response_count, "response")} from ${countLabel(
    segment.application_count,
    "application",
  )}`;
}

function diagnosticSuccessEvidence(segment: DiagnosticSegmentComparison) {
  return `${countLabel(segment.success_count, "successful application")} from ${countLabel(
    segment.application_count,
    "application",
  )}`;
}

function diagnosticNegativeEvidence(segment: DiagnosticSegmentComparison) {
  return `${countLabel(segment.negative_count, "negative outcome")} from ${countLabel(
    segment.application_count,
    "application",
  )}`;
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
    const nextFilters = canonicalFilters(filters);
    const nextQuery = queryStringFromFilters(nextFilters);
    window.history.pushState({}, "", `${window.location.pathname}${nextQuery}`);
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
  }

  function clearFilters() {
    window.history.pushState({}, "", window.location.pathname);
    setFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
  }

  const totalApplicationsValue = summaryMetricValue(
    isLoadingSummary,
    summary?.total_applications,
  );
  const distinctCompanyValue = summaryMetricValue(
    isLoadingSummary,
    summary?.distinct_company_count,
  );
  const interviewInvitationValue = summaryMetricValue(
    isLoadingSummary,
    summary?.interview_invitation_count,
  );
  const offersReceivedValue = summaryMetricValue(
    isLoadingSummary,
    summary?.offers_received,
  );
  const averageFirstResponseValue = formatTimeToFirstResponseValue(
    isLoadingSummary,
    summary?.average_time_to_first_response,
  );
  const averageFirstResponseMeta = formatTimeToFirstResponseMeta(
    isLoadingSummary,
    summary?.average_time_to_first_response,
  );
  const averageRejectionValue = formatTimeToRejectionValue(
    isLoadingSummary,
    summary?.average_time_to_rejection,
  );
  const averageRejectionMeta = formatTimeToRejectionMeta(
    isLoadingSummary,
    summary?.average_time_to_rejection,
  );
  const silenceAgeBuckets =
    summary?.personal_ghost_threshold?.silence_age_distribution ?? [];
  const strongestDiagnostic = diagnostics?.strongest_response_segments[0];
  const weakestDiagnostic = diagnostics?.weakest_response_segments[0];
  const successfulDiagnostic = diagnostics?.successful_application_segments[0];
  const negativeDiagnostic = diagnostics?.negative_outcome_segments[0];
  const strongestResponseCorrelate = diagnostics?.strongest_response_correlate;
  const wastedEffortSegment = diagnostics?.wasted_effort_segments[0];
  const bestRoiSource = diagnostics?.best_roi_source;
  const sponsorshipImpact = diagnostics?.sponsorship_response_impact;
  const sellingSkill = diagnostics?.selling_skill_segments[0];
  const deadWeightSkill = diagnostics?.dead_weight_skill_segments[0];
  const adjacentRoleSuggestion = diagnostics?.adjacent_role_suggestions[0];

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
              Go to the <a href="/">Job Search page</a> to run the next step.
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
                htmlFor="dashboard-first-seen-from"
                label="First seen from"
              >
                <TextInput
                  id="dashboard-first-seen-from"
                  onChange={(event) =>
                    setFilters({
                      ...filters,
                      firstSeenFrom: event.target.value,
                    })
                  }
                  placeholder="2026-07-01T00:00:00Z"
                  value={filters.firstSeenFrom}
                />
              </FormField>
              <FormField
                htmlFor="dashboard-first-seen-to"
                label="First seen to"
              >
                <TextInput
                  id="dashboard-first-seen-to"
                  onChange={(event) =>
                    setFilters({ ...filters, firstSeenTo: event.target.value })
                  }
                  placeholder="2026-07-31T23:59:59Z"
                  value={filters.firstSeenTo}
                />
              </FormField>
              <FormField htmlFor="dashboard-salary-min" label="Salary min">
                <TextInput
                  id="dashboard-salary-min"
                  inputMode="numeric"
                  onChange={(event) =>
                    setFilters({ ...filters, salaryMin: event.target.value })
                  }
                  placeholder="120000"
                  value={filters.salaryMin}
                />
              </FormField>
              <FormField htmlFor="dashboard-salary-max" label="Salary max">
                <TextInput
                  id="dashboard-salary-max"
                  inputMode="numeric"
                  onChange={(event) =>
                    setFilters({ ...filters, salaryMax: event.target.value })
                  }
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

        <section
          aria-labelledby="metrics-overview-title"
          className="dashboard-card"
        >
          <div>
            <p className="eyebrow">Deterministic source of truth</p>
            <h2 id="metrics-overview-title">Metrics overview</h2>
          </div>
          <div className="dashboard-metric-grid">
            <article className="metric-placeholder">
              <p className="metric-placeholder__label">Total applications</p>
              <p className="metric-placeholder__value">
                {totalApplicationsValue}
              </p>
              <p className="dashboard-card__meta">
                Q-01 reconciled from applications
              </p>
            </article>
            <article className="metric-placeholder">
              <p className="metric-placeholder__label">Distinct companies</p>
              <p className="metric-placeholder__value">
                {distinctCompanyValue}
              </p>
              <p className="dashboard-card__meta">
                Q-03 counted from normalized applications
              </p>
            </article>
            <article className="metric-placeholder">
              <h3 className="metric-placeholder__label">
                Interview invitations
              </h3>
              <p className="metric-placeholder__value">
                {interviewInvitationValue}
              </p>
              <p className="dashboard-card__meta">
                Q-07 - Counted from interview_scheduled events
              </p>
            </article>
            <article className="metric-placeholder">
              <h3 className="metric-placeholder__label">Offers received</h3>
              <p className="metric-placeholder__value">{offersReceivedValue}</p>
              <p className="dashboard-card__meta">
                Q-08 counted from offer events
              </p>
            </article>
            <article
              aria-label="Average time to first response metric"
              className="metric-placeholder"
            >
              <h3 className="metric-placeholder__label">
                Avg time to first response
              </h3>
              <p className="metric-placeholder__value">
                {averageFirstResponseValue}
              </p>
              <p className="dashboard-card__meta">{averageFirstResponseMeta}</p>
            </article>
            <article
              aria-label="Average time to rejection metric"
              className="metric-placeholder"
            >
              <h3 className="metric-placeholder__label">
                Avg time to rejection
              </h3>
              <p className="metric-placeholder__value">
                {averageRejectionValue}
              </p>
              <p className="dashboard-card__meta">{averageRejectionMeta}</p>
            </article>
            <article
              aria-label="Response rate metric"
              className="metric-placeholder"
            >
              <p className="metric-placeholder__label">Response rate</p>
              <p className="metric-placeholder__value">
                {formatRateValue(responseRate, responseRateLoadState)}
              </p>
              <p className="dashboard-card__meta">
                {formatResponseRateMeta(responseRate, responseRateLoadState)}
              </p>
            </article>
            <article
              aria-label="Rejection rate metric"
              className="metric-placeholder"
            >
              <p className="metric-placeholder__label">Rejection rate</p>
              <p className="metric-placeholder__value">
                {formatRateValue(rejectionRate, responseRateLoadState)}
              </p>
              <p className="dashboard-card__meta">
                {formatRejectionRateMeta(rejectionRate, responseRateLoadState)}
              </p>
            </article>
            <article aria-label="Ghost rate metric" className="metric-placeholder">
              <p className="metric-placeholder__label">Ghost rate</p>
              <p className="metric-placeholder__value">
                {formatRateValue(ghostRate, responseRateLoadState)}
              </p>
              <p className="dashboard-card__meta">
                {formatGhostRateMeta(ghostRate, responseRateLoadState)}
              </p>
            </article>
            <article
              aria-label="Application to interview rate metric"
              className="metric-placeholder"
            >
              <p className="metric-placeholder__label">
                Application to interview rate
              </p>
              <p className="metric-placeholder__value">
                {formatRateValue(
                  applicationToInterviewRate,
                  responseRateLoadState,
                )}
              </p>
              <p className="dashboard-card__meta">
                {formatApplicationToInterviewRateMeta(
                  applicationToInterviewRate,
                  responseRateLoadState,
                )}
              </p>
            </article>
            <article
              aria-label="Interview to offer rate metric"
              className="metric-placeholder"
            >
              <p className="metric-placeholder__label">
                Interview to offer rate
              </p>
              <p className="metric-placeholder__value">
                {formatRateValue(interviewToOfferRate, responseRateLoadState)}
              </p>
              <p className="dashboard-card__meta">
                {formatInterviewToOfferRateMeta(
                  interviewToOfferRate,
                  responseRateLoadState,
                )}
              </p>
            </article>
            {metricPlaceholders.map((metric) => (
              <article className="metric-placeholder" key={metric.label}>
                <p className="metric-placeholder__label">{metric.label}</p>
                <p className="metric-placeholder__value">Pending</p>
                <p className="dashboard-card__meta">{metric.note}</p>
              </article>
            ))}
          </div>
        </section>
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
          <article className="metric-placeholder">
            <p className="metric-placeholder__label">Baseline response rate</p>
            <p className="metric-placeholder__value">
              {diagnosticsError
                ? "Unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading"
                : formatNullableRate(diagnostics?.baseline_response_rate ?? null)}
            </p>
            <p className="dashboard-card__meta">
              {diagnosticsError
                ? "Diagnostic baseline is unavailable"
                : diagnostics
                ? `${countLabel(
                    diagnostics.baseline_response_count,
                    "response",
                  )} from ${countLabel(diagnostics.total_applications, "application")}`
                : "Loading deterministic baseline"}
            </p>
          </article>

          <article>
            <h3>Strongest response signals</h3>
            <ol className="dashboard-breakdown-ranks">
              {diagnostics?.strongest_response_segments.length ? (
                diagnostics.strongest_response_segments.map((segment) => (
                  <li key={`strong-${segment.dimension}-${segment.value}`}>
                    <div>
                      <span className="dashboard-breakdown-rank__label">
                        {diagnosticSegmentTitle(segment)}
                      </span>
                      <span>{formatResponseLift(segment.response_rate_lift)}</span>
                    </div>
                    <p>{diagnosticSegmentEvidence(segment)}</p>
                  </li>
                ))
              ) : (
                <li>
                  <div>
                    <span className="dashboard-breakdown-rank__label">
                      {diagnosticsError
                        ? "Unavailable"
                        : diagnosticsLoadState === "loading"
                          ? "Loading"
                          : "No winners"}
                    </span>
                    <span>
                      {diagnosticsError
                        ? "Diagnostic request failed"
                        : diagnosticsLoadState === "loading"
                        ? "Fetching diagnostics"
                        : "No positive lift"}
                    </span>
                  </div>
                </li>
              )}
            </ol>
          </article>

          <article>
            <h3>Q-32 successful application traits</h3>
            <p className="dashboard-card__meta">
              {diagnosticsError
                ? "Successful-trait diagnostics are unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading successful application baseline"
                : diagnostics
                ? `${formatNullableRate(
                    diagnostics.baseline_success_rate,
                  )} baseline success rate`
                : "Loading deterministic success baseline"}
            </p>
            <ol className="dashboard-breakdown-ranks">
              {diagnostics?.successful_application_segments.length ? (
                diagnostics.successful_application_segments.map((segment) => (
                  <li key={`success-${segment.dimension}-${segment.value}`}>
                    <div>
                      <span className="dashboard-breakdown-rank__label">
                        {diagnosticSegmentTitle(segment)}
                      </span>
                      <span>{formatSuccessLift(segment.success_rate_lift)}</span>
                    </div>
                    <p>{diagnosticSuccessEvidence(segment)}</p>
                  </li>
                ))
              ) : (
                <li>
                  <div>
                    <span className="dashboard-breakdown-rank__label">
                      {diagnosticsError
                        ? "Unavailable"
                        : diagnosticsLoadState === "loading"
                          ? "Loading"
                          : "No successful traits"}
                    </span>
                    <span>
                      {diagnosticsError
                        ? "Diagnostic request failed"
                        : diagnosticsLoadState === "loading"
                        ? "Fetching diagnostics"
                        : "No positive success lift"}
                    </span>
                  </div>
                </li>
              )}
            </ol>
          </article>

          <article>
            <h3>Weakest response signals</h3>
            <ol className="dashboard-breakdown-ranks">
              {diagnostics?.weakest_response_segments.length ? (
                diagnostics.weakest_response_segments.map((segment) => (
                  <li key={`weak-${segment.dimension}-${segment.value}`}>
                    <div>
                      <span className="dashboard-breakdown-rank__label">
                        {diagnosticSegmentTitle(segment)}
                      </span>
                      <span>{formatResponseLift(segment.response_rate_lift)}</span>
                    </div>
                    <p>{diagnosticSegmentEvidence(segment)}</p>
                  </li>
                ))
              ) : (
                <li>
                  <div>
                    <span className="dashboard-breakdown-rank__label">
                      {diagnosticsError
                        ? "Unavailable"
                        : diagnosticsLoadState === "loading"
                          ? "Loading"
                          : "No losers"}
                    </span>
                    <span>
                      {diagnosticsError
                        ? "Diagnostic request failed"
                        : diagnosticsLoadState === "loading"
                        ? "Fetching diagnostics"
                        : "No negative lift"}
                    </span>
                  </div>
                </li>
              )}
            </ol>
          </article>

          <article>
            <h3>Q-33 rejected or ghosted traits</h3>
            <p className="dashboard-card__meta">
              {diagnosticsError
                ? "Negative-outcome diagnostics are unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading negative outcome baseline"
                : diagnostics
                ? `${formatNullableRate(
                    diagnostics.baseline_negative_rate,
                  )} baseline negative rate`
                : "Loading deterministic negative baseline"}
            </p>
            <ol className="dashboard-breakdown-ranks">
              {diagnostics?.negative_outcome_segments.length ? (
                diagnostics.negative_outcome_segments.map((segment) => (
                  <li key={`negative-${segment.dimension}-${segment.value}`}>
                    <div>
                      <span className="dashboard-breakdown-rank__label">
                        {diagnosticSegmentTitle(segment)}
                      </span>
                      <span>{formatNegativeLift(segment.negative_rate_lift)}</span>
                    </div>
                    <p>{diagnosticNegativeEvidence(segment)}</p>
                  </li>
                ))
              ) : (
                <li>
                  <div>
                    <span className="dashboard-breakdown-rank__label">
                      {diagnosticsError
                        ? "Unavailable"
                        : diagnosticsLoadState === "loading"
                          ? "Loading"
                          : "No negative traits"}
                    </span>
                    <span>
                      {diagnosticsError
                        ? "Diagnostic request failed"
                        : diagnosticsLoadState === "loading"
                        ? "Fetching diagnostics"
                        : "No positive negative-outcome lift"}
                    </span>
                  </div>
                </li>
              )}
            </ol>
          </article>

          <article className="metric-placeholder">
            <h3 className="metric-placeholder__label">
              Q-34 strongest response correlate
            </h3>
            <p className="metric-placeholder__value">
              {diagnosticsError
                ? "Unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading"
                : strongestResponseCorrelate
                ? diagnosticSegmentTitle(strongestResponseCorrelate)
                : "No correlate"}
            </p>
            <p className="dashboard-card__meta">
              {diagnosticsError
                ? "Strongest response correlate is unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading deterministic response correlate"
                : strongestResponseCorrelate
                ? `${diagnosticSegmentTitle(
                    strongestResponseCorrelate,
                  )} is the strongest positive correlate`
                : "No segment is above the filtered response baseline"}
            </p>
          </article>

          <article>
            <h3>Q-35 wasted-effort segments</h3>
            <ol className="dashboard-breakdown-ranks">
              {diagnostics?.wasted_effort_segments.length ? (
                diagnostics.wasted_effort_segments.map((segment) => (
                  <li key={`wasted-${segment.dimension}-${segment.value}`}>
                    <div>
                      <span className="dashboard-breakdown-rank__label">
                        {diagnosticSegmentTitle(segment)}
                      </span>
                      <span>{formatResponseLift(segment.response_rate_lift)}</span>
                    </div>
                    <p>{diagnosticSegmentEvidence(segment)}</p>
                  </li>
                ))
              ) : (
                <li>
                  <div>
                    <span className="dashboard-breakdown-rank__label">
                      {diagnosticsError
                        ? "Unavailable"
                        : diagnosticsLoadState === "loading"
                          ? "Loading"
                          : "No wasted effort"}
                    </span>
                    <span>
                      {diagnosticsError
                        ? "Diagnostic request failed"
                        : diagnosticsLoadState === "loading"
                        ? "Fetching diagnostics"
                        : "No below-baseline segments"}
                    </span>
                  </div>
                </li>
              )}
            </ol>
            <p className="dashboard-card__meta">
              {wastedEffortSegment
                ? `${diagnosticSegmentTitle(wastedEffortSegment)} is below baseline`
                : diagnosticsLoadState === "loading"
                ? "Loading wasted-effort comparison"
                : "No segment is currently below the filtered response baseline"}
            </p>
          </article>

          <article className="metric-placeholder">
            <h3 className="metric-placeholder__label">Q-36 best ROI source</h3>
            <p className="metric-placeholder__value">
              {diagnosticsError
                ? "Unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading"
                : bestRoiSource
                ? diagnosticSegmentTitle(bestRoiSource)
                : "No source"}
            </p>
            <p className="dashboard-card__meta">
              {diagnosticsError
                ? "Best ROI source is unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading source interview ROI"
                : bestRoiSource
                ? `${diagnosticSegmentTitle(bestRoiSource)} has the best interview ROI`
                : "No source has interview evidence yet"}
            </p>
          </article>

          <article className="metric-placeholder">
            <h3 className="metric-placeholder__label">
              Q-37 sponsorship response impact
            </h3>
            <p className="metric-placeholder__value">
              {diagnosticsError
                ? "Unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading"
                : sponsorshipImpact
                ? formatResponseLift(sponsorshipImpact.response_rate_lift)
                : "No sponsorship comparison"}
            </p>
            <p className="dashboard-card__meta">
              {diagnosticsError
                ? "Sponsorship response impact is unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading sponsorship response impact"
                : sponsorshipImpact
                ? `${diagnosticSegmentTitle(sponsorshipImpact)} is ${formatResponseLift(
                    sponsorshipImpact.response_rate_lift,
                  )}`
                : "No sponsorship segment can be compared yet"}
            </p>
          </article>

          <article className="metric-placeholder">
            <h3 className="metric-placeholder__label">
              Q-38 selling vs dead-weight skills
            </h3>
            <p className="metric-placeholder__value">
              {diagnosticsError
                ? "Unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading"
                : sellingSkill
                ? titleize(sellingSkill.value)
                : "No selling skill"}
            </p>
            <p className="dashboard-card__meta">
              {diagnosticsError
                ? "Skill diagnostics are unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading skill interview conversion"
                : sellingSkill
                ? `${titleize(sellingSkill.value)} is selling`
                : "No skill has interview evidence yet"}
              {deadWeightSkill
                ? `; ${titleize(deadWeightSkill.value)} is below response baseline`
                : ""}
            </p>
          </article>

          <article className="metric-placeholder">
            <h3 className="metric-placeholder__label">
              Q-39 adjacent role suggestions
            </h3>
            <p className="metric-placeholder__value">
              {diagnosticsError
                ? "Unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading"
                : adjacentRoleSuggestion
                ? titleize(adjacentRoleSuggestion.value)
                : "No role suggestion"}
            </p>
            <p className="dashboard-card__meta">
              {diagnosticsError
                ? "Adjacent role suggestions are unavailable"
                : diagnosticsLoadState === "loading"
                ? "Loading role conversion signals"
                : adjacentRoleSuggestion
                ? `${titleize(
                    adjacentRoleSuggestion.value,
                  )} is your strongest adjacent role signal`
                : "No role has interview or offer evidence yet"}
            </p>
          </article>
        </div>

        <article className="metric-placeholder">
          <h3 className="metric-placeholder__label">Correlation summary</h3>
          <p className="dashboard-card__meta">
            {diagnosticsLoadState === "loading"
              ? "Loading deterministic diagnostic comparisons."
              : diagnosticsError
                ? "Diagnostic comparison summary is unavailable."
                : `${
                    strongestDiagnostic
                      ? `${diagnosticSegmentTitle(strongestDiagnostic)} is ${formatResponseLift(
                          strongestDiagnostic.response_rate_lift,
                        )}.`
                      : "No positive response-rate lift is available yet."
                  } ${
                    weakestDiagnostic
                      ? `${diagnosticSegmentTitle(weakestDiagnostic)} is ${formatResponseLift(
                          weakestDiagnostic.response_rate_lift,
                        )}.`
                      : "No negative response-rate lift is available yet."
                  } ${
                    successfulDiagnostic
                      ? `${diagnosticSegmentTitle(successfulDiagnostic)} is ${formatSuccessLift(
                          successfulDiagnostic.success_rate_lift,
                        )}.`
                      : "No successful application trait lift is available yet."
                  } ${
                    negativeDiagnostic
                      ? `${diagnosticSegmentTitle(negativeDiagnostic)} is ${formatNegativeLift(
                          negativeDiagnostic.negative_rate_lift,
                        )}.`
                      : "No rejected or ghosted trait lift is available yet."
                  }`}
          </p>
        </article>

        {diagnostics && diagnosticsLoadState === "loaded" && !diagnosticsError ? (
          <article className="metric-placeholder">
            <h3 className="metric-placeholder__label">How to read these diagnostics</h3>
            <p className="dashboard-card__meta">
              Response-rate lift is the segment response rate minus the filtered
              baseline response rate.
            </p>
            <p className="dashboard-card__meta">
              Filtered baseline response rate is the response rate for every
              application currently included by the dashboard filters.
            </p>
            <p className="dashboard-card__meta">
              A response means the application has response evidence in
              application_events, including interviews, offers, or other human
              replies.
            </p>
            <p className="dashboard-card__meta">
              Strongest and weakest signals are segments ranked by positive or
              negative lift, not recommendations by themselves.
            </p>
            <p className="dashboard-card__meta">
              Rankings use only local applications and application_events currently
              included by the dashboard filters.
            </p>
            <p className="dashboard-card__meta">
              These are directional comparisons, not proof that a segment caused an
              outcome.
            </p>
          </article>
        ) : null}
      </section>

    </main>
  );
}

function formatRateValue(
  metric: MetricRate | null,
  loadState: ResponseRateLoadState,
) {
  if (loadState === "error") {
    return "Unavailable";
  }
  if (loadState === "loading" || metric === null) {
    return "Loading";
  }
  if (metric.rate === null) {
    return "No data";
  }
  return percentageFormatter.format(metric.rate);
}

function formatNullableRate(rate: number | null | undefined) {
  return rate == null ? "No data" : percentageFormatter.format(rate);
}

function formatResponseRateMeta(
  metric: MetricRate | null,
  loadState: ResponseRateLoadState,
) {
  if (loadState === "error") {
    return "Response rate is unavailable from the local backend";
  }
  if (loadState === "loading" || metric === null) {
    return "Loading deterministic numerator and denominator";
  }
  if (metric.denominator === 0) {
    return "0 applications in the denominator";
  }
  return `${numberFormatter.format(metric.numerator)} of ${numberFormatter.format(
    metric.denominator,
  )} applications have response evidence`;
}

function formatRejectionRateMeta(
  metric: MetricRate | null,
  loadState: ResponseRateLoadState,
) {
  if (loadState === "error") {
    return "Rejection rate is unavailable from the local backend";
  }
  if (loadState === "loading" || metric === null) {
    return "Loading deterministic numerator and denominator";
  }
  if (metric.denominator === 0) {
    return "0 applications in the denominator";
  }
  const applicationLabel =
    metric.denominator === 1 ? "application is" : "applications are";
  return `${numberFormatter.format(metric.numerator)} of ${numberFormatter.format(
    metric.denominator,
  )} ${applicationLabel} rejected`;
}

function formatGhostRateMeta(
  metric: MetricRate | null,
  loadState: ResponseRateLoadState,
) {
  if (loadState === "error") {
    return "Ghost rate is unavailable from the local backend";
  }
  if (loadState === "loading" || metric === null) {
    return "Loading deterministic numerator and denominator";
  }
  if (metric.denominator === 0) {
    return "0 applications in the denominator";
  }
  return `${numberFormatter.format(metric.numerator)} of ${numberFormatter.format(
    metric.denominator,
  )} applications are ghosted or silent past threshold`;
}

function formatApplicationToInterviewRateMeta(
  metric: MetricRate | null,
  loadState: ResponseRateLoadState,
) {
  if (loadState === "error") {
    return "Application to interview rate is unavailable from the local backend";
  }
  if (loadState === "loading" || metric === null) {
    return "Loading deterministic numerator and denominator";
  }
  if (metric.denominator === 0) {
    return "0 applications in the denominator";
  }
  return `${numberFormatter.format(metric.numerator)} of ${numberFormatter.format(
    metric.denominator,
  )} applications reached interview`;
}

function formatInterviewToOfferRateMeta(
  metric: MetricRate | null,
  loadState: ResponseRateLoadState,
) {
  if (loadState === "error") {
    return "Interview to offer rate is unavailable from the local backend";
  }
  if (loadState === "loading" || metric === null) {
    return "Loading deterministic numerator and denominator";
  }
  if (metric.denominator === 0) {
    return "0 interviewed applications in the denominator";
  }
  return `${numberFormatter.format(metric.numerator)} of ${numberFormatter.format(
    metric.denominator,
  )} interviewed applications reached offer`;
}
