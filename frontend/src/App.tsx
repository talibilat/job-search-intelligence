import { PipelineActivityPanel } from "./components/PipelineActivityPanel";
import { SyncStatusPanel } from "./components/SyncStatusPanel";
import { ApplicationDetailPage } from "./pages/ApplicationDetailPage";
import Chat from "./pages/Chat";
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
  { href: "/chat", label: "Chat" },
] as const;

function JobSearchPage() {
  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">Local-first job-search intelligence</p>
        <h1 id="page-title">Your job search, from inbox to insight.</h1>
        <p className="hero-copy">
          Connect Gmail, sync your mail history, classify job-search email, and
          watch the deterministic dashboard fill in. Everything on this page
          runs locally.
        </p>
      </section>

      <PipelineActivityPanel />

      <SyncStatusPanel />
    </main>
  );
}

function App() {
  const routePath = window.location.pathname.replace(/\/+$/, "") || "/";
  const applicationDetailMatch = /^\/applications\/([^/]+)$/.exec(routePath);
  const currentPath = navigationItems.some((item) => item.href === routePath)
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
      {applicationDetailMatch ? (
        <ApplicationDetailPage applicationId={decodeURIComponent(applicationDetailMatch[1])} />
      ) : currentPath === "/setup" ? (
        <SetupPage />
      ) : currentPath === "/dashboard" ? (
        <DashboardPage />
      ) : currentPath === "/features" ? (
        <FeatureStatusDashboard />
      ) : currentPath === "/insights" ? (
        <Insights />
      ) : currentPath === "/chat" ? (
        <Chat />
      ) : (
        <JobSearchPage />
      )}
    </>
  );
}

export default App;
