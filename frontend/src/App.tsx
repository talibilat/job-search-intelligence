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
    </main>
  );
}

export default App;
