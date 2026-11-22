import { describe, expect, it, vi } from "vitest";

import {
  QDashClient,
  QDashConfig,
  QDashNotFoundError,
  QDashTimeoutError,
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

  it("reads Copilot source through bounded query parameters", async () => {
    const requests: Request[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      requests.push(new Request(input));
      return jsonResponse({});
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    await client.listSourceRoots();
    await client.searchSource({ query: "KeyError", root: "qdash", mode: "path", limit: 5 });
    await client.getSourceFile({ path: "/app/qdash/workflow/x.py", startLine: 10 });
    const urls = requests.map((request) => new URL(request.url));
    expect(urls.map((url) => url.pathname)).toEqual([
      "/api/copilot/source/roots",
      "/api/copilot/source/search",
      "/api/copilot/source/file",
    ]);
    expect(Object.fromEntries(urls[1]!.searchParams)).toEqual({
      query: "KeyError",
      root: "qdash",
      mode: "path",
      limit: "5",
    });
    expect(Object.fromEntries(urls[2]!.searchParams)).toEqual({
      path: "/app/qdash/workflow/x.py",
      start_line: "10",
    });
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

  it("exposes typed read-only operational provenance helpers", async () => {
    const requests: Request[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const request = new Request(input);
      requests.push(request);
      if (request.url.includes("lock-status")) return jsonResponse({ lock: false });
      if (request.url.includes("provenance/compare")) return jsonResponse({ execution_id_before: "before", execution_id_after: "after", changed_parameters: [] });
      if (request.url.includes("degradation-trends")) return jsonResponse({ trends: [], total_count: 0 });
      if (request.url.includes("recommendations")) return jsonResponse({ source_entity_id: "entity", recommended_tasks: [] });
      return jsonResponse({ changes: [], total_count: 0 });
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    await expect(client.getExecutionLockStatus()).resolves.toEqual({ lock: false });
    await expect(client.compareExecutions("before", "after")).resolves.toMatchObject({ execution_id_before: "before" });
    await expect(client.getRecentChanges({ parameterNames: ["t1"], withinHours: 24, limit: 5 })).resolves.toMatchObject({ total_count: 0 });
    await expect(client.getDegradationTrends({ minStreak: 4 })).resolves.toMatchObject({ total_count: 0 });
    await expect(client.getRecalibrationRecommendations("frequency:Q0:exec:task")).resolves.toMatchObject({ source_entity_id: "entity" });

    expect(requests.map((request) => new URL(request.url).pathname)).toEqual([
      "/api/executions/lock-status",
      "/api/provenance/compare",
      "/api/provenance/changes",
      "/api/provenance/degradation-trends",
      "/api/provenance/recommendations/frequency%3AQ0%3Aexec%3Atask",
    ]);
    const changesUrl = new URL(requests[2]!.url);
    expect(changesUrl.searchParams.get("parameter_names")).toBe("t1");
    expect(changesUrl.searchParams.get("within_hours")).toBe("24");
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
      model: { provider: "ollama", model_id: "qwen3:32b", host: "pi" },
    });

    expect(request?.method).toBe("POST");
    expect(await request?.json()).toMatchObject({
      chip_id: "chip-1",
      policy: { allowed_qids: ["32"] },
      skill_name: "pi-extension",
      expires_in_seconds: 21600,
      model: { provider: "ollama", model_id: "qwen3:32b", host: "pi" },
    });
  });

  it("wraps the metric script and dashboard endpoints", async () => {
    const requests: Request[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      requests.push(new Request(input));
      return jsonResponse({});
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    await client.listMetricScripts();
    await client.getMetricScript("ms_0123456789ab");
    await client.listMetricScriptTemplates();
    await client.getMetricScriptCatalog();
    await client.validateMetricScript("x = 1");
    await client.evaluateMetricScriptDraft({
      source: "x = 1",
      metric_id: "m",
      chip_id: "chip-1",
      period: { kind: "relative", days: 14 },
    });
    await client.evaluateMetricScript("ms_1", { metric_id: "m", chip_id: "chip-1", revision: 2 });
    await client.createMetricScript({ name: "Median", source: "x = 1" });
    await client.updateMetricScript("ms_1", { source: "x = 2", expected_revision: 3 });
    await client.copyMetricScript("ms_1");
    await client.deleteMetricScript("ms_1");
    await client.listDashboards();
    await client.getDashboard("cd/1");
    await client.listDashboardTemplates();
    await client.previewDashboardTemplate("frequency-collision-map");
    await client.createDashboard({ name: "Board" });
    await client.updateDashboard("cd_1", { panels: [] });

    expect(requests.map((request) => `${request.method} ${new URL(request.url).pathname}`)).toEqual([
      "GET /api/metric-scripts",
      "GET /api/metric-scripts/ms_0123456789ab",
      "GET /api/metric-scripts/templates",
      "GET /api/metric-scripts/catalog",
      "POST /api/metric-scripts/validate",
      "POST /api/metric-scripts/evaluate",
      "POST /api/metric-scripts/ms_1/evaluate",
      "POST /api/metric-scripts",
      "PATCH /api/metric-scripts/ms_1",
      "POST /api/metric-scripts/ms_1/copy",
      "DELETE /api/metric-scripts/ms_1",
      "GET /api/dashboards",
      "GET /api/dashboards/cd%2F1",
      "GET /api/dashboards/templates",
      "GET /api/dashboards/templates/frequency-collision-map/preview",
      "POST /api/dashboards",
      "PATCH /api/dashboards/cd_1",
    ]);
    expect(await requests[8]?.json()).toEqual({ source: "x = 2", expected_revision: 3 });
    expect(await requests[6]?.json()).toEqual({ metric_id: "m", chip_id: "chip-1", revision: 2 });
  });

  it("sends an agent action's source execution only as provenance", async () => {
    const bodies: unknown[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      bodies.push(await new Request(input, init).json());
      return jsonResponse({ action_id: "action-1" });
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    await client.executeAgentAction("session-1", "action-1");
    await client.executeAgentAction("session-1", "action-1", { sourceExecutionId: "exec-1" });

    expect(bodies[0]).toEqual({ update_params: false, reconfigure: false });
    expect(bodies[1]).toEqual({
      source_execution_id: "exec-1",
      update_params: false,
      reconfigure: false,
    });
  });

  it("sends autonomous steps only when asked and reads the authenticated user", async () => {
    const requests: Array<{ method: string; path: string; body: unknown }> = [];
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      requests.push({
        method: request.method,
        path: new URL(request.url).pathname,
        body: request.method === "POST" ? await request.json() : undefined,
      });
      return jsonResponse(request.method === "GET" ? { username: "alice" } : { action_id: "a-1" });
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    expect((await client.getCurrentUser()).username).toBe("alice");
    const step = { idempotencyKey: "k", expectedStateVersion: 2, actionType: "run_task" as const, taskName: "CheckRabi", qids: ["Q00"] };
    await client.submitAgentAction("s-1", step);
    await client.submitAgentAction("s-1", { ...step, autonomous: true, repeatOfActionId: "a-0" });
    await client.executeAgentAction("s-1", "a-1", { autonomous: true });
    await client.createAgentIntervention("s-1", { idempotencyKey: "h", reason: "agent_request", summary: "s", question: "q", autonomous: true });
    const model = { provider: "vllm", model_id: "qwen3-32b", host: "qdash-web-agent" };
    await client.submitAgentAction("s-1", { ...step, model });
    await client.createAgentIntervention("s-1", { idempotencyKey: "h2", reason: "agent_request", summary: "s", question: "q", model });

    expect(requests[0]).toMatchObject({ method: "GET", path: "/api/auth/me" });
    // Without the flag the request is what an older server already accepts.
    expect(requests[1]!.body).not.toHaveProperty("autonomous");
    expect(requests[1]!.body).not.toHaveProperty("repeat_of_action_id");
    expect(requests[2]!.body).toMatchObject({ autonomous: true, repeat_of_action_id: "a-0" });
    expect(requests[3]!.body).toEqual({ update_params: false, reconfigure: false, autonomous: true });
    expect(requests[4]!.body).toMatchObject({ idempotency_key: "h", autonomous: true });
    // The host's model is sent only when the host reported one.
    expect(requests[1]!.body).not.toHaveProperty("model");
    expect(requests[4]!.body).not.toHaveProperty("model");
    expect(requests[5]!.body).toMatchObject({ model });
    expect(requests[6]!.body).toMatchObject({ model });
  });

  it("reads a session's interventions without changing them", async () => {
    const requests: Request[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      requests.push(request);
      return request.url.endsWith("/interventions")
        ? jsonResponse({ items: [{ intervention_id: "int-1" }], total: 1 })
        : jsonResponse({ intervention_id: "int-1" });
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    const items = await client.listAgentInterventions("session 1");
    const one = await client.getAgentIntervention("session 1", "int-1");

    expect(items.map((item) => item.intervention_id)).toEqual(["int-1"]);
    expect(one.intervention_id).toBe("int-1");
    expect(requests.map((request) => `${request.method} ${new URL(request.url).pathname}`)).toEqual([
      "GET /api/agent-sessions/session%201/interventions",
      "GET /api/agent-sessions/session%201/interventions/int-1",
    ]);
  });

  it("records decisions and reads the audit in pages and as an export", async () => {
    const requests: Array<{ method: string; url: URL; body: unknown }> = [];
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      requests.push({
        method: request.method,
        url: new URL(request.url),
        body: request.method === "POST" ? await request.json() : undefined,
      });
      if (request.method === "POST") return jsonResponse({ decision_id: "d-1" });
      if (request.url.endsWith("/decisions")) return jsonResponse({ items: [{ decision_id: "d-1" }], total: 1 });
      return jsonResponse({ events: [], complete: true, total_events: 0 });
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    await client.recordAgentDecision("s 1", {
      idempotencyKey: "k",
      interpretation: "R2 0.4 fails the criterion",
      nextAction: "request_human",
      evidenceActionIds: ["a-1"],
    });
    await client.recordAgentDecision("s 1", {
      idempotencyKey: "k2",
      assessment: "pass",
      interpretation: "ok",
      nextAction: "next_task",
      nextActionId: "a-2",
      supersedesDecisionId: "d-0",
      model: { provider: "ollama", model_id: "qwen3:32b", host: "pi" },
    });
    expect((await client.listAgentDecisions("s 1")).map((item) => item.decision_id)).toEqual(["d-1"]);
    await client.getAgentSessionAudit("s 1", { cursor: "c-1", limit: 50 });
    await client.exportAgentSessionAudit("s 1");

    expect(requests[0]!.url.pathname).toBe("/api/agent-sessions/s%201/decisions");
    expect(requests[0]!.body).toEqual({
      idempotency_key: "k",
      interpretation: "R2 0.4 fails the criterion",
      next_action: "request_human",
      next_detail: "",
      evidence_action_ids: ["a-1"],
      evaluation_ids: [],
    });
    expect(requests[1]!.body).toMatchObject({
      assessment: "pass",
      next_action_id: "a-2",
      supersedes_decision_id: "d-0",
      model: { provider: "ollama", model_id: "qwen3:32b", host: "pi" },
    });
    expect(requests[3]!.url.pathname).toBe("/api/agent-sessions/s%201/audit");
    expect(requests[3]!.url.searchParams.get("cursor")).toBe("c-1");
    expect(requests[3]!.url.searchParams.get("limit")).toBe("50");
    expect(requests[4]!.url.pathname).toBe("/api/agent-sessions/s%201/audit/export");
  });

  it("lists sessions with repeated status filters and records an intervention", async () => {
    const requests: Request[] = [];
    const bodies: unknown[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      requests.push(request);
      if (request.method === "POST") {
        bodies.push(await request.json());
        return jsonResponse({ intervention_id: "int-2" });
      }
      return jsonResponse({ items: [{ session_id: "s-1" }], total: 1 });
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    const sessions = await client.listAgentSessions({
      chipId: "chip-001",
      statuses: ["active", "waiting_for_human"],
      mine: true,
    });
    const created = await client.createAgentIntervention("s-1", {
      idempotencyKey: "k-1",
      reason: "unknown_outcome",
      summary: "CheckRabi showed no oscillation",
      question: "Is the drive line connected?",
      taskName: "CheckRabi",
      qids: ["Q00"],
      attempts: [{ action_id: "a-1", task_name: "CheckRabi", qid: "Q00" }],
    });

    expect(sessions.map((item) => item.session_id)).toEqual(["s-1"]);
    expect(created.intervention_id).toBe("int-2");
    const listUrl = new URL(requests[0]!.url);
    expect(listUrl.pathname).toBe("/api/agent-sessions");
    expect(listUrl.searchParams.getAll("status")).toEqual(["active", "waiting_for_human"]);
    expect(listUrl.searchParams.get("chip_id")).toBe("chip-001");
    expect(listUrl.searchParams.get("mine")).toBe("true");
    expect(listUrl.searchParams.has("limit")).toBe(false);
    expect(new URL(requests[1]!.url).pathname).toBe("/api/agent-sessions/s-1/interventions");
    expect(bodies[0]).toEqual({
      idempotency_key: "k-1",
      reason: "unknown_outcome",
      summary: "CheckRabi showed no oscillation",
      question: "Is the drive line connected?",
      task_name: "CheckRabi",
      qids: ["Q00"],
      attempts: [{ action_id: "a-1", task_name: "CheckRabi", qid: "Q00" }],
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

  it("waits for a whole pipeline run, not just the first step's execution", async () => {
    const detail = (pipelineStatus: string, status = "completed") => ({
      name: "pipeline-exec-1",
      status,
      task: [],
      note: {},
      pipeline: {
        name: "coarse",
        flow_run_id: "run-1",
        root_execution_id: "exec-1",
        status: pipelineStatus,
        steps: [],
      },
    });
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(detail("running")))
      .mockResolvedValueOnce(jsonResponse(detail("completed")));
    const wait = vi.fn(async () => undefined);
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch, sleep: wait },
    );

    const result = await client.waitForExecution("exec-1", { pollIntervalSeconds: 0.01 });

    expect(result.pipeline?.status).toBe("completed");
    expect(fetch).toHaveBeenCalledTimes(2);

    // Opting out returns as soon as the step itself is done.
    const single = vi.fn().mockResolvedValueOnce(jsonResponse(detail("running")));
    const stepClient = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch: single, sleep: wait },
    );
    await expect(
      stepClient.waitForExecution("exec-1", { wholePipeline: false }),
    ).resolves.toMatchObject({ status: "completed" });
    expect(single).toHaveBeenCalledTimes(1);
  });

  it("uploads forum images as multipart data with a fetch-generated boundary", async () => {
    let request: Request | undefined;
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      request = new Request(input);
      return jsonResponse({ url: "/api/forum/images/generated.png" });
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    await expect(
      client.uploadForumImage(
        new Blob([new Uint8Array([0x89, 0x50])], { type: "image/png" }),
        "analysis.png",
      ),
    ).resolves.toEqual({ url: "/api/forum/images/generated.png" });

    expect(request?.method).toBe("POST");
    expect(request?.headers.get("Content-Type")).toMatch(/^multipart\/form-data; boundary=/);
    const form = await request?.formData();
    const file = form?.get("file");
    expect(file).toBeInstanceOf(File);
    if (!(file instanceof File)) throw new TypeError("expected a multipart file");
    expect(file.name).toBe("analysis.png");
    expect(file.type).toBe("image/png");
  });

  it("repairs the generated multipart header before sending forum images", async () => {
    let request: Request | undefined;
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      request = new Request(input);
      return jsonResponse({ url: "/api/forum/images/generated.png" });
    });
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );

    const file = new Blob(["image"], { type: "image/png" });
    await client.api.uploadForumImage({ file });

    expect(request?.headers.get("Content-Type")).toMatch(/^multipart\/form-data; boundary=/);
    const form = await request?.formData();
    const uploadedFile = form?.get("file");
    expect(uploadedFile).toBeInstanceOf(File);
    if (!(uploadedFile instanceof File)) throw new TypeError("expected a multipart file");
    expect(uploadedFile.type).toBe("image/png");
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

  it("spells out which field a FastAPI validation error is about", async () => {
    const client = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      {
        fetch: async () =>
          jsonResponse(
            {
              detail: [
                { type: "missing", loc: ["body", "policy", "qids"], msg: "Field required" },
                { type: "missing", loc: ["body", "policy", "allowed_tasks"], msg: "Field required" },
              ],
            },
            422,
          ),
      },
    );

    const result = client.createAgentSession({ chipId: "144Qv2", policy: {} as never });
    await expect(result).rejects.toThrow(
      "policy.qids: Field required; policy.allowed_tasks: Field required",
    );
    await expect(result).rejects.not.toThrow("[object Object]");
  });
});

describe("SDK-facing client helpers", () => {
  function recording(replies: Response[]) {
    const projects: (string | null)[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      projects.push(new Request(input, init).headers.get("X-Project-Id"));
      const reply = replies.shift();
      if (!reply) throw new Error("unexpected request");
      return reply;
    });
    return { fetch, projects };
  }

  it("waitForExecution still throws on 404 unless asked to treat it as pending", async () => {
    const { fetch } = recording([
      jsonResponse({ detail: "missing" }, 404),
      jsonResponse({ detail: "missing" }, 404),
    ]);
    const base = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token" }),
      { fetch },
    );
    await expect(base.waitForExecution("exec-1", { pollIntervalSeconds: 0 })).rejects.toBeInstanceOf(
      QDashNotFoundError,
    );
    const timeout = await base
      .waitForExecution("exec-1", { timeoutSeconds: 0, notFoundAsPending: true })
      .catch((caught: unknown) => caught);
    expect(timeout).toBeInstanceOf(QDashTimeoutError);
    expect(timeout).toBeInstanceOf(Error);
    expect((timeout as Error).message).toBe(
      "Execution 'exec-1' did not reach a terminal state within 0 seconds",
    );
  });

  it("withProject returns a scoped copy and keeps transport options", async () => {
    const { fetch, projects } = recording([jsonResponse({ chips: [] })]);
    const base = new QDashClient(
      new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token", projectId: "a" }),
      { fetch },
    );
    const scoped = base.withProject("b");
    expect(base.config.projectId).toBe("a");
    expect(scoped.config).toMatchObject({ baseUrl: base.config.baseUrl, apiToken: "token", projectId: "b" });
    await scoped.listChips();
    expect(projects).toEqual(["b"]);
  });
});

describe("task result pages", () => {
  const row = (index: number) => ({
    task_id: `t-${index}`,
    task_name: "CheckT1",
    qid: "6",
    chip_id: "C",
    status: "completed",
    execution_id: "e-1",
  });

  /** A fixture holding `total` rows; it answers each request with the rows at skip..skip+limit. */
  function pagedClient(total: number, options: { failAt?: number; shortAt?: number } = {}) {
    const requests: URL[] = [];
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(new Request(input).url);
      requests.push(url);
      const skip = Number(url.searchParams.get("skip") ?? 0);
      const limit = Number(url.searchParams.get("limit") ?? 50);
      if (options.failAt === skip) return jsonResponse({ detail: "boom" }, 500);
      const end = options.shortAt === skip ? skip + 1 : Math.min(total, skip + limit);
      const items = Array.from({ length: Math.max(0, end - skip) }, (_, index) => row(skip + index));
      return jsonResponse({ items, total, skip, limit, status_counts: { completed: total } });
    });
    const client = new QDashClient(
      new QDashConfig({
        baseUrl: "https://qdash.example/api",
        apiToken: "token",
        retry: { maxAttempts: 1 },
      }),
      { fetch },
    );
    return { client, requests, fetch };
  }

  it("sends the API's own filter names, with qid passed through exactly", async () => {
    const { client, requests } = pagedClient(3);
    await client.listTaskResults({
      chipId: "C",
      qid: "6-7",
      taskName: "CheckCR",
      startFrom: "2026-11-01T00:00:00Z",
      startTo: "2026-11-02T00:00:00Z",
      messageContains: "fit",
      limit: 100,
      skip: 0,
    });
    expect(Object.fromEntries(requests[0]!.searchParams)).toEqual({
      chip_id: "C",
      qid: "6-7",
      task_name: "CheckCR",
      start_from: "2026-11-01T00:00:00Z",
      start_to: "2026-11-02T00:00:00Z",
      message_contains: "fit",
      limit: "100",
      skip: "0",
    });
  });

  it.each([
    [{ limit: 200 }, /limit must be an integer from 1 to 100 \(got 200\).*collectTaskResults/],
    [{ limit: 0 }, /limit must be an integer from 1 to 100/],
    [{ limit: 2.5 }, /limit must be an integer/],
    [{ skip: -1 }, /skip must be an integer 0 or more/],
    [{ skip: 1.5 }, /skip must be an integer 0 or more/],
  ])("rejects %o before any request instead of clamping it", async (options, message) => {
    const { client, fetch } = pagedClient(300);
    await expect(client.listTaskResults(options)).rejects.toThrow(QDashValidationError);
    await expect(client.listTaskResults(options)).rejects.toThrow(message);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("collects 200 rows in two pages of 100, keeping every filter", async () => {
    const { client, requests } = pagedClient(250);
    const result = await client.collectTaskResults({ chipId: "C", qid: "6", status: "failed", maxItems: 200 });
    expect(result.items).toHaveLength(200);
    expect(result.items[0]?.task_id).toBe("t-0");
    expect(result.items[199]?.task_id).toBe("t-199");
    expect(result).toMatchObject({ total: 250, skip: 0, pages: 2, truncated: true });
    expect(requests.map((url) => [url.searchParams.get("skip"), url.searchParams.get("limit")])).toEqual([
      ["0", "100"],
      ["100", "100"],
    ]);
    for (const url of requests) {
      expect(url.searchParams.get("chip_id")).toBe("C");
      expect(url.searchParams.get("qid")).toBe("6");
      expect(url.searchParams.get("status")).toBe("failed");
    }
  });

  it("stops at the last matching row and reports a complete read", async () => {
    const { client, requests } = pagedClient(130);
    const result = await client.collectTaskResults({ maxItems: 500, skip: 20 });
    expect(result).toMatchObject({ total: 130, skip: 20, pages: 2, truncated: false });
    expect(result.items).toHaveLength(110);
    expect(requests.map((url) => url.searchParams.get("skip"))).toEqual(["20", "120"]);
  });

  it("asks only for the rows still needed and stops after an empty or short page", async () => {
    const empty = pagedClient(0);
    await expect(empty.client.collectTaskResults({ maxItems: 50 })).resolves.toMatchObject({ items: [], total: 0, pages: 1, truncated: false });
    const short = pagedClient(300, { shortAt: 100 });
    const result = await short.client.collectTaskResults({ maxItems: 150 });
    expect(short.requests.map((url) => url.searchParams.get("limit"))).toEqual(["100", "50"]);
    expect(result.items).toHaveLength(101);
    expect(result.truncated).toBe(true);
  });

  it("bounds duplicate pages even when totals keep growing", async () => {
    const { client, fetch } = pagedClient(10);
    let calls = 0;
    fetch.mockImplementation(async () => {
      calls += 1;
      if (calls > 2) throw new Error("page budget exceeded");
      return jsonResponse({ items: [row(0)], total: 100 + calls, skip: calls - 1, limit: 1, status_counts: {} });
    });
    const result = await client.collectTaskResults({ maxItems: 2, pageSize: 1 });
    expect(calls).toBe(2);
    expect(result).toMatchObject({ pages: 2, truncated: true });
    expect(result.items).toHaveLength(1);
  });

  it("does not claim completeness when duplicate pages reach the reported end", async () => {
    const { client, fetch } = pagedClient(2);
    fetch.mockImplementation(async () => jsonResponse({ items: [row(0)], total: 2, skip: fetch.mock.calls.length - 1, limit: 1, status_counts: {} }));
    const result = await client.collectTaskResults({ maxItems: 2, pageSize: 1 });
    expect(result).toMatchObject({ pages: 2, truncated: true });
    expect(result.items).toHaveLength(1);
  });

  it("cancels between pages without requesting another page", async () => {
    const { client, fetch } = pagedClient(2);
    const controller = new AbortController();
    const list = client.listTaskResults.bind(client);
    vi.spyOn(client, "listTaskResults").mockImplementation(async (options) => {
      const page = await list(options);
      controller.abort(new Error("cancelled between pages"));
      return page;
    });
    await expect(client.collectTaskResults({ maxItems: 2, pageSize: 1, signal: controller.signal })).rejects.toThrow("cancelled between pages");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("rejects the whole read when a page fails, a page is malformed, or the caller cancels", async () => {
    const failing = pagedClient(300, { failAt: 100 });
    await expect(failing.client.collectTaskResults({ maxItems: 200 })).rejects.toThrow();

    const fetch = vi.fn(async () => jsonResponse({ results: [], count: 0 }));
    const malformed = new QDashClient(new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "t" }), { fetch });
    await expect(malformed.listTaskResults()).rejects.toThrow(/items is not an array; total is not an integer/);

    const controller = new AbortController();
    controller.abort(new Error("stopped by caller"));
    const cancelled = pagedClient(300);
    await expect(cancelled.client.collectTaskResults({ maxItems: 200, signal: controller.signal })).rejects.toThrow("stopped by caller");
    expect(cancelled.fetch).not.toHaveBeenCalled();
  });

  it.each([
    [{ maxItems: 0 }, /maxItems must be an integer from 1 to 10000/],
    [{ maxItems: 20_000 }, /maxItems must be an integer from 1 to 10000/],
    [{ maxItems: 10, pageSize: 200 }, /pageSize must be an integer from 1 to 100/],
  ])("rejects collect options %o before any request", async (options, message) => {
    const { client, fetch } = pagedClient(10);
    await expect(client.collectTaskResults(options)).rejects.toThrow(message);
    expect(fetch).not.toHaveBeenCalled();
  });
});
