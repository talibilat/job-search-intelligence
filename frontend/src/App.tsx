import { ChartPanel } from "./components/charts";
import { setupWizardSections } from "./setupWizardCopy";

const phaseItems = [
  "Connect Gmail through a local-only setup flow",
  "Reconstruct applications from job-search email history",
  "Answer factual dashboard questions from deterministic data",
] as const;

function App() {
  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">Phase 0 frontend shell</p>
        <h1 id="page-title">
          JobTracker turns your inbox into job-search intelligence.
        </h1>
        <p className="hero-copy">
          This local-first app will connect to Gmail, reconstruct applications, and keep every factual answer grounded in the application timeline.
        </p>
      </section>

      <section className="status-card" aria-labelledby="status-title">
        <div>
          <p className="eyebrow">Current milestone</p>
          <h2 id="status-title">Frontend foundation ready for Phase 0 pages</h2>
        </div>
        <ul>
          {phaseItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="status-card" aria-labelledby="sync-title">
        <div>
          <p className="eyebrow">Sync readiness</p>
          <h2 id="sync-title">Sync status ready for backend wiring</h2>
        </div>
        <ul>
          <li>Manual sync and last-run state will appear here once the sync API exists.</li>
          <li>No Gmail data is fetched or retained by the Phase 0 frontend shell.</li>
        </ul>
      </section>

      <ChartPanel
        description="A small accessible wrapper layer is ready for future deterministic dashboard charts, while Phase 0 avoids real dashboard metrics."
        emptyState={{
          title: "Dashboard data pending",
          description:
            "Future deterministic dashboard metrics will render here after the metrics API exists.",
        }}
        title="Chart foundation"
      />

      <section className="wizard-copy" aria-labelledby="wizard-title">
        <div className="section-heading">
          <p className="eyebrow">First-run setup copy</p>
          <h2 id="wizard-title">The wizard must make each privacy and provider choice explicit.</h2>
          <p>
            These cards provide the setup-screen copy for provider, mode, Gmail, and privacy choices while the full wizard flow is still being scaffolded.
          </p>
        </div>

        <div className="wizard-grid">
          {setupWizardSections.map((section) => (
            <article className="wizard-card" key={section.title}>
              <h3>{section.title}</h3>
              <p>{section.body}</p>
              <ul>
                {section.options.map((option) => (
                  <li key={option.label}>
                    <strong>{option.label}</strong>
                    <span>{option.body}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

export default App;
