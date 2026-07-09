import { useEffect, useState } from "react";

import {
  listInsightsInsightsGet,
  regenerateInsightInsightsRegeneratePost,
  type InsightRegenerationCost,
  type InsightRecord,
} from "../api";
import { Alert, Button } from "../components/ui";
import {
  INSIGHT_CARDS,
  renderTextWithCitationLinks,
  type InsightDisplayConfig,
} from "./insightDisplay";

type LoadState = "loading" | "ready" | "error";
type RegeneratingType = InsightRecord["type"] | null;
type CostByInsightType = Partial<Record<InsightRecord["type"], InsightRegenerationCost>>;

function apiErrorMessage(data: unknown, fallback: string) {
  if (
    typeof data === "object" &&
    data !== null &&
    "error" in data &&
    typeof data.error === "object" &&
    data.error !== null &&
    "message" in data.error &&
    typeof data.error.message === "string"
  ) {
    return data.error.message;
  }

  return fallback;
}

function formatUtcDate(value: string) {
  return new Date(value).toLocaleString("en-US", {
    timeZone: "UTC",
    timeZoneName: "short",
  });
}

function replaceInsight(
  currentInsights: InsightRecord[],
  nextInsight: InsightRecord,
) {
  return [
    nextInsight,
    ...currentInsights.filter((insight) => insight.type !== nextInsight.type),
  ];
}

function formatCost(value: number | null | undefined, currency: string) {
  if (value === null || value === undefined) {
    return "unavailable";
  }

  return new Intl.NumberFormat("en-US", {
    currency,
    maximumFractionDigits: 6,
    style: "currency",
  }).format(value);
}

function formatTokenCount(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "Actual tokens unavailable";
  }

  return `${value.toLocaleString("en-US")} actual tokens`;
}

function InsightCostSummary({ cost }: { cost: InsightRegenerationCost }) {
  const currency = cost.currency ?? "USD";
  return (
    <div className="insight-card__cost" aria-label="Regeneration cost">
      <span>Estimated cost {formatCost(cost.estimated_cost_usd, currency)}</span>
      <span>Actual cost {formatCost(cost.actual_cost_usd, currency)}</span>
      <span>{formatTokenCount(cost.actual_total_tokens)}</span>
    </div>
  );
}

export function Insights() {
  const [insights, setInsights] = useState<InsightRecord[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [regeneratingType, setRegeneratingType] =
    useState<RegeneratingType>(null);
  const [costByInsightType, setCostByInsightType] =
    useState<CostByInsightType>({});

  useEffect(() => {
    let ignore = false;

    async function loadInsights() {
      setLoadState("loading");
      try {
        const response = await listInsightsInsightsGet();
        if (response.status !== 200) {
          if (!ignore) {
            setErrorMessage(
              apiErrorMessage(
                response.data,
                "Insights are unavailable. Start the local backend and try again.",
              ),
            );
            setLoadState("error");
          }
          return;
        }

        if (!ignore) {
          setInsights(response.data.insights);
          setErrorMessage(null);
          setLoadState("ready");
        }
      } catch {
        if (!ignore) {
          setErrorMessage(
            "Insights are unavailable. Start the local backend and try again.",
          );
          setLoadState("error");
        }
      }
    }

    void loadInsights();

    return () => {
      ignore = true;
    };
  }, []);

  async function handleRegenerate(config: InsightDisplayConfig) {
    setRegeneratingType(config.type);
    setErrorMessage(null);

    try {
      const response = await regenerateInsightInsightsRegeneratePost({
        type: config.type,
      });
      if (response.status !== 200) {
        setErrorMessage(
          apiErrorMessage(
            response.data,
            `${config.title} could not be regenerated.`,
          ),
        );
        return;
      }

      setInsights((currentInsights) =>
        replaceInsight(currentInsights, response.data.insight),
      );
      setCostByInsightType((currentCosts) => ({
        ...currentCosts,
        [response.data.insight.type]: response.data.cost,
      }));
      setLoadState("ready");
    } catch {
      setErrorMessage(
        `${config.title} could not be regenerated. Check that the local backend is running.`,
      );
    } finally {
      setRegeneratingType(null);
    }
  }

  const cachedCount = insights.length;
  const staleCount = insights.filter((insight) => insight.is_stale).length;

  return (
    <main className="app-shell insights-page">
      <section className="hero insights-hero" aria-labelledby="page-title">
        <p className="eyebrow">Phase 4 insights</p>
        <h1 id="page-title">Insights</h1>
        <p className="hero-copy">
          Narrative insights turn deterministic application history into
          grounded recommendations without making the LLM authoritative for
          counts.
        </p>
        <div className="insights-summary" aria-label="Insights cache summary">
          <span>{INSIGHT_CARDS.length} Tier 5 insights</span>
          <span>{cachedCount} cached</span>
          <span>{staleCount} stale</span>
        </div>
      </section>

      <section className="insights-board" aria-label="Cached narrative insights">
        {errorMessage ? <Alert tone="danger">{errorMessage}</Alert> : null}
        {loadState === "loading" ? (
          <p className="insights-panel__empty">Loading cached insights.</p>
        ) : null}
        {loadState !== "loading"
          ? INSIGHT_CARDS.map((config) => {
              const insight = insights.find(
                (item) => item.type === config.type,
              );
              const isRegenerating = regeneratingType === config.type;
              const cost = costByInsightType[config.type];

              return (
                <article className="insight-card" key={config.type}>
                  <div className="insight-card__header">
                    <div>
                      <p className="eyebrow">{config.question}</p>
                      <h2>{config.title}</h2>
                    </div>
                    {insight?.is_stale ? (
                      <span className="insight-card__badge">Stale cache</span>
                    ) : null}
                  </div>
                  <p className="insight-card__description">
                    {config.description}
                  </p>

                  {insight ? (
                    <div className="insight-card__content">
                      {insight.content.split("\n").map((line) => (
                        <p key={line}>{renderTextWithCitationLinks(line)}</p>
                      ))}
                      <p className="insights-panel__meta">
                        Model {insight.model} · Generated {" "}
                        {formatUtcDate(insight.generated_at)}
                      </p>
                      {cost ? <InsightCostSummary cost={cost} /> : null}
                    </div>
                  ) : (
                    <p className="insights-panel__empty">
                      {config.emptyMessage}
                    </p>
                  )}

                  <div className="insight-card__actions">
                    <Button
                      disabled={regeneratingType !== null}
                      onClick={() => void handleRegenerate(config)}
                      type="button"
                    >
                      {isRegenerating
                        ? `Regenerating ${config.title}`
                        : `Regenerate ${config.title}`}
                    </Button>
                  </div>
                </article>
              );
            })
          : null}
      </section>
    </main>
  );
}
