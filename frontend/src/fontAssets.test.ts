import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("font assets", () => {
  it("bundles the approved fonts without runtime third-party requests", () => {
    const index = readFileSync(resolve(process.cwd(), "index.html"), "utf8");
    const entry = readFileSync(resolve(process.cwd(), "src/main.tsx"), "utf8");

    expect(index).not.toMatch(/fonts\.(googleapis|gstatic)\.com/);
    expect(entry).toContain('@fontsource/instrument-sans/400.css');
    expect(entry).toContain('@fontsource/instrument-sans/500.css');
    expect(entry).toContain('@fontsource/instrument-sans/600.css');
    expect(entry).toContain('@fontsource/instrument-sans/700.css');
    expect(entry).toContain('@fontsource/jetbrains-mono/400.css');
    expect(entry).toContain('@fontsource/jetbrains-mono/500.css');
  });
});
