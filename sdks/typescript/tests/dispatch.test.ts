import { describe, expect, it } from "vitest";

import {
  QDash,
  QDashConflictError,
  QDashPreflightError,
  QDashResultUnknownError,
  QDashTransportError,
  QDashValidationError,
  type PipelineRecording,
} from "../src/index.js";

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

const spec = { spec_version: 2, targets: { kind: "qubits", qids: ["0"] }, steps: [] };
const dispatched = { execution_id: "exec-1", flow_run_id: "run-1", flow_run_url: "", qdash_ui_url: "", message: "started" };
const sessionList = () => json({ items: [{ calibration_session_id: "cs-1", chip_id: "64Qv3" }], has_more: false });

const undecodable: [string, () => Response, unknown][] = [
  ["truncated JSON labelled JSON", () => new Response('{"execution_id": "exec-1", "flo', { status: 200, headers: { "Content-Type": "application/json" } }), '{"execution_id": "exec-1", "flo'],
  ["truncated JSON without a JSON type", () => new Response('{"execution_id": "ex', { status: 201, headers: { "Content-Type": "text/plain" } }), '{"execution_id": "ex'],
  ["an empty body", () => new Response(null, { status: 200 }), undefined],
  ["a JSON array", () => json(["exec-1"]), ["exec-1"]],
];

describe("an undecodable dispatch acknowledgement is result unknown", () => {
  for (const [name, reply, body] of undecodable) {
    it(`workflow run: ${name}`, async () => {
      for (const options of [{}, { calibrationSessionId: "cs-1", idempotencyKey: "k" }]) {
        const { fetch, seen } = server({ "POST /flows/coherence_check/execute": [reply] });
        const error = await session(fetch)
          .workflows.run("coherence_check", options)
          .catch((caught: unknown) => caught);
        expect(error).toBeInstanceOf(QDashResultUnknownError);
        expect(error).not.toBeInstanceOf(QDashTransportError);
        const unknown = error as QDashResultUnknownError;
        expect(unknown.message).toMatch(/^Workflow result unknown: .*may have started.*reconcile the execution first/);
        expect(unknown.statusCode).toBe(reply().status);
        expect(unknown.body).toEqual(body);
        expect(unknown.rawResponse?.status).toBe(reply().status);
        expect(unknown.executionId).toBeUndefined();
        expect(seen).toHaveLength(1);
      }
    });

    it(`pipeline execute: ${name}`, async () => {
      for (const recordIn of [undefined, { calibrationSessionId: "cs-1", idempotencyKey: "k" }]) {
        const { fetch, seen } = server({ "GET /calibration-sessions": [sessionList], "POST /calibration-pipelines/execute": [reply] });
        const error = await session(fetch)
          .pipelines.execute(spec, { chipId: "64Qv3" }, recordIn)
          .catch((caught: unknown) => caught);
        expect(error).toBeInstanceOf(QDashResultUnknownError);
        expect((error as Error).message).toMatch(/^Pipeline result unknown: .*may have started/);
        expect((error as QDashResultUnknownError).body).toEqual(body);
        expect(seen.filter((request) => request.method === "POST")).toHaveLength(1);
      }
    });
  }

  it("keeps the client's error as the cause of a JSON-labelled body that does not parse", async () => {
    const { fetch } = server({ "POST /flows/coherence_check/execute": [undecodable[0]![1]] });
    const error = (await session(fetch).workflows.run("coherence_check").catch((caught: unknown) => caught)) as Error;
    expect(error.cause).toBeInstanceOf(Error);
  });

  it("keeps definite rejections and transport failures as they were, sent once", async () => {
    const { fetch, seen } = server({
      "POST /flows/coherence_check/execute": [
        () => json({ detail: "bad parameters" }, 422),
        () => {
          throw new TypeError("connection reset");
        },
      ],
    });
    const qdash = session(fetch);
    await expect(qdash.workflows.run("coherence_check")).rejects.toBeInstanceOf(QDashValidationError);
    const failed = await qdash.workflows.run("coherence_check").catch((caught: unknown) => caught);
    expect(failed).toBeInstanceOf(QDashTransportError);
    expect(failed).not.toBeInstanceOf(QDashResultUnknownError);
    expect(seen).toHaveLength(2);
  });

  it("keeps a valid acknowledgement as it was", async () => {
    const { fetch } = server({ "POST /flows/coherence_check/execute": [() => json(dispatched)] });
    const run = await session(fetch).workflows.run("coherence_check");
    expect(run.executionId).toBe("exec-1");
  });
});

describe("the decision check uses the decision that was sent", () => {
  const answer = (decision?: string) => ({
    ...dispatched,
    calibration_session_id: "cs-1",
    pipeline_run_id: "cpr-1",
    ...(decision ? { decision_id: decision } : {}),
  });

  /** Execute while the caller changes its recording options during the POST. */
  async function mutated(reply: unknown) {
    const recordIn: PipelineRecording = { calibrationSessionId: "cs-1", idempotencyKey: "k", decisionId: "d-1" };
    const { fetch, seen } = server({
      "GET /calibration-sessions": [sessionList],
      "POST /calibration-pipelines/execute": [
        () => {
          recordIn.decisionId = "d-changed";
          return json(reply);
        },
      ],
    });
    const outcome = await session(fetch)
      .pipelines.execute(spec, { chipId: "64Qv3" }, recordIn)
      .catch((caught: unknown) => caught);
    const posted = seen.filter((request) => request.method === "POST");
    expect(posted).toHaveLength(1);
    expect(JSON.parse(posted[0]!.body).decision_id).toBe("d-1");
    return outcome;
  }

  it("accepts an echo of the original decision", async () => {
    const run = await mutated(answer("d-1"));
    expect(run).not.toBeInstanceOf(Error);
  });

  for (const [name, reply] of [
    ["a missing", answer()],
    ["a different", answer("d-changed")],
  ] as const) {
    it(`reports ${name} decision echo as result unknown, naming the sent decision`, async () => {
      const error = await mutated(reply);
      expect(error).toBeInstanceOf(QDashResultUnknownError);
      expect((error as Error).message).toContain("without its decision d-1.");
      expect((error as Error).message).not.toContain("d-changed");
    });
  }
});

describe("the session preflight reads no session detail", () => {
  interface StoredSession {
    calibration_session_id: string;
    chip_id: string;
    created_by: string;
    origin: "manual" | "automatic";
    status: "open" | "closed";
  }

  /**
   * A server with the session routes' contract: the detail GET closes an open automatic session
   * whose work has ended (`check_automatic_session`); the list has no side effects; the execute
   * route refuses a new run in a closed session but replays a recorded key in any status.
   */
  function sessionServer(sessions: StoredSession[], options: { listStatus?: number; listBody?: unknown } = {}) {
    const seen: { method: string; path: string; query: URLSearchParams; body: string }[] = [];
    const recorded = new Map<string, unknown>();
    const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const request = new Request(input, init);
      const url = new URL(request.url);
      const path = url.pathname.replace(/^\/api/, "");
      const body = await request.clone().text();
      seen.push({ method: request.method, path, query: url.searchParams, body });
      if (request.method === "GET" && path === "/calibration-sessions") {
        if (options.listStatus) return json({ detail: "Not Found" }, options.listStatus);
        if (options.listBody !== undefined) return json(options.listBody);
        const skip = Number(url.searchParams.get("skip") ?? 0);
        const limit = Number(url.searchParams.get("limit") ?? 20);
        const chip = url.searchParams.get("chip_id");
        const mine = url.searchParams.get("mine") === "true";
        const matching = sessions.filter((item) => (!chip || item.chip_id === chip) && (!mine || item.created_by === "alice"));
        return json({ items: matching.slice(skip, skip + limit), has_more: matching.length > skip + limit });
      }
      const detail = /^\/calibration-sessions\/([^/]+)$/.exec(path);
      if (request.method === "GET" && detail) {
        const found = sessions.find((item) => item.calibration_session_id === detail[1]);
        if (!found) return json({ detail: "not found" }, 404);
        if (found.origin === "automatic" && found.status === "open") found.status = "closed";
        return json(found);
      }
      if (request.method === "POST" && path === "/calibration-pipelines/execute") {
        const sent = JSON.parse(body) as { calibration_session_id: string; idempotency_key: string };
        const replay = recorded.get(sent.idempotency_key);
        if (replay) return json({ ...(replay as object), replayed: true }, 201);
        const target = sessions.find((item) => item.calibration_session_id === sent.calibration_session_id);
        if (!target) return json({ detail: "not found" }, 404);
        if (target.status === "closed") return json({ detail: `Calibration session ${target.calibration_session_id} is closed; start a new one` }, 409);
        const answer = { ...dispatched, calibration_session_id: target.calibration_session_id, pipeline_run_id: `cpr-${recorded.size + 1}`, replayed: false };
        recorded.set(sent.idempotency_key, answer);
        return json(answer, 201);
      }
      throw new Error(`unexpected request ${request.method} ${path}`);
    };
    return { fetch, seen };
  }

  const own = (id: string, extra: Partial<StoredSession> = {}): StoredSession => ({
    calibration_session_id: id,
    chip_id: "64Qv3",
    created_by: "alice",
    origin: "manual",
    status: "open",
    ...extra,
  });
  const posts = <T extends { method: string }>(seen: T[]) => seen.filter((request) => request.method === "POST");
  const details = (seen: { path: string }[]) => seen.filter((request) => /^\/calibration-sessions\/./.test(request.path));

  it("launches into an open automatic session whose work ended, without closing it first", async () => {
    const automatic = own("cs-auto", { origin: "automatic" });
    const { fetch, seen } = sessionServer([automatic]);
    const run = await session(fetch).pipelines.execute(spec, { chipId: "64Qv3" }, { calibrationSessionId: "cs-auto", idempotencyKey: "k" });
    expect(run.response.calibration_session_id).toBe("cs-auto");
    expect(automatic.status).toBe("open");
    expect(details(seen)).toEqual([]);
    const list = seen[0]!;
    expect(list.path).toBe("/calibration-sessions");
    expect(Object.fromEntries(list.query)).toEqual({ chip_id: "64Qv3", mine: "true", limit: "100", skip: "0" });
    expect(posts(seen)).toHaveLength(1);
  });

  it("pages through the signed-in user's sessions on the chip until it finds the session", async () => {
    const others = Array.from({ length: 150 }, (_, index) => own(`cs-${index}`));
    const { fetch, seen } = sessionServer([...others, own("cs-old"), own("cs-theirs", { created_by: "bob" })]);
    await session(fetch).pipelines.execute(spec, { chipId: "64Qv3" }, { calibrationSessionId: "cs-old", idempotencyKey: "k" });
    expect(seen.filter((request) => request.method === "GET").map((request) => request.query.get("skip"))).toEqual(["0", "100"]);
    expect(posts(seen)).toHaveLength(1);
  });

  for (const [name, sessions, options] of [
    ["is missing", [own("cs-other")], {}],
    ["is on another chip", [own("cs-1", { chip_id: "other" })], { listBody: { items: [own("cs-1", { chip_id: "other" })], has_more: false } }],
    ["is another user's", [own("cs-1", { created_by: "bob" })], {}],
    ["cannot be listed in that shape", [own("cs-1")], { listBody: { sessions: [own("cs-1")] } }],
  ] as const) {
    it(`dispatches nothing when the session ${name}`, async () => {
      const { fetch, seen } = sessionServer([...sessions], options);
      const error = await session(fetch)
        .pipelines.execute(spec, { chipId: "64Qv3" }, { calibrationSessionId: "cs-1", idempotencyKey: "k" })
        .catch((caught: unknown) => caught);
      expect(error).toBeInstanceOf(Error);
      expect((error as Error).message).toMatch(/^Calibration session preflight failed: cs-1 .*nothing dispatched/);
      expect(posts(seen)).toEqual([]);
      expect(details(seen)).toEqual([]);
    });
  }

  it("dispatches nothing to a server without the session routes", async () => {
    const { fetch, seen } = sessionServer([own("cs-1")], { listStatus: 404 });
    await expect(
      session(fetch).pipelines.execute(spec, { chipId: "64Qv3" }, { calibrationSessionId: "cs-1", idempotencyKey: "k" }),
    ).rejects.toMatchObject({ name: "QDashPreflightError", cause: { statusCode: 404 } });
    expect(posts(seen)).toEqual([]);
  });

  it("distinguishes an unavailable preflight from dispatch failure", async () => {
    const { fetch, seen } = sessionServer([own("cs-1")], { listStatus: 503 });
    const error = await session(fetch)
      .pipelines.execute(spec, { chipId: "64Qv3" }, { calibrationSessionId: "cs-1", idempotencyKey: "k" })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(QDashPreflightError);
    expect(error).toMatchObject({ cause: { statusCode: 503 } });
    expect((error as Error).message).toContain("nothing dispatched");
    expect(posts(seen)).toEqual([]);
  });

  it("stops at the last page the list accepts and dispatches nothing", async () => {
    const { fetch, seen } = sessionServer([], { listBody: { items: [own("cs-x")], has_more: true } });
    const error = await session(fetch)
      .pipelines.execute(spec, { chipId: "64Qv3" }, { calibrationSessionId: "cs-1", idempotencyKey: "k" })
      .catch((caught: unknown) => caught);
    expect((error as Error).message).toMatch(/^Calibration session preflight failed/);
    const skips = seen.map((request) => Number(request.query.get("skip")));
    expect(skips.at(-1)).toBe(10_000);
    expect(skips).toHaveLength(101);
    expect(posts(seen)).toEqual([]);
  });

  it("still sends a repeated write with the same key to a session closed since, and returns the replay", async () => {
    const stored = own("cs-1");
    const { fetch, seen } = sessionServer([stored]);
    const qdash = session(fetch);
    const recordIn = { calibrationSessionId: "cs-1", idempotencyKey: "k" };
    const first = await qdash.pipelines.execute(spec, { chipId: "64Qv3" }, recordIn);
    stored.status = "closed";
    const again = await qdash.pipelines.execute(spec, { chipId: "64Qv3" }, recordIn);
    expect(again.response).toMatchObject({ pipeline_run_id: first.response.pipeline_run_id, replayed: true });
    expect(posts(seen).map((request) => request.body)).toEqual([posts(seen)[0]!.body, posts(seen)[0]!.body]);
    // A new key in the closed session reaches the server, which refuses it.
    await expect(
      qdash.pipelines.execute(spec, { chipId: "64Qv3" }, { calibrationSessionId: "cs-1", idempotencyKey: "k2" }),
    ).rejects.toBeInstanceOf(QDashConflictError);
    expect(details(seen)).toEqual([]);
  });
});
