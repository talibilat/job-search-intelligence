# Claude Code Instructions for JobTracker

This project uses `AGENTS.md` as the canonical local agent guide.

Before brainstorming, planning, ticket writing, scaffolding, or implementation:

1. Read `AGENTS.md`.
2. Read `docs/prd.md`.
3. Read `docs/groundwork-spec.md`.
4. Read `docs/questions.md`.

Follow the workflows and constraints in `AGENTS.md` exactly.

Key reminders:

- Preserve the local-first architecture.
- Keep dashboard metrics deterministic.
- Never let an LLM produce authoritative counts.
- Never execute raw SQL emitted by an LLM.
- Keep provider integrations behind interfaces.
- Use Pydantic DTOs at boundaries.
- Run the golden-set filter eval for heuristic filter changes.
- Run the golden-set classification eval for classification changes.
- Verify before claiming completion.
- Do not use the em dash character.
