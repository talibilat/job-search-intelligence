export type FeatureArea = "frontend" | "backend";

export type FeatureStatus =
  | "blocked"
  | "completed"
  | "in_progress"
  | "not_started"
  | "planned";

export interface FeatureRelationshipStep {
  label: string;
  type:
    | "api"
    | "background_job"
    | "component"
    | "controller"
    | "database"
    | "frontend_update"
    | "queue"
    | "screen"
    | "service"
    | "worker";
}

export interface FeatureHowToUse {
  prerequisites: readonly string[];
  navigationPath: string;
  steps: readonly string[];
  expectedBehaviour: string;
  expectedSuccessResult: string;
  qaValidationPoints: readonly string[];
}

export interface FeatureTestingInfo {
  canTestNow: boolean;
  entryPoint: string;
  requiredSetup: readonly string[];
  exampleInputs: readonly string[];
  expectedOutputs: readonly string[];
}

export interface FeatureStatusRecord {
  area: FeatureArea;
  assignedModules: readonly string[];
  blockers: readonly string[];
  components: readonly string[];
  connectedModules: readonly string[];
  completedDate?: string;
  dependencies: readonly string[];
  description: string;
  endpoints: readonly string[];
  files: readonly string[];
  howToUse?: FeatureHowToUse;
  id: string;
  implementationStatus: string;
  name: string;
  percentComplete?: number;
  relationship: readonly FeatureRelationshipStep[];
  remainingWork: readonly string[];
  routes: readonly string[];
  screens: readonly string[];
  sharedUi: readonly string[];
  stateConnections: readonly string[];
  status: FeatureStatus;
  testing: FeatureTestingInfo;
}

export const featureStatusLabels: Record<FeatureStatus, string> = {
  blocked: "Blocked",
  completed: "Completed",
  in_progress: "In Progress",
  not_started: "Not Started",
  planned: "Planned",
};

export const featureStatusRegistry: readonly FeatureStatusRecord[] = [
  {
    area: "frontend",
    assignedModules: ["frontend/src/pages/SetupPage.tsx", "frontend/src/setupWizardCopy.ts"],
    blockers: [],
    components: ["SetupPage", "Button", "Alert", "FormField", "TextInput"],
    connectedModules: ["Setup status API", "Gmail OAuth start API"],
    completedDate: "2026-07-05",
    dependencies: ["GET /setup/status", "GET /auth/gmail"],
    description:
      "Local-first first-run setup shell that guides provider choice, classification mode selection, and Gmail read-only OAuth start.",
    endpoints: ["GET /setup/status", "POST /setup", "GET /auth/gmail"],
    files: ["frontend/src/pages/SetupPage.tsx", "frontend/src/setupWizardCopy.ts"],
    howToUse: {
      expectedBehaviour:
        "The page loads provider defaults, recommends a classification mode, and exposes a Google authorization link when OAuth starts.",
      expectedSuccessResult:
        "The Gmail section reports connected after the callback status says Gmail is connected.",
      navigationPath: "Primary navigation -> Setup",
      prerequisites: ["Backend running locally", "Google OAuth client configured by the user"],
      qaValidationPoints: [
        "The requested Gmail scope is gmail.readonly.",
        "No client secret or token appears in the UI.",
        "Recommended classification mode matches the selected LLM provider.",
      ],
      steps: [
        "Open /setup.",
        "Review the provider and classification mode cards.",
        "Select the recommended classification mode if it is not already selected.",
        "Press Start Gmail OAuth and verify the Continue to Google link appears.",
      ],
    },
    id: "frontend-setup-shell",
    implementationStatus: "Implemented in the Phase 0 frontend shell and covered by route tests.",
    name: "First-run setup shell",
    relationship: [
      { label: "Setup", type: "screen" },
      { label: "SetupPage", type: "component" },
      { label: "GET /setup/status", type: "api" },
      { label: "setup router", type: "controller" },
      { label: "SetupStatusService", type: "service" },
      { label: "Runtime settings", type: "database" },
    ],
    remainingWork: [],
    routes: ["/setup"],
    screens: ["Setup"],
    sharedUi: ["Button", "Alert", "FormField", "TextInput"],
    stateConnections: ["Local setup form state", "Fetched setup status"],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "/setup",
      exampleInputs: ["LLM provider: Ollama", "Classification mode: local"],
      expectedOutputs: ["Setup checklist renders", "Gmail OAuth link exposes gmail.readonly scope"],
      requiredSetup: ["Mock or running backend setup endpoints"],
    },
  },
  {
    area: "frontend",
    assignedModules: ["frontend/src/pages/DashboardPage.tsx", "frontend/src/components/charts"],
    blockers: [],
    components: ["DashboardPage", "ChartPanel"],
    connectedModules: ["Future metrics API"],
    completedDate: "2026-07-05",
    dependencies: ["Future metrics endpoints"],
    description:
      "Empty deterministic dashboard route with URL-backed filter placeholders and chart empty states ready for metrics integration.",
    endpoints: ["GET /metrics/summary", "GET /metrics/rates", "GET /metrics/funnel"],
    files: ["frontend/src/pages/DashboardPage.tsx", "frontend/src/components/charts/ChartPanel.tsx"],
    howToUse: {
      expectedBehaviour:
        "The dashboard renders placeholders only and does not imply real metrics before deterministic endpoints exist.",
      expectedSuccessResult:
        "QA can confirm filters and metric cards are visible without fabricated application counts.",
      navigationPath: "Primary navigation -> Dashboard",
      prerequisites: ["Frontend dev server"],
      qaValidationPoints: [
        "Metric cards say Pending.",
        "Chart empty state explains metrics are not available yet.",
        "No LLM-generated dashboard counts appear.",
      ],
      steps: [
        "Open /dashboard.",
        "Review the dashboard filter placeholders.",
        "Confirm the chart foundation empty state is visible.",
      ],
    },
    id: "frontend-dashboard-shell",
    implementationStatus: "Implemented as a Phase 0 shell with no fabricated metrics.",
    name: "Dashboard route shell",
    relationship: [
      { label: "Dashboard", type: "screen" },
      { label: "DashboardPage", type: "component" },
      { label: "GET /metrics/summary", type: "api" },
      { label: "metrics router", type: "controller" },
      { label: "MetricsService", type: "service" },
      { label: "applications", type: "database" },
    ],
    remainingWork: [],
    routes: ["/dashboard"],
    screens: ["Dashboard"],
    sharedUi: ["ChartPanel"],
    stateConnections: ["Future route query filters"],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "/dashboard",
      exampleInputs: ["No application data required"],
      expectedOutputs: ["Dashboard shell renders", "Metric values remain Pending"],
      requiredSetup: ["Frontend dev server"],
    },
  },
  {
    area: "frontend",
    assignedModules: ["frontend/src/components/SyncStatusPanel.tsx"],
    blockers: [],
    components: ["SyncStatusPanel", "Button", "Alert"],
    connectedModules: ["Sync API"],
    completedDate: "2026-07-05",
    dependencies: ["GET /sync/status", "POST /sync"],
    description:
      "Overview panel that displays manual Gmail sync state, safe progress counts, cursor recovery, and the manual Sync now action.",
    endpoints: ["GET /sync/status", "POST /sync"],
    files: ["frontend/src/components/SyncStatusPanel.tsx"],
    howToUse: {
      expectedBehaviour:
        "The panel fetches the latest sync status, starts a manual sync on request, and polls until a running sync completes.",
      expectedSuccessResult:
        "A successful run shows raw email, provider message, page counts, and finished timestamp.",
      navigationPath: "Primary navigation -> Overview -> Gmail sync progress",
      prerequisites: ["Gmail connected", "Backend sync routes available"],
      qaValidationPoints: [
        "Status API errors are displayed as public-safe messages.",
        "The sync button is disabled while a sync is running.",
        "Progress counts update after polling returns a completed run.",
      ],
      steps: [
        "Open /.",
        "Find Gmail sync progress.",
        "Press Sync now.",
        "Wait for the panel to update from running to succeeded or failed.",
      ],
    },
    id: "frontend-sync-status-panel",
    implementationStatus: "Implemented and covered by mocked API tests.",
    name: "Manual sync status panel",
    relationship: [
      { label: "Overview", type: "screen" },
      { label: "SyncStatusPanel", type: "component" },
      { label: "POST /sync", type: "api" },
      { label: "sync router", type: "controller" },
      { label: "SyncService", type: "service" },
      { label: "raw_emails", type: "database" },
      { label: "Polling", type: "worker" },
      { label: "Overview panel refresh", type: "frontend_update" },
    ],
    remainingWork: [],
    routes: ["/"],
    screens: ["Overview"],
    sharedUi: ["Button", "Alert"],
    stateConnections: ["Fetched sync status", "Manual sync request state", "Polling timer"],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "/",
      exampleInputs: ["Click Sync now", "Mock GET /sync/status running then succeeded"],
      expectedOutputs: ["Sync is running", "Last sync succeeded", "Formatted counts"],
      requiredSetup: ["Configured Gmail connection for live testing or mocked sync API"],
    },
  },
  {
    area: "frontend",
    assignedModules: ["frontend/src/components/SyncStatusPanel.tsx", "backend/app/services/sync_service.py"],
    blockers: ["Live Gmail test data is not available in this worktree"],
    components: ["SyncStatusPanel"],
    connectedModules: ["Sync runtime", "Gmail provider adapter"],
    dependencies: ["Gmail OAuth", "Sync API", "EmailProvider adapter"],
    description:
      "Polish pass for live manual sync behaviour once real Gmail credentials and a populated local database are available.",
    endpoints: ["POST /sync", "GET /sync/status"],
    files: ["frontend/src/components/SyncStatusPanel.tsx", "backend/app/services/sync_service.py"],
    id: "frontend-sync-live-hardening",
    implementationStatus: "In progress: mocked behaviour is covered; live mailbox QA remains.",
    name: "Sync orchestration UI hardening",
    percentComplete: 70,
    relationship: [
      { label: "Overview", type: "screen" },
      { label: "SyncStatusPanel", type: "component" },
      { label: "POST /sync", type: "api" },
      { label: "sync router", type: "controller" },
      { label: "SyncService", type: "service" },
      { label: "email_sync_state", type: "database" },
    ],
    remainingWork: [
      "Exercise the full flow with real Gmail Testing mode credentials.",
      "Add QA notes for expired-cursor recovery when real provider history IDs expire.",
    ],
    routes: ["/"],
    screens: ["Overview"],
    sharedUi: ["Button", "Alert"],
    stateConnections: ["Manual sync state", "Polling timer"],
    status: "in_progress",
    testing: {
      canTestNow: true,
      entryPoint: "/",
      exampleInputs: ["Mocked running sync response", "Mocked completed sync response"],
      expectedOutputs: ["Button disables while running", "Counts refresh after completion"],
      requiredSetup: ["Mock API responses for automated tests", "Gmail credentials for live QA"],
    },
  },
  {
    area: "backend",
    assignedModules: ["backend/app/api/setup.py", "backend/app/services/setup_status.py"],
    blockers: [],
    components: [],
    connectedModules: ["SetupPage"],
    completedDate: "2026-07-05",
    dependencies: ["pydantic-settings", "Provider registry"],
    description:
      "Typed setup status and setup submission routes for first-run provider and classification-mode configuration.",
    endpoints: ["GET /setup/status", "POST /setup"],
    files: ["backend/app/api/setup.py", "backend/app/services/setup_status.py", "backend/app/models/setup.py"],
    howToUse: {
      expectedBehaviour:
        "The backend returns non-secret setup state and validates setup submissions without persisting secrets.",
      expectedSuccessResult:
        "The frontend can render setup progress and recommended classification mode from typed responses.",
      navigationPath: "API client -> GET /setup/status",
      prerequisites: ["Backend process running"],
      qaValidationPoints: [
        "Response includes no secret values.",
        "Azure OpenAI recommends hybrid mode when mode is omitted.",
        "Ollama recommends local mode when mode is omitted.",
      ],
      steps: [
        "Call GET /setup/status.",
        "Submit POST /setup with a provider selection.",
        "Confirm the response remains public-safe and typed.",
      ],
    },
    id: "backend-setup-api",
    implementationStatus: "Implemented with Pydantic DTOs and thin FastAPI routes.",
    name: "Setup wizard API",
    relationship: [
      { label: "Setup", type: "screen" },
      { label: "SetupPage", type: "component" },
      { label: "GET /setup/status", type: "api" },
      { label: "setup router", type: "controller" },
      { label: "SetupStatusService", type: "service" },
      { label: "Settings", type: "database" },
    ],
    remainingWork: [],
    routes: [],
    screens: ["Setup"],
    sharedUi: [],
    stateConnections: [],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "GET /setup/status",
      exampleInputs: ["llm_provider=ollama", "classification_mode omitted"],
      expectedOutputs: ["recommended_classification_mode=local", "setup_complete flag"],
      requiredSetup: ["Backend app test client"],
    },
  },
];
