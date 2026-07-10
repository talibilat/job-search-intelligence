import { useEffect, useId, useState } from "react";

import { PipelineActivityPanel } from "../components/PipelineActivityPanel";
import { SyncStatusPanel } from "../components/SyncStatusPanel";
import { FormField, Tabs, TextInput } from "../components/ui";
import {
  featureStatusLabels,
  featureStatusRegistry,
  type FeatureArea,
  type FeatureStatus,
  type FeatureStatusRecord,
} from "../featureStatus/featureStatusRegistry";

const areaLabels: Record<FeatureArea, string> = {
  backend: "Backend",
  frontend: "Frontend",
};

interface UserFacingFeature {
  howToRun: string;
  info?: UserFacingFeatureInfo;
  name: string;
  whatItMeans: string;
  worksToday: "yes" | "partial" | "no";
  worksTodayNote: string;
}

interface UserFacingFeatureInfo {
  dataSource: string;
  dataTable: string;
  howItWorks: string;
  missingData: string;
}

const userFacingFeatures: readonly UserFacingFeature[] = [
  {
    howToRun:
      "Setup page: save provider choices, then use the Gmail connect flow with your own Google OAuth client.",
    info: {
      dataSource: "GET /setup/status, GET /auth/gmail, and GET /auth/gmail/callback",
      dataTable: "email_connections plus encrypted SecretStore token refs",
      howItWorks:
        "Starts a read-only Gmail OAuth flow, stores token material behind SecretStore, and keeps only non-secret connection metadata in SQLite.",
      missingData:
        "If Gmail is disconnected, configure your Google OAuth client on Setup and complete the Continue to Google flow.",
    },
    name: "Connect Gmail",
    whatItMeans:
      "Authorizes read-only access to your Gmail account. Tokens are stored encrypted on this machine and never leave it.",
    worksToday: "yes",
    worksTodayNote: "Works today with your own Google Cloud OAuth client.",
  },
  {
    howToRun:
      'Feature Status runnable sync pipeline: press "Sync now". Optional limits (email count, dates, pages) bound each run.',
    info: {
      dataSource: "POST /sync and GET /sync/status",
      dataTable: "raw_emails",
      howItWorks:
        "Runs Gmail metadata backfill or incremental sync through the local backend, persists public-safe metadata, and fetches retained bodies only for likely job-search candidates.",
      missingData:
        "If values are zero or missing, connect Gmail on Setup, then run Sync now in this Feature Status section.",
    },
    name: "Sync mailbox metadata",
    whatItMeans:
      "Downloads Gmail message metadata into the local database. The first pass is a one-time historical backfill from newest to oldest mail; after it completes, each sync fetches only new mail.",
    worksToday: "yes",
    worksTodayNote: "Works today once Gmail is connected.",
  },
  {
    howToRun:
      "Runs automatically during every sync; outcomes appear in the recent synced email metadata preview on Feature Status.",
    info: {
      dataSource: "GET /pipeline/status and GET /sync/recent-emails",
      dataTable: "email_filter_decisions and raw_emails",
      howItWorks:
        "Scores synced metadata with public-safe sender, subject, label, and same-page thread signals before any model call.",
      missingData:
        "If filter counts are zero, run sync first and inspect recent email metadata for candidate or rejected filter decisions.",
    },
    name: "Job-search email filter",
    whatItMeans:
      "A deterministic heuristic (known recruiter domains, keywords, labels) decides which synced emails look job-related. Only those keep their body text locally for classification.",
    worksToday: "yes",
    worksTodayNote: "Works today; every decision is stored with a reason.",
  },
  {
    howToRun:
      'Feature Status runnable sync pipeline: press "Run classification" when candidates are waiting. Requires a configured LLM provider (Ollama or Azure OpenAI).',
    info: {
      dataSource: "GET /classification/estimate, GET /classification/reprocessing-plan, and POST /classification/run",
      dataTable: "email_classifications, classification_runs, applications, and application_events",
      howItWorks:
        "Classifies retained candidate emails through the configured provider, stores accepted classifications, and deterministically aggregates application timelines.",
      missingData:
        "If nothing runs, configure an LLM provider on Setup, sync retained candidates, then use Run classification when the pipeline says candidates are waiting.",
    },
    name: "Classify and build applications",
    whatItMeans:
      "The configured model categorizes each kept email (confirmation, rejection, interview, offer, and so on), and deterministic aggregation reconstructs one application per company and role with a timeline of events.",
    worksToday: "partial",
    worksTodayNote:
      "Works today with a running LLM provider; without one the pipeline stops after the filter step.",
  },
  {
    howToRun:
      "Dashboard page: metrics fill in automatically once applications exist. Filters live in the URL.",
    info: {
      dataSource: "GET /metrics/summary, /metrics/rates, /metrics/funnel, /metrics/timeseries, /metrics/breakdown, and /metrics/diagnostics",
      dataTable: "applications and application_events",
      howItWorks:
        "Computes counts, rates, funnels, trends, and diagnostics with deterministic backend queries over local application records.",
      missingData:
        "If charts are empty, follow the upstream Feature Status action: connect Gmail, sync, classify, then review dashboard.",
    },
    name: "Deterministic dashboard",
    whatItMeans:
      "Counts, statuses, and rates computed by SQL over the applications table. No model ever produces these numbers.",
    worksToday: "yes",
    worksTodayNote:
      "Works today; shows guided empty states until the pipeline has produced applications.",
  },
  {
    howToRun:
      "Insights page: request narrative insights after applications exist. Requires an LLM provider.",
    info: {
      dataSource: "GET /insights and POST /insights/regenerate",
      dataTable: "insights plus cited applications, application_events, and raw_emails",
      howItWorks:
        "Builds deterministic cited facts first, then asks the configured model for cached narrative synthesis only when regeneration is requested.",
      missingData:
        "If insights are missing, produce classified applications first and configure an LLM provider before regenerating an insight.",
    },
    name: "Narrative insights",
    whatItMeans:
      "Cached model-written summaries (why rejections happen, skill gaps) grounded in cited applications and emails.",
    worksToday: "partial",
    worksTodayNote:
      "API and page exist; useful output needs classified applications plus an LLM provider.",
  },
  {
    howToRun:
      "Not runnable from the product UI yet. Track the Phase 5 plan in the advanced developer inventory.",
    info: {
      dataSource: "Phase 5 planned POST /chat and GET /chat/history",
      dataTable: "planned chat_messages and email_chunks",
      howItWorks:
        "Will route questions through deterministic structured-query tools and cited semantic retrieval after the RAG agent is built.",
      missingData:
        "There is no user action yet; chat is hidden from primary navigation until the backend route and grounded UI work perfectly.",
    },
    name: "Chat with your history",
    whatItMeans:
      "A hybrid question-answering agent over your job-search history, planned for a later phase.",
    worksToday: "no",
    worksTodayNote:
      "Not built yet; no chat route, composer, backend request, or provider call is exposed.",
  },
];

const glossaryEntries: readonly { definition: string; term: string }[] = [
  {
    definition:
      "One stored Gmail message row: sender, subject, dates, and labels. Body text is only kept when the filter marks the message as a likely job email.",
    term: "Raw email",
  },
  {
    definition:
      "A message as returned by the Gmail API during a sync run, before it is stored locally.",
    term: "Provider message",
  },
  {
    definition:
      "One paginated Gmail API response. A full mailbox backfill processes many pages, resumable across runs.",
    term: "Page",
  },
  {
    definition:
      "The locally kept body text of a likely job email, stored so classification can read it. Never displayed in the UI.",
    term: "Retained body",
  },
  {
    definition:
      "The heuristic yes/no decision on whether an email looks job-search related, stored with a public-safe reason like sender_domain:greenhouse.io.",
    term: "Filter decision",
  },
  {
    definition:
      "The model-assigned category (confirmation, rejection, interview invite, offer, and so on) for a retained candidate email, stored with model and prompt version.",
    term: "Classification",
  },
  {
    definition:
      "One reconstructed job application: a company and role with a timeline of events built from many emails. The single source of truth for every dashboard number.",
    term: "Application",
  },
];

const worksTodayLabels: Record<UserFacingFeature["worksToday"], string> = {
  no: "Not yet",
  partial: "Partially",
  yes: "Works today",
};

function FeatureGuideInfo({
  feature,
  info,
}: {
  feature: string;
  info: UserFacingFeatureInfo;
}) {
  const infoId = useId();
  const [isInfoPinned, setIsInfoPinned] = useState(false);
  const [isInfoPreviewed, setIsInfoPreviewed] = useState(false);
  const [isInfoDismissed, setIsInfoDismissed] = useState(false);
  const isInfoOpen = isInfoPinned || (isInfoPreviewed && !isInfoDismissed);

  return (
    <div className="feature-guide__info">
      <button
        aria-controls={infoId}
        aria-expanded={isInfoOpen}
        aria-label={`About ${feature}`}
        className="feature-guide__info-button"
        onBlur={() => {
          setIsInfoPreviewed(false);
          setIsInfoDismissed(false);
        }}
        onClick={() => {
          if (isInfoOpen) {
            setIsInfoPinned(false);
            setIsInfoPreviewed(false);
            setIsInfoDismissed(true);
            return;
          }

          setIsInfoPinned(true);
          setIsInfoDismissed(false);
        }}
        onFocus={() => {
          setIsInfoPreviewed(true);
          setIsInfoDismissed(false);
        }}
        onMouseEnter={() => {
          setIsInfoPreviewed(true);
          setIsInfoDismissed(false);
        }}
        onMouseLeave={() => {
          setIsInfoPreviewed(false);
          setIsInfoDismissed(false);
        }}
        type="button"
      >
        i
      </button>
      {isInfoOpen ? (
        <div className="feature-guide__info-panel" id={infoId}>
          <p>{info.howItWorks}</p>
          <dl>
            <div>
              <dt>Data source</dt>
              <dd>Data source: {info.dataSource}</dd>
            </div>
            <div>
              <dt>Table</dt>
              <dd>Table: {info.dataTable}</dd>
            </div>
            <div>
              <dt>If values are zero or missing</dt>
              <dd>{info.missingData}</dd>
            </div>
          </dl>
        </div>
      ) : null}
    </div>
  );
}

type FeatureTab = FeatureArea;
type FeatureStatusFilter = "all" | FeatureStatus;
type FeatureTestableFilter = "all" | "no" | "yes";

const featureStatuses = new Set<string>([
  ...Object.keys(featureStatusLabels),
  "all",
]);
const featureTestableFilters = new Set<string>(["all", "no", "yes"]);
const featureTabs = new Set<string>(["frontend", "backend"]);

function queryValue(searchParams: URLSearchParams, key: string) {
  return searchParams.get(key)?.trim() ?? "";
}

function queryEnumValue<TValue extends string>(
  searchParams: URLSearchParams,
  key: string,
  allowedValues: ReadonlySet<string>,
  defaultValue: TValue,
) {
  const value = searchParams.get(key)?.trim();

  return value && allowedValues.has(value) ? (value as TValue) : defaultValue;
}

function initialFeatureQueryState() {
  const searchParams = new URLSearchParams(window.location.search);

  return {
    keyword: queryValue(searchParams, "search"),
    scope: queryValue(searchParams, "scope"),
    status: queryEnumValue<FeatureStatusFilter>(
      searchParams,
      "status",
      featureStatuses,
      "all",
    ),
    tab: queryEnumValue<FeatureTab>(
      searchParams,
      "tab",
      featureTabs,
      "frontend",
    ),
    testable: queryEnumValue<FeatureTestableFilter>(
      searchParams,
      "testable",
      featureTestableFilters,
      "all",
    ),
  };
}

function formatList(items: readonly string[]) {
  return items.length > 0 ? items.join(", ") : "None";
}

function uniqueList(items: readonly string[]) {
  return Array.from(new Set(items.filter(Boolean)));
}

function relationshipLabels(
  features: readonly FeatureStatusRecord[],
  type: FeatureStatusRecord["relationship"][number]["type"],
) {
  return uniqueList(
    features.flatMap((feature) =>
      feature.relationship
        .filter((step) => step.type === type)
        .map((step) => step.label),
    ),
  );
}

function featureMatchesKeyword(feature: FeatureStatusRecord, keyword: string) {
  if (!keyword) {
    return true;
  }

  const searchableText = [
    feature.name,
    feature.description,
    feature.implementationStatus,
    ...feature.assignedModules,
    ...feature.blockers,
    ...feature.components,
    ...feature.connectedModules,
    ...feature.dependencies,
    ...feature.endpoints,
    ...feature.files,
    ...feature.remainingWork,
    ...feature.routes,
    ...feature.screens,
    ...feature.sharedUi,
    ...feature.stateConnections,
    ...feature.relationship.map((step) => `${step.type} ${step.label}`),
  ]
    .join(" ")
    .toLowerCase();

  return searchableText.includes(keyword.toLowerCase());
}

function featureMatchesScope(feature: FeatureStatusRecord, scope: string) {
  if (!scope) {
    return true;
  }

  const scopedText = [
    ...feature.assignedModules,
    ...feature.components,
    ...feature.endpoints,
    ...feature.files,
    ...feature.routes,
    ...feature.screens,
  ]
    .join(" ")
    .toLowerCase();

  return scopedText.includes(scope.toLowerCase());
}

function StatusPill({ status }: { status: FeatureStatus }) {
  return (
    <span className={`feature-status-pill feature-status-pill--${status}`}>
      {featureStatusLabels[status]}
    </span>
  );
}

function FeatureMetaGrid({ feature }: { feature: FeatureStatusRecord }) {
  return (
    <dl className="feature-meta-grid">
      <div>
        <dt>Ready for testing</dt>
        <dd>{feature.testing.canTestNow ? "Yes" : "No"}</dd>
      </div>
      <div>
        <dt>Test entry point</dt>
        <dd>{feature.testing.entryPoint}</dd>
      </div>
      <div>
        <dt>Related screens</dt>
        <dd>{formatList(feature.screens)}</dd>
      </div>
      <div>
        <dt>Routes</dt>
        <dd>{formatList(feature.routes)}</dd>
      </div>
      <div>
        <dt>Components</dt>
        <dd>{formatList(feature.components)}</dd>
      </div>
      <div>
        <dt>Endpoints</dt>
        <dd>{formatList(feature.endpoints)}</dd>
      </div>
      <div>
        <dt>Dependencies</dt>
        <dd>{formatList(feature.dependencies)}</dd>
      </div>
      <div>
        <dt>Connected modules</dt>
        <dd>{formatList(feature.connectedModules)}</dd>
      </div>
      <div>
        <dt>Shared UI</dt>
        <dd>{formatList(feature.sharedUi)}</dd>
      </div>
      <div>
        <dt>State connections</dt>
        <dd>{formatList(feature.stateConnections)}</dd>
      </div>
      <div>
        <dt>Date completed</dt>
        <dd>{feature.completedDate ?? "Not completed yet"}</dd>
      </div>
      <div>
        <dt>Assigned modules</dt>
        <dd>{formatList(feature.assignedModules)}</dd>
      </div>
    </dl>
  );
}

function RelationshipMap({ feature }: { feature: FeatureStatusRecord }) {
  return (
    <ol
      className="feature-relationship-map"
      aria-label={`${feature.name} relationship map`}
    >
      {feature.relationship.map((step) => (
        <li key={`${feature.id}-${step.type}-${step.label}`}>
          <span>{step.type.replace("_", " ")}</span>
          <strong>{step.label}</strong>
        </li>
      ))}
    </ol>
  );
}

function TestingDetails({ feature }: { feature: FeatureStatusRecord }) {
  return (
    <div className="feature-testing-panel">
      <p className="feature-section-label">Testing information</p>
      <dl className="feature-testing-grid">
        <div>
          <dt>Required setup</dt>
          <dd>{formatList(feature.testing.requiredSetup)}</dd>
        </div>
        <div>
          <dt>Example inputs</dt>
          <dd>{formatList(feature.testing.exampleInputs)}</dd>
        </div>
        <div>
          <dt>Expected outputs</dt>
          <dd>{formatList(feature.testing.expectedOutputs)}</dd>
        </div>
      </dl>
    </div>
  );
}

function HowToUseDetails({ feature }: { feature: FeatureStatusRecord }) {
  if (!feature.howToUse) {
    return null;
  }

  return (
    <details className="feature-how-to">
      <summary>How to use {feature.name}</summary>
      <div className="feature-how-to__body">
        <p>
          <strong>Prerequisites:</strong>{" "}
          {formatList(feature.howToUse.prerequisites)}
        </p>
        <p>
          <strong>Navigation path:</strong> {feature.howToUse.navigationPath}
        </p>
        <div>
          <strong>Steps:</strong>
          <ol>
            {feature.howToUse.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
        <p>
          <strong>Expected behaviour:</strong>{" "}
          {feature.howToUse.expectedBehaviour}
        </p>
        <p>
          <strong>Expected success result:</strong>{" "}
          {feature.howToUse.expectedSuccessResult}
        </p>
        <div>
          <strong>Common QA validation points:</strong>
          <ul>
            {feature.howToUse.qaValidationPoints.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </div>
      </div>
    </details>
  );
}

function FeatureCard({ feature }: { feature: FeatureStatusRecord }) {
  return (
    <article className="feature-card">
      <div className="feature-card__header">
        <div>
          <p className="eyebrow">{areaLabels[feature.area]}</p>
          <h3>{feature.name}</h3>
        </div>
        <StatusPill status={feature.status} />
      </div>
      <p className="feature-card__description">{feature.description}</p>
      <p className="feature-card__status">{feature.implementationStatus}</p>
      {feature.percentComplete == null ? null : (
        <p className="feature-card__progress">
          {feature.percentComplete}% complete
        </p>
      )}
      <FeatureMetaGrid feature={feature} />
      <TestingDetails feature={feature} />
      <div className="feature-work-grid">
        <div>
          <p className="feature-section-label">Current blockers</p>
          <p>{formatList(feature.blockers)}</p>
        </div>
        <div>
          <p className="feature-section-label">Remaining work</p>
          <p>{formatList(feature.remainingWork)}</p>
        </div>
        <div>
          <p className="feature-section-label">Related files</p>
          <p>{formatList(feature.files)}</p>
        </div>
      </div>
      <div>
        <p className="feature-section-label">Connection mapping</p>
        <RelationshipMap feature={feature} />
      </div>
      <HowToUseDetails feature={feature} />
    </article>
  );
}

function FrontendTopologySummary({
  features,
}: {
  features: readonly FeatureStatusRecord[];
}) {
  return (
    <dl className="feature-summary-grid">
      <div>
        <dt>Frontend screens</dt>
        <dd>
          {formatList(
            uniqueList(features.flatMap((feature) => feature.screens)),
          )}
        </dd>
      </div>
      <div>
        <dt>Frontend routes</dt>
        <dd>
          {formatList(
            uniqueList(features.flatMap((feature) => feature.routes)),
          )}
        </dd>
      </div>
      <div>
        <dt>Frontend components</dt>
        <dd>
          {formatList(
            uniqueList(features.flatMap((feature) => feature.components)),
          )}
        </dd>
      </div>
      <div>
        <dt>Frontend shared UI elements</dt>
        <dd>
          {formatList(
            uniqueList(features.flatMap((feature) => feature.sharedUi)),
          )}
        </dd>
      </div>
      <div>
        <dt>Frontend state management connections</dt>
        <dd>
          {formatList(
            uniqueList(features.flatMap((feature) => feature.stateConnections)),
          )}
        </dd>
      </div>
      <div>
        <dt>Frontend API integrations</dt>
        <dd>
          {formatList(
            uniqueList(features.flatMap((feature) => feature.endpoints)),
          )}
        </dd>
      </div>
      <div>
        <dt>Backend services consumed by frontend</dt>
        <dd>
          {formatList(
            uniqueList(features.flatMap((feature) => feature.connectedModules)),
          )}
        </dd>
      </div>
    </dl>
  );
}

function BackendTopologySummary({
  features,
}: {
  features: readonly FeatureStatusRecord[];
}) {
  return (
    <dl className="feature-summary-grid">
      <div>
        <dt>APIs</dt>
        <dd>
          {formatList(
            uniqueList(features.flatMap((feature) => feature.endpoints)),
          )}
        </dd>
      </div>
      <div>
        <dt>Controllers</dt>
        <dd>{formatList(relationshipLabels(features, "controller"))}</dd>
      </div>
      <div>
        <dt>Services</dt>
        <dd>{formatList(relationshipLabels(features, "service"))}</dd>
      </div>
      <div>
        <dt>Database models</dt>
        <dd>{formatList(relationshipLabels(features, "database"))}</dd>
      </div>
      <div>
        <dt>DTOs and models</dt>
        <dd>{formatList(relationshipLabels(features, "dto_model"))}</dd>
      </div>
      <div>
        <dt>Runtime and config</dt>
        <dd>{formatList(relationshipLabels(features, "runtime_config"))}</dd>
      </div>
      <div>
        <dt>Background jobs</dt>
        <dd>{formatList(relationshipLabels(features, "background_job"))}</dd>
      </div>
      <div>
        <dt>Workers</dt>
        <dd>{formatList(relationshipLabels(features, "worker"))}</dd>
      </div>
      <div>
        <dt>Queues</dt>
        <dd>{formatList(relationshipLabels(features, "queue"))}</dd>
      </div>
      <div>
        <dt>Dependencies</dt>
        <dd>
          {formatList(
            uniqueList(features.flatMap((feature) => feature.dependencies)),
          )}
        </dd>
      </div>
      <div>
        <dt>Frontend consumers</dt>
        <dd>
          {formatList(
            uniqueList(features.flatMap((feature) => feature.screens)),
          )}
        </dd>
      </div>
    </dl>
  );
}

interface FeatureSectionProps {
  emptyMessage: string;
  features: readonly FeatureStatusRecord[];
  sectionId: string;
  title: string;
}

function FeatureSection({
  emptyMessage,
  features,
  sectionId,
  title,
}: FeatureSectionProps) {
  return (
    <section className="feature-section" aria-labelledby={`${sectionId}-title`}>
      <div className="feature-section__header">
        <h2 id={`${sectionId}-title`}>{title}</h2>
        <p>{features.length} visible</p>
      </div>
      {features.length > 0 ? (
        <div className="feature-card-list">
          {features.map((feature) => (
            <FeatureCard feature={feature} key={feature.id} />
          ))}
        </div>
      ) : (
        <p className="feature-empty-state">{emptyMessage}</p>
      )}
    </section>
  );
}

interface FeatureAreaViewProps {
  area: FeatureArea;
  keyword: string;
  scope: string;
  status: "all" | FeatureStatus;
  testable: "all" | "no" | "yes";
}

function FeatureAreaView({
  area,
  keyword,
  scope,
  status,
  testable,
}: FeatureAreaViewProps) {
  const visibleFeatures = featureStatusRegistry.filter((feature) => {
    const statusMatches = status === "all" || feature.status === status;
    const testableMatches =
      testable === "all" || feature.testing.canTestNow === (testable === "yes");

    return (
      feature.area === area &&
      statusMatches &&
      testableMatches &&
      featureMatchesKeyword(feature, keyword) &&
      featureMatchesScope(feature, scope)
    );
  });
  const completedFeatures = visibleFeatures.filter(
    (feature) => feature.status === "completed",
  );
  const inProgressFeatures = visibleFeatures.filter(
    (feature) => feature.status !== "completed",
  );

  return (
    <div className="feature-area-view">
      <section
        className="feature-view-summary"
        aria-label={`${areaLabels[area]} feature inventory`}
      >
        <div>
          <p className="eyebrow">{areaLabels[area]} map</p>
          <h2>{areaLabels[area]} implementation overview</h2>
        </div>
        {area === "frontend" ? (
          <FrontendTopologySummary features={visibleFeatures} />
        ) : (
          <BackendTopologySummary features={visibleFeatures} />
        )}
      </section>

      <FeatureSection
        emptyMessage="No completed features match these filters."
        features={completedFeatures}
        sectionId={`${area}-completed-features`}
        title="Completed features"
      />
      <FeatureSection
        emptyMessage="No in-progress features match these filters."
        features={inProgressFeatures}
        sectionId={`${area}-in-progress-features`}
        title="In progress"
      />
    </div>
  );
}

export function FeatureStatusDashboard() {
  const [initialState] = useState(initialFeatureQueryState);
  const [keyword, setKeyword] = useState(initialState.keyword);
  const [status, setStatus] = useState<FeatureStatusFilter>(
    initialState.status,
  );
  const [testable, setTestable] = useState<FeatureTestableFilter>(
    initialState.testable,
  );
  const [scope, setScope] = useState(initialState.scope);
  const [activeTab, setActiveTab] = useState<FeatureTab>(initialState.tab);

  useEffect(() => {
    const searchParams = new URLSearchParams();

    searchParams.set("tab", activeTab);

    if (keyword) {
      searchParams.set("search", keyword);
    }

    if (status !== "all") {
      searchParams.set("status", status);
    }

    if (testable !== "all") {
      searchParams.set("testable", testable);
    }

    if (scope) {
      searchParams.set("scope", scope);
    }

    const nextSearch = searchParams.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`;

    if (`${window.location.pathname}${window.location.search}` !== nextUrl) {
      window.history.replaceState({}, "", nextUrl);
    }
  }, [activeTab, keyword, scope, status, testable]);

  return (
    <main
      aria-labelledby="feature-status-title"
      className="app-shell feature-status-shell"
    >
      <section
        className="feature-status-hero"
        aria-labelledby="feature-status-title"
      >
        <p className="eyebrow">Feature status</p>
        <h1 id="feature-status-title">What JobTracker can do today</h1>
        <p className="hero-copy">
          Each feature below says what it means, how to run it, and whether it
          works right now. The full developer inventory of files and APIs is
          collapsed at the bottom.
        </p>
      </section>

      <section
        aria-labelledby="user-features-title"
        className="status-card feature-guide"
      >
        <div>
          <p className="eyebrow">Available features</p>
          <h2 id="user-features-title">Features and how to run them</h2>
        </div>
        <ul className="feature-guide__list">
          {userFacingFeatures.map((feature) => (
            <li className="feature-guide__item" key={feature.name}>
              <div className="feature-guide__item-header">
                <h3>{feature.name}</h3>
                <div className="feature-guide__item-actions">
                  {feature.info ? (
                    <FeatureGuideInfo feature={feature.name} info={feature.info} />
                  ) : null}
                  <span
                    className={`feature-guide__works feature-guide__works--${feature.worksToday}`}
                  >
                    {worksTodayLabels[feature.worksToday]}
                  </span>
                </div>
              </div>
              <p>{feature.whatItMeans}</p>
              <p>
                <strong>How to run it:</strong> {feature.howToRun}
              </p>
              <p className="feature-guide__note">{feature.worksTodayNote}</p>
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="runnable-sync-pipeline-title"
        className="feature-runnable-section"
      >
        <div>
          <p className="eyebrow">Runnable feature</p>
          <h2 id="runnable-sync-pipeline-title">Runnable sync pipeline</h2>
          <p>
            Use this section to inspect Gmail connection readiness, run manual sync,
            review pipeline counts, and preview public-safe synced email metadata.
          </p>
        </div>
        <PipelineActivityPanel />
        <SyncStatusPanel />
      </section>

      <section
        aria-labelledby="feature-glossary-title"
        className="status-card feature-guide"
      >
        <div>
          <p className="eyebrow">Plain language</p>
          <h2 id="feature-glossary-title">Glossary</h2>
        </div>
        <dl className="feature-guide__glossary">
          {glossaryEntries.map((entry) => (
            <div key={entry.term}>
              <dt>{entry.term}</dt>
              <dd>{entry.definition}</dd>
            </div>
          ))}
        </dl>
      </section>

      <details className="feature-advanced">
        <summary>
          Advanced: developer inventory (files, APIs, modules, and test entry
          points)
        </summary>

      <section className="feature-filters" aria-label="Feature filters">
        <FormField htmlFor="feature-search" label="Search features">
          <TextInput
            id="feature-search"
            onChange={(event) => setKeyword(event.target.value.trim())}
            placeholder="Search by feature, module, API, screen, or component"
            value={keyword}
          />
        </FormField>
        <label className="feature-select-field">
          <span>Status</span>
          <select
            value={status}
            onChange={(event) =>
              setStatus(event.target.value as FeatureStatus | "all")
            }
          >
            <option value="all">All statuses</option>
            {Object.entries(featureStatusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="feature-select-field">
          <span>Testable</span>
          <select
            value={testable}
            onChange={(event) =>
              setTestable(event.target.value as "all" | "no" | "yes")
            }
          >
            <option value="all">All</option>
            <option value="yes">Can test now</option>
            <option value="no">Not testable yet</option>
          </select>
        </label>
        <FormField
          htmlFor="feature-scope"
          label="Module, API, screen, or component"
        >
          <TextInput
            id="feature-scope"
            onChange={(event) => setScope(event.target.value.trim())}
            placeholder="Filter by /setup, SyncStatusPanel, GET /sync/status"
            value={scope}
          />
        </FormField>
      </section>

      <Tabs
        activeItemId={activeTab}
        className="feature-status-tabs"
        items={[
          {
            content: (
              <FeatureAreaView
                area="frontend"
                keyword={keyword}
                scope={scope}
                status={status}
                testable={testable}
              />
            ),
            id: "frontend",
            label: "Frontend",
          },
          {
            content: (
              <FeatureAreaView
                area="backend"
                keyword={keyword}
                scope={scope}
                status={status}
                testable={testable}
              />
            ),
            id: "backend",
            label: "Backend",
          },
        ]}
        label="Feature status views"
        onItemChange={(itemId) => setActiveTab(itemId as FeatureTab)}
      />
      </details>
    </main>
  );
}
