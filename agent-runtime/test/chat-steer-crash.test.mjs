import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

// The server runs in its own process with a mocked runtime whose sessions are
// real durable harnesses over one SQLite store and a scripted model, opened as
// the real runtime opens them: scheduling paused until the server resumes it.
const serverScript = (path, phase) => `
  import assert from "node:assert/strict";
  import { once } from "node:events";
  import { Server } from "node:http";
  import { mock } from "bun:test";
  import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
  import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
  import { createModels } from "@earendil-works/pi-ai/models";
  import { AssistantEntry, createRegistry, defineExtension, defineTool, Harness, UserEntry } from "@earendil-works/pi-durable";
  import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
  import { Type } from "typebox";
  import { CHAT_QUEUE_SETTINGS, readSteerReceipt, steerRequestId } from "../src/chat-control.ts";

  const path = ${JSON.stringify(path)};
  const phase = ${JSON.stringify(phase)};
  let server;
  const listen = Server.prototype.listen;
  Server.prototype.listen = function () {
    server = this;
    return listen.call(this, 0, "127.0.0.1");
  };
  let toolStarted;
  const started = new Promise((resolve) => (toolStarted = resolve));
  const waitTool = defineTool({
    name: "wait_calibration",
    description: "Waits (test)",
    parameters: Type.Object({}),
    execute: async () => {
      toolStarted();
      // Before the crash the tool never finishes; after it, it finishes at once.
      if (phase === "before") await new Promise(() => {});
      return { output: [{ type: "text", text: "finished" }] };
    },
  });
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const lastUser = (ctx) => {
    const message = ctx.messages.filter((m) => m.role === "user").at(-1);
    return typeof message.content === "string" ? message.content : message.content.map((b) => b.text ?? "").join("");
  };
  const answer = (ctx) => fauxAssistantMessage(fauxText("Answer: " + lastUser(ctx)));
  faux.setResponses(
    phase === "before"
      ? [fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w1" })], { stopReason: "toolUse" })]
      : [answer, answer, answer],
  );
  let openHarnesses = 0;
  let lastHarness;
  mock.module("../src/runtime.ts", () => ({
    BACKGROUND_CONTEXT,
    SharedRuntime: { create: async () => ({
      listToolNames: () => [],
      storePath: () => path,
      steerReceipt: (owner, session, project, requestId) =>
        readSteerReceipt(path, project, requestId, BACKGROUND_CONTEXT),
      openSession: async () => {
        const registry = createRegistry();
        registry.install(defineExtension({ name: "t", tools: [waitTool] }));
        const harness = await Harness.open(await openNodeSqliteStorage(path), { models, registry, settings: { retry: { enabled: false }, ...CHAT_QUEUE_SETTINGS } }, BACKGROUND_CONTEXT);
        openHarnesses++;
        lastHarness = harness;
        const conversation = await harness.root(BACKGROUND_CONTEXT, { agent: { model: { provider: model.provider, modelId: model.id } } });
        // No resume here, as in runtime.ts: the server resumes once it watches.
        return { harness, conversation, writeTools: {}, close: async () => { await harness.close(BACKGROUND_CONTEXT); openHarnesses--; } };
      },
    }) },
    answerText: async (conversation, id) => {
      const entry = await conversation.commit((tx) => tx.entry(AssistantEntry, id), BACKGROUND_CONTEXT);
      return entry.model[0].content.filter((b) => b.type === "text").map((b) => b.text).join("");
    },
    pendingApproval: async () => undefined,
  }));
  process.env.CHAT_PING_MS = "0";
  process.env.CHAT_TIMEOUT_MS = "0";
  process.env.CHAT_WRAP_UP_MS = "0";
  process.env.AGENT_RUNTIME_TOKEN = "test-runtime-token";
  delete process.env.AGENT_RUNTIME_TOKEN_FILE;
  await import("../src/server.ts");
  if (!server.listening) await once(server, "listening");
  const base = "http://127.0.0.1:" + server.address().port;
  const headers = {
    "Content-Type": "application/json",
    Authorization: "Bearer test-runtime-token",
    "x-qdash-token": "user-token",
    "x-qdash-project-id": "p1",
  };
  const post = (route, body) => fetch(base + route, { method: "POST", headers, body: JSON.stringify(body) });
  const turn = { owner_id: "alice", conversation_id: "c1", model: { provider: model.provider, name: model.id } };

  if (phase === "before") {
    post("/chat", { ...turn, request_id: "t1", message: "Calibrate Q4" }).catch(() => {});
    await started;
    const response = await post("/chat/steer", { owner_id: "alice", conversation_id: "c1", request_id: "s1", message: "Use Q5", turn_request_id: "t1" });
    assert.equal((await response.json()).status, "queued");
    // The parent kills this process now, with the steer queued and the tool running.
    console.log("QUEUED");
    await new Promise(() => {});
  }

  // After the crash. The store still holds the steer queued: no run settled it.
  let reply = await post("/chat/steer/status", { owner_id: "alice", conversation_id: "c1", request_id: "s1" });
  assert.equal(reply.status, 200);
  assert.equal((await reply.json()).status, "queued");

  // The run that died is still the conversation's run: a continue is refused as
  // busy, before anything resumes it, and the steer stays queued.
  reply = await post("/chat", { ...turn, request_id: "k1", continue: true });
  assert.equal(reply.status, 409);
  assert.equal((await reply.json()).reason, "busy");
  assert.equal(openHarnesses, 0);
  reply = await post("/chat/steer/status", { owner_id: "alice", conversation_id: "c1", request_id: "s1" });
  assert.equal((await reply.json()).status, "queued");

  // The user sends a new message. Opening the conversation recovers the run that
  // died; it places the steer and answers it before the new message.
  const lines = (await (await post("/chat", { ...turn, request_id: "t2", message: "New question" })).text())
    .trim().split("\\n").map(JSON.parse);
  const steers = lines.filter((line) => line.type === "steer");
  assert.equal(steers.length, 1, JSON.stringify(lines));
  assert.equal(steers[0].request_id, "s1");
  assert.equal(steers[0].status, "applied");
  assert.equal(steers[0].text, "Use Q5");
  // Reported as landing before this request's message, not after it.
  assert.equal(steers[0].before_turn, true, JSON.stringify(steers[0]));
  const done = lines.at(-1);
  assert.equal(done.type, "done", JSON.stringify(lines));
  assert.equal(done.text, "Answer: New question");
  // The recovered run's answer to the steer streams before this turn's own
  // message, which the stream marks, so the chat keeps that answer with the
  // earlier turn instead of showing it after the new question.
  const kinds = lines.map((line) => line.type);
  const startAt = kinds.indexOf("turn_start");
  assert.equal(kinds.filter((kind) => kind === "turn_start").length, 1, JSON.stringify(lines));
  assert.ok(startAt > kinds.indexOf("steer"), JSON.stringify(lines));
  assert.equal(lines[startAt].answer, "Answer: Use Q5");
  const textBefore = lines.slice(0, startAt).filter((line) => line.type === "text_delta").map((line) => line.delta).join("");
  const textAfter = lines.slice(startAt).filter((line) => line.type === "text_delta").map((line) => line.delta).join("");
  assert.equal(textBefore, "Answer: Use Q5");
  assert.equal(textAfter, "Answer: New question");

  // The durable transcript agrees: the steer, then its answer, then the new message.
  reply = await post("/chat/steer/status", { owner_id: "alice", conversation_id: "c1", request_id: "s1" });
  const applied = await reply.json();
  assert.equal(applied.status, "applied");
  assert.equal(applied.entry_id, steers[0].entry_id);
  const storage = await openNodeSqliteStorage(path);
  try {
    const harness = await Harness.open(storage, { models, registry: createRegistry(), readOnly: true }, BACKGROUND_CONTEXT);
    try {
      const conversation = await harness.root(BACKGROUND_CONTEXT);
      const view = await conversation.context(BACKGROUND_CONTEXT);
      const order = view.entries
        .map((entry) => (steerRequestId(entry) ? "steer" : UserEntry.is(entry) ? "user:" + entry.model[0].content : entry.model?.[0]?.role))
        .filter((kind) => kind === "steer" || String(kind).startsWith("user:"));
      assert.deepEqual(order, ["user:Calibrate Q4", "steer", "user:New question"]);
    } finally {
      await harness.close(BACKGROUND_CONTEXT);
    }
  } finally {
    await storage.close(BACKGROUND_CONTEXT).catch(() => {});
  }
  assert.equal(openHarnesses, 0);
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
  console.log("RECOVERED");
`;

test("a steer queued when the runtime is killed is placed by the recovered run, reported before the next message", async () => {
  const dir = mkdtempSync(join(tmpdir(), "chat-steer-crash-"));
  const path = join(dir, "session.sqlite");
  const cwd = new URL(".", import.meta.url);
  // Outside the try, so a failure before the planned kill still ends the child.
  let before;
  let timer;
  try {
    before = spawn("bun", ["--eval", serverScript(path, "before")], { cwd, stdio: ["ignore", "pipe", "pipe"] });
    const child = before;
    let out = "";
    let err = "";
    child.stderr.on("data", (chunk) => (err += chunk));
    await new Promise((resolve, reject) => {
      timer = setTimeout(() => reject(new Error(`no QUEUED in time\n${out}\n${err}`)), 30_000);
      child.stdout.on("data", (chunk) => {
        out += chunk;
        if (out.includes("QUEUED")) resolve();
      });
      child.on("exit", (code) => reject(new Error(`exited ${code} before the steer was queued\n${out}\n${err}`)));
    });
    clearTimeout(timer);
    // A genuine crash: no handler runs, nothing settles the run or its steer.
    assert.equal(await killed(child), "SIGKILL");

    const after = spawnSync("bun", ["--eval", serverScript(path, "after")], { cwd, encoding: "utf8", timeout: 60_000 });
    assert.equal(after.status, 0, `${after.error ?? ""}\n${after.stdout}\n${after.stderr}`);
    assert.match(after.stdout, /RECOVERED/);
  } finally {
    clearTimeout(timer);
    // A child still running (the test failed before its planned kill) keeps the
    // store, a port, and the runner's pipes open: end it before cleaning up.
    if (before && before.exitCode === null && before.signalCode === null) await killed(before);
    rmSync(dir, { recursive: true, force: true });
  }
});

/** Kill a child with SIGKILL and wait until it has exited; the signal it exited with. */
function killed(child) {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve(child.signalCode);
  const exited = new Promise((resolve) => child.once("exit", (_code, signal) => resolve(signal)));
  child.kill("SIGKILL");
  return exited;
}
