import { describe, expect, it, vi } from "vitest";

import {
  QDashClient,
  QDashConfig,
  QDashValidationError,
  type AgentSessionPolicy,
} from "../src/index.js";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("QDashClient", () => {
  it("binds authentication headers to Orval-generated operations", async () => {
    const requests: Request[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      requests.push(new Request(input));
      return jsonResponse({ chips: [], total: 0 });
    });
    const client = new QDashClient(
      new QDashConfig({
        baseUrl: "https://qdash.example/api/",
        apiToken: "token",
        projectId: "project-1",
        cfAccessClientId: "client-id",
        cfAccessClientSecret: "client-secret",
      }),
      { fetch },
    );

    await expect(client.api.listChips()).resolves.toEqual({ chips: [], total: 0 });
    expect(requests).toHaveLength(1);
    expect(requests[0]?.url).toBe("https://qdash.example/api/chips");
    expect(requests[0]?.headers.get("Authorization")).toBe("Bearer token");
    expect(requests[0]?.headers.get("X-Project-Id")).toBe("project-1");
    expect(requests[0]?.headers.get("CF-Access-Client-Id")).toBe("client-id");
    expect(requests[0]?.headers.get("CF-Access-Client-Secret")).toBe("client-secret");
  });

  it("retries retryable GET responses", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "unavailable" }, 503))
      .mockResolvedValueOnce(jsonResponse({ chips: [], total: 0 }));
    const wait = vi.fn(async () => undefined);
    const client = new QDashClient(
      new QDashConfig({
        baseUrl: "https://qdash.example/api",
        apiToken: "token",
        retry: { maxAttempts: 2, baseDelaySeconds: 0, maxDelaySeconds: 0 },
      }),
      { fetch, sleep: wait },
    );

    await expect(client.listChips()).resolves.toEqual({ chips: [], total: 0 });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(wait).toHaveBeenCalledTimes(1);
  });

  it("binds body operations from the Orval-generated API", async () => {
    let request: Request | undefined;
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      request = new Request(input);
      return jsonResponse({ session_id: "session-1" });
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );
    const policy = { allowed_qids: ["32"] } as unknown as AgentSessionPolicy;

    await client.api.createAgentSession({
      chip_id: "chip-1",
      policy,
      expires_in_seconds: 21_600,
      skill_name: "pi-extension",
      skill_version: "0.1.0",
      skill_hash: "hash",
      model_name: "model",
    });

    expect(request?.method).toBe("POST");
    expect(await request?.json()).toMatchObject({
      chip_id: "chip-1",
      policy: { allowed_qids: ["32"] },
      skill_name: "pi-extension",
      expires_in_seconds: 21600,
    });
  });

  it("maps validation responses to typed errors", async () => {
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch: async () => jsonResponse({ detail: "invalid candidate" }, 422) },
    );

    const result = client.evaluateAgentCandidateGate("session", "frequency", 1);
    await expect(result).rejects.toBeInstanceOf(QDashValidationError);
    await expect(result).rejects.toMatchObject({
      name: "QDashValidationError",
      statusCode: 422,
    });
  });
});
