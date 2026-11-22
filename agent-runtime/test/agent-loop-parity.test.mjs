/**
 * The model-driven calibration loop in both supported hosts: a real pi CLI
 * session and the production chat registry on a durable harness, loading the
 * same bundled pi-qdash, against one stateful fake of QDash's agent-session
 * API (packages/pi-qdash/tests/helpers/fake-agent-qdash.mjs).
 *
 * A scripted faux model makes the same tool calls in both hosts; the tests
 * check what each host returns to the model, what reaches QDash, and that the
 * approval boundary is the same: creating a session is a reviewed write, steps
 * inside the approved `auto` session are not, and scripts reach neither. No
 * network, model, CLI command, or credentials are used.
 */

import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { after, before, test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import {
  createAgentSession,
  createCodemodeExtension,
  createToolSearchExtension,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { Harness, MemoryStorage, ToolResultEntry } from "@earendil-works/pi-durable";

import { startFakeAgentQDash } from "../../packages/pi-qdash/tests/helpers/fake-agent-qdash.mjs";
import { ALLOWLISTED_PACKAGES } from "../src/allowed-tools.ts";
import { buildChatRegistry, buildCopilotExtension } from "../src/chat-registry.ts";
import { bundledExtensionCheckouts, trustedCheckoutRoots } from "../src/local-extensions.ts";

const context = BACKGROUND_CONTEXT;
const packagesDir = fileURLToPath(new URL("../../packages/", import.meta.url));
const LOOP_TOOLS = [
  "qdash_create_agent_session",
  "qdash_list_agent_sessions",
  "qdash_get_agent_session_context",
  "qdash_run_agent_session_step",
  "qdash_request_agent_human",
  "qdash_wait_agent_intervention",
  "qdash_wait_agent_action",
  "qdash_record_agent_decision",
  "qdash_get_agent_session_audit",
  "qdash_commit_agent_session_update",
];

let fake;
let workDir;
const savedEnv = {};
const ENV = ["QDASH_BASE_URL", "QDASH_API_TOKEN", "QDASH_USERNAME", "QDASH_PROJECT_ID", "PI_CODING_AGENT_DIR", "QCALEVAL_MODEL", "PI_QDASH_CODEMODE"];

before(async () => {
  fake = await startFakeAgentQDash();
  workDir = mkdtempSync(join(tmpdir(), "qdash-agent-loop-"));
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

function bundledPaths() {
  return bundledExtensionCheckouts(packagesDir).map(({ path }) => path);
}

function textOf(content) {
  return (Array.isArray(content) ? content : []).map((block) => (block.type === "text" ? block.text : "")).join("\n");
}

function scripted(steps) {
  const faux = fauxProvider({ tokensPerSecond: 0 });
  faux.setResponses(steps.map((step) => (ctx) => (typeof step === "function" ? step(ctx) : step)));
  return faux;
}

/**
 * A real pi CLI session with codemode and tool_search: without a UI, as `pi -p`
 * runs, or with `ui`, a dialog double that answers pi's confirmations.
 */
async function openCli(steps, { ui } = {}) {
  const faux = scripted(steps);
  const model = faux.getModel();
  const agentDir = join(workDir, "agent");
  const loader = new DefaultResourceLoader({
    cwd: workDir,
    agentDir,
    additionalExtensionPaths: bundledPaths(),
    extensionFactories: [
      createCodemodeExtension({ mode: "on" }),
      createToolSearchExtension(),
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
  await session.bindExtensions(ui ? { uiContext: ui, mode: "rpc" } : {});
  await session.setModel(modelRuntime.getModel(model.provider, model.id));
  return {
    ask: (text) => session.prompt(text),
    results: () =>
      session.messages
        .filter((message) => message.role === "toolResult")
        .map((message) => ({ name: message.toolName, text: textOf(message.content), details: message.details, isError: message.isError })),
    close: () => session.dispose(),
  };
}

/** The production chat registry on a durable harness, as the QDash web Agent runs it. */
async function openChat(steps) {
  const faux = scripted(steps);
  const loader = new DefaultResourceLoader({ cwd: workDir, agentDir: join(workDir, "runtime-agent"), additionalExtensionPaths: bundledPaths() });
  await loader.reload();
  assert.deepEqual(loader.getExtensions().errors, []);
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const connection = { toolArgs: { useEnv: true }, auth: { accessToken: "fixture-token" }, baseUrl: fake.baseUrl, close: async () => {} };
  const modelRuntime = await ModelRuntime.create({ authPath: join(workDir, "runtime-auth.json"), modelsPath: null, refreshOnCreate: false });
  const chat = buildChatRegistry(
    {
      extensions: loader.getExtensions().extensions,
      modelRuntime,
      workDir,
      extensionPaths: trustedCheckoutRoots(bundledExtensionCheckouts(packagesDir), ALLOWLISTED_PACKAGES),
      trustedPackages: [],
      copilot: buildCopilotExtension("QDash agent loop test prompt", []),
      internalCalls: {},
      codingTools: false,
    },
    connection,
  );
  const harness = await Harness.open(new MemoryStorage(), { models, registry: chat.registry, settings: { retry: { enabled: false } } }, context);
  const conversation = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id } } });
  harness.resume();
  return {
    async ask(text) {
      const submission = await conversation.submit({ type: "input", content: text }, context);
      await submission.wait(context);
    },
    async results() {
      const view = await conversation.context(context);
      return view.entries
        .filter((entry) => ToolResultEntry.is(entry))
        .map((entry) => entry.model[0])
        .map((message) => ({ name: message.toolName, text: textOf(message.content), details: message.details, isError: message.isError }));
    },
    /** The user approves a write in the approval card; the runtime runs it (server.ts submitInput). */
    approve: (approval) => chat.writeTools.runApproved(approval),
    async close() {
      await harness.close(context);
      await chat.close();
    },
  };
}

const HOSTS = [["cli", openCli], ["chat", openChat]];

/** pi's UI for a CLI session whose user answers each confirmation with `answers`, in order. */
function dialog(answers, asked = []) {
  return new Proxy(
    { confirm: async (title) => (asked.push(title), answers.shift() ?? false) },
    { get: (target, key) => (key in target ? target[key] : () => undefined) },
  );
}
const load = () => fauxAssistantMessage([fauxToolCall("tool_search", { query: LOOP_TOOLS.join(" "), limit: 25 })], { stopReason: "toolUse" });
const call = (name, args) => () => fauxAssistantMessage([fauxToolCall(name, typeof args === "function" ? args() : args)], { stopReason: "toolUse" });
const done = (text = "done") => fauxAssistantMessage([fauxText(text)]);

function autoSession(extra = {}) {
  return fake.createSession({
    chip_id: "chip-001",
    policy: {
      qids: ["Q00"],
      allowed_tasks: ["CheckRabi", "CheckChevron"],
      allowed_overrides: { qubit_frequency: { minimum: 7.4, maximum: 7.6 } },
      autonomy: "auto",
      max_actions: 6,
      ...extra,
    },
  }).session_id;
}

const sessionRequests = (sessionId, start) => fake.state.requests.slice(start).filter((request) => request.path.startsWith(`/agent-sessions/${sessionId}`));

test("creating a session waits for the user's approval in both hosts and sends nothing", async () => {
  const policy = { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "auto", max_actions: 4 };
  for (const [host, open] of HOSTS) {
    const start = fake.state.requests.length;
    const run = await open([load(), call("qdash_create_agent_session", { chipId: "chip-001", policy }), done()]);
    try {
      await run.ask("Q00 を校正して");
      const created = (await run.results()).find((result) => result.name === "qdash_create_agent_session");
      assert.ok(created, host);
      if (host === "cli") {
        assert.equal(created.isError, true);
        assert.match(created.text, /requires explicit confirmation: it is a QDash write the user approves in a confirmation dialog/);
      } else {
        assert.match(created.text, /^Approval requested/);
        assert.deepEqual(created.details.approval.args.policy, policy);
      }
      assert.ok(!fake.state.requests.slice(start).some((request) => request.method === "POST"), `${host} wrote before approval`);
    } finally {
      await run.close();
    }
  }
});

test("in both hosts an approved session records the host's model, never one the arguments name", async () => {
  const policy = { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "auto", max_actions: 4 };
  const args = { chipId: "chip-001", policy, modelName: "claimed/other-model" };
  for (const [host, open] of HOSTS) {
    const sessionsBefore = fake.state.sessions.size;
    const run = await open([load(), call("qdash_create_agent_session", args), done()], host === "cli" ? { ui: dialog([true]) } : {});
    try {
      await run.ask("Q00 を校正して");
      if (host === "chat") {
        const created = (await run.results()).find((result) => result.name === "qdash_create_agent_session");
        assert.deepEqual(created.details.approval.model, { provider: "faux", modelId: "faux-1" });
        await run.approve(created.details.approval);
      }
    } finally {
      await run.close();
    }
    assert.equal(fake.state.sessions.size, sessionsBefore + 1, host);
    const session = [...fake.state.sessions.values()].at(-1);
    assert.deepEqual(session.model, { provider: "faux", model_id: "faux-1", host: host === "cli" ? "pi" : "qdash-web-agent" }, host);
    assert.equal(session.model_name, "faux/faux-1", host);
    assert.deepEqual(session.policy.qids, ["Q00"], host);
  }
});

test("in both hosts the model runs a step, stops for an expert on an unknown result, and after a restart continues from QDash's records within the same scope", async () => {
  const outcomes = {};
  for (const [host, open] of HOSTS) {
    const sessionId = autoSession();
    const start = fake.state.requests.length;
    const dispatchStart = fake.state.dispatches.length;
    fake.queueOutcome("CheckRabi", { status: "completed", candidates: [{ parameter_name: "control_amplitude", value: 0.2, accepted: false }] });
    const lastAction = () => fake.state.actions.filter((action) => action.session_id === sessionId).at(-1).action_id;

    // First turn: measure, observe, find no documented next step, and ask a person.
    const first = await open([
      load(),
      call("qdash_get_agent_session_context", { sessionId }),
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi first, per the one-qubit skill." }),
      call("qdash_wait_agent_action", () => ({ sessionId, actionId: lastAction(), waitForExecution: true, timeoutSeconds: 5, pollIntervalSeconds: 0 })),
      call("qdash_get_agent_session_context", { sessionId }),
      call("qdash_request_agent_human", () => ({
        sessionId,
        reason: "unknown_outcome",
        summary: "CheckRabi shows a beating pattern the task knowledge does not cover.",
        question: "Is a second transition nearby, or should Chevron be rerun first?",
        taskName: "CheckRabi",
        qids: ["Q00"],
        attemptActionIds: [lastAction()],
      })),
      // While paused, a step and a flow are both refused.
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckChevron", qid: "Q00", rationale: "try anyway" }),
      done("Waiting for the expert in QDash."),
    ]);
    let firstResults;
    try {
      await first.ask("Q00 を校正して");
      firstResults = await first.results();
    } finally {
      await first.close();
    }
    const byName = (results, name) => results.filter((result) => result.name === name);
    const [step] = byName(firstResults, "qdash_run_agent_session_step");
    assert.match(step.text, /Dispatched action .*: CheckRabi on Q00; execution completed/, `${host}: ${step.text}`);
    assert.ok(!step.isError, host);
    const observed = byName(firstResults, "qdash_get_agent_session_context")[1];
    assert.match(observed.text, /candidate control_amplitude = 0\.2: rejected/, host);
    const [asked] = byName(firstResults, "qdash_request_agent_human");
    assert.match(asked.text, /The session is paused until an expert answers in QDash/, host);
    const refused = byName(firstResults, "qdash_run_agent_session_step")[1];
    assert.match(refused.text, /^Not run: The session is paused until an expert answers/, host);
    assert.equal(fake.state.sessions.get(sessionId).status, "waiting_for_human");

    // The expert answers in QDash, outside pi.
    fake.respond(sessionId, { guidance: "Beating means the frequency is off; run CheckChevron near 7.45 GHz first." });

    // A new pi process or chat: nothing from the first turn is in its context.
    const second = await open([
      load(),
      call("qdash_list_agent_sessions", { chipId: "chip-001" }),
      call("qdash_get_agent_session_context", { sessionId }),
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "resume where we stopped" }),
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.45 }, rationale: "Expert guidance: rerun Chevron near 7.45 GHz first." }),
      done(),
    ]);
    let secondResults;
    try {
      await second.ask("専門家が回答したので続けて");
      secondResults = await second.results();
    } finally {
      await second.close();
    }
    const [listed] = byName(secondResults, "qdash_list_agent_sessions");
    assert.match(listed.text, new RegExp(`${sessionId}: active`), host);
    const [reloaded] = byName(secondResults, "qdash_get_agent_session_context");
    assert.match(reloaded.text, /An expert answered intervention .* and the session is active again/, host);
    assert.match(reloaded.text, /Question asked: Is a second transition nearby/, host);
    assert.match(reloaded.text, /Guidance: Beating means the frequency is off/, host);
    assert.match(reloaded.text, /Rule: The expert's guidance is evidence/, host);
    const [replay, chevron] = byName(secondResults, "qdash_run_agent_session_step");
    assert.match(replay.text, /already ran this exact measurement/, `${host}: ${replay.text}`);
    assert.match(chevron.text, /Dispatched action .*: CheckChevron on Q00/, `${host}: ${chevron.text}`);

    const requests = sessionRequests(sessionId, start);
    // pi never answers, resumes, or reactivates; only the expert did.
    assert.ok(!requests.some((request) => /\/(respond|claim-resume|resume-outcome)$/.test(request.path)), host);
    const dispatched = fake.state.dispatches.slice(dispatchStart).map((run) => `${run.task_name}:${JSON.stringify(run.parameter_overrides)}`);
    assert.deepEqual(dispatched, ["CheckRabi:{}", 'CheckChevron:{"qubit_frequency":7.45}'], host);
    outcomes[host] = {
      dispatched,
      states: [...byName(firstResults, "qdash_get_agent_session_context"), reloaded].map((result) => result.details.state),
      refused: refused.details.state,
      replayRefused: replay.details.refused,
    };
  }
  assert.deepEqual(outcomes.cli, outcomes.chat);
  assert.deepEqual(outcomes.cli.states, ["ready", "ready", "ready"]);
  assert.equal(outcomes.cli.refused, "waiting_for_expert");
});

test("in both hosts a script can read the loop state but cannot run a step or ask for a person", async () => {
  const code = (sessionId) => `
const attempt = async (call) => { try { await call(); return "ran"; } catch (error) { return "refused"; } };
const outcome = {
  context: await attempt(() => tools.qdash_get_agent_session_context({ sessionId: ${JSON.stringify(sessionId)} })),
  step: await attempt(() => tools.qdash_run_agent_session_step({ sessionId: ${JSON.stringify(sessionId)}, taskName: "CheckRabi", qid: "Q00", rationale: "script" })),
  human: await attempt(() => tools.qdash_request_agent_human({ sessionId: ${JSON.stringify(sessionId)}, reason: "agent_request", summary: "s", question: "q" })),
};
text("RESULT " + JSON.stringify(outcome));
`;
  const outcomes = {};
  for (const [host, open] of HOSTS) {
    const sessionId = autoSession();
    const dispatchStart = fake.state.dispatches.length;
    const run = await open([call("codemode", { code: code(sessionId) }), done()]);
    try {
      await run.ask("script");
      const script = (await run.results()).find((result) => result.name === "codemode");
      const line = script.text.split("\n").find((item) => item.includes("RESULT "));
      assert.ok(line, `${host}: ${script.text}`);
      outcomes[host] = JSON.parse(line.slice(line.indexOf("RESULT ") + 7));
    } finally {
      await run.close();
    }
    assert.equal(fake.state.dispatches.length, dispatchStart, host);
    assert.equal(fake.state.sessions.get(sessionId).status, "active", host);
  }
  assert.deepEqual(outcomes.cli, { context: "ran", step: "refused", human: "refused" });
  assert.deepEqual(outcomes.chat, outcomes.cli);
});

test("in both hosts session-granted writes refuse another user's auto session and an unknown identity, and run in the user's own", async () => {
  const outcomes = {};
  for (const [host, open] of HOSTS) {
    // Same project, another editor created and approved this session.
    const theirs = fake.createSession(
      { chip_id: "chip-001", policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi"], autonomy: "auto", max_actions: 4 } },
      "bob",
    ).session_id;
    const own = autoSession();
    const confirmEach = fake.createSession({ chip_id: "chip-001", policy: { qids: ["Q00"], allowed_tasks: ["CheckRabi"], max_actions: 4 } }).session_id;
    const start = fake.state.requests.length;
    const run = await open([
      load(),
      call("qdash_run_agent_session_step", { sessionId: theirs, taskName: "CheckRabi", qid: "Q00", rationale: "continue bob's work" }),
      call("qdash_request_agent_human", { sessionId: theirs, reason: "agent_request", summary: "s", question: "q" }),
      call("qdash_run_agent_session_step", { sessionId: confirmEach, taskName: "CheckRabi", qid: "Q00", rationale: "x" }),
      () => {
        fake.setCurrentUser(null);
        return call("qdash_run_agent_session_step", { sessionId: own, taskName: "CheckRabi", qid: "Q00", rationale: "x" })();
      },
      () => {
        fake.setCurrentUser("alice");
        return call("qdash_run_agent_session_step", { sessionId: own, taskName: "CheckRabi", qid: "Q00", rationale: "mine" })();
      },
      done(),
    ]);
    let results;
    try {
      await run.ask("続けて");
      results = (await run.results()).filter((result) => result.name !== "tool_search");
    } finally {
      fake.setCurrentUser("alice");
      await run.close();
    }
    const [other, otherHuman, confirm, unknown, mine] = results;
    assert.match(other.text, /^Not run: Session .* was created by bob, not by you \(alice\)/, `${host}: ${other.text}`);
    assert.match(otherHuman.text, /^Not recorded: Session .* was created by bob/, host);
    assert.match(confirm.text, /confirm_each: every action needs the reviewed tools/, host);
    assert.match(unknown.text, /^Not run: QDash did not confirm who you are signed in as/, host);
    assert.match(mine.text, /Dispatched action .*: CheckRabi on Q00/, `${host}: ${mine.text}`);
    const writes = fake.state.requests.slice(start).filter((request) => request.method === "POST");
    // Only the user's own step wrote: one proposal and its dispatch, both autonomous.
    assert.deepEqual(writes.map((request) => [request.path.split("/").slice(1, 3).join("/"), request.body.autonomous]), [[`agent-sessions/${own}`, true], [`agent-sessions/${own}`, true]], host);
    assert.equal(fake.state.sessions.get(theirs).status, "active", host);
    outcomes[host] = results.map((result) => Boolean(result.details?.refused));
  }
  assert.deepEqual(outcomes.cli, [true, true, true, true, false]);
  assert.deepEqual(outcomes.chat, outcomes.cli);
});

test("in both hosts a dependent step reads a value only after the user approves its commit", async () => {
  const loadWithCommit = () => fauxAssistantMessage([fauxToolCall("tool_search", { query: [...LOOP_TOOLS, "qdash_commit_agent_candidate"].join(" "), limit: 25 })], { stopReason: "toolUse" });
  const outcomes = {};
  for (const [host, open] of HOSTS) {
    const sessionId = autoSession();
    const dispatchStart = fake.state.dispatches.length;
    // Each host starts from the same calibration state.
    delete fake.state.calibration.Q00;
    fake.queueOutcome("CheckChevron", { status: "completed", candidates: [{ parameter_name: "qubit_frequency", value: 7.452, qid: "Q00" }] });
    const chevronAction = () => fake.state.actions.filter((action) => action.session_id === sessionId && action.task_name === "CheckChevron").at(-1);
    const commitArgs = (extra = {}) => () => {
      const action = chevronAction();
      return { sessionId, actionId: action.action_id, parameterName: "qubit_frequency", taskId: action.candidates[0].task_id, expectedStateVersion: fake.state.sessions.get(sessionId).state_version, ...extra };
    };

    // Measure, observe the accepted candidate, and propose its commit: a reviewed write.
    const first = await open([
      loadWithCommit(),
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.45 }, rationale: "Find the frequency first." }),
      call("qdash_get_agent_session_context", { sessionId }),
      call("qdash_commit_agent_candidate", commitArgs()),
      done("Approve the commit to continue with Rabi on the new frequency."),
    ]);
    let firstResults;
    try {
      await first.ask("Q00 を校正して");
      firstResults = await first.results();
    } finally {
      await first.close();
    }
    const commit = firstResults.find((result) => result.name === "qdash_commit_agent_candidate");
    if (host === "cli") assert.match(commit.text, /requires explicit confirmation: it is a QDash write the user approves in a confirmation dialog/, host);
    else assert.match(commit.text, /^Approval requested/, host);
    // The step tool never commits, and an unapproved commit writes nothing.
    assert.deepEqual(fake.state.calibration.Q00 ?? {}, {}, host);
    assert.match(firstResults.find((result) => result.name === "qdash_get_agent_session_context").text, /candidate qubit_frequency = 7\.452: accepted/, host);

    // The user approves the commit (pi CLI: in pi's confirmation dialog; the web Agent's
    // approval runs the same reviewed call), then the loop continues on the committed value.
    if (host === "cli") {
      // A model that sets confirmWrite itself approves nothing: without a UI the commit is refused.
      const forged = await open([loadWithCommit(), call("qdash_commit_agent_candidate", commitArgs({ confirmWrite: true })), done()]);
      try {
        await forged.ask("コミットして");
        const refused = (await forged.results()).find((result) => result.name === "qdash_commit_agent_candidate");
        assert.equal(refused.isError, true);
        assert.match(refused.text, /requires explicit confirmation: it is a QDash write the user approves in a confirmation dialog/);
      } finally {
        await forged.close();
      }
      assert.deepEqual(fake.state.calibration.Q00 ?? {}, {}, host);
      // With a UI the dialog is asked even though the model set confirmWrite; declining writes nothing.
      const asked = [];
      const declined = await open([loadWithCommit(), call("qdash_commit_agent_candidate", commitArgs({ confirmWrite: true })), done()], { ui: dialog([false], asked) });
      try {
        await declined.ask("コミットして");
        const refused = (await declined.results()).find((result) => result.name === "qdash_commit_agent_candidate");
        assert.equal(refused.isError, true);
        assert.match(refused.text, /rejected by user/);
      } finally {
        await declined.close();
      }
      assert.deepEqual(fake.state.calibration.Q00 ?? {}, {}, host);
      const approved = await open([loadWithCommit(), call("qdash_commit_agent_candidate", commitArgs()), done()], { ui: dialog([true], asked) });
      try {
        await approved.ask("コミットを承認します");
        const committed = (await approved.results()).find((result) => result.name === "qdash_commit_agent_candidate");
        assert.ok(!committed.isError, committed.text);
      } finally {
        await approved.close();
      }
      // One dialog per call: the tool did not ask again after the gate's approval.
      assert.equal(asked.length, 2);
    } else {
      const args = commitArgs()();
      const response = await fetch(`${fake.baseUrl}/agent-sessions/${sessionId}/actions/${args.actionId}/candidates/qubit_frequency/commit`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ idempotency_key: "approved", expected_state_version: args.expectedStateVersion, task_id: args.taskId }),
      });
      assert.equal(response.status, 200);
    }
    assert.deepEqual(fake.state.calibration.Q00, { qubit_frequency: 7.452 }, host);

    const second = await open([
      load(),
      call("qdash_get_agent_session_context", { sessionId }),
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi on the committed frequency." }),
      done(),
    ]);
    let secondResults;
    try {
      await second.ask("続けて");
      secondResults = await second.results();
    } finally {
      await second.close();
    }
    const rabi = secondResults.find((result) => result.name === "qdash_run_agent_session_step");
    assert.match(rabi.text, /Dispatched action .*: CheckRabi on Q00/, `${host}: ${rabi.text}`);
    const runs = fake.state.dispatches.slice(dispatchStart);
    // Chevron ran on the old state; Rabi reads the committed frequency as its input.
    assert.deepEqual(runs.map((run) => [run.task_name, run.calibration]), [["CheckChevron", {}], ["CheckRabi", { qubit_frequency: 7.452 }]], host);
    outcomes[host] = runs.map((run) => run.calibration);
  }
  assert.deepEqual(outcomes.chat, outcomes.cli);
});

test("in both hosts each step's decision and the agent's own notes reach the audit without a card, and a script can read the audit but not write it", async () => {
  const outcomes = {};
  for (const [host, open] of HOSTS) {
    const sessionId = autoSession();
    const commitsBefore = fake.state.commits.length;
    fake.queueOutcome("CheckChevron", { status: "completed", candidates: [{ parameter_name: "qubit_frequency", value: 7.452, qid: "Q00" }] });
    const run = await open([
      load(),
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.45 }, rationale: "Find the frequency first." }),
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi next.", assessment: "pass", interpretation: "Chevron peak at 7.452 GHz; the gate accepted it." }),
      call("qdash_record_agent_decision", () => ({ sessionId, assessment: "pass", interpretation: "Both results pass; propose committing qubit_frequency.", nextAction: "propose_commit", evidenceActionIds: fake.state.actions.filter((action) => action.session_id === sessionId).map((action) => action.action_id) })),
      call("qdash_get_agent_session_audit", { sessionId }),
      call("codemode", {
        code: `
const attempt = async (call) => { try { await call(); return "ran"; } catch (error) { return "refused"; } };
text("RESULT " + JSON.stringify({
  audit: await attempt(() => tools.qdash_get_agent_session_audit({ sessionId: ${JSON.stringify(sessionId)} })),
  record: await attempt(() => tools.qdash_record_agent_decision({ sessionId: ${JSON.stringify(sessionId)}, interpretation: "script", nextAction: "stop" })),
}));
`,
      }),
      done(),
    ]);
    let results;
    try {
      await run.ask("Q00 を校正して");
      results = (await run.results()).filter((result) => result.name !== "tool_search");
    } finally {
      await run.close();
    }
    const [chevron, rabi, note, audit, script] = results;
    assert.match(chevron.text, /Dispatched action .*: CheckChevron on Q00/, `${host}: ${chevron.text}`);
    assert.match(rabi.text, /Audit: recorded decision decision-\d+ on action-\d+ \(next next_task\)/, `${host}: ${rabi.text}`);
    assert.match(note.text, /^Recorded decision decision-\d+: pass; next propose_commit/, `${host}: ${note.text}`);
    // Each record names the host's model, read from the host, never from an argument.
    const label = host === "cli" ? "pi" : "qdash-web-agent";
    assert.match(audit.text, new RegExp(`decision \\[agent_reported, alice\\] \\{model faux/faux-1 via ${label}\\}: Assessed pass; next next_task: CheckRabi on Q00`), host);
    for (const record of [...fake.state.actions.filter((action) => action.session_id === sessionId), ...fake.state.decisions.filter((decision) => decision.session_id === sessionId)]) {
      assert.deepEqual(record.model, { provider: "faux", model_id: "faux-1", host: label }, host);
    }
    assert.match(audit.text, /The timeline of snapshot [0-9a-f]+ is complete; records written after the snapshot was taken are not in it/, host);
    const line = script.text.split("\n").find((item) => item.includes("RESULT "));
    assert.ok(line, `${host}: ${script.text}`);
    const decisions = fake.state.decisions.filter((decision) => decision.session_id === sessionId);
    // Two decisions, none from the script; nothing was committed.
    assert.equal(decisions.length, 2, host);
    assert.equal(fake.state.commits.length, commitsBefore, host);
    outcomes[host] = {
      script: JSON.parse(line.slice(line.indexOf("RESULT ") + 7)),
      decisions: decisions.map((decision) => [decision.assessment, decision.next_action, decision.evidence_action_ids.length, Boolean(decision.next_action_id)]),
      kinds: audit.details ? audit.text.split("\n").filter((item) => item.startsWith("- #")).map((item) => item.split(" ")[3]) : [],
    };
  }
  assert.deepEqual(outcomes.cli.script, { audit: "ran", record: "refused" });
  assert.deepEqual(outcomes.cli.decisions, [["pass", "next_task", 1, true], ["pass", "propose_commit", 2, false]]);
  assert.deepEqual(outcomes.chat, outcomes.cli);
});

test("in both hosts a step dispatches only after QDash confirms its decision, and an escalation pauses even when the audit is full", async () => {
  const outcomes = {};
  for (const [host, open] of HOSTS) {
    const sessionId = autoSession();
    fake.queueOutcome("CheckChevron", { status: "completed", candidates: [{ parameter_name: "qubit_frequency", value: 7.452, qid: "Q00" }] });
    const rabi = { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi next.", assessment: "pass", interpretation: "Chevron peak at 7.452 GHz." };
    const run = await open([
      load(),
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.45 }, rationale: "Find the frequency first." }),
      () => {
        // QDash stores the decision but its answer is lost.
        fake.failDecisions({ status: 500, detail: "Internal Server Error", afterStore: true });
        return call("qdash_run_agent_session_step", rabi)();
      },
      call("qdash_run_agent_session_step", rabi),
      () => {
        fake.setDecisionQuota(fake.state.decisions.filter((decision) => decision.session_id === sessionId).length);
        return call("qdash_request_agent_human", { sessionId, reason: "policy_limit", summary: "The audit holds no more decisions.", question: "Continue in a new session?" })();
      },
      done(),
    ]);
    let results;
    try {
      await run.ask("Q00 を校正して");
      results = (await run.results()).filter((result) => result.name !== "tool_search");
    } finally {
      await run.close();
      fake.setDecisionQuota(2000);
      fake.failDecisions();
    }
    const [chevron, unconfirmed, recovered, asked] = results;
    assert.equal(chevron.details.dispatched, true, `${host}: ${chevron.text}`);
    assert.match(unconfirmed.text, /^Not dispatched: QDash did not confirm the audit decision this step follows/, `${host}: ${unconfirmed.text}`);
    assert.equal(unconfirmed.details.decisionRecorded, false, host);
    assert.equal(recovered.details.dispatched, true, `${host}: ${recovered.text}`);
    assert.equal(recovered.details.actionId, unconfirmed.details.actionId, host);
    assert.match(recovered.text, /Audit: decision decision-\d+ was already recorded for this step/, host);
    assert.match(asked.text, /The session is paused until an expert answers/, `${host}: ${asked.text}`);
    assert.match(asked.text, /Audit: the escalation decision was NOT recorded: QDash refused it .*audit is full/s, host);
    assert.equal(fake.state.sessions.get(sessionId).status, "waiting_for_human", host);
    const actions = fake.state.actions.filter((action) => action.session_id === sessionId);
    outcomes[host] = {
      actions: actions.length,
      dispatches: fake.state.dispatches.filter((entry) => actions.some((action) => action.action_id === entry.action_id)).length,
      decisions: fake.state.decisions.filter((decision) => decision.session_id === sessionId).map((decision) => [decision.next_action, decision.next_action_id === recovered.details.actionId]),
      details: [unconfirmed, recovered, asked].map((result) => [result.details.refused ?? false, result.details.dispatched ?? false, result.details.decisionRecorded, result.details.decisionOutcome ?? null, result.details.auditFull ?? false]),
    };
  }
  assert.deepEqual(outcomes.cli.actions, 2);
  assert.deepEqual(outcomes.cli.dispatches, 2);
  assert.deepEqual(outcomes.cli.decisions, [["next_task", true]]);
  assert.deepEqual(outcomes.chat, outcomes.cli);
});

test("in both hosts update authority is approved once with the session, then passing results commit without a card and failures pause before any dependent step", async () => {
  const grant = { parameters: ["qubit_frequency"], tasks: ["CheckChevron"], apply_backend: false };
  const outcomes = {};
  for (const [host, open] of HOSTS) {
    // The grant is part of the one session approval the user sees.
    const policy = { qids: ["Q00"], allowed_tasks: ["CheckChevron", "CheckRabi"], allowed_overrides: { qubit_frequency: { minimum: 7.4, maximum: 7.6 } }, autonomy: "auto", max_actions: 4, parameter_updates: grant };
    const asking = await open([load(), call("qdash_create_agent_session", { chipId: "chip-001", policy, expiresInSeconds: 3600 }), done()]);
    try {
      await asking.ask("Q00 の周波数を校正して Rabi まで確認して");
      const created = (await asking.results()).find((result) => result.name === "qdash_create_agent_session");
      if (host === "cli") assert.match(created.text, /requires explicit confirmation: it is a QDash write the user approves in a confirmation dialog/, host);
      else assert.deepEqual(created.details?.approval?.args?.policy?.parameter_updates, grant, `${host}: ${created.text}`);
    } finally {
      await asking.close();
    }

    // The approved session (created here as the approval would), then the loop without cards.
    const sessionId = autoSession({ parameter_updates: grant });
    const dispatchStart = fake.state.dispatches.length;
    delete fake.state.calibration.Q00;
    fake.queueOutcome("CheckChevron", { status: "completed", candidates: [{ parameter_name: "qubit_frequency", value: 7.452, qid: "Q00" }] });
    const chevronId = () => fake.state.actions.filter((action) => action.session_id === sessionId && action.task_name === "CheckChevron").at(-1).action_id;
    const run = await open([
      load(),
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.45 }, rationale: "Find the frequency first." }),
      call("qdash_commit_agent_session_update", () => ({ sessionId, actionId: chevronId(), parameterName: "qubit_frequency", interpretation: "Clear Chevron peak at 7.452 GHz inside the approved range." })),
      call("qdash_run_agent_session_step", { sessionId, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi on the committed frequency." }),
      call("codemode", {
        code: `
let outcome = "ran";
try { await tools.qdash_commit_agent_session_update({ sessionId: ${JSON.stringify(sessionId)}, actionId: "x", parameterName: "qubit_frequency", interpretation: "script" }); } catch (error) { outcome = "refused"; }
text("RESULT " + outcome);
`,
      }),
      done(),
    ]);
    let results;
    try {
      await run.ask("続けて");
      results = (await run.results()).filter((result) => result.name !== "tool_search");
    } finally {
      await run.close();
    }
    const [chevron, update, rabi, script] = results;
    assert.equal(chevron.details.dispatched, true, `${host}: ${chevron.text}`);
    assert.equal(update.details.committed, true, `${host}: ${update.text}`);
    assert.doesNotMatch(update.text, /Approval requested/, host);
    assert.equal(rabi.details.dispatched, true, `${host}: ${rabi.text}`);
    assert.ok(script.text.includes("RESULT refused"), `${host}: ${script.text}`);
    const runs = fake.state.dispatches.slice(dispatchStart);

    // A failed measurement: no update, no dependent step, and the session pauses for a person.
    const failedSession = autoSession({ parameter_updates: grant });
    fake.queueOutcome("CheckChevron", { status: "failed", candidates: [] });
    const failedId = () => fake.state.actions.filter((action) => action.session_id === failedSession).at(0).action_id;
    const failing = await open([
      load(),
      call("qdash_run_agent_session_step", { sessionId: failedSession, taskName: "CheckChevron", qid: "Q00", parameterOverrides: { qubit_frequency: 7.45 }, rationale: "Find the frequency first." }),
      call("qdash_run_agent_session_step", { sessionId: failedSession, taskName: "CheckRabi", qid: "Q00", rationale: "Rabi anyway." }),
      call("qdash_request_agent_human", () => ({ sessionId: failedSession, reason: "unknown_outcome", summary: "Chevron failed without a known cause.", question: "How should I continue?", attemptActionIds: [failedId()] })),
      done(),
    ]);
    let failedResults;
    try {
      await failing.ask("Q00 を校正して");
      failedResults = (await failing.results()).filter((result) => result.name !== "tool_search");
    } finally {
      await failing.close();
    }
    const [, blocked, asked] = failedResults;
    assert.match(blocked.text, /did not complete \(failed\)/, `${host}: ${blocked.text}`);
    assert.match(asked.text, /The session is paused until an expert answers/, `${host}: ${asked.text}`);
    assert.equal(fake.state.sessions.get(failedSession).status, "waiting_for_human", host);
    outcomes[host] = {
      runs: runs.map((entry) => [entry.task_name, entry.calibration]),
      commits: fake.state.commits.filter((commit) => commit.session_id === sessionId).map((commit) => [commit.parameter_name, commit.value, commit.authority]),
      failedCommits: fake.state.commits.filter((commit) => commit.session_id === failedSession).length,
      failedDispatches: fake.state.dispatches.filter((entry) => fake.state.actions.some((action) => action.session_id === failedSession && action.action_id === entry.action_id)).map((entry) => entry.task_name),
    };
  }
  assert.deepEqual(outcomes.cli, {
    runs: [["CheckChevron", {}], ["CheckRabi", { qubit_frequency: 7.452 }]],
    commits: [["qubit_frequency", 7.452, "session_policy"]],
    failedCommits: 0,
    failedDispatches: ["CheckChevron"],
  });
  assert.deepEqual(outcomes.chat, outcomes.cli);
});
