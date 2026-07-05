function Chat() {
  return (
    <main className="app-shell chat-shell">
      <section className="hero chat-hero" aria-labelledby="page-title">
        <p className="eyebrow">Phase 0 chat route shell</p>
        <h1 id="page-title">Ask your job search history.</h1>
        <p className="hero-copy">
          Chat agent work arrives in Phase 5. This shell reserves the route
          without implementing streaming, persisted history, retrieval, or
          provider calls.
        </p>
      </section>

      <section className="chat-panel" aria-labelledby="chat-shell-title">
        <div className="chat-panel__header">
          <p className="eyebrow">Grounded answers later</p>
          <h2 id="chat-shell-title">
            The conversation surface is intentionally empty.
          </h2>
          <p>
            Future answers will cite application records, source emails, or
            deterministic metric outputs. Quantitative chat answers will use
            constrained tools rather than raw SQL from an LLM.
          </p>
        </div>

        <div className="chat-card" role="status" aria-label="Chat unavailable">
          <p className="chat-card__title">Chat is not connected yet.</p>
          <p>
            The route is present so later RAG agent tickets can attach streaming
            responses and local chat history without changing the page entry
            point.
          </p>
        </div>

        <form className="chat-composer" aria-label="Chat composer">
          <label className="chat-composer__label" htmlFor="chat-message">
            Message
          </label>
          <textarea
            aria-describedby="chat-message-hint"
            className="chat-textarea"
            disabled
            id="chat-message"
            placeholder="Chat will be enabled when the Phase 5 agent exists."
            rows={4}
          />
          <p className="chat-composer__hint" id="chat-message-hint">
            Disabled until the backend chat endpoint, history store, and
            grounding checks exist.
          </p>
        </form>
      </section>
    </main>
  );
}

export default Chat;
