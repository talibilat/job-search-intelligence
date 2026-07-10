import { ApplicationDetailPage } from "./pages/ApplicationDetailPage";
import { Alert } from "./components/ui";
import { DashboardPage } from "./pages/DashboardPage";
import { FeatureStatusDashboard } from "./pages/FeatureStatusDashboard";
import { Insights } from "./pages/Insights";
import { SetupPage } from "./pages/SetupPage";

const navigationItems = [
  { href: "/", label: "Job Search" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/setup", label: "Setup" },
  { href: "/features", label: "Feature Status" },
  { href: "/insights", label: "Insights" },
] as const;

const routePaths = new Set(["/", "/dashboard", "/setup", "/features", "/insights"]);

const productFlowSteps = [
  {
    description:
      "Uses your own Gmail OAuth client with the read-only scope. Tokens stay behind the local secret store.",
    title: "Connects to Gmail locally",
  },
  {
    description:
      "Stores broad Gmail metadata first, then keeps body text only for likely job-search candidates.",
    title: "Syncs safe metadata first",
  },
  {
    description:
      "Runs deterministic filter signals before model classification so only retained candidates enter extraction.",
    title: "Filters and classifies job email",
  },
  {
    description:
      "Groups many email events into one application record with a deterministic status timeline.",
    title: "Reconstructs applications and timelines",
  },
  {
    description:
      "Reads the applications table and event timeline through metrics endpoints. LLMs never produce dashboard counts.",
    title: "Charts deterministic metrics",
  },
  {
    description:
      "Narrative insights are cached and grounded in cited local evidence only after enough data exists.",
    title: "Generates grounded insights only when supported",
  },
] as const;

function JobSearchPage() {
  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">Local-first job-search intelligence</p>
        <h1 id="page-title">Your job search, from inbox to insight.</h1>
        <p className="hero-copy">
          Connect Gmail, sync your mail history, classify job-search email, and
          watch deterministic dashboard charts fill in from the reconstructed
          applications table. Your app data stays in local SQLite, and private
          email body text is retained only when the pipeline needs it.
        </p>
      </section>

      <section className="landing-flow" aria-labelledby="landing-flow-title">
        <div>
          <p className="eyebrow">How it works</p>
          <h2 id="landing-flow-title">A private pipeline from Gmail to charts</h2>
        </div>
        <ol className="landing-flow__list">
          {productFlowSteps.map((step) => (
            <li key={step.title}>
              <h3>{step.title}</h3>
              <p>{step.description}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="landing-actions" aria-label="Next actions">
        <a className="landing-actions__primary" href="/features">
          Run features
        </a>
        <a className="landing-actions__secondary" href="/dashboard">
          View dashboard charts
        </a>
      </section>
    </main>
  );
}

function ApplicationRouteUnavailablePage() {
  return (
    <main aria-labelledby="application-detail-title" className="app-shell application-detail-shell">
      <section className="dashboard-hero" aria-labelledby="application-detail-title">
        <p className="eyebrow">Application detail</p>
        <h1 id="application-detail-title">Application unavailable</h1>
        <Alert title="Application detail unavailable" tone="danger">
          <p>The application link is malformed. Open a saved application from Feature Status or Insights.</p>
        </Alert>
      </section>
    </main>
  );
}

function safeDecodeRouteSegment(value: string) {
  try {
    const decodedValue = decodeURIComponent(value);
    const hasControlCharacter = Array.from(decodedValue).some((character) => {
      const characterCode = character.charCodeAt(0);

      return characterCode <= 0x1f || characterCode === 0x7f;
    });

    return hasControlCharacter || /[%\\/?#]/.test(decodedValue)
      ? null
      : decodedValue;
  } catch {
    return null;
  }
}

function App() {
  const routePath = window.location.pathname.replace(/\/+$/, "") || "/";
  const applicationDetailMatch = /^\/applications\/([^/]+)$/.exec(routePath);
  const applicationId = applicationDetailMatch
    ? safeDecodeRouteSegment(applicationDetailMatch[1])
    : null;
  const currentPath = applicationDetailMatch
    ? null
    : routePaths.has(routePath)
      ? routePath
      : "/";

  return (
    <>
      <nav className="app-nav" aria-label="Primary">
        <a className="app-nav__brand" href="/">
          JobTracker
        </a>
        <div className="app-nav__links">
          {navigationItems.map((item) => (
            <a
              aria-current={currentPath === item.href ? "page" : undefined}
              className="app-nav__link"
              href={item.href}
              key={item.href}
            >
              {item.label}
            </a>
          ))}
        </div>
      </nav>
      {applicationDetailMatch && applicationId ? (
        <ApplicationDetailPage applicationId={applicationId} />
      ) : applicationDetailMatch ? (
        <ApplicationRouteUnavailablePage />
      ) : currentPath === "/setup" ? (
        <SetupPage />
      ) : currentPath === "/dashboard" ? (
        <DashboardPage />
      ) : currentPath === "/features" ? (
        <FeatureStatusDashboard />
      ) : currentPath === "/insights" ? (
        <Insights />
      ) : (
        <JobSearchPage />
      )}
    </>
  );
}

export default App;
