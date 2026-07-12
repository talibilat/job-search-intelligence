export type FeatureArea = "frontend" | "backend";

export type FeatureStatus =
  "blocked" | "completed" | "in_progress" | "not_started" | "planned";

export interface FeatureRelationshipStep {
  label: string;
  type:
    | "api"
    | "background_job"
    | "component"
    | "controller"
    | "database"
    | "dto_model"
    | "frontend_update"
    | "module"
    | "planned_api"
    | "queue"
    | "runtime_config"
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

const dashboardMetricEndpoints = [
  "GET /metrics/summary",
  "GET /metrics/rates",
  "GET /metrics/funnel",
  "GET /metrics/breakdown",
  "GET /metrics/timeseries",
  "GET /metrics/response-rate-trend",
  "GET /metrics/diagnostics",
] as const;

const dashboardMetricLoadStates = [
  "Metrics summary load state",
  "Metrics rates load state",
  "Metrics funnel load state",
  "Metrics breakdown load state",
  "Metrics trend load state",
  "Metrics diagnostics load state",
] as const;

export const featureStatusRegistry: readonly FeatureStatusRecord[] = [
  {
    area: "frontend",
    assignedModules: [
      "frontend/src/pages/SetupPage.tsx",
      "frontend/src/setupWizardCopy.ts",
    ],
    blockers: [],
    components: ["SetupPage", "Button", "Alert", "FormField", "TextInput"],
    connectedModules: ["Setup status API", "Setup submit API", "Gmail OAuth start API"],
    completedDate: "2026-07-05",
    dependencies: ["GET /setup/status", "POST /setup", "GET /auth/gmail"],
    description:
      "Local-first first-run setup shell that guides provider choice, classification mode selection, and Gmail read-only OAuth start.",
    endpoints: ["GET /setup/status", "POST /setup", "GET /auth/gmail"],
    files: [
      "frontend/src/pages/SetupPage.tsx",
      "frontend/src/setupWizardCopy.ts",
    ],
    howToUse: {
      expectedBehaviour:
        "The page loads provider defaults, saves non-secret setup choices, recommends a classification mode, and exposes a Google authorization link when OAuth starts.",
      expectedSuccessResult:
        "The Gmail section reports connected after the callback status says Gmail is connected.",
      navigationPath: "Primary navigation -> Setup",
      prerequisites: [
        "Backend running locally",
        "Google OAuth client configured by the user",
      ],
      qaValidationPoints: [
        "The requested Gmail scope is gmail.readonly.",
        "No client secret or token appears in the UI.",
        "Recommended classification mode matches the selected LLM provider.",
        "Saving setup choices posts only non-secret provider and classification settings.",
      ],
      steps: [
        "Open /setup.",
        "Review the provider and classification mode cards.",
        "Select and save the desired classification mode.",
        "Press Start Gmail OAuth and verify the Continue to Google link appears.",
      ],
    },
    id: "frontend-setup-shell",
    implementationStatus:
      "Implemented in the Phase 0 frontend shell and covered by route tests.",
    name: "First-run setup shell",
    relationship: [
      { label: "Setup", type: "screen" },
      { label: "SetupPage", type: "component" },
      { label: "GET /setup/status", type: "api" },
      { label: "POST /setup", type: "api" },
      { label: "setup router", type: "controller" },
      { label: "SetupStatusService", type: "service" },
      { label: "Runtime settings", type: "runtime_config" },
    ],
    remainingWork: [
      "Implement the Phase 5 hybrid RAG route, grounded response flow, persisted history, semantic retrieval, and chat UI before exposing chat as runnable.",
    ],
    routes: ["/setup"],
    screens: ["Setup"],
    sharedUi: ["Button", "Alert", "FormField", "TextInput"],
    stateConnections: ["Local setup form state", "Fetched setup status"],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "/setup",
      exampleInputs: ["LLM provider: Ollama", "Classification mode: local"],
      expectedOutputs: [
        "Setup checklist renders",
        "Setup choices save through POST /setup",
        "Gmail OAuth link exposes gmail.readonly scope",
      ],
      requiredSetup: ["Mock or running backend setup endpoints"],
    },
  },
  {
    area: "frontend",
    assignedModules: [
      "frontend/src/pages/DashboardPage.tsx",
      "frontend/src/components/charts",
    ],
    blockers: [],
    components: ["DashboardPage", "ChartPanel"],
    connectedModules: [
      "Metrics summary API",
      ...dashboardMetricEndpoints.slice(1),
    ],
    completedDate: "2026-07-05",
    dependencies: dashboardMetricEndpoints,
    description:
      "Deterministic chart-only dashboard route with overview, funnel, trends, segmentation, and diagnostics charts powered by metrics APIs and local SQLite application data.",
    endpoints: dashboardMetricEndpoints,
    files: [
      "frontend/src/pages/DashboardPage.tsx",
      "frontend/src/components/charts/ChartPanel.tsx",
    ],
    howToUse: {
      expectedBehaviour:
        "The dashboard renders only deterministic Recharts chart panels. Empty chart states point users back to the missing setup, sync, classification, or aggregation stage instead of showing setup controls or placeholder metrics.",
      expectedSuccessResult:
        "QA can confirm every visible dashboard surface is a chart backed by deterministic metrics APIs and no LLM-generated or fabricated counts appear.",
      navigationPath: "Primary navigation -> Dashboard",
      prerequisites: ["Frontend dev server"],
      qaValidationPoints: [
        "Overview charts load from GET /metrics/summary and GET /metrics/rates.",
        "The funnel chart loads from GET /metrics/funnel.",
        "Trend charts load from GET /metrics/timeseries and GET /metrics/response-rate-trend.",
        "Segmentation charts load from GET /metrics/breakdown.",
        "Diagnostics charts load from GET /metrics/diagnostics.",
        "Chart empty states explain the missing upstream pipeline stage.",
        "Dashboard pages do not show setup controls, sync controls, feature inventory, or placeholder metric cards.",
        "No LLM-generated dashboard counts appear.",
      ],
      steps: [
        "Open /dashboard.",
        "Confirm the overview charts load from GET /metrics/summary and GET /metrics/rates.",
        "Confirm the application funnel chart loads from GET /metrics/funnel.",
        "Confirm the selected breakdown chart loads from GET /metrics/breakdown.",
        "Confirm the trend charts load from timeseries metrics endpoints.",
        "Confirm the diagnostic comparison charts load from GET /metrics/diagnostics.",
        "Confirm empty charts explain whether setup, sync, classification, or aggregation is missing.",
      ],
    },
    id: "frontend-dashboard-shell",
    implementationStatus:
      "Implemented as the current chart-only dashboard workspace for deterministic metrics slices; broader roadmap coverage remains governed by the PRD question tiers.",
    name: "Dashboard chart workspace",
    relationship: [
      { label: "Dashboard", type: "screen" },
      { label: "DashboardPage", type: "component" },
      { label: "GET /metrics/summary", type: "api" },
      { label: "GET /metrics/rates", type: "api" },
      { label: "metrics router", type: "controller" },
      { label: "MetricsSummaryService", type: "service" },
      { label: "MetricsRatesService", type: "service" },
      { label: "applications", type: "database" },
      { label: "application_events", type: "database" },
    ],
    remainingWork: [],
    routes: ["/dashboard"],
    screens: ["Dashboard"],
    sharedUi: ["ChartPanel"],
    stateConnections: [...dashboardMetricLoadStates, "Route query filters"],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "/dashboard",
      exampleInputs: ["No application data required"],
      expectedOutputs: [
        "Dashboard chart workspace renders",
        "Overview charts render deterministic values or actionable empty states",
        "Application funnel chart renders deterministic values or an actionable empty state",
        "Segmentation charts render deterministic values or actionable empty states",
        "Trend charts render deterministic values or actionable empty states",
        "Diagnostics charts render deterministic values or actionable empty states",
      ],
      requiredSetup: ["Frontend dev server"],
    },
  },
  {
    area: "frontend",
    assignedModules: ["frontend/src/pages/Insights.tsx"],
    blockers: [],
    components: ["Insights"],
    connectedModules: [
      "Insights API",
      "Deterministic application evidence",
    ],
    completedDate: "2026-07-09",
    dependencies: [
      "GET /insights",
      "POST /insights/regenerate",
      "applications",
      "raw_emails",
    ],
    description:
      "Backend-backed insights page that loads all Tier 5 cached narrative insights, shows stale cache state, citations, and regeneration cost, and regenerates one insight at a time through the user-triggered insights API without making LLM counts authoritative.",
    endpoints: ["GET /insights", "POST /insights/regenerate"],
    files: ["frontend/src/pages/Insights.tsx"],
    howToUse: {
      expectedBehaviour:
        "The page loads cached Tier 5 insights, shows each supported insight card, surfaces stale cache state and citation IDs, and can request per-insight regeneration with estimated and actual cost returned by the backend.",
      expectedSuccessResult:
        "QA can confirm cached insights render with model metadata and citations, regeneration is explicit per insight, cost is visible after regeneration, and dashboard counts are not produced by the LLM.",
      navigationPath: "Primary navigation -> Insights",
      prerequisites: ["Frontend dev server"],
      qaValidationPoints: [
        "The page calls GET /insights on load through the generated API client.",
        "Each regenerate action calls POST /insights/regenerate with the selected insight type.",
        "A successful regenerate response surfaces estimated cost, actual cost, and actual token count when available.",
        "The page shows backend errors without exposing email content or provider payloads.",
      ],
      steps: [
        "Open /insights.",
        "Read the Tier 5 insight cards from Q-40 through Q-46.",
        "Seed or mock cached insights and confirm stale state plus citation IDs render.",
        "Press a regenerate action and confirm the returned insight plus cost summary replaces that card.",
      ],
    },
    id: "frontend-insights-shell",
    implementationStatus:
      "Implemented as the Phase 4 cached insights frontend backed by GET /insights and POST /insights/regenerate.",
    name: "Insights cached narrative view",
    relationship: [
      { label: "Insights", type: "screen" },
      { label: "Insights", type: "component" },
      { label: "GET /insights", type: "api" },
      { label: "POST /insights/regenerate", type: "api" },
      { label: "insights router", type: "controller" },
      { label: "InsightsService", type: "service" },
      { label: "insights", type: "database" },
      { label: "applications", type: "database" },
    ],
    remainingWork: [],
    routes: ["/insights"],
    screens: ["Insights"],
    sharedUi: ["Button", "Alert"],
    stateConnections: ["Cached insight state", "Per-insight regeneration request state"],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "/insights",
      exampleInputs: ["Cached Tier 5 insights"],
      expectedOutputs: [
        "Tier 5 insight cards render",
        "Stale state and citation IDs render when present",
        "Per-insight regenerate actions are available",
        "Regeneration cost appears after a successful regenerate response",
      ],
      requiredSetup: ["Frontend dev server", "Mock or running insights API"],
    },
  },
  {
    area: "frontend",
    assignedModules: [],
    blockers: [],
    components: [],
    connectedModules: [
      "Future chat API",
      "Future hybrid RAG agent",
      "Future chat history store",
    ],
    dependencies: [
      "Future POST /chat",
      "Future GET /chat/history",
      "Future semantic retrieval",
    ],
    description:
      "Phase 5 chat is intentionally unavailable in the product UI until streaming, persisted history, retrieval, and grounding checks are implemented.",
    endpoints: [],
    files: [],
    howToUse: {
      expectedBehaviour:
        "Feature Status documents that chat is not runnable yet; chat is hidden from primary navigation and direct /chat shows the unavailable Phase 5 page.",
      expectedSuccessResult:
        "QA can confirm chat is absent from primary navigation and direct /chat renders the unavailable Phase 5 page instead of presenting a broken shell.",
      navigationPath: "Feature Status -> Advanced developer inventory",
      prerequisites: ["Frontend dev server", "Feature Status page"],
      qaValidationPoints: [
        "Primary navigation does not include Chat.",
        "Direct /chat does not render a placeholder composer.",
        "No backend chat request, provider call, or retrieval action is triggered from the product UI.",
      ],
      steps: [
        "Open Feature Status and expand the advanced developer inventory.",
        "Confirm Chat is listed as unavailable Phase 5 work rather than a runnable page.",
        "Open /chat and confirm the unavailable Phase 5 page renders instead of a chat composer.",
      ],
    },
    id: "frontend-chat-unavailable",
    implementationStatus:
      "Unavailable in product routes; streaming chat, persisted history, retrieval, and agent behaviour remain deferred to Phase 5.",
    name: "Chat unavailable marker",
    relationship: [
      { label: "Future POST /chat", type: "planned_api" },
      { label: "Future GET /chat/history", type: "planned_api" },
      { label: "chat router", type: "controller" },
      { label: "ChatService", type: "service" },
      { label: "chat_messages", type: "database" },
      { label: "email_chunks", type: "database" },
    ],
    remainingWork: [],
    routes: [],
    screens: [],
    sharedUi: [],
    stateConnections: [],
    status: "planned",
    testing: {
      canTestNow: true,
      entryPoint: "/features",
      exampleInputs: ["Direct /chat navigation", "Primary navigation"],
      expectedOutputs: [
        "Chat is absent from primary navigation",
        "Direct /chat renders the unavailable Phase 5 page",
        "No chat response is generated from product UI",
      ],
      requiredSetup: ["Frontend dev server", "Feature Status page"],
    },
  },
  {
    area: "frontend",
    assignedModules: [
      "frontend/src/pages/FeatureStatusDashboard.tsx",
      "frontend/src/featureStatus/featureStatusRegistry.ts",
    ],
    blockers: [],
    components: ["FeatureStatusDashboard", "Tabs", "FormField", "TextInput"],
    connectedModules: [
      "Feature status registry",
      "Frontend topology summary",
      "Backend topology summary",
    ],
    completedDate: "2026-07-06",
    dependencies: ["Feature status registry", "Route query strings"],
    description:
      "Registry-backed developer inventory page that maps implemented frontend and backend surfaces, searchable QA entry points, and topology summaries.",
    endpoints: [],
    files: [
      "frontend/src/pages/FeatureStatusDashboard.tsx",
      "frontend/src/featureStatus/featureStatusRegistry.ts",
      "frontend/src/App.tsx",
    ],
    howToUse: {
      expectedBehaviour:
        "The dashboard renders registry records for implemented and in-progress surfaces, keeps filters in the route query string, and distinguishes implemented endpoints from planned dependencies.",
      expectedSuccessResult:
        "QA can share a filtered /features URL and inspect route, component, relationship, topology, and how-to-use details for each registered surface.",
      navigationPath: "Primary navigation -> Feature Status",
      prerequisites: ["Frontend dev server"],
      qaValidationPoints: [
        "The /features route appears in the frontend topology summary.",
        "Search, status, testable, scope, and tab filters persist in route query strings.",
        "Frontend API integrations list only currently wired frontend calls, not planned future endpoints.",
      ],
      steps: [
        "Open /features.",
        "Search for feature status or filter the module scope to /features.",
        "Confirm this dashboard record lists FeatureStatusDashboard, topology summaries, filters, relationship mapping, and QA guidance.",
        "Copy the URL after changing filters and confirm the same filtered view reloads from the query string.",
      ],
    },
    id: "frontend-feature-status-dashboard",
    implementationStatus:
      "Implemented as a self-describing registry-backed frontend QA dashboard with URL-backed filters and topology summaries.",
    name: "Feature Status Dashboard inventory",
    relationship: [
      { label: "Feature Status", type: "screen" },
      { label: "FeatureStatusDashboard", type: "component" },
      { label: "Feature status registry", type: "module" },
      { label: "Frontend topology summary", type: "component" },
      { label: "Backend topology summary", type: "component" },
      { label: "Route query filters", type: "frontend_update" },
    ],
    remainingWork: [],
    routes: ["/features"],
    screens: ["Feature Status"],
    sharedUi: ["Tabs", "FormField", "TextInput"],
    stateConnections: [
      "Search filter query state",
      "Status filter query state",
      "Testable filter query state",
      "Scope filter query state",
      "Active tab query state",
    ],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "/features",
      exampleInputs: [
        "search=feature status",
        "scope=/features",
        "tab=backend",
      ],
      expectedOutputs: [
        "Feature status dashboard renders",
        "FeatureStatusDashboard appears in the registry cards",
        "Filtered views survive refresh through URLSearchParams",
      ],
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
    stateConnections: [
      "Fetched sync status",
      "Manual sync request state",
      "Polling timer",
    ],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "/",
      exampleInputs: [
        "Click Sync now",
        "Mock GET /sync/status running then succeeded",
      ],
      expectedOutputs: [
        "Sync is running",
        "Last sync succeeded",
        "Formatted counts",
      ],
      requiredSetup: [
        "Configured Gmail connection for live testing or mocked sync API",
      ],
    },
  },
  {
    area: "frontend",
    assignedModules: [
      "frontend/src/components/SyncStatusPanel.tsx",
      "backend/app/services/sync_service.py",
    ],
    blockers: ["Live Gmail test data is not available in this worktree"],
    components: ["SyncStatusPanel"],
    connectedModules: ["Sync runtime", "Gmail provider adapter"],
    dependencies: ["Gmail OAuth", "Sync API", "EmailProvider adapter"],
    description:
      "Polish pass for live manual sync behaviour once real Gmail credentials and a populated local database are available.",
    endpoints: ["POST /sync", "GET /sync/status"],
    files: [
      "frontend/src/components/SyncStatusPanel.tsx",
      "backend/app/services/sync_service.py",
    ],
    id: "frontend-sync-live-hardening",
    implementationStatus:
      "In progress: mocked behaviour is covered; live mailbox QA remains.",
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
      exampleInputs: [
        "Mocked running sync response",
        "Mocked completed sync response",
      ],
      expectedOutputs: [
        "Button disables while running",
        "Counts refresh after completion",
      ],
      requiredSetup: [
        "Mock API responses for automated tests",
        "Gmail credentials for live QA",
      ],
    },
  },
  {
    area: "backend",
    assignedModules: [
      "backend/app/api/health.py",
      "backend/app/models/health.py",
    ],
    blockers: [],
    components: [],
    connectedModules: ["FastAPI app shell", "Frontend OpenAPI generation"],
    completedDate: "2026-07-05",
    dependencies: ["FastAPI app factory"],
    description:
      "Minimal liveness endpoint that confirms the local FastAPI backend process is reachable without touching secrets, email data, or the database.",
    endpoints: ["GET /health"],
    files: [
      "backend/app/api/health.py",
      "backend/app/models/health.py",
      "backend/app/api/router.py",
    ],
    howToUse: {
      expectedBehaviour:
        "The route returns a typed status=ok response when the backend process is running and routable.",
      expectedSuccessResult:
        "QA and local setup checks can confirm backend liveness before exercising setup, sync, classification, or application APIs.",
      navigationPath: "API client -> GET /health",
      prerequisites: ["Backend process running locally"],
      qaValidationPoints: [
        "The response body is exactly the typed liveness shape with status=ok.",
        "The endpoint does not read or expose secrets, OAuth tokens, email content, or database rows.",
        "OpenAPI generation includes HealthResponse for frontend contract checks.",
      ],
      steps: [
        "Start the backend app.",
        "Call GET /health.",
        "Confirm the response is HTTP 200 with status=ok.",
      ],
    },
    id: "backend-health-check-api",
    implementationStatus:
      "Implemented as a Phase 0 liveness route with a typed Pydantic response model.",
    name: "Health check API",
    relationship: [
      { label: "Developer API", type: "screen" },
      { label: "GET /health", type: "api" },
      { label: "health router", type: "controller" },
      { label: "HealthResponse", type: "dto_model" },
      { label: "FastAPI runtime", type: "runtime_config" },
    ],
    remainingWork: [],
    routes: [],
    screens: ["Developer API"],
    sharedUi: [],
    stateConnections: [],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "GET /health",
      exampleInputs: ["No request body or query parameters"],
      expectedOutputs: ["HTTP 200", "status=ok"],
      requiredSetup: ["Backend app test client or running local backend"],
    },
  },
  {
    area: "backend",
    assignedModules: [
      "backend/app/api/setup.py",
      "backend/app/services/setup_status.py",
    ],
    blockers: [],
    components: [],
    connectedModules: ["SetupPage"],
    completedDate: "2026-07-05",
    dependencies: ["pydantic-settings", "Provider registry"],
    description:
      "Typed setup status and setup submission routes for first-run provider and classification-mode configuration.",
    endpoints: ["GET /setup/status", "POST /setup"],
    files: [
      "backend/app/api/setup.py",
      "backend/app/services/setup_status.py",
      "backend/app/models/setup.py",
    ],
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
    implementationStatus:
      "Implemented with Pydantic DTOs and thin FastAPI routes.",
    name: "Setup wizard API",
    relationship: [
      { label: "Setup", type: "screen" },
      { label: "SetupPage", type: "component" },
      { label: "GET /setup/status", type: "api" },
      { label: "setup router", type: "controller" },
      { label: "SetupStatusService", type: "service" },
      { label: "Settings", type: "runtime_config" },
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
      expectedOutputs: [
        "recommended_classification_mode=local",
        "setup_complete flag",
      ],
      requiredSetup: ["Backend app test client"],
    },
  },
  {
    area: "backend",
    assignedModules: [
      "backend/app/api/provider_config.py",
      "backend/app/services/provider_config.py",
    ],
    blockers: [
      "LLM health checks remain blocked until the config route is wired to a configured provider adapter.",
    ],
    components: ["SetupPage"],
    connectedModules: [
      "First-run setup shell",
      "ProviderRegistry",
      "LLM provider adapters",
    ],
    completedDate: "2026-07-05",
    dependencies: [
      "Provider registry",
      "AppSettings",
      "SecretStore metadata",
      "LLMProvider adapter",
    ],
    description:
      "Provider configuration API that exposes non-secret provider settings, validates provider updates, and recommends classification modes.",
    endpoints: ["GET /config/providers", "PUT /config/providers"],
    files: [
      "backend/app/api/provider_config.py",
      "backend/app/services/provider_config.py",
      "backend/app/services/llm_health.py",
      "backend/app/models/provider_config.py",
    ],
    howToUse: {
      expectedBehaviour:
        "The API returns only public provider metadata and applies validated in-process config updates while LLM health checks remain blocked.",
      expectedSuccessResult:
        "The setup UI can display supported providers and recommendations without exposing API keys or OAuth secrets.",
      navigationPath: "API client -> GET /config/providers",
      prerequisites: ["Backend running", "Configured provider registry"],
      qaValidationPoints: [
        "Provider responses include secret requirement refs but never secret values.",
        "Changing LLM provider updates the recommended classification mode when no explicit mode is provided.",
        "Invalid provider settings return typed validation or bad-request errors.",
      ],
      steps: [
        "Call GET /config/providers to inspect current provider choices.",
        "Call PUT /config/providers with a valid provider or model setting update.",
        "Do not treat POST /config/providers/llm/health as a successful QA path until the provider adapter dependency is wired.",
      ],
    },
    id: "backend-provider-config-api",
    implementationStatus:
      "Implemented with thin FastAPI config routes, Pydantic DTOs, registry validation, and provider recommendation logic; LLM health-check success remains blocked.",
    name: "Provider configuration API",
    relationship: [
      { label: "Setup", type: "screen" },
      { label: "SetupPage", type: "component" },
      { label: "GET /config/providers", type: "api" },
      { label: "PUT /config/providers", type: "api" },
      {
        label: "Future POST /config/providers/llm/health",
        type: "planned_api",
      },
      { label: "config router", type: "controller" },
      { label: "ProviderConfigService", type: "service" },
      { label: "AppSettings", type: "runtime_config" },
      { label: "LLM health check", type: "worker" },
    ],
    remainingWork: [
      "Wire POST /config/providers/llm/health to a real configured LLM provider adapter before marking the health-check path completed.",
    ],
    routes: [],
    screens: ["Setup"],
    sharedUi: [],
    stateConnections: [],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "GET /config/providers",
      exampleInputs: [
        "llm_provider=ollama",
        "ollama_chat_model=llama3.1",
        "classification_mode omitted",
      ],
      expectedOutputs: [
        "ProviderConfigResponse",
        "recommended_classification_mode=local for Ollama",
        "public-safe provider configuration response",
      ],
      requiredSetup: ["Backend app test client"],
    },
  },
  {
    area: "backend",
    assignedModules: [
      "backend/app/api/auth.py",
      "backend/app/services/gmail_auth.py",
    ],
    blockers: [],
    components: ["SetupPage"],
    connectedModules: [
      "First-run setup shell",
      "GmailEmailProvider",
      "SecretStore",
    ],
    completedDate: "2026-07-05",
    dependencies: ["Gmail OAuth", "SecretStore", "EmailConnectionRepository"],
    description:
      "Gmail read-only OAuth start and callback API that issues provider authorization URLs, validates state, stores token material through the configured secret store, and persists only non-secret connection metadata.",
    endpoints: ["GET /auth/gmail", "GET /auth/gmail/callback"],
    files: [
      "backend/app/api/auth.py",
      "backend/app/services/gmail_auth.py",
      "backend/app/providers/email/gmail.py",
    ],
    howToUse: {
      expectedBehaviour:
        "The start endpoint returns a Google authorization URL with gmail.readonly, and the callback exchanges the code only after state validation.",
      expectedSuccessResult:
        "A successful callback returns an EmailConnection DTO without exposing OAuth tokens or client secrets.",
      navigationPath:
        "API client -> GET /auth/gmail -> GET /auth/gmail/callback",
      prerequisites: [
        "Backend running",
        "User-owned Google OAuth client configured",
        "Secret store configured",
      ],
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
      exampleInputs: [
        "Configured Gmail client id",
        "Valid OAuth state",
        "Callback code from Google",
      ],
      expectedOutputs: [
        "Authorization URL",
        "gmail.readonly scope",
        "EmailConnection metadata",
      ],
      requiredSetup: [
        "Backend app test client or configured local backend",
        "User-owned Google OAuth client",
      ],
    },
  },
  {
    area: "backend",
    assignedModules: [
      "backend/app/api/classification.py",
      "backend/app/services/classification_estimate.py",
      "backend/app/services/classification_reprocessing.py",
      "backend/app/services/structured_extraction.py",
    ],
    blockers: [],
    components: [],
    connectedModules: [
      "ClassificationService",
      "StructuredExtractionService",
      "EmailRepository",
      "ClassificationRunRepository",
    ],
    completedDate: "2026-07-05",
    dependencies: [
      "retained raw_emails",
      "email_classifications",
      "classification_runs",
      "LLMProvider adapter",
    ],
    description:
      "Classification control API that estimates candidate volume and cost, reports deterministic reprocessing buckets, and runs retained-email classification batches with accounting.",
    endpoints: [
      "GET /classification/estimate",
      "GET /classification/reprocessing-plan",
      "POST /classification/run",
    ],
    files: [
      "backend/app/api/classification.py",
      "backend/app/services/classification_estimate.py",
      "backend/app/services/classification_reprocessing.py",
      "backend/app/services/structured_extraction.py",
      "backend/app/db/repositories/classification_run.py",
    ],
    howToUse: {
      expectedBehaviour:
        "The estimate and reprocessing-plan endpoints read local metadata without calling an LLM, while the run endpoint classifies retained candidates through the configured provider and stores accepted results plus run accounting.",
      expectedSuccessResult:
        "QA can confirm candidate counts, prompt/model version buckets, malformed counts, and token accounting reconcile with local repository data.",
      navigationPath:
        "API client -> GET /classification/estimate -> GET /classification/reprocessing-plan -> POST /classification/run",
      prerequisites: [
        "Backend running",
        "Retained candidate emails in local SQLite",
        "Configured LLM provider for POST /classification/run",
      ],
      qaValidationPoints: [
        "GET /classification/estimate does not expose email content or call the LLM provider.",
        "GET /classification/reprocessing-plan separates unclassified, stale-model, stale-prompt-version, and up-to-date buckets deterministically.",
        "POST /classification/run stores only accepted classifications and reports malformed outputs without writing application events.",
      ],
      steps: [
        "Seed or sync retained candidate emails into local SQLite.",
        "Call GET /classification/estimate and verify candidate and token estimates.",
        "Call GET /classification/reprocessing-plan and inspect prompt/model buckets.",
        "Call POST /classification/run with a configured LLM provider and verify classification run accounting.",
      ],
    },
    id: "backend-classification-control-api",
    implementationStatus:
      "Implemented with thin FastAPI classification routes, deterministic read-only planning helpers, structured extraction service orchestration, and run accounting persistence.",
    name: "Classification control API",
    relationship: [
      { label: "Developer API", type: "screen" },
      { label: "GET /classification/estimate", type: "api" },
      { label: "GET /classification/reprocessing-plan", type: "api" },
      { label: "POST /classification/run", type: "api" },
      { label: "classification router", type: "controller" },
      { label: "Classification estimate service", type: "service" },
      { label: "Classification reprocessing service", type: "service" },
      { label: "StructuredExtractionService", type: "service" },
      { label: "raw_emails", type: "database" },
      { label: "email_classifications", type: "database" },
      { label: "classification_runs", type: "database" },
      { label: "LLMProvider", type: "worker" },
    ],
    remainingWork: [],
    routes: [],
    screens: ["Developer API"],
    sharedUi: [],
    stateConnections: [],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "GET /classification/estimate",
      exampleInputs: [
        "Retained candidate rows",
        "classification_model=llama3.1",
        "classification_prompt_version=current",
      ],
      expectedOutputs: [
        "ClassificationPreRunEstimate",
        "ClassificationReprocessingPlan",
        "ClassificationRunResponse with token totals and malformed count",
      ],
      requiredSetup: [
        "Backend app test client",
        "Retained candidate fixtures",
        "Configured or mocked LLM provider for POST /classification/run",
      ],
    },
  },
  {
    area: "backend",
    assignedModules: [
      "backend/app/api/sync.py",
      "backend/app/services/sync_service.py",
    ],
    blockers: [],
    components: ["SyncStatusPanel"],
    connectedModules: [
      "Overview page",
      "GmailEmailProvider",
      "Email repositories",
      "Sync state repositories",
    ],
    completedDate: "2026-07-05",
    dependencies: [
      "Gmail OAuth",
      "raw_emails",
      "email_sync_state",
      "email_backfill_state",
    ],
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
      prerequisites: [
        "Backend running",
        "Gmail connected",
        "Writable local SQLite database",
      ],
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
      exampleInputs: [
        "Connected Gmail account",
        "Existing expired cursor",
        "Fresh metadata page",
      ],
      expectedOutputs: [
        "EmailSyncStatus response",
        "Public-safe sync errors",
        "Updated raw_emails and sync cursors",
      ],
      requiredSetup: [
        "Backend app test client with mocked provider",
        "Gmail credentials for live QA",
      ],
    },
  },
  {
    area: "backend",
    assignedModules: [
      "backend/app/api/applications.py",
      "backend/app/services/applications.py",
    ],
    blockers: [],
    components: ["DashboardPage"],
    connectedModules: [
      "Future deterministic dashboard",
      "ApplicationRepository",
      "ApplicationEventsService",
    ],
    completedDate: "2026-07-06",
    dependencies: ["applications", "application_events", "raw_emails"],
    description:
      "Application read API that lists canonical application records, returns one application detail row, and exposes the ordered event timeline from the local SQLite source of truth.",
    endpoints: [
      "GET /applications",
      "GET /applications/{id}",
      "GET /applications/{id}/events",
    ],
    files: [
      "backend/app/api/applications.py",
      "backend/app/services/applications.py",
      "backend/app/db/repositories/applications.py",
      "backend/app/models/records.py",
    ],
    howToUse: {
      expectedBehaviour:
        "The API returns deterministic application rows with composable filters, typed 404s for missing detail records, and ordered timeline events for existing applications.",
      expectedSuccessResult:
        "Dashboard and QA clients can inspect application status, source, sponsorship, work mode, salary, and event history without LLM-generated facts.",
      navigationPath:
        "API client -> GET /applications -> GET /applications/{id} -> GET /applications/{id}/events",
      prerequisites: [
        "Backend running",
        "SQLite database with aggregated applications and events",
      ],
      qaValidationPoints: [
        "List filters compose across status, source, sponsorship, date range, role, salary band, and work mode.",
        "Missing application IDs return the standard typed 404 error.",
        "Event timelines are ordered and reconcile with the application_events table.",
      ],
      steps: [
        "Seed or aggregate application records into local SQLite.",
        "Call GET /applications with and without filters.",
        "Call GET /applications/{id} for a returned application ID.",
        "Call GET /applications/{id}/events and confirm the event timeline order.",
      ],
    },
    id: "backend-application-read-api",
    implementationStatus:
      "Implemented with thin FastAPI routes, typed query validation, application detail service reads, and event timeline service reads.",
    name: "Application read API",
    relationship: [
      { label: "Dashboard", type: "screen" },
      { label: "DashboardPage", type: "component" },
      { label: "GET /applications", type: "api" },
      { label: "GET /applications/{id}", type: "api" },
      { label: "GET /applications/{id}/events", type: "api" },
      { label: "applications router", type: "controller" },
      { label: "ApplicationDetailService", type: "service" },
      { label: "ApplicationEventsService", type: "service" },
      { label: "applications", type: "database" },
      { label: "application_events", type: "database" },
    ],
    remainingWork: [],
    routes: [],
    screens: ["Dashboard", "Developer API"],
    sharedUi: [],
    stateConnections: [],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "GET /applications",
      exampleInputs: [
        "status=interview",
        "source=linkedin&work_mode=remote",
        "GET /applications/{id}/events for a seeded application ID",
      ],
      expectedOutputs: [
        "ApplicationRecord list",
        "ApplicationRecord detail response",
        "Ordered ApplicationEventRecord timeline or typed 404",
      ],
      requiredSetup: [
        "Backend app test client",
        "Application and event fixtures in local SQLite",
      ],
    },
  },
  {
    area: "backend",
    assignedModules: [
      "backend/app/api/applications.py",
      "backend/app/services/application_corrections.py",
      "backend/app/services/manual_edit.py",
      "backend/app/services/manual_merge.py",
    ],
    blockers: [],
    components: ["DashboardPage"],
    connectedModules: [
      "Future deterministic dashboard",
      "ApplicationCorrectionService",
      "ManualApplicationEditService",
      "ManualApplicationMergeService",
      "CorrectionRepository",
    ],
    completedDate: "2026-07-06",
    dependencies: [
      "applications",
      "application_events",
      "application_corrections",
      "raw_emails",
    ],
    description:
      "Manual correction API that audits user status edits, timeline event edits, and duplicate-application merges while locking corrected records from automatic overwrite.",
    endpoints: [
      "PATCH /applications/{application_id}/status",
      "PATCH /applications/{application_id}/events/{event_id}",
      "POST /applications/{application_id}/split",
      "POST /applications/{application_id}/merge",
    ],
    files: [
      "backend/app/api/applications.py",
      "backend/app/services/application_corrections.py",
      "backend/app/services/manual_edit.py",
      "backend/app/services/manual_merge.py",
      "backend/app/db/repositories/corrections.py",
      "backend/app/models/application_edit.py",
      "backend/app/models/application_merge.py",
    ],
    howToUse: {
      expectedBehaviour:
        "The API applies a requested correction in one transaction, sets manual_lock on the affected application, and stores a before/after audit row in application_corrections.",
      expectedSuccessResult:
        "QA can verify the corrected application, moved timeline events, and audit correction records reconcile with the local SQLite tables.",
      navigationPath:
        "API client -> PATCH /applications/{application_id}/status, PATCH /applications/{application_id}/events/{event_id}, POST /applications/{application_id}/split, or POST /applications/{application_id}/merge",
      prerequisites: [
        "Backend running",
        "SQLite database with application, event, and correction fixtures",
      ],
      qaValidationPoints: [
        "Status edits return an updated ApplicationRecord with manual_lock=true and a status_edit correction.",
        "Event edits reject no-op changes and missing source emails with typed public API errors.",
        "Split requests move selected events into a new manually locked application and record a split correction.",
        "Merge requests move source events into the target application, delete the source application, and record a merge correction.",
      ],
      steps: [
        "Seed at least two application records and one event timeline into local SQLite.",
        "Call PATCH /applications/{application_id}/status with a corrected current_status and optional reason.",
        "Call PATCH /applications/{application_id}/events/{event_id} with a changed event field and verify status replay.",
        "Call POST /applications/{application_id}/split with selected_event_ids and target application fields.",
        "Call POST /applications/{application_id}/merge with source_application_id for a duplicate record.",
      ],
    },
    id: "backend-application-manual-corrections-api",
    implementationStatus:
      "Implemented with thin FastAPI routes, audited manual edit and merge services, typed request and response DTOs, and repository-backed correction records.",
    name: "Application manual corrections API",
    relationship: [
      { label: "Dashboard", type: "screen" },
      { label: "DashboardPage", type: "component" },
      { label: "PATCH /applications/{application_id}/status", type: "api" },
      {
        label: "PATCH /applications/{application_id}/events/{event_id}",
        type: "api",
      },
      { label: "POST /applications/{application_id}/split", type: "api" },
      { label: "POST /applications/{application_id}/merge", type: "api" },
      { label: "applications router", type: "controller" },
      { label: "ApplicationCorrectionService", type: "service" },
      { label: "ManualApplicationEditService", type: "service" },
      { label: "ManualApplicationMergeService", type: "service" },
      { label: "applications", type: "database" },
      { label: "application_events", type: "database" },
      { label: "application_corrections", type: "database" },
    ],
    remainingWork: [],
    routes: [],
    screens: ["Dashboard", "Developer API"],
    sharedUi: [],
    stateConnections: [],
    status: "completed",
    testing: {
      canTestNow: true,
      entryPoint: "PATCH /applications/{application_id}/status",
      exampleInputs: [
        "current_status=interview&reason=Corrected from email review",
        "event_type=rejection for an existing event ID",
        "selected_event_ids=event-1,event-2 for a misgrouped application",
        "source_application_id=duplicate-application-id",
      ],
      expectedOutputs: [
        "ApplicationStatusEditResponse with manual_lock=true",
        "ApplicationEventEditResponse with replayed current status",
        "ApplicationSplitResponse with a new manually locked application and split correction",
        "ApplicationMergeResponse with moved_event_count and merge correction",
      ],
      requiredSetup: [
        "Backend app test client",
        "Application, event, raw email, and correction fixtures in local SQLite",
      ],
    },
  },
  {
    area: "backend",
    assignedModules: [
      "backend/app/api/wipe_data.py",
      "backend/app/services/wipe_data.py",
    ],
    blockers: [],
    components: [],
    connectedModules: [
      "Local data settings",
      "SQLite data directory",
      "Derived artifact cleanup",
    ],
    completedDate: "2026-07-05",
    dependencies: ["AppSettings", "Configured local data paths"],
    description:
      "Safety-checked local data deletion endpoint that requires the exact confirmation phrase, preflights configured filesystem targets, and removes local database and derived artifacts without touching unsafe paths.",
    endpoints: ["POST /local-data/wipe"],
    files: [
      "backend/app/api/wipe_data.py",
      "backend/app/services/wipe_data.py",
      "backend/app/models/wipe_data.py",
    ],
    howToUse: {
      expectedBehaviour:
        "The route validates the confirmation phrase and refuses unsafe configured targets before any deletion happens.",
      expectedSuccessResult:
        "The response reports status=wiped plus deleted and missing local paths, with no secrets or private email content in the body.",
      navigationPath: "API client -> POST /local-data/wipe",
      prerequisites: [
        "Backend running",
        "Disposable local app data or isolated test directory",
      ],
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
      exampleInputs: [
        "confirmation_phrase=wipe-local-data",
        "Isolated SQLite test path",
      ],
      expectedOutputs: [
        "status=wiped",
        "deleted_paths list",
        "missing_paths list",
      ],
      requiredSetup: [
        "Backend app test client",
        "Disposable local data directory",
      ],
    },
  },
];
