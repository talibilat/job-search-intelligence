import { describe, expect, it } from "vitest";

import config from "../vite.config";

describe("vite config", () => {
  it("proxies the metrics API to the local backend", () => {
    const viteConfig = config as { server?: { proxy?: Record<string, unknown> } };

    expect(viteConfig.server?.proxy).toHaveProperty("/metrics");
  });
});
