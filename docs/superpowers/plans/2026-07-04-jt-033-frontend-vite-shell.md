# JT-033 Frontend Vite Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 0 frontend application shell with React, TypeScript, and Vite for `JT-033`.

**Architecture:** The frontend shell is a minimal Vite single-page React app under `frontend/`.
It renders static Phase 0 product copy and establishes the root mount point without introducing routes, API calls, UI primitives, charts, or CI.
This keeps `JT-033` as the foundation other frontend tickets can build on.

**Tech Stack:** React, TypeScript, Vite, npm, plain CSS.

## Global Constraints

- Work only in a dedicated Treehouse worktree for `JT-033`.
- Target base branch is `origin/main`.
- Preserve the local-first product invariant: factual answers come from `applications` and `application_events`.
- Do not introduce telemetry, shared credentials, autonomous outbound email, auto-apply behavior, or multi-user SaaS assumptions.
- Do not add generated API client work from `JT-035`.
- Do not add shared UI primitives from `JT-042`.
- Do not add frontend lint scripts, ESLint config, or dedicated typecheck package scripts from `JT-034`.
- Do not add frontend CI from `JT-048`.
- Do not add Playwright smoke harness work from `JT-054`.
- Do not add setup, dashboard, insights, chat, Recharts, or route-query helper work from later frontend tickets.
- Keep Markdown full sentences on their own physical lines.
- Do not use the em dash character.

---

## File Structure

- Create `frontend/package.json` as the npm project manifest with Vite scripts.
- Create `frontend/package-lock.json` by running npm install commands.
- Create `frontend/index.html` as the Vite HTML entrypoint.
- Create `frontend/vite.config.ts` for the React plugin.
- Create `frontend/tsconfig.json` for project references.
- Create `frontend/tsconfig.app.json` for browser TypeScript settings.
- Create `frontend/tsconfig.node.json` for Vite config TypeScript settings.
- Create `frontend/src/main.tsx` as the React root renderer.
- Create `frontend/src/App.tsx` as the static Phase 0 shell component.
- Create `frontend/src/index.css` for app-level styling only.
- Create `frontend/src/vite-env.d.ts` for Vite client types.
- Modify `README.md` only to reflect that the frontend shell exists and to document current frontend commands.
- Leave `frontend/src/api/.gitkeep`, `frontend/src/components/.gitkeep`, `frontend/src/lib/.gitkeep`, and `frontend/src/pages/.gitkeep` in place for later tickets.

---

### Task 1: Prepare The Isolated Worktree

**Files:**

- No application files are created in this task.

**Interfaces:**

- Consumes: Treehouse lease for `JT-033`.
- Produces: Clean branch `jt-033-frontend-vite-shell` at `origin/main`.

- [ ] **Step 1: Verify the leased worktree is clean**

Run: `git status --short --branch`

Expected: the active branch is `jt-033-frontend-vite-shell` and there are no tracked or untracked changes except work created for this issue.

- [ ] **Step 2: Confirm the worktree base**

Run: `git rev-parse HEAD` and `git rev-parse origin/main`

Expected: both commands print the same commit before implementation changes are added.

---

### Task 2: Establish Frontend Package Metadata

**Files:**

- Create: `frontend/package.json`
- Create by command: `frontend/package-lock.json`

**Interfaces:**

- Consumes: empty `frontend/` scaffold from `JT-002`.
- Produces: npm package with `dev`, `build`, and `preview` scripts.

- [ ] **Step 1: Run the frontend smoke check before implementation**

Run: `npm run build`

Expected: failure because `frontend/package.json` does not exist yet.

- [ ] **Step 2: Add the initial package manifest**

Write `frontend/package.json` with this content:

```json
{
  "name": "job-search-intelligence-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  }
}
```

- [ ] **Step 3: Install frontend dependencies**

Run: `npm install react react-dom`

Expected: npm adds React runtime dependencies to `frontend/package.json` and creates `frontend/package-lock.json`.

- [ ] **Step 4: Install frontend development dependencies**

Run: `npm install --save-dev @types/react @types/react-dom @vitejs/plugin-react typescript vite`

Expected: npm adds TypeScript, Vite, React plugin, and React type packages to `frontend/package.json` and updates `frontend/package-lock.json`.

---

### Task 3: Add Vite And TypeScript Entry Files

**Files:**

- Create: `frontend/index.html`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/src/vite-env.d.ts`

**Interfaces:**

- Consumes: npm package metadata from Task 2.
- Produces: Vite can resolve `index.html`, compile TSX, and load React.

- [ ] **Step 1: Add the Vite HTML entrypoint**

Write `frontend/index.html` with this content:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="Local-first job-search intelligence app" />
    <title>JobTracker</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Add the Vite config**

Write `frontend/vite.config.ts` with this content:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
```

- [ ] **Step 3: Add TypeScript project references**

Write `frontend/tsconfig.json` with this content:

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

- [ ] **Step 4: Add browser TypeScript settings**

Write `frontend/tsconfig.app.json` with this content:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "allowImportingTsExtensions": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["src"]
}
```

- [ ] **Step 5: Add Node TypeScript settings for Vite config**

Write `frontend/tsconfig.node.json` with this content:

```json
{
  "compilerOptions": {
    "target": "ES2023",
    "lib": ["ES2023"],
    "allowImportingTsExtensions": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 6: Add Vite client types**

Write `frontend/src/vite-env.d.ts` with this content:

```ts
/// <reference types="vite/client" />
```

---

### Task 4: Add The React App Shell

**Files:**

- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/index.css`

**Interfaces:**

- Consumes: `index.html` root element with id `root`.
- Produces: static Phase 0 frontend shell rendered by React.

- [ ] **Step 1: Add the React root renderer**

Write `frontend/src/main.tsx` with this content:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 2: Add the app shell component**

Write `frontend/src/App.tsx` with this content:

```tsx
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
        <h1 id="page-title">JobTracker turns your inbox into job-search intelligence.</h1>
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
```

- [ ] **Step 3: Add app-level CSS**

Write `frontend/src/index.css` with this content:

```css
:root {
  color: #132019;
  background: #f4f1ea;
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-synthesis: none;
  line-height: 1.5;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

* {
  box-sizing: border-box;
}

body {
  min-width: 320px;
  min-height: 100vh;
  margin: 0;
  overflow-x: hidden;
}

button,
input,
textarea,
select {
  font: inherit;
}

.app-shell {
  width: min(100%, 1120px);
  min-width: 0;
  min-height: 100vh;
  margin: 0 auto;
  padding: 64px 24px;
}

.hero {
  display: grid;
  gap: 24px;
  max-width: 860px;
}

.eyebrow {
  margin: 0;
  color: #3f6b52;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  max-width: 820px;
  margin-bottom: 0;
  color: #102417;
  font-size: clamp(2.7rem, 8vw, 5.9rem);
  line-height: 0.92;
  letter-spacing: -0.08em;
  overflow-wrap: anywhere;
}

h2 {
  margin-bottom: 0;
  color: #102417;
  font-size: clamp(1.45rem, 3vw, 2.25rem);
  line-height: 1;
  letter-spacing: -0.04em;
  overflow-wrap: anywhere;
}

.hero-copy {
  max-width: 650px;
  margin-bottom: 0;
  color: #4e5e53;
  font-size: clamp(1.05rem, 2vw, 1.3rem);
}

.status-card {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 32px;
  min-width: 0;
  margin-top: 56px;
  padding: 32px;
  border: 1px solid #d8d0bf;
  border-radius: 28px;
  background: #fffaf0;
  box-shadow: 0 24px 70px rgb(36 50 38 / 12%);
}

.status-card ul {
  display: grid;
  gap: 16px;
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.status-card li {
  min-width: 0;
  padding: 16px 18px;
  border-radius: 18px;
  background: #edf6eb;
  color: #203f2c;
  font-weight: 700;
  overflow-wrap: anywhere;
}

@media (max-width: 720px) {
  .app-shell {
    padding: 40px 18px;
  }

  h1 {
    font-size: clamp(2.1rem, 10vw, 3rem);
    line-height: 0.98;
    letter-spacing: -0.06em;
  }

  .status-card {
    grid-template-columns: minmax(0, 1fr);
    padding: 24px;
  }
}
```

---

### Task 5: Update README Documentation

**Files:**

- Modify: `README.md`

**Interfaces:**

- Consumes: frontend package scripts from Task 2.
- Produces: documentation that accurately describes the current frontend shell.

- [ ] **Step 1: Update repository status copy**

Change the Phase 0 status paragraph so it says the repo contains the frontend Vite React TypeScript shell.

- [ ] **Step 2: Add frontend commands to Development**

Add these bullets to the Development section:

```markdown
- Frontend setup: `npm install` from `frontend/`.
- Frontend dev server: `npm run dev` from `frontend/`.
- Current frontend TypeScript check: `npx tsc -b` from `frontend/`.
- Current frontend build check: `npm run build` from `frontend/`.
- Current frontend preview server: `npm run preview` from `frontend/` after a successful build.
- At the time of the JT-033 plan, frontend lint and test scripts were pending; JT-034 and JT-054 owned those later checks.
```

---

### Task 6: Verify And Prepare For Review

**Files:**

- All files from Tasks 2 through 5.

**Interfaces:**

- Consumes: frontend shell and README changes.
- Produces: verification evidence for the `JT-033` PR.

- [ ] **Step 1: Run the frontend TypeScript check**

Run: `npx tsc -b`

Expected: TypeScript project references compile without errors.

- [ ] **Step 2: Run the frontend build**

Run: `npm run build`

Expected: Vite produces `frontend/dist/` without errors.

- [ ] **Step 3: Start the frontend dev server**

Run: `npm run dev -- --host 127.0.0.1`

Expected: Vite reports a local URL on `127.0.0.1`.

- [ ] **Step 4: Verify the served shell**

Fetch the local URL while the dev server is running.

Expected: the HTML response is served and the app assets are reachable.

- [ ] **Step 5: Stop the frontend dev server**

Stop the dev server process after verification.

- [ ] **Step 6: Run backend baseline tests if backend files changed**

Run: `uv run pytest` from `backend/` if backend files changed during the work.

Expected: backend tests pass.

- [ ] **Step 7: Review diff for scope discipline**

Run: `git diff --stat` and `git diff -- frontend README.md docs/superpowers/plans/2026-07-04-jt-033-frontend-vite-shell.md`.

Expected: changes are limited to the frontend shell, README, package lock, and this plan document.

---

## Self-Review

- Spec coverage: Tasks 2 through 4 implement the Vite React TypeScript app shell required by `JT-033`.
- Spec coverage: Task 5 updates relevant documentation.
- Spec coverage: Task 6 verifies the frontend TypeScript check, build, and dev server smoke path.
- Scope check: The plan excludes lint scripts, ESLint config, generated API client, UI primitives, CI, Playwright, route pages, Recharts, and route-query helper work.
- Type consistency: `App` is the default export consumed by `main.tsx`.
- Type consistency: The Vite entrypoint uses `src/main.tsx`, matching `index.html`.
