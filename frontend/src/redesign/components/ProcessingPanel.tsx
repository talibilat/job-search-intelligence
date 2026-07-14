import { useEffect, useRef, useState } from "react";

import {
  classificationEstimateClassificationEstimateGet,
  pipelineStatusPipelineStatusGet,
  providerReadinessConfigProvidersReadinessGet,
  processingRunProcessingRunPost,
  processingStatusProcessingStatusGet,
  type ClassificationPreRunEstimate,
  type PipelineStatus,
  type ProcessingRunResult,
  type ProcessingStatus,
  type ProviderReadinessResponse,
} from "../../api";
import { publicApiError } from "../apiError";

type WorkflowState =
  | "waiting-for-sync"
  | "waiting-for-classification"
  | "processing"
  | "blocked-config"
  | "provider-failure"
  | "ready";

interface ProcessingPanelProps {
  onProcessed: () => void;
  reloadKey: number;
}

function resolveWorkflowState(
  pipeline: PipelineStatus,
  processing: ProcessingStatus,
  readiness: ProviderReadinessResponse,
): WorkflowState {
  if (processing.state === "running") return "processing";
  if (processing.state === "failed") return "provider-failure";
  if (pipeline.next_action !== "run_classification") {
    return pipeline.next_action === "review_dashboard" ? "ready" : "waiting-for-sync";
  }
  if (readiness.classification_generation.state === "missing_config" || readiness.classification_generation.state === "missing_credential") {
    return "blocked-config";
  }
  if (!readiness.ready_to_classify) return "provider-failure";
  return "waiting-for-classification";
}

const STATE_COPY: Record<WorkflowState, { label: string; title: string }> = {
  "waiting-for-sync": { label: "Waiting for sync", title: "Finish reading your inbox" },
  "waiting-for-classification": { label: "Ready to process", title: "Turn synced email into applications" },
  processing: { label: "Processing", title: "Building your application history" },
  "blocked-config": { label: "Setup needed", title: "Configure classification first" },
  "provider-failure": { label: "Provider unavailable", title: "Classification cannot start" },
  ready: { label: "Up to date", title: "Your dashboard is ready" },
};

export function ProcessingPanel({ onProcessed, reloadKey }: ProcessingPanelProps) {
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [processing, setProcessing] = useState<ProcessingStatus | null>(null);
  const [readiness, setReadiness] = useState<ProviderReadinessResponse | null>(null);
  const [estimate, setEstimate] = useState<ClassificationPreRunEstimate | null>(null);
  const [result, setResult] = useState<ProcessingRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runFailed, setRunFailed] = useState(false);
  const requestId = useRef(0);

  useEffect(() => {
    const currentRequest = ++requestId.current;
    const load = async () => {
      setError(null);
      try {
        const [pipelineResponse, processingResponse, readinessResponse, estimateResponse] = await Promise.all([
          pipelineStatusPipelineStatusGet(),
          processingStatusProcessingStatusGet(),
          providerReadinessConfigProvidersReadinessGet(),
          classificationEstimateClassificationEstimateGet(),
        ]);
        if (currentRequest !== requestId.current) return;
        if (pipelineResponse.status !== 200 || processingResponse.status !== 200 || readinessResponse.status !== 200 || estimateResponse.status !== 200) {
          setError("Processing status could not be loaded.");
          return;
        }
        setPipeline(pipelineResponse.data);
        setProcessing(processingResponse.data);
        setReadiness(readinessResponse.data);
        setEstimate(estimateResponse.data);
      } catch (loadError) {
        if (currentRequest === requestId.current) {
          setError(publicApiError(loadError, "Processing status could not be loaded."));
        }
      }
    };
    void load();
    return () => {
      requestId.current += 1;
    };
  }, [reloadKey]);

  const runProcessing = async () => {
    if (running) return;
    setRunning(true);
    setResult(null);
    setError(null);
    setRunFailed(false);
    try {
      const response = await processingRunProcessingRunPost({});
      if (response.status !== 200) {
        setRunFailed(true);
        setError(publicApiError({ response }, "Processing failed. Check your provider and retry."));
        return;
      }
      setResult(response.data);
      onProcessed();
    } catch (runError) {
      setRunFailed(true);
      setError(publicApiError(runError, "Processing failed. Check your provider and retry."));
    } finally {
      setRunning(false);
    }
  };

  if (error && !pipeline) {
    return <div role="status" style={{ color: "#96403C", fontSize: "13px" }}>{error}</div>;
  }
  if (!pipeline || !processing || !readiness || !estimate) {
    return <div role="status" style={{ color: "#666D66", fontSize: "13px" }}>Checking processing status...</div>;
  }

  const workflowState: WorkflowState = running
    ? "processing"
    : runFailed
      ? "provider-failure"
      : resolveWorkflowState(pipeline, processing, readiness);
  const copy = STATE_COPY[workflowState];
  const providerMessage = readiness.classification_generation.action ?? readiness.classification_generation.message;
  const body = workflowState === "waiting-for-sync"
    ? pipeline.next_action_reason
    : workflowState === "waiting-for-classification"
      ? `${estimate.candidate_count} retained candidate email${estimate.candidate_count === 1 ? "" : "s"} can be processed with ${estimate.model}. This only starts when you click below.`
      : workflowState === "processing"
        ? "Classification, application grouping, and ghost inference are running in controlled batches."
        : workflowState === "blocked-config" || workflowState === "provider-failure"
          ? providerMessage
          : pipeline.next_action_reason;

  return (
    <section aria-label="Email processing" data-workflow-state={workflowState} style={{ padding: "18px 20px", border: "1px solid #D8DED7", borderRadius: "14px", background: "#F8FBF8", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "20px" }}>
      <div>
        <div style={{ color: workflowState === "provider-failure" || workflowState === "blocked-config" ? "#96403C" : "#1E5136", fontSize: "10.5px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>{copy.label}</div>
        <h2 style={{ margin: "3px 0", fontSize: "15px" }}>{copy.title}</h2>
        <p style={{ margin: 0, maxWidth: "680px", color: "#666D66", fontSize: "12.5px" }}>{body}</p>
        {workflowState === "waiting-for-classification" && estimate.estimated_cost_usd != null ? (
          <p style={{ margin: "5px 0 0", color: "#8A6A14", fontSize: "11.5px" }}>Estimated provider cost: ${estimate.estimated_cost_usd.toFixed(4)}. Prompt {estimate.prompt_version}.</p>
        ) : null}
        {result ? <p role="status" style={{ margin: "5px 0 0", color: "#1E5136", fontSize: "11.5px" }}>Processed {result.processed_count}; accepted {result.accepted_count}; malformed {result.malformed_count}; applications {result.applications_upserted}; events {result.events_upserted}; ghosts {result.ghost_updates}; conflicts {result.manual_conflict_count}.</p> : null}
        {error ? <p role="alert" style={{ margin: "5px 0 0", color: "#96403C", fontSize: "11.5px" }}>{error}</p> : null}
      </div>
      {workflowState === "waiting-for-classification" || workflowState === "processing" || runFailed ? (
        <button disabled={running || workflowState === "processing"} onClick={() => void runProcessing()} style={{ flex: "none", padding: "9px 16px", border: "none", borderRadius: "999px", background: "#1E5136", color: "#F6F4EC", fontSize: "12.5px", fontWeight: 700, cursor: running ? "wait" : "pointer" }} type="button">
          {running ? "Processing..." : runFailed ? "Retry processing" : `Process ${Math.min(estimate.candidate_count, processing.candidate_limit)} emails`}
        </button>
      ) : null}
    </section>
  );
}
