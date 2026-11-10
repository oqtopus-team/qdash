import { afterEach, describe, expect, it, vi } from "vitest";

import nextConfig from "../../../next.config.js";

type Rewrite = { source: string; destination: string };

async function rewrites(): Promise<Rewrite[]> {
  return (await nextConfig.rewrites()) as Rewrite[];
}

describe("next.config.js rewrites", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("proxies Prefect only from the development server", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("INTERNAL_PREFECT_URL", "http://127.0.0.1:4300");

    expect(await rewrites()).toEqual(
      expect.arrayContaining([
        { source: "/prefect/api/:path*", destination: "http://127.0.0.1:4300/api/:path*" },
        { source: "/prefect/:path*", destination: "http://127.0.0.1:4300/prefect/:path*" },
      ]),
    );
  });

  it("never proxies Prefect from a production build, even with a Prefect URL", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("INTERNAL_PREFECT_URL", "http://prefect-server:4200");

    const sources = (await rewrites()).map((rewrite) => rewrite.source);

    expect(sources).toEqual(["/api/:path*"]);
  });
});
