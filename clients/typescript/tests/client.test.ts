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

function binaryResponse(payload: Uint8Array, mediaType = "image/png"): Response {
  const body = payload.buffer.slice(
    payload.byteOffset,
    payload.byteOffset + payload.byteLength,
  ) as ArrayBuffer;
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": mediaType },
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

  it("downloads execution figures as binary files", async () => {
    let request: Request | undefined;
    const bytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      request = new Request(input);
      return binaryResponse(bytes);
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    const file = await client.getExecutionFigure("/app/calib_data/run/fig/result.png");

    expect(request?.url).toBe(
      "https://qdash.example/api/executions/figure?path=%2Fapp%2Fcalib_data%2Frun%2Ffig%2Fresult.png",
    );
    expect(file.mediaType).toBe("image/png");
    expect(file.filename).toBe("result.png");
    expect([...new Uint8Array(file.data)]).toEqual([...bytes]);
  });

  it("downloads a figure selected from a task result", async () => {
    const requests: Request[] = [];
    const bytes = new Uint8Array([1, 2, 3]);
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const request = new Request(input);
      requests.push(request);
      if (request.url.endsWith("/tasks/task-1/result")) {
        return jsonResponse({
          task_id: "task-1",
          figure_path: ["/fig/a.png"],
          json_figure_path: ["/fig/a.json"],
        });
      }
      return binaryResponse(bytes, "application/json");
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    const file = await client.getTaskResultFigure("task-1", { preferJson: true });

    expect(requests.map((request) => new URL(request.url).pathname)).toEqual([
      "/api/tasks/task-1/result",
      "/api/executions/figure",
    ]);
    expect(file.path).toBe("/fig/a.json");
    expect(file.mediaType).toBe("application/json");
    expect(file.figurePaths).toEqual(["/fig/a.png"]);
    expect(file.jsonFigurePaths).toEqual(["/fig/a.json"]);
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
