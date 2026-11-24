import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  COOLDOWN_NOT_ASSOCIATED,
  QDash,
  QDashApiError,
  QDashValidationError,
  type TaskResultResponse,
} from "../src/index.js";

type Schema = { properties: Record<string, unknown>; required?: string[] };
const openapi = JSON.parse(readFileSync(new URL("../../../docs/oas/openapi.json", import.meta.url), "utf8")) as {
  components: { schemas: Record<string, Schema> };
  paths: Record<string, Record<string, unknown>>;
};

/** Fixtures carry exactly the published component's keys, and all of its required ones. */
function published<T extends object>(value: T, component: string): T {
  const schema = openapi.components.schemas[component]!;
  expect(Object.keys(value).filter((key) => !(key in schema.properties))).toEqual([]);
  for (const key of schema.required ?? []) expect(value).toHaveProperty(key);
  return value;
}

const result = (overrides: Partial<TaskResultResponse> = {}): TaskResultResponse =>
  published(
    {
      task_id: "t-1",
      task_name: "CheckT1",
      qid: "6",
      chip_id: "C",
      status: "failed",
      execution_id: "e-1",
      flow_name: "one_qubit",
      user_id: "u-1",
      username: "alice",
      figure_path: ["/data/t1.png"],
      json_figure_path: [],
      raw_data_path: [],
      input_parameters: {},
      output_parameters: { t1: { value: 31.5, unit: "us" } } as unknown as TaskResultResponse["output_parameters"],
      output_parameter_names: ["t1", "t1_fit_r2"],
      run_parameters: {},
      message: "fit did not converge",
      start_at: "2026-11-22T10:00:00Z",
      end_at: "2026-11-22T10:01:00Z",
      elapsed_time: "0:01:00",
      source_task_id: null,
      re_executions: [],
      ...overrides,
    },
    "TaskResultResponse",
  );

const execution = (tasks: unknown[], chipId = "C") =>
  published(
    { name: "run", status: "failed", flow_name: "one_qubit", chip_id: chipId, task: tasks, note: {}, tags: [] },
    "ExecutionResponseDetail",
  );

const qubit = (data: Record<string, unknown>) =>
  published({ qid: "6", chip_id: "C", status: "active", data }, "QubitResponse");

const cooldown = (overrides: Record<string, unknown> = {}) =>
  published(
    {
      cooldown_id: "2026-001",
      cryo_id: "cryo-a",
      description: "",
      started_at: "2026-11-01T00:00:00Z",
      ended_at: null,
      chip_ids: ["C"],
      ...overrides,
    },
    "CooldownResponse",
  );

type Body = unknown | { status: number };
const httpError = (status: number) => ({ __status: status });

/** A fetch answering the evidence reads from `routes` by path; anything else is a 404. */
function qdashWith(routes: Record<string, Body>) {
  const requests: string[] = [];
  const projects: Array<string | null> = [];
  const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(input, init);
    const url = new URL(request.url);
    requests.push(url.pathname);
    projects.push(request.headers.get("X-Project-Id"));
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    const body = routes[url.pathname];
    if (body === undefined) return json({ detail: `no ${url.pathname}` }, 404);
    if (body && typeof body === "object" && "__status" in body) return json({ detail: "unavailable" }, (body as { __status: number }).__status);
    return json(body);
  };
  const qdash = new QDash({ baseUrl: "https://qdash.example/api", apiToken: "token", projectId: "p-1", readAttempts: 1 }, { fetch });
  return { qdash, requests, projects };
}

describe("qdash.taskResults.evidence", () => {
  it("joins the result, its execution entry, the target's stored outputs, and a named cooldown", async () => {
    const own = { task_id: "t-1", name: "CheckT1", qid: "6", status: "failed", task_type: "qubit" };
    const { qdash, requests, projects } = qdashWith({
      "/api/tasks/t-1/result": result(),
      "/api/executions/e-1": execution([own, { task_id: "t-0", status: "completed" }]),
      "/api/chips/C/qubits/6": qubit({ t1: { value: 24, unit: "us", task_id: "t-old" }, other: 1 }),
      "/api/cooldowns/2026-001": cooldown(),
    });
    const evidence = await qdash.taskResults.evidence("t-1", { cooldownId: "2026-001" });

    expect(requests).toEqual(["/api/tasks/t-1/result", "/api/executions/e-1", "/api/chips/C/qubits/6", "/api/cooldowns/2026-001"]);
    // Every read stays in the client's project.
    expect(projects).toEqual(["p-1", "p-1", "p-1", "p-1"]);
    expect(evidence.taskId).toBe("t-1");
    // QDash's status is kept as it is.
    expect(evidence.result.status).toBe("failed");
    expect(evidence.execution).toMatchObject({ status: "ok", value: { task: own, chipMatches: true } });
    expect(evidence.target).toMatchObject({
      status: "ok",
      value: {
        kind: "qubit",
        kindSource: "execution_task_type",
        id: "6",
        outputs: { t1: { stored: { value: 24, unit: "us", task_id: "t-old" }, fromThisResult: false } },
        outputsNotStored: ["t1_fit_r2"],
      },
    });
    expect(evidence.cooldown).toMatchObject({
      status: "ok",
      value: { association: "named", checks: { chipListed: true, resultStartWithin: true } },
    });
  });

  it("reports the cooldown as not associated, and reads none, when no cooldown is named", async () => {
    const { qdash, requests } = qdashWith({
      "/api/tasks/t-1/result": result(),
      "/api/executions/e-1": execution([]),
      "/api/chips/C/qubits/6": qubit({}),
    });
    const evidence = await qdash.taskResults.evidence("t-1");
    expect(evidence.cooldown).toEqual({ status: "not_associated", reason: COOLDOWN_NOT_ASSOCIATED });
    expect(requests.some((path) => path.startsWith("/api/cooldowns"))).toBe(false);
    // The execution does not list the result: said, not guessed.
    expect(evidence.execution).toMatchObject({ status: "ok", value: { task: null } });
  });

  it("checks a named cooldown against the result without claiming the association", async () => {
    const { qdash } = qdashWith({
      "/api/tasks/t-1/result": result(),
      "/api/executions/e-1": execution([]),
      "/api/chips/C/qubits/6": qubit({}),
      "/api/cooldowns/2025-009": cooldown({ cooldown_id: "2025-009", chip_ids: ["D"], started_at: "2025-01-01T00:00:00Z", ended_at: "2025-02-01T00:00:00Z" }),
    });
    const { cooldown: context } = await qdash.taskResults.evidence("t-1", { cooldownId: "2025-009" });
    expect(context).toMatchObject({ status: "ok", value: { association: "named", checks: { chipListed: false, resultStartWithin: false } } });
  });

  it("reports failed secondary reads with their status and substitutes nothing", async () => {
    const { qdash } = qdashWith({
      "/api/tasks/t-1/result": result({ qid: "6-7" }),
      "/api/executions/e-1": httpError(503),
      "/api/chips/C/couplings/6-7": httpError(500),
      "/api/cooldowns/2026-001": httpError(404),
    });
    const evidence = await qdash.taskResults.evidence("t-1", { cooldownId: "2026-001" });
    expect(evidence.execution).toMatchObject({ status: "failed", statusCode: 503 });
    // Without the execution, the kind comes from the qid format.
    expect(evidence.target).toMatchObject({ status: "failed", statusCode: 500 });
    expect(evidence.cooldown).toMatchObject({ status: "failed", statusCode: 404 });
    for (const part of [evidence.execution, evidence.target, evidence.cooldown]) expect(part).not.toHaveProperty("value");
  });

  it("marks parts with nothing to read from as not applicable", async () => {
    const { qdash, requests } = qdashWith({
      "/api/tasks/t-1/result": result({ qid: "", execution_id: "" }),
    });
    const evidence = await qdash.taskResults.evidence("t-1");
    expect(evidence.execution.status).toBe("not_applicable");
    expect(evidence.target.status).toBe("not_applicable");
    expect(requests).toEqual(["/api/tasks/t-1/result"]);
  });

  it("reads a coupling target by the qid format when the execution says no task type", async () => {
    const { qdash, requests } = qdashWith({
      "/api/tasks/t-1/result": result({ qid: "6-7" }),
      "/api/executions/e-1": execution([{ task_id: "t-1", status: "failed" }]),
      "/api/chips/C/couplings/6-7": published({ qid: "6-7", chip_id: "C", status: "active", data: {} }, "CouplingResponse"),
    });
    const { target } = await qdash.taskResults.evidence("t-1");
    expect(target).toMatchObject({ status: "ok", value: { kind: "coupling", kindSource: "qid_format" } });
    expect(requests).toContain("/api/chips/C/couplings/6-7");
  });

  it("rejects a failed or mismatched result read, and invalid arguments before any request", async () => {
    await expect(qdashWith({ "/api/tasks/t-1/result": httpError(500) }).qdash.taskResults.evidence("t-1")).rejects.toBeInstanceOf(QDashApiError);
    await expect(qdashWith({ "/api/tasks/t-1/result": result({ task_id: "t-2" }) }).qdash.taskResults.evidence("t-1")).rejects.toThrow(/task_id "t-2"/);
    const { qdash, requests } = qdashWith({});
    await expect(qdash.taskResults.evidence(" ")).rejects.toBeInstanceOf(QDashValidationError);
    await expect(qdash.taskResults.evidence("t-1", { cooldownId: "" })).rejects.toThrow(/cooldownId/);
    await expect(qdash.taskResults.evidence("t-1", { since: "x" } as never)).rejects.toThrow(/since is not an option/);
    expect(requests).toEqual([]);
  });

  it("encodes a cooldown ID into one path segment", async () => {
    const { qdash, requests } = qdashWith({
      "/api/tasks/t-1/result": result({ qid: "", execution_id: "" }),
    });
    const { cooldown: context } = await qdash.taskResults.evidence("t-1", { cooldownId: "../chips" });
    expect(requests[1]).toBe("/api/cooldowns/..%2Fchips");
    expect(context.status).toBe("failed");
  });
});
