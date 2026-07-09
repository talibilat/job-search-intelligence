import { describe, expect, it } from "vitest";

import config from "../vite.config";

describe("vite config", () => {
  it("proxies the metrics API to the local backend", () => {
    const viteConfig = config as { server?: { proxy?: Record<string, unknown> } };

    expect(viteConfig.server?.proxy).toHaveProperty("/metrics");
  });

  it("proxies the pipeline, classification, insights, and applications APIs", () => {
    const viteConfig = config as { server?: { proxy?: Record<string, unknown> } };

    expect(viteConfig.server?.proxy).toHaveProperty("/pipeline");
    expect(viteConfig.server?.proxy).toHaveProperty("/classification");
    expect(viteConfig.server?.proxy).toHaveProperty("/insights");
    expect(viteConfig.server?.proxy).toHaveProperty("/applications");
  });
});
