/**
 * QDash chat runs pi-qdash's waiting tools one poll per durable wake, parked
 * between polls (durable-waits.ts). These tests drive the real pi-qdash tools
 * through a Harness against a QDash fixture and check that a wait parks,
 * wakes, times out, stops, survives a restart against its original deadline,
 * fails as the pi CLI fails, and ends with the pi CLI's result.
 */

import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";
import { setTimeout as delay } from "node:timers/promises";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import { createRegistry, Harness, MemoryStorage, ToolResultEntry } from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import qdashExtension from "@oqtopus-team/pi-qdash/extensions/qdash.ts";

import { createQDashConnection } from "../src/auth.ts";
import { toNdjsonEvents } from "../src/events.ts";
import { ViewEventStream } from "../src/view-events.ts";
import { toolPolicyExtension } from "../src/codemode.ts";
import { buildQDashExtension } from "../src/durable-tools.ts";

const context = BACKGROUND_CONTEXT;

/** JSON bodies per path, served in order; the last one repeats. Other paths are 404. */
const routes = new Map();
/** Milliseconds a path's response is held back, to stop a wait while its poll is in flight. */
const delays = new Map();
const requests = [];
let server;
let connection;
let otherConnection;
let savedBaseUrl;

function serve(path, ...responses) {
  routes.set(path, responses);
}

before(async () => {
  server = createServer(async (req, res) => {
    if (delays.has(req.url)) await delay(delays.get(req.url));
    requests.push({ method: req.method, path: req.url, token: req.headers.authorization, project: req.headers["x-project-id"] });
    const queue = routes.get(req.url);
    const body = queue === undefined ? undefined : queue.length > 1 ? queue.shift() : queue[0];
    res.writeHead(body === undefined ? 404 : 200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(body ?? { detail: "not found" }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  savedBaseUrl = process.env.QDASH_BASE_URL;
  process.env.QDASH_BASE_URL = `http://127.0.0.1:${server.address().port}`;
  connection = await createQDashConnection({ accessToken: "alice-token", projectId: "alice-project" });
  otherConnection = await createQDashConnection({ accessToken: "bob-token", projectId: "bob-project" });
});

after(async () => {
  await connection.close();
  await otherConnection.close();
  if (savedBaseUrl === undefined) delete process.env.QDASH_BASE_URL;
  else process.env.QDASH_BASE_URL = savedBaseUrl;
  const closed = new Promise((resolve) => server.close(resolve));
  server.closeAllConnections();
  await closed;
});

function installedTools() {
  const tools = new Map();
  qdashExtension({
    registerTool: (definition) => tools.set(definition.name, { definition }),
    registerCommand() {},
    on() {},
  });
  return [{ tools }];
}

const extensions = installedTools();

function execution(status, extra = {}) {
  return { execution_id: "e1", name: "flow", status, chip_id: "A", task: [], note: {}, ...extra };
}

/** The pi CLI's result for the same call: the pi-qdash tool running the client's own polling loop. */
async function cliResult(name, args) {
  const tool = extensions[0].tools.get(name).definition;
  return tool.execute("cli", { ...args, ...connection.toolArgs }, undefined, undefined, { hasUI: false });
}

async function open({ storage = new MemoryStorage(), now, conn = connection } = {}) {
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const qdash = buildQDashExtension(extensions, {}, "/tmp", conn);
  const registry = createRegistry();
  registry.install(qdash.extension);
  registry.install(toolPolicyExtension({ nestedTools: qdash.nestedTools, deferredTools: qdash.deferredTools }));
  const harness = await Harness.open(
    storage,
    { models, registry, settings: { retry: { enabled: false } }, ...(now ? { now } : {}) },
    context,
  );
  // Both waiting tools are deferred; this chat already loaded them with tool_search.
  const conversation = await harness.root(context, {
    agent: {
      model: { provider: model.provider, modelId: model.id },
      modelTools: { add: qdash.extension.tools.filter((tool) => tool.name.startsWith("qdash_wait_")) },
    },
  });
  return { faux, harness, conversation };
}

async function call(chat, name, args) {
  chat.faux.setResponses([
    fauxAssistantMessage([fauxToolCall(name, args, { id: "c1" })], { stopReason: "toolUse" }),
    fauxAssistantMessage(fauxText("done")),
  ]);
  chat.harness.resume();
  return chat.conversation.submit({ type: "input", content: "wait" }, context);
}

/** The state of model call c1's tool task. */
async function callState(harness) {
  const { tasks } = await harness.inspect(context);
  return tasks.find((task) => task.record.kind === "pi.tool" && task.record.input?.callId === "c1")?.state;
}

async function until(predicate, what) {
  for (let i = 0; i < 500; i++) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error(`timed out waiting for ${what}`);
}

async function result(conversation) {
  const view = await conversation.context(context);
  const [entry] = view.entries.filter((candidate) => ToolResultEntry.is(candidate));
  return entry.model[0];
}

const text = (message) => message.content.map((block) => block.text ?? "").join("\n");

test("a wait parks between polls and ends with the pi CLI's result", async () => {
  requests.length = 0;
  serve("/executions/e1", execution("running"), execution("running"), execution("completed"));
  const chat = await open();
  try {
    const submission = await call(chat, "qdash_wait_execution", { executionId: "e1", pollIntervalSeconds: 0.05 });
    await until(async () => (await callState(chat.harness))?.kind === "sleeping", "the first park");
    // Parked: no request in flight, nothing running in the Harness for it.
    assert.equal(chat.harness.wake().active, false);
    assert.equal((await submission.wait(context)).status, "done");
    const chatResult = await result(chat.conversation);
    assert.equal(chatResult.isError, false, text(chatResult));
    assert.equal(requests.filter((r) => r.path === "/executions/e1").length, 3);
    assert.ok(requests.every((r) => r.token === "Bearer alice-token" && r.project === "alice-project"));

    serve("/executions/e1", execution("completed"));
    const cli = await cliResult("qdash_wait_execution", { executionId: "e1" });
    assert.equal(text(chatResult), cli.content[0].text);
    assert.deepEqual(JSON.parse(text(chatResult)), JSON.parse(cli.content[0].text));
  } finally {
    await chat.harness.close(context);
  }
});

test("a pipeline step's execution waits for the whole pipeline, as the client does", async () => {
  requests.length = 0;
  serve(
    "/executions/e1",
    execution("completed", { pipeline: { status: "running" } }),
    execution("completed", { pipeline: { status: "completed" } }),
  );
  const chat = await open();
  try {
    const submission = await call(chat, "qdash_wait_execution", { executionId: "e1", pollIntervalSeconds: 0.02 });
    assert.equal((await submission.wait(context)).status, "done");
    const message = await result(chat.conversation);
    assert.equal(message.isError, false);
    assert.equal(JSON.parse(text(message)).pipeline.status, "completed");
    assert.equal(requests.length, 2);
  } finally {
    await chat.harness.close(context);
  }
});

test("a wait past its timeout fails with the client's timeout error", async () => {
  serve("/executions/e1", execution("running"));
  const chat = await open();
  try {
    const args = { executionId: "e1", timeoutSeconds: 0.15, pollIntervalSeconds: 0.03 };
    const submission = await call(chat, "qdash_wait_execution", args);
    assert.equal((await submission.wait(context)).status, "done");
    const message = await result(chat.conversation);
    assert.equal(message.isError, true);
    await assert.rejects(cliResult("qdash_wait_execution", args), (error) => {
      assert.ok(text(message).includes(error.message), `${text(message)} vs ${error.message}`);
      return true;
    });
    assert.match(text(message), /did not reach a terminal state within 0.15 seconds/);
  } finally {
    await chat.harness.close(context);
  }
});

test("a failed QDash request ends the wait with the same error as the pi CLI", async () => {
  routes.delete("/executions/missing");
  const chat = await open();
  try {
    const args = { executionId: "missing", pollIntervalSeconds: 0.02 };
    assert.equal((await (await call(chat, "qdash_wait_execution", args)).wait(context)).status, "done");
    const message = await result(chat.conversation);
    assert.equal(message.isError, true);
    await assert.rejects(cliResult("qdash_wait_execution", args), (error) => {
      assert.ok(text(message).includes(error.message), `${text(message)} vs ${error.message}`);
      return true;
    });
  } finally {
    await chat.harness.close(context);
  }
});

test("a negative interval is refused before any request, as the client refuses it", async () => {
  requests.length = 0;
  const chat = await open();
  try {
    await (await call(chat, "qdash_wait_execution", { executionId: "e1", pollIntervalSeconds: -1 })).wait(context);
    const message = await result(chat.conversation);
    assert.equal(message.isError, true);
    assert.match(text(message), /Polling timeout and interval must be non-negative/);
    assert.equal(requests.length, 0);
  } finally {
    await chat.harness.close(context);
  }
});

test("stopping a parked wait ends it at once and never touches the execution", async () => {
  requests.length = 0;
  serve("/executions/e1", execution("running"));
  const chat = await open();
  try {
    const submission = await call(chat, "qdash_wait_execution", { executionId: "e1", pollIntervalSeconds: 60 });
    await until(async () => (await callState(chat.harness))?.kind === "sleeping", "the park");
    const started = Date.now();
    await chat.conversation.abort(context);
    const settled = await submission.wait(context);
    assert.ok(Date.now() - started < 5_000);
    const message = await result(chat.conversation);
    assert.equal(message.isError, true);
    assert.equal(settled.reason, "aborted");
    assert.match(text(message), /qdash_wait_execution was aborted/);
    // One read, no cancel or other write, and no poll after the stop.
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert.deepEqual(requests.map((r) => `${r.method} ${r.path}`), ["GET /executions/e1"]);
    assert.equal(await callState(chat.harness), undefined);
  } finally {
    await chat.harness.close(context);
  }
});

test("an agent action wait parks until the action names its execution or fails", async () => {
  const path = "/agent-sessions/s1/actions/a1";
  const action = (fields) => ({ action_id: "a1", session_id: "s1", execution_status: "pending", operation_id: "op-1", execution_id: null, ...fields });
  serve(path, action({}), action({ execution_id: "e9" }));
  let chat = await open();
  try {
    const args = { sessionId: "s1", actionId: "a1", waitForExecution: true, pollIntervalSeconds: 0.02 };
    assert.equal((await (await call(chat, "qdash_wait_agent_action", args)).wait(context)).status, "done");
    const message = await result(chat.conversation);
    assert.equal(message.isError, false);
    serve(path, action({ execution_id: "e9" }));
    assert.equal(text(message), (await cliResult("qdash_wait_agent_action", args)).content[0].text);
  } finally {
    await chat.harness.close(context);
  }
  serve(path, action({ operation_id: null, execution_status: "failed" }));
  chat = await open();
  try {
    await (await call(chat, "qdash_wait_agent_action", { sessionId: "s1", actionId: "a1", pollIntervalSeconds: 0.02 })).wait(context);
    const message = await result(chat.conversation);
    assert.equal(message.isError, false);
    assert.equal(JSON.parse(text(message)).execution_status, "failed");
  } finally {
    await chat.harness.close(context);
  }
});

test("a wait recovered after a restart keeps its original deadline and the reopening connection", async () => {
  const dir = await mkdtemp(join(tmpdir(), "qdash-wait-"));
  let clock = 1_000_000;
  const now = () => clock;
  try {
    requests.length = 0;
    serve("/executions/e1", execution("running"));
    const first = await open({ storage: await openNodeSqliteStorage(join(dir, "chat.db")), now });
    const conversationId = first.conversation.id;
    await call(first, "qdash_wait_execution", { executionId: "e1", timeoutSeconds: 120, pollIntervalSeconds: 30 });
    await until(async () => (await callState(first.harness))?.kind === "sleeping", "the park");
    const parked = await callState(first.harness);
    assert.equal(parked.until, clock + 30_000);
    // The runtime dies while the wait is parked.
    await first.harness.close(context);

    // It comes back after the deadline: the wait polls once and times out,
    // measured from the call's start, not from the restart.
    clock += 600_000;
    const second = await open({ storage: await openNodeSqliteStorage(join(dir, "chat.db")), now, conn: otherConnection });
    try {
      assert.equal(second.conversation.id, conversationId);
      second.faux.setResponses([fauxAssistantMessage(fauxText("timed out"))]);
      second.harness.resume();
      await until(async () => {
        const view = await second.conversation.context(context);
        return view.entries.some((entry) => ToolResultEntry.is(entry));
      }, "the recovered wait's result");
      const message = await result(second.conversation);
      assert.equal(message.isError, true);
      assert.match(text(message), /did not reach a terminal state within 120 seconds/);
      const polls = requests.filter((r) => r.path === "/executions/e1");
      assert.equal(polls.length, 2);
      // The recovered poll reads as the user whose request reopened the chat.
      assert.equal(polls[1].token, "Bearer bob-token");
    } finally {
      await second.harness.close(context);
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("a wait recovered before its deadline picks up a completion that happened while down", async () => {
  const dir = await mkdtemp(join(tmpdir(), "qdash-wait-"));
  let clock = 5_000_000;
  const now = () => clock;
  try {
    serve("/executions/e1", execution("running"));
    const first = await open({ storage: await openNodeSqliteStorage(join(dir, "chat.db")), now });
    await call(first, "qdash_wait_execution", { executionId: "e1", timeoutSeconds: 600, pollIntervalSeconds: 30 });
    await until(async () => (await callState(first.harness))?.kind === "sleeping", "the park");
    await first.harness.close(context);

    serve("/executions/e1", execution("completed"));
    clock += 45_000;
    const second = await open({ storage: await openNodeSqliteStorage(join(dir, "chat.db")), now });
    try {
      second.faux.setResponses([fauxAssistantMessage(fauxText("finished"))]);
      second.harness.resume();
      await until(async () => {
        const view = await second.conversation.context(context);
        return view.entries.some((entry) => ToolResultEntry.is(entry));
      }, "the recovered wait's result");
      const message = await result(second.conversation);
      assert.equal(message.isError, false);
      assert.equal(JSON.parse(text(message)).status, "completed");
    } finally {
      await second.harness.close(context);
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("waiting tools stay model-only, so scripts cannot long-poll", () => {
  const qdash = buildQDashExtension(extensions, {}, "/tmp", connection);
  assert.ok(qdash.extension.tools.some((tool) => tool.name === "qdash_wait_execution"));
  assert.ok(!qdash.nestedTools.includes("qdash_wait_execution"));
  assert.ok(!qdash.nestedTools.includes("qdash_wait_agent_action"));
});

/** The chat stream's NDJSON lines for `conversation`, as the chat handler streams them. */
async function streamLines(conversation) {
  const out = [];
  const watch = await conversation.watch(context);
  const stream = new ViewEventStream(conversation, watch.value, (event) => out.push(...toNdjsonEvents(event)), context);
  let live;
  watch.start(async (update) => {
    if (update.kind !== "value") return;
    live = update.value.docs["pi.live"];
    await stream.push(update.value);
  });
  return { out, live: () => live, stop: () => watch.stop() };
}

test("a parked wait stays a running tool in the chat stream and the turn stays busy", async () => {
  serve("/executions/e1", execution("running"));
  const chat = await open();
  const lines = await streamLines(chat.conversation);
  try {
    const submission = await call(chat, "qdash_wait_execution", { executionId: "e1", pollIntervalSeconds: 60 });
    await until(async () => (await callState(chat.harness))?.kind === "sleeping", "the park");
    await until(() => lines.out.some((line) => line.type === "tool_start" && line.id === "c1"), "tool_start");
    await delay(50);
    // Started, not ended, and no answer: the UI keeps the row running and Stop enabled.
    assert.ok(!lines.out.some((line) => line.type === "tool_end"), JSON.stringify(lines.out));
    assert.notEqual(lines.live()?.run, undefined);
    assert.equal(lines.live().tools.find((slot) => slot.callId === "c1").status, "sleeping");

    await chat.conversation.abort(context);
    await submission.wait(context);
    await until(() => lines.out.some((line) => line.type === "tool_end" && line.id === "c1"), "tool_end");
    const end = lines.out.find((line) => line.type === "tool_end" && line.id === "c1");
    assert.equal(end.is_error ?? end.isError, true, JSON.stringify(end));
  } finally {
    await lines.stop();
    await chat.harness.close(context);
  }
});

test("stopping a wait while its poll is in flight drops the poll at once", async () => {
  requests.length = 0;
  serve("/executions/slow", execution("running", { execution_id: "slow" }));
  delays.set("/executions/slow", 2_000);
  const chat = await open();
  try {
    const submission = await call(chat, "qdash_wait_execution", { executionId: "slow", pollIntervalSeconds: 0.01 });
    await until(async () => (await callState(chat.harness))?.kind === "running", "the poll");
    await delay(50);
    const started = Date.now();
    await chat.conversation.abort(context);
    assert.equal((await submission.wait(context)).reason, "aborted");
    assert.ok(Date.now() - started < 1_500, `stop took ${Date.now() - started} ms`);
    assert.equal((await result(chat.conversation)).isError, true);
  } finally {
    delays.delete("/executions/slow");
    await chat.harness.close(context);
  }
});
