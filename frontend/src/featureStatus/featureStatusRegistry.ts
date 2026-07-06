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
  {
    area: "backend",
    assignedModules: ["backend/app/api/auth.py", "backend/app/services/gmail_auth.py"],
    blockers: [],
    components: ["SetupPage"],
    connectedModules: ["First-run setup shell", "GmailEmailProvider", "SecretStore"],
    completedDate: "2026-07-05",
    dependencies: ["Gmail OAuth", "SecretStore", "EmailConnectionRepository"],
    description:
      "Gmail read-only OAuth start and callback API that issues provider authorization URLs, validates state, stores token material through the configured secret store, and persists only non-secret connection metadata.",
    endpoints: ["GET /auth/gmail", "GET /auth/gmail/callback"],
    files: ["backend/app/api/auth.py", "backend/app/services/gmail_auth.py", "backend/app/providers/email/gmail.py"],
    howToUse: {
      expectedBehaviour:
        "The start endpoint returns a Google authorization URL with gmail.readonly, and the callback exchanges the code only after state validation.",
      expectedSuccessResult:
        "A successful callback returns an EmailConnection DTO without exposing OAuth tokens or client secrets.",
      navigationPath: "API client -> GET /auth/gmail -> GET /auth/gmail/callback",
      prerequisites: ["Backend running", "User-owned Google OAuth client configured", "Secret store configured"],
      qaValidationPoints: [
        "Authorization start returns only the read-only Gmail scope.",
        "Invalid OAuth state returns a typed public-safe 400 error.",
        "Callback responses contain connection metadata but no token material.",
      ],
      steps: [
        "Call GET /auth/gmail.",
        "Open the returned authorization URL in a browser.",
        "Complete Google authorization with the user-owned OAuth client.",
        "Call GET /auth/gmail/callback with the returned code and state.",
      ],
    },
    id: "backend-gmail-oauth-api",
    implementationStatus:
      "Implemented with thin FastAPI auth routes, state validation, provider abstraction, and secret-store-backed token handling.",
    name: "Gmail read-only OAuth API",
    relationship: [
      { label: "Setup", type: "screen" },
      { label: "SetupPage", type: "component" },
      { label: "GET /auth/gmail", type: "api" },
      { label: "auth router", type: "controller" },
      { label: "GmailAuthService", type: "service" },
      { label: "email_connections", type: "database" },
    ],
    remainingWork: [],
    routes: [],
    screens: ["Setup"],
    sharedUi: [],
    stateConnections: [],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "GET /auth/gmail",
      exampleInputs: ["Configured Gmail client id", "Valid OAuth state", "Callback code from Google"],
      expectedOutputs: ["Authorization URL", "gmail.readonly scope", "EmailConnection metadata"],
      requiredSetup: ["Backend app test client or configured local backend", "User-owned Google OAuth client"],
    },
  },
  {
    area: "backend",
    assignedModules: ["backend/app/api/sync.py", "backend/app/services/sync_service.py"],
    blockers: [],
    components: ["SyncStatusPanel"],
    connectedModules: ["Overview page", "GmailEmailProvider", "Email repositories", "Sync state repositories"],
    completedDate: "2026-07-05",
    dependencies: ["Gmail OAuth", "raw_emails", "email_sync_state", "email_backfill_state"],
    description:
      "Manual email sync API that resolves the configured Gmail connection, runs full backfill or incremental sync as needed, reports progress, prevents concurrent runs, and keeps sync state public-safe.",
    endpoints: ["POST /sync", "GET /sync/status"],
    files: [
      "backend/app/api/sync.py",
      "backend/app/services/sync_service.py",
      "backend/app/db/repositories/sync_state.py",
      "backend/app/db/repositories/backfill_state.py",
    ],
    howToUse: {
      expectedBehaviour:
        "POST /sync starts one manual run, while GET /sync/status returns idle, running, succeeded, or failed progress without exposing provider payloads.",
      expectedSuccessResult:
        "A successful run records metadata, retained candidate bodies, filter decisions, page counts, message counts, and cursor progress.",
      navigationPath: "API client -> POST /sync and GET /sync/status",
      prerequisites: ["Backend running", "Gmail connected", "Writable local SQLite database"],
      qaValidationPoints: [
        "A second concurrent POST /sync returns a typed 409 error.",
        "No raw email body or OAuth token appears in status output.",
        "Status counts reconcile with the persisted sync run state.",
      ],
      steps: [
        "Connect Gmail through the setup OAuth flow.",
        "Call POST /sync.",
        "Poll GET /sync/status while the run is active.",
        "Confirm the final status includes provider, account, mode, timestamps, and counts.",
      ],
    },
    id: "backend-manual-sync-api",
    implementationStatus:
      "Implemented with a configured sync runtime, in-process run lock, resumable backfill state, incremental cursor state, and public API errors.",
    name: "Manual sync API",
    relationship: [
      { label: "Overview", type: "screen" },
      { label: "SyncStatusPanel", type: "component" },
      { label: "POST /sync", type: "api" },
      { label: "sync router", type: "controller" },
      { label: "EmailSyncService", type: "service" },
      { label: "raw_emails", type: "database" },
      { label: "email_sync_state", type: "database" },
      { label: "email_backfill_state", type: "database" },
      { label: "APScheduler sync-on-open", type: "background_job" },
      { label: "Status polling", type: "worker" },
      { label: "SyncStatusPanel refresh", type: "frontend_update" },
    ],
    remainingWork: [],
    routes: [],
    screens: ["Overview"],
    sharedUi: [],
    stateConnections: [],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "POST /sync",
      exampleInputs: ["Connected Gmail account", "Existing expired cursor", "Fresh metadata page"],
      expectedOutputs: ["EmailSyncStatus response", "Public-safe sync errors", "Updated raw_emails and sync cursors"],
      requiredSetup: ["Backend app test client with mocked provider", "Gmail credentials for live QA"],
    },
  },
  {
    area: "backend",
    assignedModules: ["backend/app/api/wipe_data.py", "backend/app/services/wipe_data.py"],
    blockers: [],
    components: [],
    connectedModules: ["Local data settings", "SQLite data directory", "Derived artifact cleanup"],
    completedDate: "2026-07-05",
    dependencies: ["AppSettings", "Configured local data paths"],
    description:
      "Safety-checked local data deletion endpoint that requires the exact confirmation phrase, preflights configured filesystem targets, and removes local database and derived artifacts without touching unsafe paths.",
    endpoints: ["POST /local-data/wipe"],
    files: ["backend/app/api/wipe_data.py", "backend/app/services/wipe_data.py", "backend/app/models/wipe_data.py"],
    howToUse: {
      expectedBehaviour:
        "The route validates the confirmation phrase and refuses unsafe configured targets before any deletion happens.",
      expectedSuccessResult:
        "The response reports status=wiped plus deleted and missing local paths, with no secrets or private email content in the body.",
      navigationPath: "API client -> POST /local-data/wipe",
      prerequisites: ["Backend running", "Disposable local app data or isolated test directory"],
      qaValidationPoints: [
        "Missing or incorrect confirmation phrase is rejected by request validation.",
        "Unsafe configured targets return a typed 400 error and delete nothing.",
        "Successful responses list only local filesystem paths, not email content.",
      ],
      steps: [
        "Create an isolated test data directory.",
        "Point the backend settings at that directory.",
        "Call POST /local-data/wipe with confirmation_phrase=wipe-local-data.",
        "Confirm the configured local database and derived artifacts are removed.",
      ],
    },
    id: "backend-local-data-wipe-api",
    implementationStatus:
      "Implemented with a thin FastAPI route, typed request and response DTOs, exact confirmation validation, and service-level safety preflight.",
    name: "Local data wipe API",
    relationship: [
      { label: "Developer API", type: "screen" },
      { label: "POST /local-data/wipe", type: "api" },
      { label: "local-data router", type: "controller" },
      { label: "WipeDataService", type: "service" },
      { label: "SQLite database file", type: "database" },
    ],
    remainingWork: [],
    routes: [],
    screens: ["Developer API"],
    sharedUi: [],
    stateConnections: [],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "POST /local-data/wipe",
      exampleInputs: ["confirmation_phrase=wipe-local-data", "Isolated SQLite test path"],
      expectedOutputs: ["status=wiped", "deleted_paths list", "missing_paths list"],
      requiredSetup: ["Backend app test client", "Disposable local data directory"],
    },
  },
];
