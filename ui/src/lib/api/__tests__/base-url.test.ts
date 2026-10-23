import { afterEach, describe, expect, it, vi } from "vitest";

describe("API_BASE_URL", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("stays same-origin even when the legacy public API URL is set", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://legacy-api.example.com/api");
    vi.resetModules();

    const [{ AXIOS_INSTANCE }, { API_BASE_URL }] = await Promise.all([
      import("@/lib/api/custom-instance"),
      import("@/lib/api/base-url"),
    ]);

    expect(API_BASE_URL).toBe("/api");
    expect(AXIOS_INSTANCE.defaults.baseURL).toBe("/api");
  });
});
