import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  QDash,
  QDashApiError,
  QDashValidationError,
  type TaskResultListItem,
  type TaskResultResponse,
} from "../src/index.js";

type Schema = { properties: Record<string, unknown>; required?: string[] };
const openapi = JSON.parse(readFileSync(new URL("../../../docs/oas/openapi.json", import.meta.url), "utf8")) as {
  components: { schemas: Record<string, Schema> };
  paths: Record<string, Record<string, { parameters?: { name: string; in: string }[] }>>;
};

/** Fixtures carry exactly the published component's keys, and all of its required ones. */
function published<T extends object>(value: T, component: string): T {
  const schema = openapi.components.schemas[component]!;
  expect(Object.keys(value).filter((key) => !(key in schema.properties))).toEqual([]);
  for (const key of schema.required ?? []) expect(value).toHaveProperty(key);
  return value;
}

// A GET /task-results row (TaskResultListItem): it has no output_parameters.
const row = (taskId: string, taskName: string, startAt: string, qid = "6"): TaskResultListItem =>
  published(
    {
      task_id: taskId,
      task_name: taskName,
      qid,
      chip_id: "C",
      status: "completed",
      execution_id: `exec-${taskId}`,
      user_id: "u-1",
      username: "alice",
      message: "",
      has_stack_trace: false,
      source_task_id: null,
      invocation: null,
      start_at: startAt,
      end_at: startAt,
      elapsed_time: "0:00:12",
    },
    "TaskResultListItem",
  );

// An output parameter as TaskResultOutputParameterModel serializes it.
const output = (value: unknown, error = 0.1, calibratedAt = "2026-11-20T00:00:00Z") => ({
  parameter_name: "",
  qid_role: "",
  source: null,
  required: false,
  value,
  value_type: "float",
  error,
  unit: "us",
  description: "",
  calibrated_at: calibratedAt,
  execution_id: "",
  task_id: "",
  previous_database_value: null,
  database_updated: false,
  database_updates: [],
});

// A GET /tasks/{task_id}/result body (TaskResultResponse).
const detail = (listRow: TaskResultListItem, outputParameters: Record<string, unknown>): TaskResultResponse =>
  published(
    {
      task_id: listRow.task_id,
      task_name: listRow.task_name,
      qid: listRow.qid,
      chip_id: listRow.chip_id,
      status: listRow.status,
      execution_id: listRow.execution_id,
      flow_name: "one_qubit",
      user_id: "u-1",
      username: "alice",
      figure_path: [],
      json_figure_path: [],
      raw_data_path: [],
      input_parameters: {},
      output_parameters: outputParameters as TaskResultResponse["output_parameters"],
      output_parameter_names: Object.keys(outputParameters),
      run_parameters: {},
      start_at: listRow.start_at,
      end_at: listRow.end_at,
      elapsed_time: listRow.elapsed_time,
      source_task_id: null,
      re_executions: [],
    },
    "TaskResultResponse",
  );

const t1New = row("t1-new", "CheckT1", "2026-11-22T10:00:00Z");
const rabiNew = row("rabi-new", "CheckRabi", "2026-11-22T09:00:00Z");
const t1Old = row("t1-old", "CheckT1", "2026-11-21T10:00:00Z");
const rabiOld = row("rabi-old", "CheckRabi", "2026-11-21T09:00:00Z");
const t1Oldest = row("t1-oldest", "CheckT1", "2026-11-20T10:00:00Z");
const echoOnly = row("echo-1", "CheckT2Echo", "2026-11-22T08:00:00Z");

type Detail = TaskResultResponse | Record<string, unknown> | { status: number } | undefined;

/** A fetch answering GET /task-results with `rows` (newest first) and GET /tasks/{id}/result from `details`. */
function qdashWith(rows: unknown[], details: Record<string, Detail> = {}, total = rows.length) {
  const requests: URL[] = [];
  const fetch = async (input: RequestInfo | URL): Promise<Response> => {
    const url = new URL(new Request(input).url);
    requests.push(url);
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    if (url.pathname === "/api/task-results") {
      return json({ items: rows, total, skip: 0, limit: Number(url.searchParams.get("limit")), status_counts: {} });
    }
    const match = url.pathname.match(/^\/api\/tasks\/([^/]+)\/result$/);
    if (match) {
      const body = details[decodeURIComponent(match[1]!)];
      if (body === undefined) return json({ detail: "Task result not found" }, 404);
      if ("status" in body && typeof body.status === "number") return json({ detail: "database unavailable" }, body.status);
      return json(body);
    }
    return json({ detail: `no ${url.pathname}` }, 404);
  };
  const qdash = new QDash({ baseUrl: "https://qdash.example/api", apiToken: "token", readAttempts: 1 }, { fetch });
  const detailReads = () => requests.filter((url) => url.pathname.startsWith("/api/tasks/")).map((url) => url.pathname).sort();
  return { qdash, requests, detailReads };
}

describe("qdash.taskResults.compareLatest", () => {
  it("lists with the published query parameters and reads only the two newest details per task", async () => {
    const { qdash, requests, detailReads } = qdashWith([t1New, rabiNew, t1Old, rabiOld, t1Oldest], {
      "t1-new": detail(t1New, { t1: output(31.5), t1_fit_r2: output(0.98) }),
      "t1-old": detail(t1Old, { t1: output(24.0), t1_fit_r2: output(0.98) }),
      "t1-oldest": detail(t1Oldest, { t1: output(1) }),
      "rabi-new": detail(rabiNew, { rabi_amplitude: output(0.42), rabi_frequency: output(12.1) }),
      "rabi-old": detail(rabiOld, { rabi_amplitude: output(0.4) }),
    });
    const comparison = await qdash.taskResults.compareLatest({ chipId: "C", qid: "6", limit: 5 });

    expect(requests[0]!.pathname).toBe("/api/task-results");
    expect(Object.fromEntries(requests[0]!.searchParams)).toEqual({ chip_id: "C", qid: "6", limit: "5" });
    const listParameters = openapi.paths["/task-results"]!.get!.parameters!.filter((p) => p.in === "query").map((p) => p.name);
    for (const key of requests[0]!.searchParams.keys()) expect(listParameters).toContain(key);
    // The third CheckT1 result is not read.
    expect(detailReads()).toEqual(["/api/tasks/rabi-new/result", "/api/tasks/rabi-old/result", "/api/tasks/t1-new/result", "/api/tasks/t1-old/result"]);

    expect(comparison.chipId).toBe("C");
    expect(comparison.qid).toBe("6");
    expect(comparison.rows).toEqual({ read: 5, total: 5 });
    expect(comparison.insufficient).toEqual([]);
    // Ordered by each task's newest row; the newest row is `after`.
    expect(comparison.compared.map((item) => [item.task, item.before.task_id, item.after.task_id, item.status])).toEqual([
      ["CheckT1", "t1-old", "t1-new", "compared"],
      ["CheckRabi", "rabi-old", "rabi-new", "compared"],
    ]);
    expect(comparison.compared[0]!.changes).toEqual({ t1: { before: 24.0, after: 31.5 } });
    expect(comparison.compared[1]!.changes).toEqual({
      rabi_amplitude: { before: 0.4, after: 0.42 },
      rabi_frequency: { before: undefined, after: 12.1 },
    });
  });

  it("reports agreeing values as unchanged even when error or calibrated_at differ", async () => {
    const { qdash } = qdashWith([t1New, t1Old], {
      "t1-new": detail(t1New, { t1: output(24.0, 0.1) }),
      "t1-old": detail(t1Old, { t1: output(24.0, 0.3, "2026-11-01T00:00:00Z") }),
    });
    const { compared } = await qdash.taskResults.compareLatest({ chipId: "C", qid: "6" });
    expect(compared.map((item) => [item.status, item.changes])).toEqual([["compared", {}]]);
  });

  it("ignores object key order at any depth but not array order", async () => {
    const { qdash } = qdashWith([t1New, t1Old], {
      "t1-old": detail(t1Old, { config: output({ nested: { a: 1, b: 2 }, items: [{ x: 3, y: 4 }, 5] }), sequence: output([1, 2]) }),
      "t1-new": detail(t1New, { config: output({ items: [{ y: 4, x: 3 }, 5], nested: { b: 2, a: 1 } }), sequence: output([2, 1]) }),
    });
    const { compared } = await qdash.taskResults.compareLatest({ chipId: "C", qid: "6" });
    expect(compared[0]!.changes).toEqual({ sequence: { before: [1, 2], after: [2, 1] } });
  });

  it("lists a task with one result as insufficient and reads no detail for it", async () => {
    const { qdash, detailReads } = qdashWith([echoOnly, t1New], {}, 40);
    const comparison = await qdash.taskResults.compareLatest({ chipId: "C", qid: "6" });
    expect(comparison.compared).toEqual([]);
    expect(comparison.insufficient).toEqual([
      { task: "CheckT2Echo", results: 1 },
      { task: "CheckT1", results: 1 },
    ]);
    expect(comparison.rows).toEqual({ read: 2, total: 40 });
    expect(detailReads()).toEqual([]);
  });

  it.each<[string, Detail, RegExp]>([
    ["a server error", { status: 500 }, /reading the result of t1-old failed/],
    ["a missing result", undefined, /reading the result of t1-old failed/],
    ["a body that is not an object", [] as unknown as Record<string, unknown>, /the result of t1-old is not an object/],
    ["no output_parameters", { ...detail(t1Old, {}), output_parameters: null }, /t1-old has no output_parameters object/],
    ["another task's result", detail(t1New, { t1: output(31.5) }), /the result read for t1-old has task_id "t1-new"/],
    ["another task name", { ...detail(t1Old, { t1: output(31.5) }), task_name: "CheckRabi" }, /task_name "CheckRabi", not "CheckT1"/],
    ["another target", { ...detail(t1Old, { t1: output(31.5) }), qid: "7" }, /qid "7", not "6"/],
    ["another chip", { ...detail(t1Old, { t1: output(31.5) }), chip_id: "D" }, /chip_id "D", not "C"/],
  ])("makes the task unavailable, not unchanged, on %s", async (_label, oldDetail, reason) => {
    const details: Record<string, Detail> = { "t1-new": detail(t1New, { t1: output(31.5) }) };
    if (oldDetail !== undefined) details["t1-old"] = oldDetail;
    const { qdash } = qdashWith([t1New, t1Old], details);
    const [item] = (await qdash.taskResults.compareLatest({ chipId: "C", qid: "6" })).compared;
    expect(item!.status).toBe("unavailable");
    expect(item!.changes).toBeNull();
    expect(item!.error).toMatch(reason);
  });

  it("compares a coupling through the list's exact qid filter", async () => {
    const cNew = row("c-new", "CheckCrossResonance", "2026-11-22T10:00:00Z", "6-7");
    const cOld = row("c-old", "CheckCrossResonance", "2026-11-21T10:00:00Z", "6-7");
    const { qdash, requests } = qdashWith([cNew, cOld], {
      "c-new": detail(cNew, { cr_amplitude: output(0.8) }),
      "c-old": detail(cOld, { cr_amplitude: output(0.7) }),
    });
    const { compared } = await qdash.taskResults.compareLatest({ chipId: "C", qid: "6-7" });
    expect(requests[0]!.searchParams.get("qid")).toBe("6-7");
    expect(compared[0]!.changes).toEqual({ cr_amplitude: { before: 0.7, after: 0.8 } });
  });

  it("rejects a list row without task_name instead of guessing its task", async () => {
    const { qdash } = qdashWith([{ ...t1New, task_name: "" }, t1Old]);
    await expect(qdash.taskResults.compareLatest({ chipId: "C", qid: "6" })).rejects.toThrow(QDashApiError);
    await expect(qdash.taskResults.compareLatest({ chipId: "C", qid: "6" })).rejects.toThrow(/row t1-new has no task_name/);
  });

  it.each([
    [{ qid: "6" }, /chipId is required/],
    [{ chipId: "C" }, /qid is required/],
    [{ chipId: "C", qid: " " }, /qid is required/],
    [{ chipId: "C", qid: "6", limit: 1 }, /limit must be an integer from 2 to 100 \(got 1\)/],
    [{ chipId: "C", qid: "6", limit: 101 }, /limit must be an integer from 2 to 100/],
    [{ chipId: "C", qid: "6", limit: 2.5 }, /limit must be an integer from 2 to 100/],
    [{ chipId: "C", qid: "6", taskName: "CheckT1" }, /taskName is not an option of compareLatest/],
    [{ chipId: "C", couplingId: "6-7" }, /qid is required.*couplingId is not an option/],
  ])("rejects %o before any request", async (options, message) => {
    const { qdash, requests } = qdashWith([]);
    const call = () => qdash.taskResults.compareLatest(options as Parameters<typeof qdash.taskResults.compareLatest>[0]);
    await expect(call()).rejects.toThrow(QDashValidationError);
    await expect(call()).rejects.toThrow(message);
    expect(requests).toEqual([]);
  });
});
