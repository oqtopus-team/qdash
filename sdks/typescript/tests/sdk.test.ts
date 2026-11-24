import { readdirSync, readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  ApiError,
  QDash,
  QDashConfig,
  QDashConfigError,
  QDashNotFoundError,
  QDashTimeoutError,
  QDashValidationError,
  customOneQubit,
  muxTargets,
  qubitTargets,
  sweep,
  type CalibrationPipelineSpecStepsItem,
  type TaskCall,
} from "../src/index.js";

type Reply = { status?: number; body?: unknown };

/** A fetch that answers from a queue per "METHOD /path" and records every request. */
function server(routes: Record<string, Reply[]>) {
  const requests: { method: string; path: string; body: unknown; project: string | null }[] = [];
  const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(input, init);
    const url = new URL(request.url);
    const key = `${request.method} ${url.pathname.replace(/^\/api/, "")}`;
    const text = await request.text();
    requests.push({
      method: request.method,
      path: key.split(" ")[1]!,
      body: text ? JSON.parse(text) : undefined,
      project: request.headers.get("X-Project-Id"),
    });
    const reply = routes[key]?.shift();
    if (!reply) throw new Error(`unexpected request ${key}`);
    return new Response(JSON.stringify(reply.body ?? {}), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { fetch, requests };
}

function session(fetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>, projectId?: string) {
  return new QDash(
    { baseUrl: "https://qdash.example/api", apiToken: "token", ...(projectId ? { projectId } : {}) },
    { fetch, sleep: async () => {} },
  );
}

const detail = (status: string, pipelineStatus?: string) => ({
  name: "coherence",
  status,
  task: [],
  note: {},
  ...(pipelineStatus
    ? {
        pipeline: {
          name: "coherence",
          flow_run_id: "run-1",
          root_execution_id: "exec-1",
          status: pipelineStatus,
          steps: [],
        },
      }
    : {}),
});

const dispatched = {
  execution_id: "exec-1",
  flow_run_id: "run-1",
  flow_run_url: "http://prefect/run-1",
  qdash_ui_url: "http://qdash/execution/exec-1",
  message: "started",
};

// The T1 / T2 echo coherence check of the coherence_check template, as the docs show it.
const timeRange = sweep.logspace(Math.log10(300), Math.log10(500_000), 51);
const targets = qubitTargets(["0", "1"]);
const tasks: TaskCall[] = [
  { name: "Configure" },
  { name: "CheckT1", run: { time_range: timeRange } },
  { name: "CheckT2Echo", run: { time_range: timeRange } },
];
const steps: CalibrationPipelineSpecStepsItem[] = [customOneQubit({ step_name: "coherence", tasks })];
const runParameters = { readout_duration: 1024, interval: 262_144 };

const expectedSpec = {
  spec_version: 2,
  targets: { qids: ["0", "1"] },
  steps: [
    {
      type: "CustomOneQubit",
      step_name: "coherence",
      tasks: [
        { name: "Configure" },
        { name: "CheckT1", run: { time_range: { value: [Math.log10(300), Math.log10(500_000), 51], value_type: "np.logspace" } } },
        { name: "CheckT2Echo", run: { time_range: { value: [Math.log10(300), Math.log10(500_000), 51], value_type: "np.logspace" } } },
      ],
    },
  ],
  default_run_parameters: runParameters,
};

describe("QDash SDK session", () => {
  it("sends nothing while a session, chip or workflow scope is defined", () => {
    const { fetch, requests } = server({});
    const qdash = session(fetch, "p1");
    const chip = qdash.chip("64Qv3");
    expect(chip.chipId).toBe("64Qv3");
    expect(qdash.workflows).toBeDefined();
    expect(requests).toEqual([]);
    expect(() => qdash.chip("")).toThrow(TypeError);
  });

  it("scopes a project without changing the given config or the original session", async () => {
    const { fetch, requests } = server({ "GET /flows": [{ body: { flows: [] } }, { body: { flows: [] } }, { body: { flows: [] } }] });
    const config = new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token", projectId: "default-project" });
    const base = new QDash(config, { fetch });
    const qdash = new QDash(config, { projectId: "p2", fetch });
    const other = base.withProject("p3");

    expect(qdash.projectId).toBe("p2");
    expect(qdash.config.projectId).toBe("p2");
    expect(config.projectId).toBe("default-project");
    expect(base.projectId).toBe("default-project");
    await qdash.workflows.list();
    await base.workflows.list();
    await other.api.flow.listFlows();
    expect(requests.map((request) => request.project)).toEqual(["p2", "default-project", "p3"]);
    expect(() => new QDash(config, { projectId: "" })).toThrow(QDashConfigError);
    expect(() => base.withProject("")).toThrow(QDashConfigError);
  });

  it("keeps a frozen snapshot, so the reported project is the one sent", async () => {
    const { fetch, requests } = server({ "GET /flows": [{ body: { flows: [] } }] });
    const options = { baseUrl: "https://qdash.example/api", apiToken: "token", projectId: "p1" };
    const qdash = new QDash(options, { fetch });
    options.projectId = "changed";
    expect(Object.isFrozen(qdash.config)).toBe(true);
    expect(() => {
      (qdash.config as { projectId?: string }).projectId = "x";
    }).toThrow(TypeError);
    await qdash.workflows.list();
    expect(qdash.projectId).toBe("p1");
    expect(requests[0]?.project).toBe("p1");
  });

  it("builds an owning session from the environment with a project", async () => {
    const { fetch, requests } = server({ "GET /flows": [{ body: { flows: [] } }] });
    const qdash = QDash.fromEnv({
      env: { QDASH_BASE_URL: "https://qdash.example/api", QDASH_API_TOKEN: "t", QDASH_PROJECT_ID: "env-p" },
      projectId: "p3",
      fetch,
    });
    expect(qdash.projectId).toBe("p3");
    await qdash.workflows.list();
    expect(requests[0]?.project).toBe("p3");
  });
});

describe("Chip calibration", () => {
  it("validates with the spec version 2 wire payload and dispatches nothing", async () => {
    const { fetch, requests } = server({
      "POST /calibration-pipelines/validate": [{ body: { valid: true, backend_name: "qubex", problems: [] } }],
    });
    const chip = session(fetch, "p1").chip("64Qv3");

    const check = await chip.validateCalibration(targets, steps, { defaultRunParameters: runParameters });

    expect(check.valid).toBe(true);
    expect(requests).toEqual([
      { method: "POST", path: "/calibration-pipelines/validate", body: { chip_id: "64Qv3", spec: expectedSpec }, project: "p1" },
    ]);
  });

  it("sends only the options given, including the backend outside the spec", async () => {
    const { fetch, requests } = server({
      "POST /calibration-pipelines/validate": [{ body: { valid: true, backend_name: "fake" } }],
    });
    await session(fetch).chip("16Q").validateCalibration(muxTargets([0, 1], { excludeQids: ["5"] }), steps, {
      name: "coherence-t1-t2echo",
      tags: ["sdk"],
      backendName: "fake",
    });
    expect(requests[0]?.body).toEqual({
      chip_id: "16Q",
      backend_name: "fake",
      spec: {
        spec_version: 2,
        name: "coherence-t1-t2echo",
        targets: { mux_ids: [0, 1], exclude_qids: ["5"] },
        steps: expectedSpec.steps,
        tags: ["sdk"],
      },
    });
  });

  it("calibrate dispatches once, returns the execution ID, and does not wait", async () => {
    const { fetch, requests } = server({ "POST /calibration-pipelines/execute": [{ body: dispatched }] });
    const run = await session(fetch, "p1").chip("64Qv3").calibrate(targets, steps, {
      defaultRunParameters: runParameters,
    });

    expect(run.executionId).toBe("exec-1");
    expect(run.response).toEqual(dispatched);
    expect(requests).toEqual([
      { method: "POST", path: "/calibration-pipelines/execute", body: { chip_id: "64Qv3", spec: expectedSpec }, project: "p1" },
    ]);
  });

  it("dispatches without a project, leaving the server's default project to apply", async () => {
    const { fetch, requests } = server({
      "POST /calibration-pipelines/execute": [{ body: dispatched }, { body: dispatched }],
    });
    const qdash = session(fetch);
    expect(qdash.projectId).toBeUndefined();
    const run = await qdash.chip("64Qv3").calibrate(targets, steps, { defaultRunParameters: runParameters });
    await qdash.pipelines.execute(expectedSpec, { chipId: "64Qv3" });

    expect(run.executionId).toBe("exec-1");
    expect(requests).toEqual([
      { method: "POST", path: "/calibration-pipelines/execute", body: { chip_id: "64Qv3", spec: expectedSpec }, project: null },
      { method: "POST", path: "/calibration-pipelines/execute", body: { chip_id: "64Qv3", spec: expectedSpec }, project: null },
    ]);
  });

  it("records a run in a calibration session under its retry key", async () => {
    const { fetch, requests } = server({
      "GET /calibration-sessions/cs-1": [{ body: { calibration_session_id: "cs-1", chip_id: "64Qv3", status: "open" } }],
      "POST /calibration-pipelines/execute": [{ body: { ...dispatched, calibration_session_id: "cs-1", pipeline_run_id: "cpr-1", replayed: false } }],
    });
    const qdash = session(fetch, "p1");
    const run = await qdash.pipelines.execute(expectedSpec, { chipId: "64Qv3" }, { calibrationSessionId: "cs-1", idempotencyKey: "key-1" });

    expect(run.response.pipeline_run_id).toBe("cpr-1");
    expect(requests).toEqual([
      { method: "GET", path: "/calibration-sessions/cs-1", body: undefined, project: "p1" },
      {
        method: "POST",
        path: "/calibration-pipelines/execute",
        body: { chip_id: "64Qv3", spec: expectedSpec, calibration_session_id: "cs-1", idempotency_key: "key-1" },
        project: "p1",
      },
    ]);
    await expect(
      qdash.pipelines.execute(expectedSpec, { chipId: "64Qv3" }, { calibrationSessionId: "cs-1", idempotencyKey: "" }),
    ).rejects.toThrow(TypeError);
  });

  it("names the decision a recorded run carries out", async () => {
    const { fetch, requests } = server({
      "GET /calibration-sessions/cs-1": [{ body: { calibration_session_id: "cs-1", chip_id: "64Qv3" } }],
      "POST /calibration-pipelines/execute": [{ body: { ...dispatched, calibration_session_id: "cs-1", pipeline_run_id: "cpr-1", decision_id: "d-1", replayed: false } }],
    });
    const qdash = session(fetch, "p1");
    await qdash.pipelines.execute(expectedSpec, { chipId: "64Qv3" }, { calibrationSessionId: "cs-1", idempotencyKey: "key-1", decisionId: "d-1" });
    expect(requests[1]?.body).toEqual({
      chip_id: "64Qv3",
      spec: expectedSpec,
      calibration_session_id: "cs-1",
      idempotency_key: "key-1",
      decision_id: "d-1",
    });
  });

  it("sends a reported origin only when the caller gives one", async () => {
    const { fetch, requests } = server({
      "POST /calibration-pipelines/execute": [{ body: dispatched }],
    });
    const qdash = session(fetch, "p1");
    const origin = { source: "agent_tool" as const, tool: "qdash_run_pipeline", client: "pi-qdash" };
    await qdash.pipelines.execute(expectedSpec, { chipId: "64Qv3" }, undefined, { reportedOrigin: origin });

    expect(requests[0]?.body).toEqual({ chip_id: "64Qv3", spec: expectedSpec, reported_origin: origin });
  });

  it("propagates a 422 with its problems", async () => {
    const problems = [{ path: "steps[0].tasks[1]", message: "CheckT1 needs Rabi parameters" }];
    const { fetch } = server({
      "POST /calibration-pipelines/execute": [{ status: 422, body: { detail: { message: "not valid", problems } } }],
    });
    const error = await session(fetch, "p1")
      .chip("64Qv3")
      .calibrate(targets, steps)
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(QDashValidationError);
    expect((error as QDashValidationError).payload).toEqual({ detail: { message: "not valid", problems } });
  });

  it("waits for the whole run: pending 404, then a completed first step of a running pipeline", async () => {
    const { fetch, requests } = server({
      "POST /calibration-pipelines/execute": [{ body: dispatched }],
      "GET /executions/exec-1": [
        { status: 404, body: { detail: "not found" } },
        { body: detail("completed", "running") },
        { body: detail("completed", "failed") },
      ],
    });
    const run = await session(fetch, "p1").chip("64Qv3").calibrate(targets, steps);
    const result = await run.wait({ pollIntervalSeconds: 0 });

    expect(result.executionId).toBe("exec-1");
    expect(result.status).toBe("failed");
    expect(result.detail.status).toBe("completed");
    expect(result.detail.pipeline?.status).toBe("failed");
    expect(requests.map((request) => request.method)).toEqual(["POST", "GET", "GET", "GET"]);
  });

  it("falls back to the execution status without pipeline metadata", async () => {
    const { fetch } = server({
      "POST /calibration-pipelines/execute": [{ body: dispatched }],
      "GET /executions/exec-1": [{ body: detail("running") }, { body: detail("cancelled") }],
    });
    const run = await session(fetch, "p1").chip("64Qv3").calibrate(targets, steps);
    await expect(run.get()).resolves.toMatchObject({ status: "running" });
    await expect(run.wait({ pollIntervalSeconds: 0 })).resolves.toMatchObject({ status: "cancelled" });
  });

  it("times out without cancelling, and get() reports a missing execution", async () => {
    const { fetch, requests } = server({
      "POST /calibration-pipelines/execute": [{ body: dispatched }],
      "GET /executions/exec-1": [{ status: 404 }, { status: 404 }],
    });
    const run = await session(fetch, "p1").chip("64Qv3").calibrate(targets, steps);
    await expect(run.wait({ timeoutSeconds: 0, pollIntervalSeconds: 0 })).rejects.toBeInstanceOf(QDashTimeoutError);
    await expect(run.get()).rejects.toBeInstanceOf(QDashNotFoundError);
    expect(requests.every((request) => request.method !== "DELETE" && !request.path.includes("cancel"))).toBe(true);
  });
});

describe("Pipelines", () => {
  it("sends a whole spec, typed or not, unchanged", async () => {
    const legacy = { steps: [{ type: "OneQubitCheck" }], targets: { qids: ["0"] } };
    const { fetch, requests } = server({
      "GET /calibration-pipelines/catalog": [{ body: { backend_name: "fake" } }],
      "POST /calibration-pipelines/validate": [{ body: { valid: false, backend_name: "fake" } }],
      "POST /calibration-pipelines/execute": [{ body: dispatched }],
      "GET /executions/exec-1": [{ body: detail("completed", "completed") }],
    });
    const qdash = session(fetch, "p1");
    await qdash.pipelines.catalog({ backendName: "fake" });
    await qdash.pipelines.validate(legacy, { chipId: "64Qv3" });
    const run = await qdash.pipelines.execute(expectedSpec, { chipId: "64Qv3" });
    const raw = await run.wait({ pollIntervalSeconds: 0 });

    expect(raw.pipeline?.status).toBe("completed");
    expect(requests.map((request) => [request.method, request.path, request.body])).toEqual([
      ["GET", "/calibration-pipelines/catalog", undefined],
      ["POST", "/calibration-pipelines/validate", { chip_id: "64Qv3", spec: legacy }],
      ["POST", "/calibration-pipelines/execute", { chip_id: "64Qv3", spec: expectedSpec }],
      ["GET", "/executions/exec-1", undefined],
    ]);
  });

  it("writes only keys the published schema declares", () => {
    const schemas = JSON.parse(readFileSync(new URL("../../../docs/oas/openapi.json", import.meta.url), "utf8"))
      .components.schemas as Record<string, { properties: Record<string, unknown>; required?: string[] }>;
    const check = (value: Record<string, unknown>, component: string) => {
      const schema = schemas[component]!;
      expect(Object.keys(value).filter((key) => !(key in schema.properties))).toEqual([]);
      for (const key of schema.required ?? []) expect(value).toHaveProperty(key);
    };
    check(expectedSpec, "CalibrationPipelineSpec");
    check(qubitTargets(["0"]) as Record<string, unknown>, "PipelineTargets");
    check(muxTargets([0], { excludeQids: ["1"] }) as Record<string, unknown>, "PipelineTargets");
    const step = steps[0] as unknown as Record<string, unknown>;
    check(step, "CustomOneQubitStep");
    for (const call of step.tasks as Record<string, unknown>[]) check(call, "TaskCall");
    // The sweep value types the TaskCall.run schema documents.
    const runDoc = String((schemas.TaskCall!.properties.run as { description?: string }).description);
    for (const valueType of ["np.arange", "np.linspace", "np.logspace", "range", "list"]) {
      expect(runDoc).toContain(`"${valueType}"`);
    }
  });
});

describe("sweep and definitions", () => {
  it("declares sweeps without expanding them", () => {
    expect(sweep.values(1, 2.5)).toEqual({ value: [1, 2.5], value_type: "list" });
    expect(sweep.linspace(0, 1, 11)).toEqual({ value: [0, 1, 11], value_type: "np.linspace" });
    expect(sweep.arange(0, 10, 2)).toEqual({ value: [0, 10, 2], value_type: "np.arange" });
    expect(sweep.range(0, 5, 1)).toEqual({ value: [0, 5, 1], value_type: "range" });
    expect(() => sweep.values()).toThrow(RangeError);
    expect(() => sweep.linspace(0, 1, 0)).toThrow(RangeError);
    expect(() => sweep.arange(0, 1, 0)).toThrow(RangeError);
    expect(() => sweep.range(0, 1.5, 1)).toThrow(TypeError);
    expect(() => sweep.logspace(Number.NaN, 1, 3)).toThrow(TypeError);
  });

  it("rejects a string where a list of IDs belongs", () => {
    expect(() => qubitTargets("01" as unknown as string[])).toThrow(TypeError);
    expect(muxTargets([3])).toEqual({ mux_ids: [3] });
  });
});

describe("Workflows", () => {
  const flow = {
    name: "coherence_check",
    created_by: "alice",
    description: "T1 and T2 echo",
    code: "...",
    flow_function_name: "coherence_check",
    chip_id: "64Qv3",
    default_parameters: { qids: ["0"] },
    file_path: "flows/coherence_check.py",
    created_at: "",
    updated_at: "",
    tags: [],
  };

  it("lists and reads registered workflows without dispatching", async () => {
    const { fetch, requests } = server({
      "GET /flows": [{ body: { flows: [{ ...flow, code: undefined }] } }],
      "GET /flows/coherence_check": [{ body: flow }, { status: 404, body: { detail: "missing" } }],
    });
    const qdash = session(fetch, "p1");
    const [summary] = await qdash.workflows.list();
    const workflow = await qdash.workflows.get("coherence_check");

    expect(summary?.name).toBe("coherence_check");
    expect(workflow.chipId).toBe("64Qv3");
    expect(workflow.defaultParameters).toEqual({ qids: ["0"] });
    expect(workflow.detail).toEqual(flow);
    await expect(qdash.workflows.get("coherence_check")).rejects.toBeInstanceOf(QDashNotFoundError);
    expect(requests.every((request) => request.method === "GET")).toBe(true);
  });

  it("checks names before any request and runs without a project on the server's default", async () => {
    const { fetch, requests } = server({ "POST /flows/coherence_check/execute": [{ body: dispatched }] });
    const qdash = session(fetch);
    await expect(qdash.workflows.get("../chips")).rejects.toThrow(TypeError);
    await expect(qdash.workflows.run("bad name")).rejects.toThrow(TypeError);
    expect(requests).toEqual([]);

    const run = await qdash.workflows.run("coherence_check");
    expect(run.executionId).toBe("exec-1");
    expect(requests).toEqual([
      { method: "POST", path: "/flows/coherence_check/execute", body: { parameters: {} }, project: null },
    ]);
  });

  it("runs with the saved defaults or overrides and follows the whole run", async () => {
    const { fetch, requests } = server({
      "GET /flows/coherence_check": [{ body: flow }],
      "POST /flows/coherence_check/execute": [{ body: dispatched }, { body: dispatched }],
      "GET /executions/exec-1": [{ status: 404 }, { body: detail("completed", "completed") }],
    });
    const qdash = session(fetch, "p1");
    const workflow = await qdash.workflows.get("coherence_check");
    const run = await workflow.run();
    await qdash.workflows.run("coherence_check", { parameters: { qids: ["0", "1"] } });
    const result = await run.wait({ pollIntervalSeconds: 0 });

    expect(run.name).toBe("coherence_check");
    expect(run.executionId).toBe("exec-1");
    expect(result.status).toBe("completed");
    expect(requests.filter((request) => request.method === "POST").map((request) => request.body)).toEqual([
      { parameters: {} },
      { parameters: { qids: ["0", "1"] } },
    ]);
  });
});

describe("package boundary", () => {
  it("raises its own errors, which are the generated client's ApiError", async () => {
    const { fetch } = server({ "GET /executions/exec-1": [{ status: 404 }, { status: 404 }] });
    const qdash = session(fetch);
    const caught = await qdash.run("exec-1").get().catch((error: unknown) => error);
    expect(caught).toBeInstanceOf(QDashNotFoundError);
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught).toMatchObject({ statusCode: 404 });
    // The generated client raises ApiError itself; the SDK's errors are its subclasses.
    const raw = await qdash.api.execution.getExecution({ execution_id: "exec-1" }).catch((error: unknown) => error);
    expect(raw).toBeInstanceOf(ApiError);
    expect(raw).not.toBeInstanceOf(QDashNotFoundError);
  });

  it("imports nothing from the legacy client", () => {
    const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
    expect(manifest.dependencies["@oqtopus-team/qdash-client"]).toBeUndefined();
    const sources = readdirSync(new URL("../src", import.meta.url), { recursive: true, withFileTypes: false }) as string[];
    for (const name of sources.filter((file) => file.endsWith(".ts"))) {
      const text = readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
      expect(text, name).not.toMatch(/(from\s+|import\(\s*)["']@oqtopus-team\/qdash-client/);
    }
  });
});
