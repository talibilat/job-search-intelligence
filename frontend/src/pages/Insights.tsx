import { useEffect, useState } from "react";

import {
  InsightType,
  listInsightsInsightsGet,
  regenerateInsightInsightsRegeneratePost,
  type InsightRecord,
} from "../api";
import { Alert, Button } from "../components/ui";

type LoadState = "loading" | "ready" | "error";

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

function insightTitle(type: InsightRecord["type"]) {
  if (type === "recurring_feedback") {
    return "Recurring recruiter feedback";
  }

  return type.replaceAll("_", " ");
}

export function Insights() {
  const [insights, setInsights] = useState<InsightRecord[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRegenerating, setIsRegenerating] = useState(false);

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

  async function handleRegenerateRecurringFeedback() {
    setIsRegenerating(true);
    setErrorMessage(null);

    try {
      const response = await regenerateInsightInsightsRegeneratePost({
        type: InsightType.recurring_feedback,
      });
      if (response.status !== 200) {
        setErrorMessage(
          apiErrorMessage(
            response.data,
            "Recurring feedback could not be regenerated.",
          ),
        );
        return;
      }

      setInsights((currentInsights) => [
        response.data.insight,
        ...currentInsights.filter(
          (insight) => insight.type !== response.data.insight.type,
        ),
      ]);
      setLoadState("ready");
    } catch {
      setErrorMessage(
        "Recurring feedback could not be regenerated. Check that the local backend is running.",
      );
    } finally {
      setIsRegenerating(false);
    }
  }

  const recurringFeedback = insights.find(
    (insight) => insight.type === "recurring_feedback",
  );

  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">Phase 4 insights</p>
        <h1 id="page-title">Insights</h1>
        <p className="hero-copy">
          Narrative insights turn deterministic application history into
          grounded recommendations without making the LLM authoritative for
          counts.
        </p>
      </section>

      <section className="status-card insights-panel" aria-labelledby="insights-status-title">
        <div>
          <p className="eyebrow">Q-41</p>
          <h2 id="insights-status-title">Recurring recruiter feedback</h2>
          <p>
            Answers what recruiter or interviewer feedback consistently says to
            improve, using cited feedback events from the application timeline.
          </p>
          <div className="sync-panel__actions">
            <Button
              disabled={isRegenerating}
              onClick={() => void handleRegenerateRecurringFeedback()}
              type="button"
            >
              {isRegenerating ? "Regenerating" : "Regenerate Q-41"}
            </Button>
          </div>
        </div>
        <div className="insights-panel__body">
          {errorMessage ? <Alert tone="danger">{errorMessage}</Alert> : null}
          {loadState === "loading" ? (
            <p className="insights-panel__empty">Loading cached insights.</p>
          ) : recurringFeedback ? (
            <article className="insights-panel__insight">
              <p className="eyebrow">{insightTitle(recurringFeedback.type)}</p>
              <p>{recurringFeedback.content}</p>
              <p className="insights-panel__meta">
                Model {recurringFeedback.model} · Generated {" "}
                {new Date(recurringFeedback.generated_at).toLocaleString("en-US", {
                  timeZone: "UTC",
                  timeZoneName: "short",
                })}
              </p>
            </article>
          ) : (
            <p className="insights-panel__empty">
              No cached recurring feedback insight exists yet. Regenerate Q-41
              after feedback events are available.
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
