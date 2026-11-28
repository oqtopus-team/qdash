/**
 * Every QDash agent record carries the model the host ran, read from the
 * extension context (`ctx.model`), never from a tool argument: a session, each
 * proposed action, each decision, and each intervention. A model switch shows
 * on later records only; it changes no earlier record and no approval.
 */

import assert from "node:assert/strict";
import { after, before, test } from "node:test";

import { QDash } from "@oqtopus-team/qdash-sdk";

import { QDashConnection } from "../.test-dist/lib/qdash-connection.js";

import { DEFAULT_HOST_NAME, HOST_NAME_KEY, hostModelIdentity } from "../.test-dist/lib/host-model.js";
import { HOST_WRITE_APPROVAL_KEY } from "../.test-dist/lib/write-approval.js";
import qdashExtension from "../.test-dist/qdash.js";
import { registerAgentLoopTools } from "../.test-dist/tools/agent-loop.js";
import { startFakeAgentQDash } from "./helpers/fake-agent-qdash.mjs";

let fake;
const saved = {};
before(async () => {
  fake = await startFakeAgentQDash();
  for (const name of ["QDASH_BASE_URL", "QDASH_API_TOKEN"]) saved[name] = process.env[name];
  process.env.QDASH_BASE_URL = fake.baseUrl;
  process.env.QDASH_API_TOKEN = "fixture-token";
});
after(() => {
  for (const [name, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
  fake.close();
});

/** A pi-ai Model as pi hands it to an extension, including fields that must never leave the host. */
const piModel = (provider, id) => ({
  provider,
  id,
  name: `${id} display name`,
  api: "openai-completions",
  baseUrl: "http://10.0.0.5:8000/v1",
  headers: { Authorization: "Bearer sk-secret-header" },
  contextWindow: 65536,
  maxTokens: 8192,
});

test("the identity is the host model's provider and ID, labelled with the host", () => {
  assert.deepEqual(hostModelIdentity({ model: piModel("ollama", "qwen3:32b") }), {
    provider: "ollama",
    model_id: "qwen3:32b",
    host: DEFAULT_HOST_NAME,
  });
  assert.deepEqual(hostModelIdentity({ model: piModel("vllm", "Qwen/Qwen3-32B"), [HOST_NAME_KEY]: "qdash-web-agent" }), {
    provider: "vllm",
    model_id: "Qwen/Qwen3-32B",
    host: "qdash-web-agent",
  });
  // No model, or one that is not an identifier, is left out rather than guessed.
  for (const ctx of [undefined, {}, { model: undefined }, { model: { provider: "ollama" } }, { model: { provider: "x", id: "http://host/v1" } }, { model: { provider: "x", id: "has spaces" } }, { model: { provider: "x", id: "m".repeat(201) } }]) {
    assert.equal(hostModelIdentity(ctx), undefined, JSON.stringify(ctx));
  }
  // An unusable host label falls back to pi instead of dropping the identity.
  assert.equal(hostModelIdentity({ model: piModel("a", "b"), [HOST_NAME_KEY]: "Not A Label" }).host, DEFAULT_HOST_NAME);
});

function loadPi() {
  const tools = new Map();
  const pi = {
    registerTool: (definition) => tools.set(definition.name, definition),
    registerCommand() {},
    registerShortcut() {},
    registerFlag() {},
    getFlag() {},
    appendEntry() {},
    sendMessage() {},
    on() {},
    getAllTools: () => [],
    getActiveTools: () => [...tools.keys()],
    setActiveTools() {},
    getSettings: () => ({}),
  };
  qdashExtension(pi);
  return tools;
}

/** The context a host passes when it already collected the user's approval of this call. */
const approvedCtx = (toolName, toolCallId, extra = {}) => ({
  hasUI: false,
  [HOST_WRITE_APPROVAL_KEY]: { toolCallId, toolName },
  ...extra,
});

const POLICY = { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "confirm_each", max_actions: 4 };

function lastPost(before, suffix) {
  return fake.state.requests.slice(before).filter((request) => request.method === "POST" && request.path.endsWith(suffix)).at(-1);
}

test("a session records the host's model, not a model named in the arguments", async () => {
  const tools = loadPi();
  const name = "qdash_create_agent_session";
  assert.equal("modelName" in tools.get(name).parameters.properties, false, "no tool argument names the model");
  assert.equal("model" in tools.get(name).parameters.properties, false);
  const before = fake.state.requests.length;
  // A model may still send such fields; they are ignored.
  const input = { chipId: "chip-001", policy: structuredClone(POLICY), modelName: "claimed/other-model", model: { provider: "claimed", model_id: "other" } };
  await tools.get(name).execute("create-1", input, undefined, undefined, approvedCtx(name, "create-1", { model: piModel("ollama", "qwen3:32b") }));
  const posted = lastPost(before, "/agent-sessions");
  assert.deepEqual(posted.body.model, { provider: "ollama", model_id: "qwen3:32b", host: "pi" });
  assert.equal("model_name" in posted.body, false);
  const sent = JSON.stringify(posted.body);
  for (const secret of ["10.0.0.5", "sk-secret", "display name", "claimed"]) assert.doesNotMatch(sent, new RegExp(secret));
  assert.equal([...fake.state.sessions.values()].at(-1).model_name, "ollama/qwen3:32b");
});

test("without a host model nothing is reported, and QDash shows none", async () => {
  const tools = loadPi();
  const name = "qdash_create_agent_session";
  const before = fake.state.requests.length;
  await tools.get(name).execute("create-2", { chipId: "chip-001", policy: structuredClone(POLICY) }, undefined, undefined, approvedCtx(name, "create-2"));
  const posted = lastPost(before, "/agent-sessions");
  assert.equal("model" in posted.body, false);
  const session = [...fake.state.sessions.values()].at(-1);
  assert.equal(session.model, null);
  assert.equal(session.model_name, "");
});

test("a reviewed action records the model of the host that ran it", async () => {
  const tools = loadPi();
  const session = fake.createSession({ chip_id: "chip-001", policy: structuredClone(POLICY) });
  const name = "qdash_submit_agent_action";
  const before = fake.state.requests.length;
  await tools.get(name).execute(
    "submit-1",
    { sessionId: session.session_id, expectedStateVersion: 0, actionType: "run_task", taskName: "CheckRabi", qids: ["Q00"], diagnosis: "Rabi" },
    undefined,
    undefined,
    approvedCtx(name, "submit-1", { model: piModel("vllm", "qwen3-32b"), [HOST_NAME_KEY]: "qdash-web-agent" }),
  );
  assert.deepEqual(lastPost(before, "/actions").body.model, { provider: "vllm", model_id: "qwen3-32b", host: "qdash-web-agent" });
});

function loopTools() {
  const registered = new Map();
  registerAgentLoopTools({ registerTool(tool) { registered.set(tool.name, tool); } }, {
    async makeClient() {
      return new QDashConnection(new QDash({ baseUrl: fake.baseUrl, apiToken: "fixture-token" }));
    },
  });
  return (name, id, params, ctx) => registered.get(name).execute(id, params, undefined, undefined, { hasUI: false, ...ctx });
}

test("a model switch between steps attributes each step to its own model and rewrites nothing", async () => {
  const call = loopTools();
  const policy = { qids: ["Q00"], allowed_tasks: ["CheckRabi", "CheckChevron"], allowed_overrides: {}, autonomy: "auto", max_actions: 6 };
  const sessionId = fake.createSession({ chip_id: "chip-001", policy }).session_id;
  const approved = structuredClone(fake.state.sessions.get(sessionId).policy);
  const first = { model: piModel("ollama", "qwen3:32b") };
  // The same model ID served by another provider, in the web Agent.
  const second = { model: piModel("vllm", "qwen3:32b"), [HOST_NAME_KEY]: "qdash-web-agent" };

  fake.queueOutcome("CheckRabi", { status: "completed" });
  const step1 = await call("qdash_run_agent_session_step", "step-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi first." }, first);
  assert.equal(step1.details.dispatched, true);
  const [action1] = fake.state.actions.filter((action) => action.session_id === sessionId);
  assert.deepEqual(action1.model, { provider: "ollama", model_id: "qwen3:32b", host: "pi" });

  fake.queueOutcome("CheckChevron", { status: "completed" });
  const step2 = await call(
    "qdash_run_agent_session_step",
    "step-2",
    { sessionId, taskName: "CheckChevron", qid: "Q00", rationale: "Chevron next.", assessment: "pass", interpretation: "Rabi oscillation is clean.", evidenceActionIds: [action1.action_id] },
    second,
  );
  assert.equal(step2.details.dispatched, true);
  const actions = fake.state.actions.filter((action) => action.session_id === sessionId);
  assert.deepEqual(actions[1].model, { provider: "vllm", model_id: "qwen3:32b", host: "qdash-web-agent" });
  // The earlier record still names the model that took it.
  assert.deepEqual(actions[0].model, { provider: "ollama", model_id: "qwen3:32b", host: "pi" });
  const decision = fake.state.decisions.find((item) => item.session_id === sessionId && item.next_action_id === actions[1].action_id);
  assert.deepEqual(decision.model, { provider: "vllm", model_id: "qwen3:32b", host: "qdash-web-agent" });

  // A replay of the first call under the new model returns the first record unchanged.
  await call("qdash_run_agent_session_step", "step-1", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi first." }, second);
  assert.equal(fake.state.actions.filter((action) => action.session_id === sessionId).length, 2);
  assert.deepEqual(fake.state.actions.find((action) => action.action_id === action1.action_id).model.provider, "ollama");

  const recorded = await call("qdash_record_agent_decision", "decide-1", { sessionId, interpretation: "Chevron shows the peak.", nextAction: "complete", evidenceActionIds: [actions[1].action_id], model: { provider: "claimed", model_id: "x" } }, {});
  assert.equal(recorded.details.refused, undefined);
  const unreported = fake.state.decisions.find((item) => item.session_id === sessionId && item.next_action === "complete");
  assert.equal(unreported.model, null, "a model in the arguments is not an identity");

  await call("qdash_request_agent_human", "human-1", { sessionId, reason: "agent_request", summary: "Check the readout.", question: "Is the readout stable?" }, second);
  const intervention = fake.state.interventions.find((item) => item.session_id === sessionId);
  assert.deepEqual(intervention.model, { provider: "vllm", model_id: "qwen3:32b", host: "qdash-web-agent" });

  // The switch changed neither the approval nor the creator.
  const session = fake.state.sessions.get(sessionId);
  assert.deepEqual(session.policy, approved);
  assert.equal(session.created_by, "alice");

  const audit = await call("qdash_get_agent_session_audit", "audit", { sessionId }, {});
  const text = audit.content.map((block) => block.text).join("\n");
  assert.match(text, new RegExp(`action_proposed \\[server_record, alice\\] \\{model ollama/qwen3:32b via pi\\}: Authorized CheckRabi`));
  assert.match(text, /action_proposed \[server_record, alice\] \{model vllm\/qwen3:32b via qdash-web-agent\}: Authorized CheckChevron/);
  assert.match(text, /model not reported/);
  assert.match(text, /not verified by QDash/);
  assert.match(text, /Assessed not stated; next complete[^\n]*\[missing: model\]/);
});
