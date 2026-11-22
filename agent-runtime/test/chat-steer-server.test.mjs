import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

// The server runs in its own process with a mocked runtime whose sessions are
// real durable harnesses over one SQLite store and a scripted model.
test("steer and continue over HTTP: same open harness, owner and project checks, settled report", { timeout: 60_000 }, () => {
  const script = `
    import assert from "node:assert/strict";
    import { once } from "node:events";
    import { Server } from "node:http";
    import { mock } from "bun:test";
    import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
    import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
    import { createModels } from "@earendil-works/pi-ai/models";
    import { AssistantEntry, createRegistry, defineExtension, defineTool, Harness } from "@earendil-works/pi-durable";
    import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
    import { mkdtempSync, rmSync } from "node:fs";
    import { tmpdir } from "node:os";
    import { join } from "node:path";
    import { Type } from "typebox";
    import { CHAT_QUEUE_SETTINGS, readSteerReceipt } from "../src/chat-control.ts";

    let server;
    const listen = Server.prototype.listen;
    Server.prototype.listen = function () {
      server = this;
      return listen.call(this, 0, "127.0.0.1");
    };

    let toolStarted;
    let started = new Promise((resolve) => (toolStarted = resolve));
    let releaseTool;
    let released = new Promise((resolve) => (releaseTool = resolve));
    // The next call of the tool waits again until releaseTool().
    const arm = () => {
      started = new Promise((resolve) => (toolStarted = resolve));
      released = new Promise((resolve) => (releaseTool = resolve));
    };
    const waitTool = defineTool({
      name: "wait_calibration",
      description: "Waits (test)",
      parameters: Type.Object({}),
      execute: async (_args, _api, toolContext) => {
        toolStarted();
        await new Promise((resolve, reject) => {
          released.then(resolve);
          toolContext.abortSignal?.addEventListener("abort", () => reject(new Error("cancelled")), { once: true });
        });
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
    faux.setResponses([
      fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w1" })], { stopReason: "toolUse" }),
      (ctx) => fauxAssistantMessage(fauxText("Answer: " + lastUser(ctx))),
    ]);
    const dir = mkdtempSync(join(tmpdir(), "chat-steer-"));
    const path = join(dir, "session.sqlite");
    let submitGate;
    let submitEntered = () => {};
    let opens = 0;
    let openHarnesses = 0;
    const seenAuth = [];
    mock.module("../src/runtime.ts", () => ({
      BACKGROUND_CONTEXT,
      SharedRuntime: { create: async () => ({
        listToolNames: () => [],
        expandSkillCommand: (message) => message,
        storePath: () => path,
        steerReceipt: (owner, session, project, requestId) =>
          readSteerReceipt(path, project, requestId, BACKGROUND_CONTEXT),
        openSession: async (request, auth) => {
          opens++;
          seenAuth.push(auth.projectId);
          const registry = createRegistry();
          registry.install(defineExtension({ name: "t", tools: [waitTool] }));
          const harness = await Harness.open(await openNodeSqliteStorage(path), { models, registry, settings: { retry: { enabled: false }, ...CHAT_QUEUE_SETTINGS } }, BACKGROUND_CONTEXT);
          openHarnesses++;
          const root = await harness.root(BACKGROUND_CONTEXT, { agent: { model: { provider: model.provider, modelId: model.id } } });
          harness.resume();
          // While submitGate is set, the turn's own submit waits for it: its input is still being admitted.
          const conversation = new Proxy(root, {
            get: (target, key) => {
              if (key === "submit") {
                return async (...args) => {
                  if (submitGate) {
                    submitEntered();
                    await submitGate;
                  }
                  return target.submit(...args);
                };
              }
              const value = target[key];
              return typeof value === "function" ? value.bind(target) : value;
            },
          });
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
    const headers = (project, token = "user-token") => ({
      "Content-Type": "application/json",
      Authorization: "Bearer test-runtime-token",
      ...(token ? { "x-qdash-token": token } : {}),
      ...(project ? { "x-qdash-project-id": project } : {}),
    });
    const post = (path, body, h) => fetch(base + path, { method: "POST", headers: h, body: JSON.stringify(body) });
    const steer = (body, project = "p1", token) =>
      post("/chat/steer", { owner_id: "alice", conversation_id: "c1", request_id: "s1", message: "Use Q5", turn_request_id: "t1", ...body }, headers(project, token));

    try {
      // Nothing runs: refused, so the user sends it as a new message (under a new request ID:
      // a refused one is never admitted later).
      let response = await steer({ request_id: "s0" });
      assert.equal(response.status, 409);
      assert.deepEqual(await response.json(), { status: "rejected", reason: "idle" });

      const chat = await post("/chat", {
        owner_id: "alice", conversation_id: "c1", request_id: "t1", message: "Calibrate Q4",
        model: { provider: model.provider, name: model.id },
      }, headers("p1"));
      assert.equal(chat.status, 200);
      const body = chat.text();
      await started;

      // A second turn is still refused while one runs.
      response = await post("/chat", { owner_id: "alice", conversation_id: "c1", message: "again" }, headers("p1"));
      assert.equal(response.status, 409);

      assert.equal((await steer({}, "p1", null)).status, 401);
      assert.equal((await steer({ message: "  " })).status, 400);
      assert.equal((await steer({ request_id: "" })).status, 400);
      // A steer names the turn it was sent to.
      assert.equal((await steer({ turn_request_id: undefined })).status, 400);
      // A steer sent to another turn is not admitted by this one.
      response = await steer({ request_id: "s-other", turn_request_id: "t0" });
      assert.equal(response.status, 409);
      assert.deepEqual(await response.json(), { status: "rejected", reason: "idle" });
      response = await post("/chat/steer", { owner_id: "alice", conversation_id: "c1", request_id: "s1", message: "x" }, { "Content-Type": "application/json", "x-qdash-token": "t" });
      assert.equal(response.status, 401);
      // Another project's credentials cannot steer this run.
      response = await steer({}, "p2");
      assert.equal(response.status, 403);
      response = await steer({}, null);
      assert.equal(response.status, 403);
      // Another owner has nothing running under this conversation.
      response = await steer({ owner_id: "mallory" });
      assert.equal(response.status, 409);

      response = await steer({});
      assert.equal(response.status, 200);
      const queued = await response.json();
      assert.equal(queued.status, "queued");
      const again = await (await steer({})).json();
      assert.equal(again.submission_id, queued.submission_id);
      // The steer used the turn's open harness: no second open.
      assert.equal(opens, 1);
      assert.equal(openHarnesses, 1);

      releaseTool();
      const lines = (await body).trim().split("\\n").map(JSON.parse);
      const kinds = lines.map((line) => line.type);
      const steerAt = kinds.indexOf("steer");
      assert.ok(steerAt > kinds.indexOf("tool_end"), kinds.join(","));
      assert.ok(steerAt < kinds.indexOf("text_delta"), kinds.join(","));
      assert.deepEqual(
        { ...lines[steerAt], entry_id: undefined },
        { type: "steer", request_id: "s1", status: "applied", entry_id: undefined, text: "Use Q5", answer: "" },
      );
      const done = lines.at(-1);
      assert.equal(done.type, "done");
      assert.equal(done.text, "Answer: Use Q5");
      assert.match(done.entry_id, /^\\d+$/);
      assert.equal(lines.filter((line) => line.type === "steer").length, 1);
      assert.equal(openHarnesses, 0);

      // Retried after the turn: what happened to it, read from the durable store, not a refusal.
      response = await steer({});
      assert.equal(response.status, 200);
      const appliedReply = await response.json();
      assert.equal(appliedReply.status, "applied");
      assert.equal(appliedReply.entry_id, lines[steerAt].entry_id);
      // A new one is refused: nothing runs, and the store has never seen it.
      response = await steer({ request_id: "s2" });
      assert.equal(response.status, 409);
      assert.deepEqual(await response.json(), { status: "rejected", reason: "idle" });

      // Status only: read-only, scoped to the project the steer was sent from.
      const status = (body, project = "p1") =>
        post("/chat/steer/status", { owner_id: "alice", conversation_id: "c1", request_id: "s1", ...body }, headers(project));
      response = await status({});
      assert.equal(response.status, 200);
      assert.deepEqual(await response.json(), { status: "applied", submission_id: appliedReply.submission_id, entry_id: appliedReply.entry_id });
      // Another project learns nothing about it and cannot claim it, with or without a turn running.
      assert.equal((await status({}, "p2")).status, 403);
      assert.equal((await steer({}, "p2")).status, 403);
      assert.equal((await post("/chat/steer/status", { owner_id: "alice", conversation_id: "c1", request_id: "s1" }, headers("p1", null))).status, 401);
      response = await status({ request_id: "never" });
      assert.deepEqual(await response.json(), { status: "not_found" });
      assert.equal(openHarnesses, 0);

      // The run answered: nothing to continue, and nothing was opened for long.
      response = await post("/chat", {
        owner_id: "alice", conversation_id: "c1", request_id: "k1", continue: true,
        model: { provider: model.provider, name: model.id },
      }, headers("p1"));
      const refused = await response.json();
      assert.equal(response.status, 409, JSON.stringify(refused));
      assert.equal(refused.reason, "nothing_to_continue");
      response = await post("/chat", {
        owner_id: "alice", conversation_id: "c1", continue: true, approval: { id: "x", approve: true },
      }, headers("p1"));
      assert.equal(response.status, 400);
      assert.equal(openHarnesses, 0);

      // A model error, then continue: answered without a new user message; a retry recovers it.
      faux.appendResponses([
        fauxAssistantMessage([], { stopReason: "error", errorMessage: "HTTP 503" }),
        (ctx) => fauxAssistantMessage(fauxText("Continued: " + lastUser(ctx))),
      ]);
      const turn = { owner_id: "alice", conversation_id: "c1", model: { provider: model.provider, name: model.id } };
      const read = async (r) => (await r.text()).trim().split("\\n").map(JSON.parse);
      let out = await read(await post("/chat", { ...turn, request_id: "t2", message: "Plot it" }, headers("p1")));
      assert.equal(out.at(-1).type, "error");
      assert.match(out.at(-1).message, /model_error/);
      const calls = faux.state.callCount;
      out = await read(await post("/chat", { ...turn, request_id: "k2", continue: true }, headers("p1")));
      assert.equal(out.at(-1).type, "done", JSON.stringify(out));
      assert.equal(out.at(-1).text, "Continued: Plot it");
      const retried = await read(await post("/chat", { ...turn, request_id: "k2", continue: true }, headers("p1")));
      assert.deepEqual(retried.at(-1), out.at(-1));
      assert.equal(faux.state.callCount, calls + 1);
      // The retry carries the request ID of the earlier input: refused, not run as a continue.
      response = await post("/chat", { ...turn, request_id: "t2", continue: true }, headers("p1"));
      assert.equal(response.status, 409);

      // Stop after the steer was admitted, before the stream reported it: the store says
      // it was withdrawn. A status lookup that found nothing fences that request ID, so a
      // request still on its way cannot admit it after the chat was told it was not sent.
      arm();
      faux.appendResponses([
        fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w2" })], { stopReason: "toolUse" }),
        (ctx) => fauxAssistantMessage(fauxText("Late: " + lastUser(ctx))),
      ]);
      const stopTurn = post("/chat", { ...turn, request_id: "t3", message: "Slow one" }, headers("p1")).then(read);
      await started;
      response = await steer({ request_id: "s3", message: "Admitted then stopped", turn_request_id: "t3" });
      assert.equal((await response.json()).status, "queued");
      response = await status({ request_id: "s4" });
      assert.deepEqual(await response.json(), { status: "not_found" });
      // The fence lasts as long as the turn: many other lookups do not evict it.
      for (let i = 0; i < 1010; i++) {
        assert.equal((await status({ request_id: "flood-" + i }).then((r) => r.json())).status, "not_found");
      }
      response = await steer({ request_id: "s4", message: "Arrived after the lookup", turn_request_id: "t3" });
      assert.equal(response.status, 409);
      assert.deepEqual(await status({ request_id: "s4" }).then((r) => r.json()), { status: "not_found" });
      // A request ID refused while nothing ran is not admitted by a later turn either.
      response = await steer({ request_id: "s2", message: "Refused earlier" });
      assert.equal(response.status, 409);
      // Nor is a steer of an earlier turn that arrives late, never looked up.
      response = await steer({ request_id: "s6", message: "Sent during t1, delayed" });
      assert.equal(response.status, 409);
      assert.deepEqual(await status({ request_id: "s6" }).then((r) => r.json()), { status: "not_found" });
      response = await post("/chat/abort", { owner_id: "alice", conversation_id: "c1" }, headers("p1"));
      assert.equal(response.status, 200);
      const stopped = await stopTurn;
      assert.ok(stopped.some((line) => line.type === "steer" && line.request_id === "s3" && line.status === "withdrawn"), JSON.stringify(stopped));
      const withdrawn = await status({ request_id: "s3" }).then((r) => r.json());
      assert.equal(withdrawn.status, "withdrawn");
      assert.equal((await steer({ request_id: "s3", message: "Admitted then stopped", turn_request_id: "t3" }).then((r) => r.json())).status, "withdrawn");
      assert.equal(openHarnesses, 0);

      // Stop after the steer was placed: it stays applied, in the stream and in the store.
      arm();
      // The stopped turn left its answer unused: start this one's script afresh.
      faux.setResponses([
        fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w3" })], { stopReason: "toolUse" }),
        fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w4" })], { stopReason: "toolUse" }),
      ]);
      const placedTurn = post("/chat", { ...turn, request_id: "t4", message: "Two rounds" }, headers("p1")).then(read);
      await started;
      response = await steer({ request_id: "s5", message: "Placed then stopped", turn_request_id: "t4" });
      assert.equal((await response.json()).status, "queued");
      // Let the first round end, which places the steer; the next round waits.
      const releaseFirst = releaseTool;
      arm();
      releaseFirst();
      await started;
      response = await post("/chat/abort", { owner_id: "alice", conversation_id: "c1" }, headers("p1"));
      assert.equal(response.status, 200);
      const placedLines = await placedTurn;
      const placedSteer = placedLines.find((line) => line.type === "steer" && line.request_id === "s5");
      assert.equal(placedSteer?.status, "applied", JSON.stringify(placedLines));
      assert.ok(!placedLines.some((line) => line.type === "steer" && line.status === "withdrawn"));
      assert.notEqual(placedLines.at(-1).type, "done");
      assert.deepEqual(await status({ request_id: "s5" }).then((r) => r.json()), {
        status: "applied", submission_id: (await steer({ request_id: "s5", message: "Placed then stopped", turn_request_id: "t4" }).then((r) => r.json())).submission_id, entry_id: placedSteer.entry_id,
      });

      // Stop while the turn's own input is still being admitted: the stop is
      // not lost, the turn aborts once its input is in, and a steer sent
      // meanwhile waits for that and is never placed.
      arm();
      faux.setResponses([
        fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w5" })], { stopReason: "toolUse" }),
        (ctx) => fauxAssistantMessage(fauxText("Should not answer: " + lastUser(ctx))),
      ]);
      let openSubmit;
      submitGate = new Promise((resolve) => (openSubmit = resolve));
      const entered = new Promise((resolve) => (submitEntered = resolve));
      const early = post("/chat", { ...turn, request_id: "t5", message: "Stop me early" }, headers("p1")).then(read);
      await entered;
      let steerSettled = false;
      const earlySteer = steer({ request_id: "s7", message: "Too early", turn_request_id: "t5" }).then(async (r) => {
        steerSettled = true;
        return r.json();
      });
      response = await post("/chat/abort", { owner_id: "alice", conversation_id: "c1" }, headers("p1"));
      assert.equal(response.status, 200);
      await new Promise((resolve) => setTimeout(resolve, 50));
      assert.equal(steerSettled, false);
      submitGate = undefined;
      openSubmit();
      const earlyOut = await early;
      assert.equal(earlyOut.at(-1).type, "error", JSON.stringify(earlyOut));
      assert.match(earlyOut.at(-1).message, /aborted/);
      assert.ok(!earlyOut.some((line) => line.type === "done"));
      assert.notEqual((await earlySteer).status, "applied");
      assert.notEqual((await status({ request_id: "s7" }).then((r) => r.json())).status, "applied");
      assert.equal(openHarnesses, 0);

      // A store whose lock another connection holds: the lookup says it cannot tell (503), never not_found.
      const { DatabaseSync } = await import("node:sqlite");
      const holder = new DatabaseSync(path);
      try {
        holder.exec("BEGIN IMMEDIATE");
        const before = Date.now();
        response = await status({ request_id: "s5" });
        assert.equal(response.status, 503);
        assert.ok(Date.now() - before < 5000);
        response = await status({ request_id: "never-sent" });
        assert.equal(response.status, 503);
      } finally {
        holder.exec("ROLLBACK");
        holder.close();
      }
      assert.equal((await status({ request_id: "s5" }).then((r) => r.json())).status, "applied");
      assert.equal(openHarnesses, 0);
    } finally {
      server.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
      rmSync(dir, { recursive: true, force: true });
    }
  `;
  const result = spawnSync("bun", ["--eval", script], {
    cwd: new URL(".", import.meta.url),
    encoding: "utf8",
    timeout: 60_000,
  });
  assert.equal(result.status, 0, `${result.error ?? ""}\n${result.stdout}\n${result.stderr}`);
});
