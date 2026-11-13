import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import nextConfig from "../../../next.config.js";

describe("next.config.js", () => {
  it("leaves /api and /prefect to Caddy", () => {
    // Caddy proxies /api and /prefect, with the Prefect access check, in production
    // and under `task dev-local`. A Next.js rewrite or route handler under /api would
    // bypass that check or buffer the Copilot chat stream.
    expect("rewrites" in nextConfig).toBe(false);
    expect(existsSync(resolve(__dirname, "../../app/api"))).toBe(false);
  });

  it("keeps the redirects of renamed pages", async () => {
    const redirects = await nextConfig.redirects();

    expect(redirects).toEqual(
      expect.arrayContaining([
        { source: "/files", destination: "/config", permanent: true },
        { source: "/task-knowledge", destination: "/knowledge", permanent: true },
      ]),
    );
  });
});
