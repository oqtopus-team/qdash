import { describe, expect, it } from "vitest";

import { read, sessionAuth } from "../src/_http.js";
import {
  ApiError,
  QDash,
  QDashApiError,
  QDashAuthError,
  QDashConfig,
  QDashConfigError,
  QDashConflictError,
  QDashTransportError,
  customOneQubit,
  qubitTargets,
  type QDashConfigOptions,
  type QDashSessionOptions,
} from "../src/index.js";

type Handler = (request: Request) => Response | Promise<Response>;

interface Seen {
  method: string;
  path: string;
  headers: Headers;
  body: string;
}

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

/** A fetch answering each request with the next handler of its "METHOD /path" and recording it. */
function server(routes: Record<string, Handler[]>) {
  const seen: Seen[] = [];
  const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(input, init);
    const path = new URL(request.url).pathname.replace(/^\/api/, "");
    const key = `${request.method} ${path}`;
    seen.push({ method: request.method, path, headers: request.headers, body: await request.clone().text() });
    const handler = routes[key]?.shift();
    if (!handler) throw new Error(`unexpected request ${key}`);
    return handler(request);
  };
  return { fetch, seen };
}

function session(
  fetch: typeof globalThis.fetch,
  config: Partial<QDashConfigOptions> = {},
  options: QDashSessionOptions = {},
) {
  const sleeps: number[] = [];
  const qdash = new QDash(
    { baseUrl: "https://qdash.example/api", apiToken: "token", ...config },
    {
      fetch,
      sleep: async (milliseconds) => {
        sleeps.push(milliseconds);
      },
      ...options,
    },
  );
  return { qdash, sleeps };
}

const spec = { spec_version: 2, targets: qubitTargets(["0"]), steps: [customOneQubit({ tasks: [{ name: "CheckT1" }] })] };
const hang = (request: Request) =>
  new Promise<Response>((_resolve, reject) => {
    request.signal.addEventListener("abort", () => reject(request.signal.reason), { once: true });
  });

describe("writes are sent once", () => {
  for (const [status, ErrorClass] of [
    [409, QDashConflictError],
    [500, QDashApiError],
    [503, QDashApiError],
    [429, QDashApiError],
  ] as const) {
    it(`a ${status} answer to a dispatch is thrown, not retried`, async () => {
      const { fetch, seen } = server({ "POST /calibration-pipelines/execute": [() => json({ detail: "busy" }, status)] });
      const { qdash, sleeps } = session(fetch);
      const error = await qdash.pipelines.execute(spec, { chipId: "C" }).catch((caught: unknown) => caught);
      expect(error).toBeInstanceOf(ErrorClass);
      expect(error).toMatchObject({ statusCode: status, payload: { detail: "busy" } });
      // A synthetic Response has no URL, so the message names no path here.
      expect((error as Error).message).toBe(`${status}: busy`);
      expect(seen).toHaveLength(1);
      expect(sleeps).toEqual([]);
    });
  }

  it("a timed-out dispatch is a transport error and is not sent again", async () => {
    const { fetch, seen } = server({ "POST /flows/f/execute": [hang] });
    const { qdash } = session(fetch, { timeoutSec: 0.05 });
    await expect(qdash.workflows.run("f")).rejects.toBeInstanceOf(QDashTransportError);
    expect(seen).toHaveLength(1);
  });

  it("a connection failure of a write is a transport error, sent once", async () => {
    const { fetch, seen } = server({
      "PATCH /dashboards/d1": [
        () => {
          throw new TypeError("fetch failed");
        },
      ],
    });
    const { qdash } = session(fetch);
    const { Dashboard } = await import("../src/index.js");
    const error = await qdash.dashboards
      .update("d1", new Dashboard({ name: "n" }), { expectedVersion: 1 })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(QDashTransportError);
    expect(error).toMatchObject({ statusCode: undefined });
    expect(seen).toHaveLength(1);
  });

  it("the generated client sends every call once by default", async () => {
    const { fetch, seen } = server({ "GET /flows": [() => json({}, 503)] });
    const { qdash } = session(fetch);
    const error = await qdash.api.flow.listFlows().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(seen).toHaveLength(1);
  });
});

describe("reads are sent again after a transient failure", () => {
  it("retries a 503 and a dropped connection up to readAttempts, honouring Retry-After", async () => {
    const { fetch, seen } = server({
      "GET /flows": [
        () => json({ detail: "busy" }, 503, { "Retry-After": "2" }),
        () => {
          throw new TypeError("socket hang up");
        },
        () => json({ flows: [] }),
      ],
    });
    const { qdash, sleeps } = session(fetch);
    await expect(qdash.workflows.list()).resolves.toEqual([]);
    expect(seen).toHaveLength(3);
    expect(sleeps).toEqual([2000, 400]);
  });

  it("stops at readAttempts and throws the last error", async () => {
    const { fetch, seen } = server({ "GET /flows": [() => json({}, 502), () => json({ detail: "down" }, 502)] });
    const { qdash } = session(fetch, { readAttempts: 2 });
    await expect(qdash.workflows.list()).rejects.toMatchObject({ statusCode: 502, message: "502: down" });
    expect(seen).toHaveLength(2);
  });

  it("does not retry a 4xx answer", async () => {
    const { fetch, seen } = server({ "GET /flows/f": [() => json({ detail: "no" }, 404)] });
    const { qdash } = session(fetch);
    await expect(qdash.workflows.get("f")).rejects.toMatchObject({ statusCode: 404 });
    expect(seen).toHaveLength(1);
  });

  it("never retries a caller's abort and rejects with its reason", async () => {
    const controller = new AbortController();
    const reason = new Error("stop");
    let calls = 0;
    const promise = read({ attempts: 3, sleep: async () => {}, signal: controller.signal }, async () => {
      calls += 1;
      controller.abort(reason);
      throw new ApiError({ message: "aborted" });
    });
    await expect(promise).rejects.toBe(reason);
    expect(calls).toBe(1);
  });
});

describe("request headers", () => {
  it("sends the token, project, Cloudflare Access headers and user agent with the custom fetch", async () => {
    const { fetch, seen } = server({ "GET /flows": [() => json({ flows: [] }), () => json({ flows: [] }), () => json({ flows: [] })] });
    const { qdash } = session(fetch, {
      projectId: "p1",
      cfAccessClientId: "cid",
      cfAccessClientSecret: "csecret",
      userAgent: "probe/1",
    });
    await qdash.workflows.list();
    // A call's undefined project leaves the session's; a defined one overrides it for that call.
    await qdash.api.flow.listFlows({ projectId: undefined });
    await qdash.api.flow.listFlows({ projectId: "p9" });
    const [first, second, third] = seen;
    expect(first!.headers.get("Authorization")).toBe("Bearer token");
    expect(first!.headers.get("CF-Access-Client-Id")).toBe("cid");
    expect(first!.headers.get("CF-Access-Client-Secret")).toBe("csecret");
    expect(first!.headers.get("User-Agent")).toBe("probe/1");
    expect(first!.headers.get("X-Fern-Language")).toBeNull();
    expect(seen.map((request) => request.headers.get("X-Project-Id"))).toEqual(["p1", "p1", "p9"]);
    expect(second!.headers.get("Authorization")).toBe("Bearer token");
    expect(third!.headers.get("Authorization")).toBe("Bearer token");
  });

  it("names the SDK in the default user agent and sends no project when none is configured", async () => {
    const { fetch, seen } = server({ "GET /flows": [() => json({ flows: [] })] });
    await session(fetch).qdash.workflows.list();
    expect(seen[0]!.headers.get("User-Agent")).toMatch(/^qdash-sdk-ts\//);
    expect(seen[0]!.headers.get("X-Project-Id")).toBeNull();
  });
});

describe("username and password sign-in", () => {
  const password = { username: "alice", passwordEnv: "QDASH_PW", apiToken: undefined } as Partial<QDashConfigOptions>;
  const env = { QDASH_PW: "pw" };

  it("signs in once with the form body and reuses the token, also in a project-scoped session", async () => {
    const { fetch, seen } = server({
      "POST /auth/login": [() => json({ access_token: "jwt", token_type: "bearer" })],
      "GET /flows": [() => json({ flows: [] }), () => json({ flows: [] }), () => json({ flows: [] })],
    });
    const { qdash } = session(fetch, password, { env });
    await Promise.all([qdash.workflows.list(), qdash.workflows.list()]);
    await qdash.withProject("p2").workflows.list();
    expect(seen.map((request) => `${request.method} ${request.path}`)).toEqual([
      "POST /auth/login",
      "GET /flows",
      "GET /flows",
      "GET /flows",
    ]);
    expect(new URLSearchParams(seen[0]!.body).get("username")).toBe("alice");
    expect(new URLSearchParams(seen[0]!.body).get("password")).toBe("pw");
    expect(seen[0]!.headers.get("Authorization")).toBeNull();
    expect(seen.slice(1).every((request) => request.headers.get("Authorization") === "Bearer jwt")).toBe(true);
    expect(seen[3]!.headers.get("X-Project-Id")).toBe("p2");
  });

  for (const [name, reply, message] of [
    ["invalid JSON", () => new Response("<html>", { status: 200, headers: { "Content-Type": "text/html" } }), "Login response was not valid JSON"],
    ["invalid JSON labelled JSON", () => new Response("{oops", { status: 200, headers: { "Content-Type": "application/json" } }), "Login response was not valid JSON"],
    ["a JSON array", () => json(["jwt"]), "Login response must be a JSON object"],
    ["no access_token", () => json({ token_type: "bearer" }), "Login response did not include access_token"],
  ] as const) {
    it(`turns a login response with ${name} into QDashAuthError`, async () => {
      const { fetch, seen } = server({ "POST /auth/login": [reply] });
      const { qdash } = session(fetch, password, { env });
      const error = await qdash.workflows.list().catch((caught: unknown) => caught);
      expect(error).toBeInstanceOf(QDashAuthError);
      expect((error as Error).message).toBe(message);
      expect(seen).toHaveLength(1);
    });
  }

  it("reports a rejected login and tries again on the next request", async () => {
    const { fetch, seen } = server({
      "POST /auth/login": [() => json({ detail: "Incorrect username or password" }, 401), () => json({ access_token: "jwt" })],
      "GET /flows": [() => json({ flows: [] })],
    });
    const { qdash } = session(fetch, password, { env });
    await expect(qdash.workflows.list()).rejects.toBeInstanceOf(QDashAuthError);
    await expect(qdash.workflows.list()).resolves.toEqual([]);
    expect(seen).toHaveLength(3);
  });

  const logins = (seen: Seen[]) => seen.filter((request) => request.path === "/auth/login").length;
  const bearer = (request: Seen | undefined) => request?.headers.get("Authorization");

  it("signs in again on the next request after a 401, without resending the read that got it", async () => {
    const { fetch, seen } = server({
      "POST /auth/login": [() => json({ access_token: "t1" }), () => json({ access_token: "t2" })],
      "GET /flows": [() => json({ detail: "expired" }, 401), () => json({ flows: [] }), () => json({ flows: [] })],
    });
    const { qdash, sleeps } = session(fetch, password, { env });
    const error = await qdash.workflows.list().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(QDashAuthError);
    expect((error as QDashAuthError).statusCode).toBe(401);
    expect(seen.map((request) => request.path)).toEqual(["/auth/login", "/flows"]);
    await qdash.workflows.list();
    await qdash.workflows.list();
    expect(seen.map((request) => request.path)).toEqual(["/auth/login", "/flows", "/auth/login", "/flows", "/flows"]);
    expect(seen.slice(3).map(bearer)).toEqual(["Bearer t2", "Bearer t2"]);
    expect(sleeps).toEqual([]);
  });

  it("sends a write that got a 401 once and throws it; the next call signs in", async () => {
    const { fetch, seen } = server({
      "POST /auth/login": [() => json({ access_token: "t1" }), () => json({ access_token: "t2" })],
      "POST /calibration-pipelines/execute": [() => json({ detail: "expired" }, 401), () => json({ execution_id: "e", flow_run_id: "r", flow_run_url: "", qdash_ui_url: "", message: "" })],
    });
    const { qdash } = session(fetch, password, { env });
    await expect(qdash.pipelines.execute(spec, { chipId: "64Qv3" })).rejects.toBeInstanceOf(QDashAuthError);
    expect(seen.map((request) => request.path)).toEqual(["/auth/login", "/calibration-pipelines/execute"]);
    await qdash.pipelines.execute(spec, { chipId: "64Qv3" });
    expect(seen.map((request) => request.path)).toEqual([
      "/auth/login",
      "/calibration-pipelines/execute",
      "/auth/login",
      "/calibration-pipelines/execute",
    ]);
    expect(bearer(seen[3])).toBe("Bearer t2");
  });

  it("drops the sign-in after a 401 to a generated client call too", async () => {
    const { fetch, seen } = server({
      "POST /auth/login": [() => json({ access_token: "t1" }), () => json({ access_token: "t2" })],
      "GET /flows": [() => json({ detail: "expired" }, 401), () => json({ flows: [] })],
    });
    const { qdash } = session(fetch, password, { env });
    const raw = await qdash.api.flow.listFlows().catch((caught: unknown) => caught);
    expect(raw).toBeInstanceOf(ApiError);
    expect((raw as ApiError).statusCode).toBe(401);
    await qdash.workflows.list();
    expect(logins(seen)).toBe(2);
    expect(bearer(seen.at(-1))).toBe("Bearer t2");
  });

  it.each(["t2", "t1"])("keeps a newer sign-in (%s) when an older request gets a 401", async (newToken) => {
    let answerStale: (response: Response) => void = () => {};
    const stale = new Promise<Response>((resolve) => {
      answerStale = resolve;
    });
    const { fetch, seen } = server({
      "POST /auth/login": [() => json({ access_token: "t1" }), () => json({ access_token: newToken })],
      "GET /flows": [() => stale, () => json({ detail: "expired" }, 401), () => json({ flows: [] }), () => json({ flows: [] })],
    });
    const { qdash } = session(fetch, password, { env });
    // Both requests share one sign-in and carry t1.
    const slow = qdash.workflows.list().catch((caught: unknown) => caught);
    await expect(qdash.workflows.list()).rejects.toBeInstanceOf(QDashAuthError);
    expect(logins(seen)).toBe(1);
    // The next request signs in again and gets t2.
    await qdash.workflows.list();
    expect(logins(seen)).toBe(2);
    // The 401 of the request that carried t1 arrives last; t2 stays.
    answerStale(json({ detail: "expired" }, 401));
    expect(await slow).toBeInstanceOf(QDashAuthError);
    await qdash.workflows.list();
    expect(logins(seen)).toBe(2);
    expect(seen.filter((request) => request.path === "/flows").map(bearer)).toEqual([
      "Bearer t1",
      "Bearer t1",
      `Bearer ${newToken}`,
      `Bearer ${newToken}`,
    ]);
  });

  it("keeps a new sign-in with the same token when a request of the old one, paused after taking its token, gets a 401", async () => {
    let release: (value: string) => void = () => {};
    const gate = new Promise<string>((resolve) => {
      release = resolve;
    });
    const { fetch, seen } = server({
      // The server issues the same token string twice.
      "POST /auth/login": [() => json({ access_token: "same" }), () => json({ access_token: "same" })],
      "GET /flows": [
        () => json({ detail: "expired" }, 401),
        () => json({ flows: [] }),
        () => json({ detail: "expired" }, 401),
        () => json({ flows: [] }),
      ],
    });
    const { qdash } = session(fetch, password, { env });
    // A generated call takes its token, then waits in an async header supplier before fetch.
    const paused = qdash.api.flow.listFlows({ headers: { "X-Trace": () => gate } }).catch((caught: unknown) => caught);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(logins(seen)).toBe(1);
    expect(seen.filter((request) => request.path === "/flows")).toHaveLength(0);
    // Another request gets a 401 and drops the first sign-in; the next signs in again.
    await expect(qdash.workflows.list()).rejects.toBeInstanceOf(QDashAuthError);
    await qdash.workflows.list();
    expect(logins(seen)).toBe(2);
    // The paused request of the first sign-in is sent now and gets a 401: the new sign-in stays.
    release("trace");
    expect(await paused).toMatchObject({ statusCode: 401 });
    await qdash.workflows.list();
    expect(logins(seen)).toBe(2);
    const flows = seen.filter((request) => request.path === "/flows");
    expect(flows.map(bearer)).toEqual(["Bearer same", "Bearer same", "Bearer same", "Bearer same"]);
    expect(flows[2]?.headers.get("X-Trace")).toBe("trace");
    // Only the real token reaches the network.
    for (const request of seen) {
      for (const [name, value] of request.headers) {
        expect(`${name}: ${value}`).not.toMatch(/qdash-sdk-sign-in/);
      }
    }
  });

  it("sends a caller's own Authorization of a generated call as given and keeps the sign-in after its 401", async () => {
    const { fetch, seen } = server({
      "POST /auth/login": [() => json({ access_token: "t1" })],
      "GET /flows": [() => json({ detail: "bad" }, 401), () => json({ flows: [] })],
    });
    const { qdash } = session(fetch, password, { env });
    const raw = await qdash.api.flow.listFlows({ headers: { Authorization: "Bearer mine" } }).catch((caught: unknown) => caught);
    expect(raw).toMatchObject({ statusCode: 401 });
    await qdash.workflows.list();
    expect(seen.filter((request) => request.path === "/flows").map(bearer)).toEqual(["Bearer mine", "Bearer t1"]);
    expect(logins(seen)).toBe(1);
  });

  it("sends a request paused across many sign-ins with its own token, and its 401 keeps the newest", async () => {
    let release: (value: string) => void = () => {};
    const gate = new Promise<string>((resolve) => {
      release = resolve;
    });
    const cycles = 25;
    const logins401 = Array.from({ length: cycles + 1 }, (_, index) => () => json({ access_token: `t${index + 1}` }));
    const flows: Handler[] = [];
    for (let index = 0; index < cycles; index += 1) flows.push(() => json({ detail: "expired" }, 401));
    flows.push(() => json({ flows: [] }), () => json({ detail: "expired" }, 401));
    const { fetch, seen } = server({ "POST /auth/login": logins401, "GET /flows": flows });
    const { qdash } = session(fetch, password, { env });
    const paused = qdash.api.flow.listFlows({ headers: { "X-Trace": () => gate } }).catch((caught: unknown) => caught);
    await new Promise((resolve) => setTimeout(resolve, 0));
    // Each 401 drops the current sign-in and the next request signs in again.
    for (let index = 0; index < cycles; index += 1) {
      await expect(qdash.workflows.list()).rejects.toBeInstanceOf(QDashAuthError);
    }
    expect(logins(seen)).toBe(cycles);
    await expect(qdash.workflows.list()).resolves.toEqual([]);
    const latest = `Bearer t${cycles + 1}`;
    expect(bearer(seen.at(-1))).toBe(latest);
    // The first sign-in's request still carries t1; its 401 does not drop the newest sign-in.
    release("trace");
    expect(await paused).toMatchObject({ statusCode: 401 });
    expect(bearer(seen.at(-1))).toBe("Bearer t1");
    expect(logins(seen)).toBe(cycles + 1);
  });

  it("leaves nothing behind for requests whose header supplier fails or is aborted before fetch", async () => {
    const { fetch, seen } = server({
      "POST /auth/login": [() => json({ access_token: "t1" })],
      "GET /flows": [() => json({ flows: [] })],
    });
    const { qdash } = session(fetch, password, { env });
    for (let index = 0; index < 20; index += 1) {
      const failed = await qdash.api.flow
        .listFlows({ headers: { "X-Trace": () => Promise.reject(new Error("no trace")) } })
        .catch((caught: unknown) => caught);
      expect((failed as Error).message).toMatch(/no trace/);
      const controller = new AbortController();
      const aborted = qdash.api.flow
        .listFlows({
          abortSignal: controller.signal,
          headers: {
            "X-Trace": () =>
              new Promise<string>((_, reject) => {
                if (controller.signal.aborted) reject(controller.signal.reason);
                controller.signal.addEventListener("abort", () => reject(controller.signal.reason));
              }),
          },
        })
        .catch((caught: unknown) => caught);
      controller.abort(new Error("stopped"));
      expect(await aborted).toBeInstanceOf(Error);
    }
    // None reached the network, the one sign-in stays, and the next request uses it.
    expect(seen.map((request) => request.path)).toEqual(["/auth/login"]);
    await expect(qdash.workflows.list()).resolves.toEqual([]);
    expect(seen.map((request) => `${request.path} ${bearer(request) ?? ""}`)).toEqual(["/auth/login ", "/flows Bearer t1"]);
  });

  it("looks up no sign-in history: the session's fetch sends the token a request carries", async () => {
    const { fetch, seen } = server({
      "POST /auth/login": [() => json({ access_token: "t1" })],
      "GET /flows": [() => json({ detail: "x" }, 401), () => json({ flows: [] })],
    });
    const auth = sessionAuth(new QDashConfig({ baseUrl: "https://qdash.example/api", ...password }), fetch, env);
    const marker = await (auth.token as () => Promise<string>)();
    expect(marker).not.toBe("t1");
    expect(marker.endsWith(":t1")).toBe(true);
    // A marker naming a sign-in this session never issued is sent with its own token, and its
    // 401 leaves the current sign-in: nothing is looked up or recorded per sign-in.
    const forged = marker.replace(/\d+:t1$/, "999999:other");
    const answer = await auth.fetch!("https://qdash.example/api/flows", { headers: { Authorization: `Bearer ${forged}` } });
    expect(answer.status).toBe(401);
    await auth.fetch!("https://qdash.example/api/flows", { headers: { Authorization: `Bearer ${marker}` } });
    expect(seen.map((request) => `${request.path} ${bearer(request) ?? ""}`)).toEqual([
      "/auth/login ",
      "/flows Bearer other",
      "/flows Bearer t1",
    ]);
    expect(await (auth.token as () => Promise<string>)()).toBe(marker);
    // A malformed marker is refused before anything is sent.
    const prefix = marker.slice(0, marker.lastIndexOf("1:t1"));
    await expect(
      auth.fetch!("https://qdash.example/api/flows", { headers: { Authorization: `Bearer ${prefix}nonsense` } }),
    ).rejects.toBeInstanceOf(QDashAuthError);
    expect(seen).toHaveLength(3);
  });

  it("shares the dropped sign-in with project-scoped sessions: one new sign-in for both", async () => {
    const { fetch, seen } = server({
      "POST /auth/login": [() => json({ access_token: "t1" }), () => json({ access_token: "t2" })],
      "GET /flows": [() => json({ detail: "expired" }, 401), () => json({ flows: [] }), () => json({ flows: [] })],
    });
    const { qdash } = session(fetch, password, { env });
    const scoped = qdash.withProject("p2");
    await expect(qdash.workflows.list()).rejects.toBeInstanceOf(QDashAuthError);
    await Promise.all([scoped.workflows.list(), qdash.workflows.list()]);
    expect(logins(seen)).toBe(2);
    expect(seen.slice(-2).map(bearer)).toEqual(["Bearer t2", "Bearer t2"]);
  });

  it("does not sign in or resend after a 401 with a configured API token", async () => {
    const { fetch, seen } = server({
      "GET /flows": [() => json({ detail: "revoked" }, 401), () => json({ detail: "revoked" }, 401)],
    });
    const { qdash } = session(fetch);
    await expect(qdash.workflows.list()).rejects.toBeInstanceOf(QDashAuthError);
    await expect(qdash.workflows.list()).rejects.toBeInstanceOf(QDashAuthError);
    expect(seen.map((request) => `${request.path} ${bearer(request)}`)).toEqual(["/flows Bearer token", "/flows Bearer token"]);
  });

  it("needs the password variable before anything is sent", async () => {
    const { fetch, seen } = server({});
    const { qdash } = session(fetch, password, { env: {} });
    await expect(qdash.workflows.list()).rejects.toThrow(QDashConfigError);
    expect(seen).toEqual([]);
  });
});

describe("wire serialization", () => {
  it("sends snake_case bodies as written: nested unions, nulls kept, undefined fields omitted", async () => {
    const { fetch, seen } = server({ "POST /calibration-pipelines/validate": [() => json({ valid: true, backend_name: "fake" })] });
    const { qdash } = session(fetch);
    const step = customOneQubit({
      step_name: "s",
      execution_mode: "manual",
      rounds: [["0"], ["1"]],
      tasks: [
        { name: "CheckT1", call_id: null, update_calibration_parameters: null, run: undefined },
        { name: "CheckRamsey", call_id: "fine", on_failure: "continue", input: { qubit_frequency: 5.1 } },
      ],
    });
    await qdash.pipelines.validate(
      { spec_version: 2, targets: { mux_ids: [1], exclude_qids: ["5"] }, steps: [step, { type: "FilterByStatus" }] },
      { chipId: "C", backendName: undefined },
    );
    expect(JSON.parse(seen[0]!.body)).toEqual({
      chip_id: "C",
      spec: {
        spec_version: 2,
        targets: { mux_ids: [1], exclude_qids: ["5"] },
        steps: [
          {
            type: "CustomOneQubit",
            step_name: "s",
            execution_mode: "manual",
            rounds: [["0"], ["1"]],
            tasks: [
              { name: "CheckT1", call_id: null, update_calibration_parameters: null },
              { name: "CheckRamsey", call_id: "fine", on_failure: "continue", input: { qubit_frequency: 5.1 } },
            ],
          },
          { type: "FilterByStatus" },
        ],
      },
    });
    expect(seen[0]!.headers.get("Content-Type")).toMatch(/^application\/json/);
  });

  it("passes snake_case query parameters of the generated client through", async () => {
    const urls: string[] = [];
    const fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      urls.push(new Request(input, init).url);
      return json({ items: [], total: 0, skip: 0, limit: 5 });
    };
    const { qdash } = session(fetch);
    await qdash.api.taskResult.listTaskResults({ chip_id: "C", qid: "6-7", limit: 5 });
    const url = new URL(urls[0]!);
    expect(Object.fromEntries(url.searchParams)).toEqual({ chip_id: "C", qid: "6-7", limit: "5" });
  });
});
