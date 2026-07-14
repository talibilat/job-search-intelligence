import { ProviderSetup } from "../components/ProviderSetup";
import "./SetupPage.css";

export function SetupPage() {
  return (
    <main className="app-shell setup-page">
      <section className="setup-hero" aria-labelledby="setup-page-title">
        <p className="eyebrow">First-run setup</p>
        <h1 id="setup-page-title">Set up JobTracker locally</h1>
        <p className="hero-copy">
          Add your own credentials, verify the local providers, and connect Gmail with read-only
          access. Setup is complete only when Gmail sync and classification are both ready.
        </p>
      </section>
      <section aria-label="Setup checklist" className="setup-checklist-card">
        <h2>Setup checklist</h2>
        <ol>
          <li>Choose provider</li>
          <li>Connect Gmail read-only</li>
          <li>Verify sync and classification readiness</li>
        </ol>
      </section>
      <ProviderSetup firstRun />
    </main>
  );
}
