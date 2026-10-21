import { afterEach, describe, expect, it, vi } from "vitest";

import { resolvePrefectUrl } from "../prefectUrl";

describe("resolvePrefectUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses the explicit override without a trailing slash", () => {
    vi.stubEnv("NEXT_PUBLIC_PREFECT_URL", " https://prefect.example/ ");
    expect(resolvePrefectUrl({ hostname: "192.168.0.4" })).toBe("https://prefect.example");
  });

  it("uses the page host on the default port when no override is set", () => {
    vi.stubEnv("NEXT_PUBLIC_PREFECT_URL", "");
    vi.stubEnv("NEXT_PUBLIC_PREFECT_PORT", "");
    expect(resolvePrefectUrl({ hostname: "192.168.0.4" })).toBe("http://192.168.0.4:4200");
  });

  it("uses the configured port over plain HTTP", () => {
    vi.stubEnv("NEXT_PUBLIC_PREFECT_URL", "");
    vi.stubEnv("NEXT_PUBLIC_PREFECT_PORT", "4300");
    expect(resolvePrefectUrl({ hostname: "localhost" })).toBe("http://localhost:4300");
  });

  it("brackets bare IPv6 hostnames and keeps bracketed ones", () => {
    vi.stubEnv("NEXT_PUBLIC_PREFECT_URL", "");
    vi.stubEnv("NEXT_PUBLIC_PREFECT_PORT", "");
    expect(resolvePrefectUrl({ hostname: "::1" })).toBe("http://[::1]:4200");
    expect(resolvePrefectUrl({ hostname: "[::1]" })).toBe("http://[::1]:4200");
  });

  it("falls back to localhost without a location", () => {
    vi.stubEnv("NEXT_PUBLIC_PREFECT_URL", "");
    vi.stubEnv("NEXT_PUBLIC_PREFECT_PORT", "");
    expect(resolvePrefectUrl()).toBe("http://localhost:4200");
  });
});
