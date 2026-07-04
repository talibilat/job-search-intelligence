import { Button } from "../components/ui";
import { setupWizardSections } from "../setupWizardCopy";
import "./SetupPage.css";

const setupSteps = [
  {
    title: "Choose provider",
    body: "Select Azure OpenAI or Ollama without storing secret values in the browser shell.",
  },
  {
    title: "Classification mode",
    body: "Confirm hybrid, llm, or local mode before any future inbox classification run.",
  },
  {
    title: "Connect Gmail",
    body: "Prepare for a user-owned Google OAuth client with gmail.readonly scope only.",
  },
  {
    title: "Ready state",
    body: "Keep setup incomplete until provider choices and Gmail authorization are explicitly accepted.",
  },
] as const;

export function SetupPage() {
  return (
    <main className="app-shell setup-page">
      <section className="setup-hero" aria-labelledby="setup-page-title">
        <p className="eyebrow">First-run setup</p>
        <h1 id="setup-page-title">Set up JobTracker locally</h1>
        <p className="hero-copy">
          Configure provider choices, classification mode, and Gmail authorization boundaries before the app reaches a ready state.
        </p>
        <div className="setup-actions" aria-label="Setup actions">
          <Button disabled>Save setup choices</Button>
          <Button disabled variant="secondary">
            Gmail OAuth pending
          </Button>
        </div>
      </section>

      <section className="setup-layout" aria-labelledby="setup-checklist-title">
        <div className="setup-checklist-card">
          <p className="eyebrow">Phase 0 shell</p>
          <h2 id="setup-checklist-title">Setup checklist</h2>
          <p>
            This shell makes the required first-run choices visible while later tickets wire the real persistence, secret store, and OAuth flows.
          </p>
          <ol className="setup-checklist">
            {setupSteps.map((step, index) => (
              <li key={step.title}>
                <span aria-hidden="true">{index + 1}</span>
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>

        <aside className="setup-privacy-card" aria-labelledby="setup-privacy-title">
          <p className="eyebrow">Privacy boundary</p>
          <h2 id="setup-privacy-title">No secrets in this page shell</h2>
          <p>
            Secret material stays behind SecretStore-owned backend boundaries. This UI only names the choices the setup API shell will validate.
          </p>
        </aside>
      </section>

      <section className="wizard-copy" id="setup-choices" aria-labelledby="setup-choices-title">
        <div className="section-heading">
          <p className="eyebrow">Required choices</p>
          <h2 id="setup-choices-title">The wizard must make each privacy and provider choice explicit.</h2>
          <p>
            These cards keep setup aligned with FR-0 and FR-6 without implementing later provider auth or secret persistence work.
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
