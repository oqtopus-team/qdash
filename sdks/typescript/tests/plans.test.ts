import { describe, expect, it } from "vitest";

import { QDash, QDashConflictError, QDashResultUnknownError, QDashTransportError } from "../src/index.js";

type Handler = (request: Request) => Response | Promise<Response>;

function server(routes: Record<string, Handler[]>) {
  const seen: { method: string; path: string; body: string }[] = [];
  const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(input, init);
    const path = new URL(request.url).pathname.replace(/^\/api/, "");
    const key = `${request.method} ${path}`;
    seen.push({ method: request.method, path, body: await request.clone().text() });
    const handler = routes[key]?.shift();
    if (!handler) throw new Error(`unexpected request ${key}`);
    return handler(request);
  };
  return { fetch, seen };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const session = (fetch: typeof globalThis.fetch) =>
  new QDash({ baseUrl: "https://qdash.example/api", apiToken: "token" }, { fetch, sleep: async () => {} });

const spec = { spec_version: 2, targets: { qids: ["0"] }, steps: [] };
const DIGEST = `sha256:v1:${"a".repeat(64)}`;
const plan = {
  plan_id: "cpp-1",
  chip_id: "64Qv3",
  backend_name: "qubex",
  created_by: "alice",
  created_at: "2026-11-26T00:00:00Z",
  expires_at: "2026-11-27T00:00:00Z",
  expired: false,
  review_version: 1,
  review_digest: DIGEST,
  spec,
  target_qids: ["0"],
  steps: [],
  warnings: [],
  task_run_count: 0,
  default_run_parameters: {},
  task_parameters: {},
  replayed: false,
};
const dispatched = {
  execution_id: "exec-1",
  flow_run_id: "run-1",
  flow_run_url: "",
  qdash_ui_url: "",
  message: "started",
  pipeline_run_id: "cpr-1",
  calibration_session_id: "cs-auto",
  plan_id: "cpp-1",
  review_digest: DIGEST,
};

describe("stored pipeline plans", () => {
  it("creates a plan with its idempotency key, sent once", async () => {
    const { fetch, seen } = server({ "POST /calibration-pipelines/plans": [() => json(plan, 201)] });
    const created = await session(fetch).pipelines.createPlan(spec, { chipId: "64Qv3" }, { idempotencyKey: "tool:1" });
    expect(created.plan_id).toBe("cpp-1");
    expect(seen).toHaveLength(1);
    expect(JSON.parse(seen[0]!.body)).toEqual({ chip_id: "64Qv3", spec, idempotency_key: "tool:1" });
  });

  it("never sends a creation again after a conflict or a failed transport", async () => {
    const conflict = server({ "POST /calibration-pipelines/plans": [() => json({ detail: "other request" }, 409)] });
    await expect(
      session(conflict.fetch).pipelines.createPlan(spec, { chipId: "64Qv3" }, { idempotencyKey: "k" }),
    ).rejects.toBeInstanceOf(QDashConflictError);
    expect(conflict.seen).toHaveLength(1);
    const broken = server({
      "POST /calibration-pipelines/plans": [
        () => {
          throw new TypeError("network down");
        },
      ],
    });
    await expect(
      session(broken.fetch).pipelines.createPlan(spec, { chipId: "64Qv3" }, { idempotencyKey: "k" }),
    ).rejects.toBeInstanceOf(QDashTransportError);
    expect(broken.seen).toHaveLength(1);
  });

  it("refuses a creation without a key", () => {
    const { fetch } = server({});
    expect(() => session(fetch).pipelines.createPlan(spec, { chipId: "64Qv3" }, { idempotencyKey: " " })).toThrow(TypeError);
  });

  it("reads a plan by ID", async () => {
    const { fetch, seen } = server({ "GET /calibration-pipelines/plans/cpp-1": [() => json(plan)] });
    expect((await session(fetch).pipelines.getPlan("cpp-1")).review_digest).toBe(DIGEST);
    expect(seen[0]!.path).toBe("/calibration-pipelines/plans/cpp-1");
  });

  it("executes a plan with the approved digest and checks the echo", async () => {
    const { fetch, seen } = server({ "POST /calibration-pipelines/plans/cpp-1/execute": [() => json(dispatched, 202)] });
    const run = await session(fetch).pipelines.executePlan(
      "cpp-1",
      { chipId: "64Qv3", expectedReviewDigest: DIGEST },
      { idempotencyKey: "run:1" },
    );
    expect(run.executionId).toBe("exec-1");
    expect(JSON.parse(seen[0]!.body)).toEqual({
      chip_id: "64Qv3",
      expected_review_digest: DIGEST,
      idempotency_key: "run:1",
    });
  });

  const echoes: [string, Record<string, unknown>][] = [
    ["no plan", { plan_id: null }],
    ["another plan", { plan_id: "cpp-2" }],
    ["no review digest", { review_digest: null }],
    ["another review digest", { review_digest: `sha256:v1:${"b".repeat(64)}` }],
  ];
  for (const [name, change] of echoes) {
    it(`reports a response with ${name} as result unknown, sent once`, async () => {
      for (const recordIn of [undefined, { idempotencyKey: "run:1" }]) {
        const { fetch, seen } = server({
          "POST /calibration-pipelines/plans/cpp-1/execute": [() => json({ ...dispatched, ...change }, 202)],
        });
        const error = await session(fetch)
          .pipelines.executePlan("cpp-1", { chipId: "64Qv3", expectedReviewDigest: DIGEST }, recordIn)
          .catch((caught: unknown) => caught);
        expect(error).toBeInstanceOf(QDashResultUnknownError);
        expect((error as Error).message).toMatch(/^Pipeline plan result unknown: .*plan cpp-1/);
        expect((error as QDashResultUnknownError).executionId).toBe("exec-1");
        expect(seen).toHaveLength(1);
      }
    });
  }

  it("reports a recorded plan run without its run as result unknown", async () => {
    const { fetch } = server({
      "POST /calibration-pipelines/plans/cpp-1/execute": [() => json({ ...dispatched, pipeline_run_id: null }, 202)],
    });
    await expect(
      session(fetch).pipelines.executePlan("cpp-1", { chipId: "64Qv3", expectedReviewDigest: DIGEST }, { idempotencyKey: "k" }),
    ).rejects.toBeInstanceOf(QDashResultUnknownError);
  });

  it("keeps a definite refusal as an error and does not send it again", async () => {
    const { fetch, seen } = server({
      "POST /calibration-pipelines/plans/cpp-1/execute": [() => json({ detail: "expired" }, 410)],
    });
    const error = await session(fetch)
      .pipelines.executePlan("cpp-1", { chipId: "64Qv3", expectedReviewDigest: DIGEST })
      .catch((caught: unknown) => caught);
    expect(error).not.toBeInstanceOf(QDashResultUnknownError);
    expect(seen).toHaveLength(1);
  });
});
