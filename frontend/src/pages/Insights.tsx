const insightPlaceholders = [
  "Cached narrative insights will summarize rejection themes, skill gaps, role fit, weekly actions, and the search story.",
  "Future generated insights must cite the applications and emails they are drawn from.",
  "Regeneration remains a later Phase 4 behavior so Phase 0 does not trigger model calls or costs.",
] as const;

export function Insights() {
  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">Phase 0 insights shell</p>
        <h1 id="page-title">Insights</h1>
        <p className="hero-copy">
          Narrative insights will eventually turn deterministic application
          history into grounded recommendations without making the LLM
          authoritative for counts.
        </p>
      </section>

      <section className="status-card" aria-labelledby="insights-status-title">
        <div>
          <p className="eyebrow">Current state</p>
          <h2 id="insights-status-title">
            Narrative insights are not generated yet.
          </h2>
        </div>
        <ul>
          {insightPlaceholders.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </main>
  );
}
