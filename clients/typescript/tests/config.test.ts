import { mkdtemp, readFile, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { QDashConfig, QDashConfigError } from "../src/index.js";

describe("QDashConfig", () => {
  it("loads the same environment variables as the Python client", () => {
    const config = QDashConfig.fromEnv({
      QDASH_BASE_URL: "https://qdash.example/api/",
      QDASH_API_TOKEN: "token",
      QDASH_PROJECT_ID: "project-1",
      QDASH_CF_ACCESS_CLIENT_ID: "cf-id",
      QDASH_CF_ACCESS_CLIENT_SECRET: "cf-secret",
      QDASH_RETRY_MAX_ATTEMPTS: "4",
    });

    expect(config.baseUrl).toBe("https://qdash.example/api");
    expect(config.projectId).toBe("project-1");
    expect(config.retry.maxAttempts).toBe(4);
  });

  it("round-trips Python-compatible profiles with owner-only permissions", async () => {
    const directory = await mkdtemp(join(tmpdir(), "qdash-client-ts-"));
    const path = join(directory, "config.ini");
    const original = new QDashConfig({
      baseUrl: "https://qdash.example/api",
      apiToken: "token",
      projectId: "project-1",
      timeoutSeconds: 12,
    });

    await original.save("mackerel", path);
    const loaded = await QDashConfig.fromFile("mackerel", path);

    expect(loaded.baseUrl).toBe(original.baseUrl);
    expect(loaded.apiToken).toBe("token");
    expect(loaded.timeoutSeconds).toBe(12);
    expect((await stat(path)).mode & 0o777).toBe(0o600);
    expect(await readFile(path, "utf8")).toContain("[mackerel]");
  });

  it("requires QDASH_BASE_URL", () => {
    expect(() => QDashConfig.fromEnv({})).toThrow(QDashConfigError);
  });
});
