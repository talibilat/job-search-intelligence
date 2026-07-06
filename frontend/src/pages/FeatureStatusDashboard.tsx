import { useState } from "react";

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
      feature.relationship.filter((step) => step.type === type).map((step) => step.label),
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
    <ol className="feature-relationship-map" aria-label={`${feature.name} relationship map`}>
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
          <strong>Prerequisites:</strong> {formatList(feature.howToUse.prerequisites)}
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
          <strong>Expected behaviour:</strong> {feature.howToUse.expectedBehaviour}
        </p>
        <p>
          <strong>Expected success result:</strong> {feature.howToUse.expectedSuccessResult}
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
        <p className="feature-card__progress">{feature.percentComplete}% complete</p>
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

function FrontendTopologySummary({ features }: { features: readonly FeatureStatusRecord[] }) {
  return (
    <dl className="feature-summary-grid">
      <div>
        <dt>Frontend screens</dt>
        <dd>{formatList(uniqueList(features.flatMap((feature) => feature.screens)))}</dd>
      </div>
      <div>
        <dt>Frontend routes</dt>
        <dd>{formatList(uniqueList(features.flatMap((feature) => feature.routes)))}</dd>
      </div>
      <div>
        <dt>Frontend components</dt>
        <dd>{formatList(uniqueList(features.flatMap((feature) => feature.components)))}</dd>
      </div>
      <div>
        <dt>Frontend shared UI elements</dt>
        <dd>{formatList(uniqueList(features.flatMap((feature) => feature.sharedUi)))}</dd>
      </div>
      <div>
        <dt>Frontend state management connections</dt>
        <dd>{formatList(uniqueList(features.flatMap((feature) => feature.stateConnections)))}</dd>
      </div>
      <div>
        <dt>Frontend API integrations</dt>
        <dd>{formatList(uniqueList(features.flatMap((feature) => feature.endpoints)))}</dd>
      </div>
      <div>
        <dt>Backend services consumed by frontend</dt>
        <dd>{formatList(uniqueList(features.flatMap((feature) => feature.connectedModules)))}</dd>
      </div>
    </dl>
  );
}

function BackendTopologySummary({ features }: { features: readonly FeatureStatusRecord[] }) {
  return (
    <dl className="feature-summary-grid">
      <div>
        <dt>APIs</dt>
        <dd>{formatList(uniqueList(features.flatMap((feature) => feature.endpoints)))}</dd>
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
        <dt>External integrations</dt>
        <dd>{formatList(uniqueList(features.flatMap((feature) => feature.dependencies)))}</dd>
      </div>
      <div>
        <dt>Frontend consumers</dt>
        <dd>{formatList(uniqueList(features.flatMap((feature) => feature.screens)))}</dd>
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

function FeatureSection({ emptyMessage, features, sectionId, title }: FeatureSectionProps) {
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

function FeatureAreaView({ area, keyword, scope, status, testable }: FeatureAreaViewProps) {
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
  const completedFeatures = visibleFeatures.filter((feature) => feature.status === "completed");
  const inProgressFeatures = visibleFeatures.filter((feature) => feature.status !== "completed");

  return (
    <div className="feature-area-view">
      <section className="feature-view-summary" aria-label={`${areaLabels[area]} feature inventory`}>
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
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<"all" | FeatureStatus>("all");
  const [testable, setTestable] = useState<"all" | "no" | "yes">("all");
  const [scope, setScope] = useState("");

  return (
    <main aria-labelledby="feature-status-title" className="app-shell feature-status-shell">
      <section className="feature-status-hero" aria-labelledby="feature-status-title">
        <p className="eyebrow">Developer inventory</p>
        <h1 id="feature-status-title">Feature Status Dashboard</h1>
        <p className="hero-copy">
          A registry-backed map of completed and in-progress frontend and backend
          features, their test entry points, and the modules that connect them.
        </p>
      </section>

      <section className="feature-filters" aria-label="Feature filters">
        <FormField htmlFor="feature-search" label="Search features">
          <TextInput
            id="feature-search"
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="Search by feature, module, API, screen, or component"
            value={keyword}
          />
        </FormField>
        <label className="feature-select-field">
          <span>Status</span>
          <select value={status} onChange={(event) => setStatus(event.target.value as FeatureStatus | "all")}>
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
          <select value={testable} onChange={(event) => setTestable(event.target.value as "all" | "no" | "yes")}>
            <option value="all">All</option>
            <option value="yes">Can test now</option>
            <option value="no">Not testable yet</option>
          </select>
        </label>
        <FormField htmlFor="feature-scope" label="Module, API, screen, or component">
          <TextInput
            id="feature-scope"
            onChange={(event) => setScope(event.target.value)}
            placeholder="Filter by /setup, SyncStatusPanel, GET /sync/status"
            value={scope}
          />
        </FormField>
      </section>

      <Tabs
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
      />
    </main>
  );
}
