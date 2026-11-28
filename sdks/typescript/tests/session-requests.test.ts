import { describe, expect, it } from "vitest";

import {
  QDash,
  QDashAuthError,
  QDashNotFoundError,
  QDashPreflightError,
  QDashTransportError,
  QDashValidationError,
  type QDashSessionOptions,
} from "../src/index.js";

const BASE = "https://qdash.example/api";

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

interface Seen {
  method: string;
  path: string;
  search: URLSearchParams;
  headers: Headers;
  body: string;
}

function session(answer: (seen: Seen) => Response | Promise<Response>, options: QDashSessionOptions = {}) {
  const seen: Seen[] = [];
  const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(input, init);
    const url = new URL(request.url);
    const entry = {
      method: request.method,
      path: url.pathname.replace(/^\/api/, ""),
      search: url.searchParams,
      headers: request.headers,
      body: await request.text(),
    };
    seen.push(entry);
    return answer(entry);
  };
  const sleeps: number[] = [];
  const qdash = new QDash(
    { baseUrl: BASE, apiToken: "tok", projectId: "p-1", readAttempts: 3 },
    { fetch, sleep: async (ms) => void sleeps.push(ms), ...options },
  );
  return { qdash, seen, sleeps };
}

describe("QDash.read and QDash.send", () => {
  it("read sends a generated GET again after a transient status and raises the SDK's errors", async () => {
    let calls = 0;
    const { qdash, sleeps } = session(() => (++calls < 3 ? json({ detail: "busy" }, 503) : json({ chips: [], total: 0 })));
    await expect(qdash.read((o) => qdash.api.chip.listChips(o))).resolves.toEqual({ chips: [], total: 0 });
    expect(calls).toBe(3);
    expect(sleeps).toHaveLength(2);
    const missing = session(() => json({ detail: "no chip" }, 404));
    await expect(missing.qdash.read((o) => missing.qdash.api.chip.getChip({ chip_id: "X" }, o))).rejects.toBeInstanceOf(QDashNotFoundError);
    expect(missing.seen).toHaveLength(1);
  });

  it("send sends a call once and raises the SDK's errors", async () => {
    const { qdash, seen } = session(() => json({ detail: "busy" }, 503));
    await expect(qdash.send((o) => qdash.api.forum.createForumPost({ category: "general", title: "t", content: "c" }, o))).rejects.toMatchObject({ statusCode: 503 });
    expect(seen).toHaveLength(1);
  });

  it("a caller's abort rejects with its reason and is not retried", async () => {
    const controller = new AbortController();
    const { qdash, seen } = session(() => {
      controller.abort(new Error("stop"));
      return json({ detail: "busy" }, 503);
    });
    await expect(qdash.read((o) => qdash.api.chip.listChips(o), { signal: controller.signal })).rejects.toThrow("stop");
    expect(seen).toHaveLength(1);
  });
});

describe("QDash.fetch", () => {
  it("sends the session's auth, project and headers, with list queries repeated", async () => {
    const { qdash, seen } = session(() => new Response("bytes", { headers: { "Content-Type": "image/png" } }));
    const response = await qdash.fetch("/executions/figure", { query: { path: "/a.png", status: ["x", "y"], skip: undefined, n: null }, headers: { Accept: "*/*" } });
    expect(await response.text()).toBe("bytes");
    expect(seen[0]!.path).toBe("/executions/figure");
    expect(seen[0]!.search.get("path")).toBe("/a.png");
    expect(seen[0]!.search.getAll("status")).toEqual(["x", "y"]);
    expect(seen[0]!.search.has("skip")).toBe(false);
    expect(seen[0]!.headers.get("authorization")).toBe("Bearer tok");
    expect(seen[0]!.headers.get("x-project-id")).toBe("p-1");
    expect(seen[0]!.headers.get("accept")).toBe("*/*");
    expect(seen[0]!.headers.get("user-agent")).toMatch(/^qdash-sdk-ts\//);
  });

  it("a withProject session sends its own project", async () => {
    const { qdash, seen } = session(() => json({}));
    await qdash.withProject("p-2").fetch("x");
    expect(seen[0]!.headers.get("x-project-id")).toBe("p-2");
  });

  it("retries GETs, sends other methods once, and raises the SDK error with the body", async () => {
    let gets = 0;
    const { qdash, seen } = session(({ method }) =>
      method === "GET" ? (++gets < 2 ? json({ detail: "busy" }, 429, { "Retry-After": "0" }) : json({ ok: true })) : json({ detail: [{ loc: ["body", "x"], msg: "bad" }] }, 422),
    );
    expect(await (await qdash.fetch("/r")).json()).toEqual({ ok: true });
    expect(gets).toBe(2);
    await expect(qdash.fetch("/w", { method: "POST", json: { x: 1 } })).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(QDashValidationError);
      expect((error as QDashValidationError).payload).toEqual({ detail: [{ loc: ["body", "x"], msg: "bad" }] });
      expect((error as Error).message).toMatch(/x: bad$/);
      return true;
    });
    const post = seen.filter((entry) => entry.method === "POST");
    expect(post).toHaveLength(1);
    expect(post[0]!.body).toBe('{"x":1}');
    expect(post[0]!.headers.get("content-type")).toBe("application/json");
  });

  it("maps a 401, a failed connection and a bad path", async () => {
    const auth = session(() => json({ detail: "nope" }, 401));
    await expect(auth.qdash.fetch("/r")).rejects.toBeInstanceOf(QDashAuthError);
    const down = session(() => {
      throw new TypeError("fetch failed");
    });
    await expect(down.qdash.fetch("/r")).rejects.toBeInstanceOf(QDashTransportError);
    expect(down.seen).toHaveLength(3);
    const { qdash, seen } = session(() => json({}));
    await expect(qdash.fetch("https://elsewhere.example/x")).rejects.toThrow(TypeError);
    await expect(qdash.fetch("//elsewhere.example/x")).rejects.toThrow(TypeError);
    await expect(qdash.fetch("/x", { headers: { Authorization: "Bearer other" } })).rejects.toThrow(/set by the session/);
    await expect(qdash.fetch("/x", { headers: { "X-Project-Id": "other" } })).rejects.toThrow(/set by the session/);
    expect(seen).toHaveLength(0);
  });
});

describe("QDash.preflightCalibrationSession", () => {
  it("passes for the user's session on the chip, reading only the list", async () => {
    const { qdash, seen } = session(() => json({ items: [{ calibration_session_id: "cs-1", chip_id: "C" }], has_more: false }));
    await qdash.preflightCalibrationSession("cs-1", "C");
    expect(seen.map((entry) => `${entry.method} ${entry.path}`)).toEqual(["GET /calibration-sessions"]);
    expect(seen[0]!.search.get("mine")).toBe("true");
    expect(seen[0]!.search.get("chip_id")).toBe("C");
  });

  it("fails with QDashPreflightError when the session is missing, on another chip or the list fails", async () => {
    const missing = session(() => json({ items: [], has_more: false }));
    await expect(missing.qdash.preflightCalibrationSession("cs-1", "C")).rejects.toBeInstanceOf(QDashPreflightError);
    const other = session(() => json({ items: [{ calibration_session_id: "cs-1", chip_id: "D" }], has_more: false }));
    await expect(other.qdash.preflightCalibrationSession("cs-1", "C")).rejects.toBeInstanceOf(QDashPreflightError);
    const failing = session(() => json({ detail: "down" }, 404));
    await expect(failing.qdash.preflightCalibrationSession("cs-1", "C")).rejects.toSatisfy(
      (error: unknown) => error instanceof QDashPreflightError && (error as Error).cause instanceof QDashNotFoundError,
    );
    const { qdash, seen } = session(() => json({}));
    await expect(qdash.preflightCalibrationSession("  ", "C")).rejects.toBeInstanceOf(QDashPreflightError);
    expect(seen).toHaveLength(0);
  });
});

describe("generated list queries and text responses", () => {
  const rawQuery = (seen: Seen) => seen.search.toString();

  it("repeats every optional list query parameter on the wire, never one JSON text", async () => {
    const { qdash, seen } = session((entry) =>
      entry.path === "/agent-sessions" ? json({ sessions: [] }) : json({ items: [], total: 0, has_more: false }),
    );
    await qdash.read((o) => qdash.api.agentSession.listAgentSessions({ chip_id: "C", status: ["active", "waiting_for_human"], limit: 5 }, o));
    await qdash.read((o) =>
      qdash.api.calibrationSession.listCalibrationSessions({ status: ["open", "closed"], origin: ["manual", "automatic"] }, o),
    );
    await qdash.read((o) => qdash.api.chip.listChipQubits({ chip_id: "C", qids: ["0", "1"] }, o));
    await qdash.read((o) => qdash.api.provenance.getRecentChanges({ parameter_names: ["t1", "t2_echo"], limit: 3 }, o));
    await qdash.read((o) => qdash.api.provenance.getDegradationTrends({ parameter_names: ["t1", "t2_echo"] }, o));

    expect(seen.map((entry) => `${entry.path}?${rawQuery(entry)}`)).toEqual([
      "/agent-sessions?chip_id=C&status=active&status=waiting_for_human&limit=5",
      "/calibration-sessions?status=open&status=closed&origin=manual&origin=automatic",
      "/chips/C/qubits?qids=0&qids=1",
      "/provenance/changes?limit=3&parameter_names=t1&parameter_names=t2_echo",
      "/provenance/degradation-trends?parameter_names=t1&parameter_names=t2_echo",
    ]);
    for (const entry of seen) {
      expect(entry.headers.get("X-Project-Id")).toBe("p-1");
      expect(rawQuery(entry)).not.toContain("%5B");
    }
  });

  it("sends a single list value as one parameter and leaves out an empty or absent list", async () => {
    const { qdash, seen } = session(() => json({ sessions: [] }));
    await qdash.read((o) => qdash.api.agentSession.listAgentSessions({ status: ["active"] }, o));
    await qdash.read((o) => qdash.api.agentSession.listAgentSessions({ status: [] }, o));
    await qdash.read((o) => qdash.api.agentSession.listAgentSessions({}, o));
    expect(seen.map(rawQuery)).toEqual(["status=active", "", ""]);
  });

  it("reads the task knowledge Markdown as text, even when it looks like JSON", async () => {
    const markdown = "# CheckT1\n\n![fig](data:image/png;base64,AAA=)\n";
    const { qdash, seen } = session((entry) =>
      new Response(entry.path.endsWith("/CheckT1/knowledge/markdown") ? markdown : "{\"a\": 1}", {
        headers: { "Content-Type": "text/markdown; charset=utf-8" },
      }),
    );
    await expect(qdash.read((o) => qdash.api.task.getTaskKnowledgeMarkdown({ task_name: "CheckT1" }, o))).resolves.toBe(markdown);
    await expect(qdash.read((o) => qdash.api.task.getTaskKnowledgeMarkdown({ task_name: "Other" }, o))).resolves.toBe("{\"a\": 1}");
    expect(seen[0]?.path).toBe("/tasks/CheckT1/knowledge/markdown");
  });
});
