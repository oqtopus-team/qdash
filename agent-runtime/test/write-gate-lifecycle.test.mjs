/**
 * The pi CLI write gate inside a real pi session (pi-coding-agent's agent
 * loop and extension runner, a scripted faux model, and a fake QDash): the
 * approval covers exactly the arguments the dialog showed, is used once, and
 * does not outlive a call that a later `tool_call` hook blocks or an abort
 * skips. No network, model, CLI command, or credentials are used.
 */

import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";

import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";
import qdashExtension from "@oqtopus-team/pi-qdash/extensions/qdash.ts";
import { hasGateApproval } from "@oqtopus-team/pi-qdash/extensions/lib/write-approval.ts";

import { startFakeAgentQDash } from "../../packages/pi-qdash/tests/helpers/fake-agent-qdash.mjs";

let fake;
let workDir;
const savedEnv = {};
const ENV = ["QDASH_BASE_URL", "QDASH_API_TOKEN", "QDASH_USERNAME", "QDASH_PROJECT_ID", "PI_CODING_AGENT_DIR", "PI_QDASH_CODEMODE"];

before(async () => {
  fake = await startFakeAgentQDash();
  workDir = mkdtempSync(join(tmpdir(), "qdash-write-gate-"));
  for (const name of ENV) savedEnv[name] = process.env[name];
  for (const name of ENV) delete process.env[name];
  process.env.QDASH_BASE_URL = fake.baseUrl;
  process.env.QDASH_API_TOKEN = "fixture-token";
  process.env.PI_CODING_AGENT_DIR = join(workDir, "agent");
});

after(async () => {
  await fake.close();
  for (const name of ENV) {
    if (savedEnv[name] === undefined) delete process.env[name];
    else process.env[name] = savedEnv[name];
  }
  rmSync(workDir, { recursive: true, force: true });
});

const POLICY = { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "confirm_each", max_actions: 4 };
const create = (id) => fauxAssistantMessage([fauxToolCall("qdash_create_agent_session", { chipId: "chip-001", policy: structuredClone(POLICY) }, { id })], { stopReason: "toolUse" });
const done = () => fauxAssistantMessage([fauxText("done")]);

function textOf(content) {
  return (Array.isArray(content) ? content : []).map((block) => (block.type === "text" ? block.text : "")).join("\n");
}

/**
 * A real pi session loading pi-qdash first and then `later`, an extension
 * whose own `tool_call` hook runs after the write gate's. `ui` answers pi's
 * confirmations.
 */
async function open(steps, { later = () => {}, ui, mode = "rpc" }) {
  const faux = fauxProvider({ tokensPerSecond: 0 });
  faux.setResponses(steps);
  const model = faux.getModel();
  const agentDir = join(workDir, "agent");
  const events = [];
  const loader = new DefaultResourceLoader({
    cwd: workDir,
    agentDir,
    noExtensions: true,
    extensionFactories: [
      qdashExtension,
      (pi) => {
        for (const name of ["tool_call", "tool_execution_end", "turn_end", "agent_end"]) {
          pi.on(name, (event) => {
            events.push({ type: name, toolCallId: event.toolCallId, approved: event.toolCallId ? hasGateApproval(event.toolCallId) : undefined });
          });
        }
        later(pi);
      },
      (pi) => {
        pi.registerProvider(model.provider, {
          name: "Faux",
          baseUrl: model.baseUrl,
          apiKey: "test-key",
          api: model.api,
          streamSimple: (m, ctx, options) => faux.provider.streamSimple(m, ctx, options),
          models: [{ id: model.id, name: model.name, api: model.api, reasoning: false, input: ["text"], cost: model.cost, contextWindow: model.contextWindow, maxTokens: model.maxTokens }],
        });
      },
    ],
  });
  await loader.reload();
  assert.deepEqual(loader.getExtensions().errors, []);
  const modelRuntime = await ModelRuntime.create({ authPath: join(workDir, "auth.json"), modelsPath: null, refreshOnCreate: false });
  const { session } = await createAgentSession({
    cwd: workDir,
    agentDir,
    resourceLoader: loader,
    sessionManager: SessionManager.inMemory(),
    settingsManager: SettingsManager.inMemory(),
    modelRuntime,
  });
  await session.bindExtensions({ uiContext: ui, mode });
  await session.setModel(modelRuntime.getModel(model.provider, model.id));
  return {
    session,
    events,
    ask: (text) => session.prompt(text),
    results: () =>
      session.messages
        .filter((message) => message.role === "toolResult")
        .map((message) => ({ name: message.toolName, id: message.toolCallId, text: textOf(message.content), isError: message.isError })),
    close: () => session.dispose(),
  };
}

/** pi's UI whose user answers each confirmation with `answer(title, message, opts)`. */
function dialog(answer) {
  const asked = [];
  const ui = new Proxy(
    {
      confirm: async (title, message, opts) => {
        asked.push({ title, message, signal: opts?.signal });
        return answer(title, message, opts);
      },
    },
    { get: (target, key) => (key in target ? target[key] : () => undefined) },
  );
  return { ui, asked };
}

const created = (start) => fake.state.requests.slice(start).filter((request) => request.method === "POST" && request.path === "/agent-sessions");

test("an approved call runs once with exactly one dialog that shows its arguments and the session grant", async () => {
  const { ui, asked } = dialog(() => true);
  const run = await open([create("call-ok"), done()], { ui });
  const start = fake.state.requests.length;
  try {
    await run.ask("make a session");
    const [result] = run.results();
    assert.equal(result.isError, false, result.text);
    assert.equal(asked.length, 1);
    assert.equal(asked[0].title, "Approve QDash write operation?");
    assert.match(asked[0].message, /Create an agent session on chip chip-001:/);
    assert.match(asked[0].message, /- qubits: Q00/);
    assert.match(asked[0].message, /"allowed_tasks": \[\n\s+"CheckRabi"/);
    assert.ok(asked[0].signal instanceof AbortSignal, "the dialog follows pi's abort signal");
    const [request] = created(start);
    assert.deepEqual(request.body.policy.qids, ["Q00"]);
    // The approval was spent by the call; nothing is left once it ended.
    assert.equal(hasGateApproval("call-ok"), false);
  } finally {
    await run.close();
  }
});

test("a later hook that changes nested arguments after the approval stops the call before QDash", async () => {
  const { ui, asked } = dialog(() => true);
  const later = (pi) =>
    pi.on("tool_call", (event) => {
      event.input.policy.qids.push("Q01");
    });
  const run = await open([create("call-mut"), done()], { ui, later });
  const start = fake.state.requests.length;
  try {
    await run.ask("make a session");
    const [result] = run.results();
    assert.equal(result.isError, true);
    assert.match(result.text, /arguments changed after the user saw them/);
    assert.equal(asked.length, 1);
    assert.deepEqual(created(start), []);
    assert.equal(hasGateApproval("call-mut"), false);
  } finally {
    await run.close();
  }
});

test("a later hook that blocks the call leaves no approval behind", async () => {
  const { ui } = dialog(() => true);
  const later = (pi) => pi.on("tool_call", () => ({ block: true, reason: "blocked by a later policy" }));
  const run = await open([create("call-blocked"), done()], { ui, later });
  const start = fake.state.requests.length;
  try {
    await run.ask("make a session");
    const [result] = run.results();
    assert.match(result.text, /blocked by a later policy/);
    assert.deepEqual(created(start), []);
    // The gate recorded the approval before the later hook ran...
    assert.equal(run.events.find((event) => event.type === "tool_call" && event.toolCallId === "call-blocked").approved, true);
    // ...and pi ends a blocked call with tool_execution_end, which forgets it.
    const end = run.events.find((event) => event.type === "tool_execution_end" && event.toolCallId === "call-blocked");
    assert.ok(end, "pi reports the end of a blocked call");
    assert.equal(hasGateApproval("call-blocked"), false);
  } finally {
    await run.close();
  }
});

test("an abort while the dialog is open or after the approval never runs the call or keeps the approval", async () => {
  // While the dialog is open: the user's accept arrives after the turn was aborted.
  {
    let session;
    const { ui, asked } = dialog(async (_title, _message, opts) => {
      // pi's abort waits for the turn to settle, which waits on this dialog.
      void session.abort();
      assert.equal(opts.signal.aborted, true);
      return true;
    });
    const run = await open([create("call-abort-dialog"), done()], { ui });
    session = run.session;
    const start = fake.state.requests.length;
    try {
      await run.ask("make a session");
      assert.equal(asked.length, 1);
      assert.deepEqual(created(start), []);
      assert.equal(hasGateApproval("call-abort-dialog"), false);
    } finally {
      await run.close();
    }
  }
  // After the gate approved, before the tool ran: a later hook aborts the turn.
  {
    let session;
    const { ui } = dialog(() => true);
    const later = (pi) =>
      pi.on("tool_call", () => {
        void session.abort();
      });
    const run = await open([create("call-abort-after"), done()], { ui, later });
    session = run.session;
    const start = fake.state.requests.length;
    try {
      await run.ask("make a session");
      assert.equal(run.events.find((event) => event.type === "tool_call" && event.toolCallId === "call-abort-after").approved, true);
      assert.ok(run.events.some((event) => event.type === "tool_execution_end" && event.toolCallId === "call-abort-after"));
      assert.deepEqual(created(start), []);
      assert.equal(hasGateApproval("call-abort-after"), false);
    } finally {
      await run.close();
    }
  }
});

/**
 * pi's terminal UI: `custom()` builds the review component and `review`
 * plays the user's keys on it (a 12-row terminal); `confirm()` must not be used.
 */
function terminal(review) {
  const reviews = [];
  const theme = { fg: (_color, text) => text, bold: (text) => text };
  // pi's default keys for the bindings the review uses (pi-qdash's own test uses pi-tui's KeybindingsManager).
  const keys = { "tui.select.cancel": "\x1b", "tui.select.pageDown": "\x1b[6~", "tui.select.pageUp": "\x1b[5~", "tui.select.up": "\x1b[A", "tui.select.down": "\x1b[B" };
  const keybindings = { matches: (data, id) => keys[id] === data };
  const ui = new Proxy(
    {
      confirm: async () => assert.fail("the terminal UI reviews writes with custom(), not confirm()"),
      custom: (factory) =>
        new Promise((resolve) => {
          const tui = { terminal: { rows: 12 }, requestRender() {} };
          const view = factory(tui, theme, keybindings, resolve);
          reviews.push(view);
          review(view);
        }),
    },
    { get: (target, key) => (key in target ? target[key] : () => undefined) },
  );
  return { ui, reviews };
}

test("in pi's terminal UI the gate approves only after the user scrolled the whole review", async () => {
  const pages = [];
  const { ui, reviews } = terminal((view) => {
    view.render(60);
    view.handleInput("y"); // refused: the end is not shown yet
    for (let step = 0; step < 100 && !view.reviewedToEnd; step += 1) {
      pages.push(view.render(60).join("\n"));
      view.handleInput("\x1b[6~");
    }
    pages.push(view.render(60).join("\n"));
    view.handleInput("y");
  });
  const run = await open([create("call-tui"), done()], { ui, mode: "tui" });
  const start = fake.state.requests.length;
  try {
    await run.ask("make a session");
    const [result] = run.results();
    assert.equal(result.isError, false, result.text);
    assert.equal(reviews.length, 1);
    assert.ok(pages.length > 1, "the review needed scrolling in a 12-row terminal");
    const shown = pages.join("\n");
    assert.match(shown, /Create an agent session on chip chip-001:/);
    assert.match(shown, /"CheckRabi"/);
    assert.equal(created(start).length, 1);
    assert.equal(hasGateApproval("call-tui"), false);
  } finally {
    await run.close();
  }
});

test("in pi's terminal UI a declined or escaped review runs nothing", async () => {
  for (const key of ["n", "\x1b"]) {
    const { ui } = terminal((view) => {
      view.render(60);
      view.handleInput(key);
    });
    const run = await open([create(`call-tui-${key.length}`), done()], { ui, mode: "tui" });
    const start = fake.state.requests.length;
    try {
      await run.ask("make a session");
      const [result] = run.results();
      assert.equal(result.isError, true);
      assert.match(result.text, /rejected by user/);
      assert.deepEqual(created(start), []);
    } finally {
      await run.close();
    }
  }
});
