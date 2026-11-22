import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

// The server runs in its own process with a mocked runtime whose stores are
// real SQLite durable harnesses and whose skill expansion is the real one, over
// a skill file the test writes. A scripted model records the text of every user
// message it receives, so each scenario checks what the model actually read.
const preamble = (dir) => `
  import assert from "node:assert/strict";
  import { once } from "node:events";
  import { Server } from "node:http";
  import { join } from "node:path";
  import { mock } from "bun:test";
  import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
  import { fauxAssistantMessage, fauxProvider, fauxText } from "@earendil-works/pi-ai";
  import { createModels } from "@earendil-works/pi-ai/models";
  import { AssistantEntry, createRegistry, Harness, ROOT_CONVERSATION_ID, UserEntry } from "@earendil-works/pi-durable";
  import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
  import { CHAT_QUEUE_SETTINGS, readSteerReceipt } from "../src/chat-control.ts";
  import { expandSkillCommand } from "../src/skill-tool.ts";

  const dir = ${JSON.stringify(dir)};
  const skills = [{ name: "qdash-characterization", description: "Remeasure properties.", filePath: join(dir, "SKILL.md") }];
  let server;
  const listen = Server.prototype.listen;
  Server.prototype.listen = function () {
    server = this;
    return listen.call(this, 0, "127.0.0.1");
  };

  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const agent = { model: { provider: model.provider, modelId: model.id } };
  const text = (message) => typeof message.content === "string" ? message.content : message.content.map((b) => b.text ?? "").join("");
  // The text of the newest user message of every model request.
  const received = [];
  const reply = (ctx) => {
    received.push(text(ctx.messages.filter((m) => m.role === "user").at(-1)));
    return fauxAssistantMessage(fauxText("ok"));
  };
  faux.setResponses(Array.from({ length: 50 }, () => reply));

  const pathOf = (owner, store) => join(dir, owner + "-" + store + ".sqlite");
  mock.module("../src/runtime.ts", () => ({
    BACKGROUND_CONTEXT,
    SharedRuntime: { create: async () => ({
      listToolNames: () => [],
      expandSkillCommand: (message) => expandSkillCommand(message, skills),
      storePath: pathOf,
      steerReceipt: (owner, session, project, requestId, target = {}) =>
        readSteerReceipt(pathOf(owner, target.storeSessionId ?? session), project, requestId, BACKGROUND_CONTEXT, target.conversationId ?? ROOT_CONVERSATION_ID),
      openSession: async (request) => {
        const harness = await Harness.open(
          await openNodeSqliteStorage(pathOf(request.ownerId, request.storeSessionId ?? request.sessionId)),
          { models, registry: createRegistry(), settings: { retry: { enabled: false }, ...CHAT_QUEUE_SETTINGS } },
          BACKGROUND_CONTEXT,
        );
        const conversation = await harness.root(BACKGROUND_CONTEXT, { agent });
        await conversation.configure(agent, BACKGROUND_CONTEXT);
        return { harness, conversation, writeTools: {}, close: () => harness.close(BACKGROUND_CONTEXT) };
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
  const chat = async (body) => {
    const response = await fetch(base + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer test-runtime-token", "x-qdash-token": "user-token", "x-qdash-project-id": "p1" },
      body: JSON.stringify({ owner_id: "alice", model: { provider: model.provider, name: model.id }, ...body }),
    });
    assert.equal(response.status, 200, await response.clone().text());
    const out = (await response.text()).trim().split("\\n").filter(Boolean).map(JSON.parse);
    assert.ok(out.some((line) => line.type === "done"), JSON.stringify(out));
  };
  // The users' messages the store keeps, read without a writer.
  const stored = async (store) => {
    const harness = await Harness.open(await openNodeSqliteStorage(pathOf("alice", store)), { models, registry: createRegistry(), readOnly: true }, BACKGROUND_CONTEXT);
    try {
      const view = await (await harness.conversation(ROOT_CONVERSATION_ID, BACKGROUND_CONTEXT)).context(BACKGROUND_CONTEXT);
      return view.entries.filter((entry) => UserEntry.is(entry)).map((entry) => text(entry.model[0]));
    } finally {
      await harness.close(BACKGROUND_CONTEXT);
    }
  };
  const SKILL = '<skill name="qdash-characterization">\\n# Characterization\\nRun T1 first.\\n</skill>';
  try {
`;

const epilogue = `
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
  console.log("SCENARIO OK");
`;

function runScenario(body) {
  const dir = mkdtempSync(join(tmpdir(), "chat-skill-command-"));
  writeFileSync(
    join(dir, "SKILL.md"),
    "---\nname: qdash-characterization\ndescription: Remeasure properties.\n---\n\n# Characterization\nRun T1 first.\n",
  );
  try {
    const result = spawnSync("bun", ["--eval", preamble(dir) + body + epilogue], {
      cwd: new URL(".", import.meta.url),
      encoding: "utf8",
      timeout: 60_000,
    });
    assert.equal(result.status, 0, `${result.error ?? ""}\n${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /SCENARIO OK/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("the first turn of a task-result chat expands the user's skill command after the task context", { timeout: 70_000 }, () => {
  runScenario(`
    const context = "# Task result\\nT1 of Q0 is 12 us.\\n\\n## Your task\\n\\n";
    await chat({
      conversation_id: "task",
      request_id: "t1",
      message: "/skill:qdash-characterization remeasure T1 of Q0",
      initial_context: context,
    });
    const expected = context + SKILL + "\\n\\nremeasure T1 of Q0";
    assert.deepEqual(received, [expected]);
    assert.deepEqual(await stored("task"), [expected]);

    // A later turn gets no context again, and its skill command expands as well.
    await chat({
      conversation_id: "task",
      request_id: "t2",
      message: "/skill:qdash-characterization Q1 too",
      initial_context: context,
    });
    assert.equal(received.at(-1), SKILL + "\\n\\nQ1 too");

    // Text that is not a command reaches the model as typed, after the context on a new chat.
    await chat({ conversation_id: "task-plain", request_id: "t3", message: "Is this trustworthy?", initial_context: context });
    assert.equal(received.at(-1), context + "Is this trustworthy?");
  `);
});

test("an ordinary chat expands a skill command and keeps other text as typed", { timeout: 70_000 }, () => {
  runScenario(`
    await chat({ conversation_id: "plain", request_id: "p1", message: "/skill:qdash-characterization\\nQ0\\nQ1" });
    assert.equal(received.at(-1), SKILL + "\\n\\nQ0\\nQ1");
    await chat({ conversation_id: "plain", request_id: "p2", message: "please /skill:qdash-characterization" });
    assert.equal(received.at(-1), "please /skill:qdash-characterization");
    await chat({ conversation_id: "plain", request_id: "p3", message: "/skill:unknown x" });
    assert.equal(received.at(-1), "/skill:unknown x");
  `);
});

test("an opening QDash wrote in full replaces the first message and is not expanded", { timeout: 70_000 }, () => {
  runScenario(`
    await chat({
      conversation_id: "investigation",
      request_id: "i1",
      message: "/skill:qdash-characterization x",
      initial_message: "/skill:qdash-characterization opening",
    });
    assert.equal(received.at(-1), "/skill:qdash-characterization opening");
  `);
});
