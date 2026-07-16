interface SetupWizardOption {
  label: string;
  body: string;
}

interface SetupWizardSection {
  title: string;
  body: string;
  options: readonly SetupWizardOption[];
}

export const setupWizardSections: readonly SetupWizardSection[] = [
  {
    title: "Choose your LLM provider",
    body: "Pick where classification, extraction, insights, and chat prompts will run once provider adapters are enabled.",
    options: [
      {
        label: "Azure OpenAI",
        body: "Use your own Azure resource for hosted model quality. Store the API key through SecretStore, then provide the endpoint, API version, chat deployment, and embedding deployment as non-secret setup values.",
      },
      {
        label: "Ollama",
        body: "Use a local Ollama server for offline-first operation. Confirm the local base URL and pulled chat and embedding model names before continuing.",
      },
    ],
  },
  {
    title: "Pick a classification mode",
    body: "Choose how much work goes to the selected provider before the app builds the application timeline.",
    options: [
      {
        label: "hybrid",
        body: "Run the heuristic pre-filter first, then send candidate job-search email to the configured LLM provider. This is the default cost-controlled hosted mode.",
      },
      {
        label: "llm",
        body: "Skip the heuristic pre-filter and send every retained email selected for classification to the configured LLM provider. Use this only when you intentionally prefer model coverage over cost control.",
      },
      {
        label: "local",
        body: "Use the local Ollama path so job-search classification and extraction stay on the machine.",
      },
    ],
  },
  {
    title: "Connect Gmail read-only",
    body: "Authorize a user-owned Google OAuth client with the gmail.readonly scope so JobTracker can ingest metadata and selected retained bodies without sending email or modifying the mailbox.",
    options: [
      {
        label: "OAuth client JSON",
        body: "Keep the Google client JSON outside the repository because it can contain client secret material.",
      },
      {
        label: "Refresh token",
        body: "Store OAuth token material through SecretStore so it is encrypted at rest and never returned by setup status APIs.",
      },
    ],
  },
  {
    title: "Confirm privacy boundaries",
    body: "Review the local-first constraints before the ready state is enabled.",
    options: [
      {
        label: "No shared credentials",
        body: "The app never ships shared API keys, OAuth clients, tokens, or provider accounts.",
      },
      {
        label: "No telemetry",
        body: "Local app state stays in SQLite, and nothing leaves the machine except configured LLM calls and Gmail OAuth/API sync requests.",
      },
      {
        label: "No dashboard counts from LLMs",
        body: "Factual metrics come from deterministic application data, not model output.",
      },
      {
        label: "Local data can be wiped",
        body: "Use POST /local-data/wipe with the exact wipe-local-data confirmation phrase when you intentionally want to delete configured local app data and derived artifacts.",
      },
    ],
  },
] as const;
