import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

// The server runs in its own process with a mocked runtime whose stores are real
// SQLite durable harnesses, opened by store and conversation as runtime.ts opens
// them, with a scripted model.
test("branch over HTTP: fork, branch chat, one writer per store, exact steer and stop, delete", { timeout: 90_000 }, () => {
  const script = `
    import assert from "node:assert/strict";
    import { existsSync, mkdtempSync, rmSync } from "node:fs";
    import { once } from "node:events";
    import { Server } from "node:http";
    import { tmpdir } from "node:os";
    import { join } from "node:path";
    import { mock } from "bun:test";
    import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
    import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
    import { createModels } from "@earendil-works/pi-ai/models";
    import { AssistantEntry, createRegistry, defineExtension, defineTool, Harness, ROOT_CONVERSATION_ID, UserEntry } from "@earendil-works/pi-durable";
    import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
    import { Type } from "typebox";
    import { BranchError, branchFrom, openBranch } from "../src/branch.ts";
    import { CHAT_QUEUE_SETTINGS, readSteerReceipt, steerRequestId } from "../src/chat-control.ts";
    import { removeStore } from "../src/store-identity.ts";

    let server;
    const listen = Server.prototype.listen;
    Server.prototype.listen = function () {
      server = this;
      return listen.call(this, 0, "127.0.0.1");
    };

    let toolStarted;
    let started;
    let releaseTool;
    let released;
    const arm = () => {
      started = new Promise((resolve) => (toolStarted = resolve));
      released = new Promise((resolve) => (releaseTool = resolve));
    };
    arm();
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
    const text = (message) => typeof message.content === "string" ? message.content : message.content.map((b) => b.text ?? "").join("");
    let calls = 0;
    // A message starting with WAIT calls the waiting tool first; anything else is answered at once.
    const reply = (ctx) => {
      const last = ctx.messages.at(-1);
      const user = text(ctx.messages.filter((m) => m.role === "user").at(-1));
      if (last.role === "user" && user.startsWith("WAIT")) {
        return fauxAssistantMessage([fauxToolCall("wait_calibration", {}, { id: "w" + ++calls })], { stopReason: "toolUse" });
      }
      return fauxAssistantMessage(fauxText("Answer: " + user));
    };
    faux.setResponses(Array.from({ length: 100 }, () => reply));

    const dir = mkdtempSync(join(tmpdir(), "branch-server-"));
    const pathOf = (owner, store) => join(dir, owner + "-" + store + ".sqlite");
    let openHarnesses = 0;
    const seenAuth = [];
    const open = async (owner, store) => {
      const registry = createRegistry();
      registry.install(defineExtension({ name: "t", tools: [waitTool] }));
      const harness = await Harness.open(await openNodeSqliteStorage(pathOf(owner, store)), { models, registry, settings: { retry: { enabled: false }, ...CHAT_QUEUE_SETTINGS } }, BACKGROUND_CONTEXT);
      openHarnesses++;
      return { harness, close: async () => { await harness.close(BACKGROUND_CONTEXT); openHarnesses--; } };
    };
    mock.module("../src/runtime.ts", () => ({
      BACKGROUND_CONTEXT,
      SharedRuntime: { create: async () => ({
        listToolNames: () => [],
        storePath: pathOf,
        steerReceipt: (owner, session, project, requestId, target = {}) =>
          readSteerReceipt(pathOf(owner, target.storeSessionId ?? session), project, requestId, BACKGROUND_CONTEXT, target.conversationId ?? ROOT_CONVERSATION_ID),
        openSession: async (request, auth) => {
          seenAuth.push(auth.projectId);
          const { harness, close } = await open(request.ownerId, request.storeSessionId ?? request.sessionId);
          try {
            const agent = { model: { provider: model.provider, modelId: model.id } };
            const conversation = request.conversationId === undefined
              ? await harness.root(BACKGROUND_CONTEXT, { agent })
              : await openBranch(harness, request.conversationId, BACKGROUND_CONTEXT);
            await conversation.configure(agent, BACKGROUND_CONTEXT);
            return { harness, conversation, writeTools: {}, close };
          } catch (error) {
            await close();
            throw error;
          }
        },
        forkSession: async (request, auth) => {
          seenAuth.push(auth.projectId);
          if (!existsSync(pathOf(request.ownerId, request.storeSessionId))) throw new BranchError("store_not_found", "the chat's store was not found");
          const { harness, close } = await open(request.ownerId, request.storeSessionId);
          try {
            const source = request.sourceConversationId === undefined
              ? await harness.conversation(ROOT_CONVERSATION_ID, BACKGROUND_CONTEXT)
              : await openBranch(harness, request.sourceConversationId, BACKGROUND_CONTEXT);
            const result = await branchFrom(harness, source, request.at, request.targetSessionId, BACKGROUND_CONTEXT);
            assert.equal((await harness.inspect(BACKGROUND_CONTEXT)).scheduling, "paused");
            return result;
          } finally {
            await close();
          }
        },
        deleteSessionState: async (owner, store, generation) => removeStore(pathOf(owner, store), generation).outcome,
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
    const headers = (project = "p1", token = "user-token") => ({
      "Content-Type": "application/json",
      Authorization: "Bearer test-runtime-token",
      ...(token ? { "x-qdash-token": token } : {}),
      ...(project ? { "x-qdash-project-id": project } : {}),
    });
    const post = (path, body, h = headers()) => fetch(base + path, { method: "POST", headers: h, body: JSON.stringify(body) });
    const lines = async (response) => (await response.text()).trim().split("\\n").filter(Boolean).map(JSON.parse);
    const turn = { owner_id: "alice", model: { provider: model.provider, name: model.id } };
    const root = { ...turn, conversation_id: "c1" };
    const chat = async (body) => {
      const response = await post("/chat", body);
      assert.equal(response.status, 200, await response.clone().text());
      const out = await lines(response);
      return { out, done: out.find((line) => line.type === "done"), error: out.find((line) => line.type === "error") };
    };
    const branchRequest = (body, h) => post("/chat/branch", { owner_id: "alice", store_session_id: "c1", ...body }, h);
    // The users' messages a conversation of a store holds, read without a writer.
    const users = async (store, conversationId) => {
      const storage = await openNodeSqliteStorage(pathOf("alice", store));
      const harness = await Harness.open(storage, { models, registry: createRegistry(), readOnly: true }, BACKGROUND_CONTEXT);
      try {
        const conversation = await harness.conversation(conversationId, BACKGROUND_CONTEXT);
        const view = await conversation.context(BACKGROUND_CONTEXT);
        return view.entries
          .filter((entry) => UserEntry.is(entry) || steerRequestId(entry))
          .map((entry) => text(entry.model[0]));
      } finally {
        await harness.close(BACKGROUND_CONTEXT);
      }
    };

    try {
      const q1 = await chat({ ...root, request_id: "t1", message: "Q1" });
      assert.equal(q1.done.text, "Answer: Q1");
      const e1 = q1.done.entry_id;
      const q2 = await chat({ ...root, request_id: "t2", message: "Q2" });
      const e2 = q2.done.entry_id;

      // Malformed, unauthenticated, and unknown-store requests are refused before any store is opened.
      let response = await branchRequest({ entry_id: "abc", target_session_id: "b1" });
      assert.equal(response.status, 400);
      response = await branchRequest({ entry_id: e1, target_session_id: "b1" }, headers("p1", null));
      assert.equal(response.status, 401);
      response = await branchRequest({ store_session_id: "nope", entry_id: e1, target_session_id: "b1" });
      assert.equal(response.status, 404);
      assert.equal((await response.json()).reason, "store_not_found");
      assert.equal(existsSync(pathOf("alice", "nope")), false);
      // Another owner's store of the same name is another store.
      response = await branchRequest({ owner_id: "mallory", entry_id: e1, target_session_id: "b1" });
      assert.equal(response.status, 404);

      // Branch at the first answer; the same request again returns the same branch.
      response = await branchRequest({ entry_id: e1, target_session_id: "b1" });
      assert.equal(response.status, 200);
      const created = await response.json();
      assert.equal(created.created, true);
      const b1 = created.conversation_id;
      response = await branchRequest({ entry_id: e1, target_session_id: "b1" });
      assert.deepEqual(await response.json(), { conversation_id: b1, created: false });
      // The same target from another answer conflicts.
      response = await branchRequest({ entry_id: e2, target_session_id: "b1" });
      assert.equal(response.status, 409);
      assert.equal((await response.json()).reason, "conflict");
      // The user's message is not an answer.
      const userEntry = String(Number(e1) - 1);
      response = await branchRequest({ entry_id: userEntry, target_session_id: "bx" });
      assert.equal(response.status, 409);
      assert.equal((await response.json()).reason, "not_final_answer");

      // Chat on the branch: it continues from Q1/A1, the root keeps Q2.
      const branch = { ...turn, conversation_id: "b1", store_session_id: "c1", store_conversation_id: b1 };
      const qb = await chat({ ...branch, request_id: "tb1", message: "QB" });
      assert.equal(qb.done.text, "Answer: QB");
      assert.deepEqual(await users("c1", Number(b1)), ["Q1", "QB"]);
      assert.deepEqual(await users("c1", ROOT_CONVERSATION_ID), ["Q1", "Q2"]);
      // A branch ID the store did not fork is refused, not opened.
      response = await post("/chat", { ...branch, store_conversation_id: "999", request_id: "x", message: "?" });
      assert.equal(response.status, 404);
      response = await post("/chat", { ...branch, store_conversation_id: "x1", request_id: "x", message: "?" });
      assert.equal(response.status, 400);

      // The root runs: the store has one writer, and requests about the branch never reach the root's turn.
      arm();
      const running = post("/chat", { ...root, request_id: "t3", message: "WAIT root" });
      await started;
      const branchRef = { owner_id: "alice", conversation_id: "b1", store_session_id: "c1", store_conversation_id: b1 };
      response = await post("/chat/steer", { ...branchRef, request_id: "sb0", message: "to the branch", turn_request_id: "t3" });
      assert.equal(response.status, 409);
      assert.deepEqual(await response.json(), { status: "rejected", reason: "idle" });
      response = await post("/chat/abort", branchRef);
      assert.equal(response.status, 404);
      response = await post("/chat", { ...branch, request_id: "tb2", message: "QB2" });
      assert.equal(response.status, 409);
      assert.equal((await response.json()).reason, "store_busy");
      response = await branchRequest({ entry_id: e2, target_session_id: "b2" });
      assert.equal(response.status, 409);
      assert.equal((await response.json()).reason, "busy");
      response = await fetch(base + "/session", { method: "DELETE", headers: headers(), body: JSON.stringify({ owner_id: "alice", conversation_id: "c1" }) });
      assert.equal(response.status, 409);
      // The root's own steer still reaches it.
      response = await post("/chat/steer", { owner_id: "alice", conversation_id: "c1", request_id: "sr1", message: "Use Q5", turn_request_id: "t3" });
      assert.equal((await response.json()).status, "queued");
      // Its receipt is the root's: the branch has no steer of that ID.
      response = await post("/chat/steer/status", { ...branchRef, request_id: "sr1" });
      assert.deepEqual(await response.json(), { status: "not_found" });
      releaseTool();
      const rootOut = await lines(await running);
      assert.equal(rootOut.at(-1).text, "Answer: Use Q5");
      assert.deepEqual(await users("c1", ROOT_CONVERSATION_ID), ["Q1", "Q2", "WAIT root", "Use Q5"]);
      assert.deepEqual(await users("c1", Number(b1)), ["Q1", "QB"]);
      response = await post("/chat/steer/status", { owner_id: "alice", conversation_id: "c1", request_id: "sr1" });
      assert.equal((await response.json()).status, "applied");

      // Steer, stop, status, and continue on the branch itself.
      arm();
      const branchRun = post("/chat", { ...branch, request_id: "tb3", message: "WAIT branch" });
      await started;
      response = await post("/chat/steer", { ...branchRef, request_id: "sb1", message: "Use Q7", turn_request_id: "tb3" }, headers("p2"));
      assert.equal(response.status, 403);
      response = await post("/chat/steer", { owner_id: "alice", conversation_id: "c1", request_id: "sr2", message: "to the root", turn_request_id: "tb3" });
      assert.deepEqual(await response.json(), { status: "rejected", reason: "idle" });
      response = await post("/chat/abort", { owner_id: "alice", conversation_id: "c1" });
      assert.equal(response.status, 404);
      response = await post("/chat/steer", { ...branchRef, request_id: "sb1", message: "Use Q7", turn_request_id: "tb3" });
      assert.equal((await response.json()).status, "queued");
      releaseTool();
      const branchOut = await lines(await branchRun);
      const placed = branchOut.find((line) => line.type === "steer");
      assert.equal(placed.request_id, "sb1");
      assert.equal(branchOut.at(-1).text, "Answer: Use Q7");
      response = await post("/chat/steer/status", { ...branchRef, request_id: "sb1" });
      const applied = await response.json();
      assert.equal(applied.status, "applied");
      assert.equal(applied.entry_id, placed.entry_id);
      response = await post("/chat/steer/status", { owner_id: "alice", conversation_id: "c1", request_id: "sb1" });
      assert.deepEqual(await response.json(), { status: "not_found" });

      arm();
      const stopped = post("/chat", { ...branch, request_id: "tb4", message: "WAIT again" });
      await started;
      response = await post("/chat/abort", branchRef);
      assert.equal(response.status, 200);
      const stoppedOut = await lines(await stopped);
      assert.equal(stoppedOut.at(-1).type, "error");
      const continued = await chat({ ...branch, request_id: "tb5", continue: true });
      assert.equal(continued.done.text, "Answer: WAIT again");
      assert.deepEqual(await users("c1", Number(b1)), ["Q1", "QB", "WAIT branch", "Use Q7", "WAIT again"]);

      // A branch of the branch, at an answer of its own.
      response = await branchRequest({ source_conversation_id: b1, entry_id: qb.done.entry_id, target_session_id: "b3" });
      assert.equal(response.status, 200);
      const b3 = (await response.json()).conversation_id;
      const q3 = await chat({ ...turn, conversation_id: "b3", store_session_id: "c1", store_conversation_id: b3, request_id: "t4", message: "Q3" });
      assert.equal(q3.done.text, "Answer: Q3");
      assert.deepEqual(await users("c1", Number(b3)), ["Q1", "QB", "Q3"]);

      // The runtime dies mid-run on the branch: after a restart nothing in
      // memory holds the store, only the store itself says the run is unfinished.
      arm();
      {
        const { harness, close } = await open("alice", "c1");
        const conversation = await openBranch(harness, Number(b1), BACKGROUND_CONTEXT);
        await conversation.configure({ model: { provider: model.provider, modelId: model.id } }, BACKGROUND_CONTEXT);
        await conversation.submit({ type: "input", content: "WAIT crashed" }, BACKGROUND_CONTEXT);
        await started;
        await close();
      }
      // A sibling's turn is refused before it resumes the store, so the
      // branch's recovered run never runs beside it, and writes nothing.
      const rootBefore = await users("c1", ROOT_CONVERSATION_ID);
      response = await post("/chat", { ...root, request_id: "t5", message: "Q5" });
      assert.equal(response.status, 409);
      assert.equal((await response.json()).reason, "store_busy");
      response = await post("/chat", { ...turn, conversation_id: "b3", store_session_id: "c1", store_conversation_id: b3, request_id: "t6", message: "Q6" });
      assert.equal(response.status, 409);
      assert.equal((await response.json()).reason, "store_busy");
      assert.deepEqual(await users("c1", ROOT_CONVERSATION_ID), rootBefore);
      response = await branchRequest({ entry_id: e2, target_session_id: "b4" });
      assert.equal(response.status, 409);
      assert.equal((await response.json()).reason, "busy");
      // The branch's own next request recovers its run first, then answers.
      releaseTool();
      const recovered = await chat({ ...branch, request_id: "tb6", message: "QB6" });
      assert.equal(recovered.done.text, "Answer: QB6");
      assert.deepEqual((await users("c1", Number(b1))).slice(-2), ["WAIT crashed", "QB6"]);
      // Then the store is free again.
      const q5 = await chat({ ...root, request_id: "t5", message: "Q5" });
      assert.equal(q5.done.text, "Answer: Q5");

      // Every request used the caller's own credentials.
      assert.ok(seenAuth.every((project) => project === "p1"), JSON.stringify(seenAuth));
      assert.equal(openHarnesses, 0);
      const health = await (await fetch(base + "/health")).json();
      assert.equal(health.running, 0);

      // Deleting the store removes it; the API calls this once no chat session uses it.
      response = await fetch(base + "/session", { method: "DELETE", headers: headers(), body: JSON.stringify({ owner_id: "alice", conversation_id: "b1", store_session_id: "c1" }) });
      assert.equal(response.status, 200);
      assert.equal(existsSync(pathOf("alice", "c1")), false);
    } finally {
      server.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
      rmSync(dir, { recursive: true, force: true });
    }
    console.log("BRANCHED");
  `;
  const result = spawnSync("bun", ["--eval", script], {
    cwd: new URL(".", import.meta.url),
    encoding: "utf8",
    timeout: 80_000,
  });
  assert.equal(result.status, 0, `${result.error ?? ""}\n${result.stdout}\n${result.stderr}`);
  assert.match(result.stdout, /BRANCHED/);
});
