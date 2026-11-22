/**
 * The deterministic parts of the fake-backend agent loop validation
 * (agent-runtime/validation/fake-loop/): the harness's approval policy, the
 * guard extension inside a real pi session, the RPC driver, the evaluator, the
 * fail-closed preflight, and the report. No model, QDash deployment, or
 * credentials are used; the real-model run is opt-in and not part of CI.
 */

import assert from "node:assert/strict";
import { createServer } from "node:http";
import { existsSync, fstatSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { after, before, test } from "node:test";

import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";

import { startFakeAgentQDash } from "../../packages/pi-qdash/tests/helpers/fake-agent-qdash.mjs";
import { inZone } from "../../packages/pi-qdash/tests/helpers/time-zone.mjs";
import { bundledExtensions } from "../src/bundled-extensions.ts";
import { decideApproval } from "../validation/fake-loop/approval.ts";
import { evaluateScenario, numberForms } from "../validation/fake-loop/evaluate.ts";
import { GUARD_MESSAGES, guardToolCall } from "../validation/fake-loop/guard-extension.ts";
import { isLoopbackUrl, listChipExecutions, listScenarioSessions, preflight, QDashApi, sessionsCreatedSince } from "../validation/fake-loop/qdash-api.ts";
import { prepareLocalCli } from "../src/local-cli.ts";
import { effectiveSecrets, redact, renderMarkdown, secretValues } from "../validation/fake-loop/report.ts";
import { classifyOutcome, compactArgs, lineSplitter, runPrompt } from "../validation/fake-loop/rpc-driver.ts";
import { armFault, disarmFault, FaultFileError, faultPath, launchFor, main, parseOptions, writeSessionArtifacts } from "../validation/fake-loop/run.ts";
import { SCENARIOS, selectScenarios } from "../validation/fake-loop/scenarios.ts";

const target = { chipId: "agentval-loop", qid: "4" };
const packagesDir = fileURLToPath(new URL("../../packages/", import.meta.url));
const guardPath = fileURLToPath(new URL("../validation/fake-loop/guard-extension.ts", import.meta.url));
const fakePi = fileURLToPath(new URL("./helpers/fake-pi-rpc.mjs", import.meta.url));

let workDir;
before(() => {
  workDir = mkdtempSync(join(tmpdir(), "qdash-fake-loop-"));
});
after(() => rmSync(workDir, { recursive: true, force: true }));

// ---------------------------------------------------------------- approvals

const sessionArgs = (policy = {}, extra = {}) => ({
  chipId: target.chipId,
  policy: { qids: ["4"], allowed_tasks: ["CheckT1"], autonomy: "auto", max_actions: 3, ...policy },
  expiresInSeconds: 1800,
  ...extra,
});
const context = (scenario, sessions = []) => ({ target, plan: SCENARIOS[scenario].approvals, scenarioSessionIds: new Set(sessions) });

test("the harness approves only a session inside the scenario's scope", () => {
  const ok = decideApproval({ toolName: "qdash_create_agent_session", args: sessionArgs() }, context("t1-rerun"));
  assert.equal(ok.approve, true);
  const refused = [
    sessionArgs({}, { chipId: "64Q" }),
    { ...sessionArgs(), chipId: undefined },
    sessionArgs({ qids: ["4", "5"] }),
    sessionArgs({ qids: ["Q04"] }),
    sessionArgs({ allowed_tasks: ["CheckT1", "CheckRabi"] }),
    sessionArgs({ max_actions: 50 }),
    sessionArgs({ allow_reconfigure: true }),
    sessionArgs({}, { expiresInSeconds: 86_400 }),
    sessionArgs({}, { profile: "production" }),
    { chipId: target.chipId },
  ];
  for (const args of refused) {
    assert.equal(decideApproval({ toolName: "qdash_create_agent_session", args }, context("t1-rerun")).approve, false, JSON.stringify(args));
  }
  // QDash gives a session without an expiry its 6-hour default, so the expiry must be explicit
  // and within the scenario's bound (and no shorter than QDash accepts).
  const { expiresInSeconds: _omit, ...noExpiry } = sessionArgs();
  for (const expiresInSeconds of [undefined, null, "1800", 0, -60, 59, 3601, 1800.5, Number.NaN, Number.POSITIVE_INFINITY, true]) {
    const args = expiresInSeconds === undefined ? noExpiry : sessionArgs({}, { expiresInSeconds });
    const decision = decideApproval({ toolName: "qdash_create_agent_session", args }, context("t1-rerun"));
    assert.equal(decision.approve, false, String(expiresInSeconds));
    assert.match(decision.reason, /expiresInSeconds from 60 to 3600/);
  }
  for (const expiresInSeconds of [60, 3600]) {
    assert.equal(decideApproval({ toolName: "qdash_create_agent_session", args: sessionArgs({}, { expiresInSeconds }) }, context("t1-rerun")).approve, true, String(expiresInSeconds));
  }
  // A question about a stored value approves no session at all.
  assert.equal(decideApproval({ toolName: "qdash_create_agent_session", args: sessionArgs() }, context("stored-t1")).approve, false);
});

test("update authority is approved only with the dependent scenario's session, exactly as planned, and no commit is approved per call", () => {
  const grant = { parameters: ["qubit_frequency"], tasks: ["CheckChevron"], apply_backend: false };
  const dependent = (policy = {}) =>
    sessionArgs({ allowed_tasks: ["CheckChevron", "CheckRabi"], allowed_overrides: { qubit_frequency: { minimum: 7.0, maximum: 8.5 } }, max_actions: 4, parameter_updates: grant, ...policy });
  const approve = (args, scenario = "dependent-commit") => decideApproval({ toolName: "qdash_create_agent_session", args }, context(scenario)).approve;
  assert.equal(approve(dependent()), true);
  // Widened or vague grants, and grants in scenarios that approve none, are declined.
  assert.equal(approve(dependent({ parameter_updates: { ...grant, parameters: ["qubit_frequency", "control_amplitude"] } })), false);
  assert.equal(approve(dependent({ parameter_updates: { ...grant, tasks: ["CheckChevron", "CheckRabi"] } })), false);
  assert.equal(approve(dependent({ parameter_updates: { ...grant, apply_backend: true } })), false);
  assert.equal(approve(dependent({ allowed_overrides: { qubit_frequency: { minimum: 7.0 } } })), false);
  assert.equal(approve(dependent({ parameter_updates: "all" })), false);
  assert.equal(approve(sessionArgs({ parameter_updates: { parameters: ["t1"], tasks: ["CheckT1"] } }), "t1-rerun"), false);
  assert.equal(approve(sessionArgs({ parameter_updates: { parameters: ["t1"], tasks: ["CheckT1"] } }), "unknown-failure"), false);
  // A session without a grant stays approvable; its commits then need approval the harness never gives.
  assert.equal(approve(dependent({ parameter_updates: undefined })), true);
  const commit = { toolName: "qdash_commit_agent_candidate", args: { sessionId: "s-1", actionId: "a-1", parameterName: "qubit_frequency", taskId: "t-1", expectedStateVersion: 2 } };
  const set = { toolName: "qdash_commit_agent_candidate_set", args: { sessionId: "s-1", candidates: [{ action_id: "a", parameter_name: "qubit_frequency", task_id: "t" }], expectedStateVersion: 2 } };
  for (const request of [commit, set]) {
    const decision = decideApproval(request, context("dependent-commit", ["s-1"]));
    assert.equal(decision.approve, false);
    assert.match(decision.reason, /approved with the session, not per call/);
  }
  for (const toolName of ["qdash_apply_agent_candidate_commit", "qdash_run_pipeline", "qdash_execute_flow", "qdash_submit_agent_action", "qdash_create_forum_post"]) {
    assert.equal(decideApproval({ toolName, args: { sessionId: "s-1" } }, context("dependent-commit", ["s-1"])).approve, false, toolName);
  }
});

// ---------------------------------------------------------------- guard

test("the guard refuses other connections and calls beyond the budget, and leaves write approval to pi-qdash", () => {
  // pi-qdash ignores a model's confirmWrite itself; the guard does not need to refuse it.
  assert.equal(guardToolCall("qdash_create_agent_session", { confirmWrite: true }, 0, 10), undefined);
  assert.deepEqual(guardToolCall("qdash_get_chip", { profile: "prod" }, 0, 10), { block: true, reason: GUARD_MESSAGES.connection });
  assert.deepEqual(guardToolCall("qdash_get_chip", { useEnv: false }, 0, 10), { block: true, reason: GUARD_MESSAGES.connection });
  assert.deepEqual(guardToolCall("read", {}, 10, 10), { block: true, reason: GUARD_MESSAGES.budget });
  assert.equal(guardToolCall("qdash_create_agent_session", { chipId: "agentval-loop" }, 0, 10), undefined);
  assert.equal(guardToolCall("qdash_run_agent_session_step", { sessionId: "s" }, 9, 10), undefined);
});

test("in a guarded pi session every reviewed write reaches the approval dialog, whatever confirmWrite the model sets", async () => {
  const fake = await startFakeAgentQDash();
  const saved = { ...process.env };
  process.env.QDASH_BASE_URL = fake.baseUrl;
  process.env.QDASH_API_TOKEN = "fixture-token";
  process.env.QDASH_VALIDATION_GUARD = "1";
  process.env.QDASH_VALIDATION_MAX_TOOL_CALLS = "10";
  const policy = { qids: ["4"], allowed_tasks: ["CheckT1"], autonomy: "auto", max_actions: 3 };
  const create = (extra) => fauxAssistantMessage([fauxToolCall("qdash_create_agent_session", { chipId: "agentval-loop", policy, ...extra })], { stopReason: "toolUse" });
  const faux = fauxProvider({ tokensPerSecond: 0 });
  faux.setResponses([create({ confirmWrite: true }), create({}), create({}), fauxAssistantMessage([fauxText("done")])]);
  const model = faux.getModel();
  const agentDir = join(workDir, "guard-agent");
  const loader = new DefaultResourceLoader({
    cwd: workDir,
    agentDir,
    additionalExtensionPaths: [guardPath, ...bundledExtensions(packagesDir).map(({ path }) => path)],
    extensionFactories: [
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
  const confirms = [];
  const answers = [false, false, true];
  const ui = new Proxy(
    { confirm: async (title) => (confirms.push(title), answers.shift() ?? false) },
    { get: (target, key) => (key in target ? target[key] : () => undefined) },
  );
  try {
    await loader.reload();
    assert.deepEqual(loader.getExtensions().errors, []);
    const modelRuntime = await ModelRuntime.create({ authPath: join(workDir, "auth.json"), modelsPath: null, refreshOnCreate: false });
    const { session } = await createAgentSession({ cwd: workDir, agentDir, resourceLoader: loader, sessionManager: SessionManager.inMemory(), settingsManager: SettingsManager.inMemory(), modelRuntime });
    await session.bindExtensions({ uiContext: ui, mode: "rpc" });
    await session.setModel(modelRuntime.getModel(model.provider, model.id));
    await session.prompt("Measure T1 again on qubit 4 of chip agentval-loop.");
    const results = session.messages.filter((message) => message.role === "toolResult");
    const text = (message) => message.content.map((block) => block.text ?? "").join("");
    // 1: the model's own confirmWrite skips nothing: the dialog is asked and declined.
    assert.equal(results[0].isError, true);
    assert.match(text(results[0]), /rejected by user/);
    // 2: asked and declined; 3: asked and approved, then QDash creates the session.
    assert.equal(results[1].isError, true);
    assert.equal(results[2].isError, false);
    assert.equal(confirms.length, 3);
    const posts = fake.state.requests.filter((request) => request.method === "POST" && request.path === "/agent-sessions");
    assert.equal(posts.length, 1);
    session.dispose();
  } finally {
    // Restore in place: replacing process.env with a plain object would detach it from the
    // runtime, so a later change (such as TZ) would no longer take effect.
    for (const key of Object.keys(process.env)) if (!(key in saved)) delete process.env[key];
    Object.assign(process.env, saved);
    await fake.close();
  }
});

// ---------------------------------------------------------------- RPC driver

test("records split on LF only and long arguments are cut", () => {
  const lines = [];
  const split = lineSplitter((line) => lines.push(line));
  split('{"a":"x y"}\n{"b"');
  split(":1}\r\n");
  assert.deepEqual(lines, ['{"a":"x y"}', '{"b":1}']);
  assert.equal(compactArgs({ text: "z".repeat(1000) }).text.length, 603);
  assert.equal(classifyOutcome(true, { content: [{ type: "text", text: GUARD_MESSAGES.budget }] }), "guard_blocked");
  assert.equal(classifyOutcome(true, { content: [{ type: "text", text: "QDash write operation rejected by user" }] }), "declined");
  assert.equal(classifyOutcome(true, { content: [{ type: "text", text: "boom" }] }), "error");
});

test("the driver answers a confirm for the one pending reviewed write and keeps no tool result text", async () => {
  const seen = [];
  const transcript = await runPrompt({
    command: process.execPath,
    args: [fakePi],
    env: { ...process.env, FAKE_PI_MODE: "approve" },
    prompt: "hello",
    timeoutMs: 10_000,
    onDialog: async (request, call) => {
      seen.push({ title: request.title, call });
      return { confirmed: true, reason: "test approval" };
    },
  });
  assert.equal(transcript.settled, true);
  assert.equal(transcript.timedOut, false);
  assert.equal(seen.length, 1);
  assert.equal(seen[0].call.toolName, "qdash_create_agent_session");
  assert.deepEqual(transcript.approvals, [{ title: "Approve QDash write operation?", toolName: "qdash_create_agent_session", toolCallId: "call-1", confirmed: true, reason: "test approval" }]);
  assert.deepEqual(transcript.toolCalls.map((call) => [call.toolName, call.outcome]), [["qdash_get_chip", "ok"], ["qdash_create_agent_session", "ok"]]);
  assert.equal(transcript.toolCalls[1].args.policy.note.length, 603);
  assert.equal(transcript.finalText, "Stored T1 is 25.3 us. Done.");
  assert.equal(transcript.totalTokens, 42);
  assert.ok(!JSON.stringify(transcript).includes("\"created\""));
});

test("a declined dialog is recorded and a run that never settles is aborted at its deadline", async () => {
  const declined = await runPrompt({ command: process.execPath, args: [fakePi], env: { ...process.env, FAKE_PI_MODE: "approve" }, prompt: "x", timeoutMs: 10_000, onDialog: async () => ({ confirmed: false, reason: "no" }) });
  assert.equal(declined.toolCalls[1].outcome, "declined");
  const hung = await runPrompt({ command: process.execPath, args: [fakePi], env: { ...process.env, FAKE_PI_MODE: "hang" }, prompt: "x", timeoutMs: 300, onDialog: async () => ({ confirmed: true, reason: "" }) });
  assert.equal(hung.timedOut, true);
  assert.equal(hung.aborted, true);
});

// ---------------------------------------------------------------- evaluator

const T0 = Date.parse("2026-11-22T10:00:00Z");
const at = (seconds) => new Date(T0 + seconds * 1000).toISOString();
const transcript = (extra = {}) => ({ toolCalls: [], approvals: [], finalText: "answer", settled: true, timedOut: false, aborted: false, exitCode: 0, durationMs: 1, totalTokens: 1, extensionErrors: 0, stderrLines: 0, ...extra });

// A dispatched measurement. `startedAt` is when its execution started (one second after the
// proposal unless given); the graph, audit, and chip execution fixtures read it.
const action = (id, task, seconds, status = "completed", startedAt = seconds + 1) => ({ action_id: id, action_type: "run_task", task_name: task, qids: ["4"], execution_status: status, execution_id: `e-${id}`, created_at: at(seconds), _startedAt: at(startedAt) });
const apiAction = ({ _startedAt, ...rest }) => rest;

function sessionEvidence({ id = "s-1", tasks = ["CheckT1"], actions = [], commits = [], interventions = [], extraEvents = [], repeats = {} } = {}) {
  const measured = actions.filter((item) => item.execution_status !== "not_started");
  return {
    session: { session_id: id, chip_id: target.chipId, created_by: "alice", status: "active", state_version: 3, policy: { qids: ["4"], allowed_tasks: tasks, autonomy: "auto", max_actions: 3 } },
    actions: actions.map(apiAction),
    interventions,
    commits,
    audit: {
      events: [
        ...measured.map((item) => ({ kind: "measurement", action_id: item.action_id, execution_id: item.execution_id, provenance: "server_record", status: item.execution_status, task_id: `t-${item.action_id}`, task_name: item.task_name, qid: "4" })),
        ...extraEvents,
      ],
    },
    graph: {
      nodes: measured.map((item) => ({
        node_id: `measurement:${item.action_id}`,
        kind: "measurement",
        at: item._startedAt,
        status: item.execution_status,
        missing: [],
        measurement: { action_id: item.action_id, task_name: item.task_name, qid: "4", dispatch_status: item.execution_status, execution_id: item.execution_id, execution_status: item.execution_status, task_id: `t-${item.action_id}`, task_status: item.execution_status, started_at: item._startedAt, repeat_of_action_id: repeats[item.action_id] ?? null },
      })),
    },
  };
}
// The chip's execution record of each action, linked to it.
const executionsOf = (actions, session = "s-1") => actions.map((item) => ({ execution_id: item.execution_id, status: item.execution_status, start_at: item._startedAt, agent_session: { session_id: session, linked: true, action_id: item.action_id } }));
const approval = (toolCallId, toolName) => ({ title: "Approve", toolName, toolCallId, confirmed: true, reason: "ok" });
const created = transcript({
  toolCalls: [{ toolCallId: "c1", toolName: "qdash_create_agent_session", args: {}, outcome: "ok" }],
  approvals: [approval("c1", "qdash_create_agent_session")],
});
const evaluate = (scenario, extra) => evaluateScenario({ scenario: SCENARIOS[scenario], target, username: "alice", startedAt: at(0), initial: transcript(), sessions: [], chipExecutions: [], ...extra });
const failedChecks = (verdict) => verdict.checks.filter((check) => check.gating && !check.passed).map((check) => check.id);
const actual = (verdict, id) => verdict.checks.find((check) => check.id === id)?.actual;

test("a stored-value question passes without measuring, and the reported answer never gates", () => {
  const pass = evaluate("stored-t1", { storedT1: 25.312, initial: transcript({ finalText: "T1 is 25.31 us" }) });
  assert.equal(pass.status, "passed");
  assert.equal(pass.checks.find((check) => check.id === "reported_stored_value").passed, true);
  const unquoted = evaluate("stored-t1", { storedT1: 25.312, initial: transcript({ finalText: "T1 looks fine" }) });
  assert.equal(unquoted.status, "passed");
  assert.equal(unquoted.checks.find((check) => check.id === "reported_stored_value").gating, false);
  const actions = [action("a1", "CheckT1", 5)];
  const measured = evaluate("stored-t1", { initial: created, sessions: [sessionEvidence({ actions })], chipExecutions: executionsOf(actions) });
  assert.equal(measured.status, "failed");
  assert.deepEqual(failedChecks(measured).sort(), ["measurement_count", "measurements_in_scope", "session_count", "session_scope:s-1"].sort());
  assert.deepEqual(numberForms(25.312), ["25", "25.3", "25.31", "25.312"]);
});

test("a T1 rerun passes with one linked, audited T1 measurement and fails on anything more", () => {
  const one = [action("a1", "CheckT1", 5)];
  const ok = evaluate("t1-rerun", { initial: created, sessions: [sessionEvidence({ actions: one })], chipExecutions: executionsOf(one) });
  assert.deepEqual(failedChecks(ok), []);
  assert.equal(ok.status, "passed");

  const two = [action("a1", "CheckT1", 5), action("a2", "CheckRabi", 9)];
  const extra = evaluate("t1-rerun", { initial: created, sessions: [sessionEvidence({ tasks: ["CheckT1", "CheckRabi"], actions: two })], chipExecutions: executionsOf(two) });
  assert.ok(failedChecks(extra).includes("measurement_count"));
  assert.ok(failedChecks(extra).includes("measurements_in_scope"));
  assert.ok(failedChecks(extra).includes("session_scope:s-1"));

  const unlinked = evaluate("t1-rerun", { initial: created, sessions: [sessionEvidence({ actions: one })], chipExecutions: [...executionsOf(one), { execution_id: "e-flow", status: "completed", start_at: at(3), agent_session: null }] });
  assert.deepEqual(failedChecks(unlinked), ["no_unlinked_executions"]);

  const unapproved = evaluate("t1-rerun", { initial: transcript({ toolCalls: [{ toolCallId: "c1", toolName: "qdash_create_agent_session", args: {}, outcome: "ok" }] }), sessions: [sessionEvidence({ actions: one })], chipExecutions: executionsOf(one) });
  assert.deepEqual(failedChecks(unapproved), ["reviewed_writes_approved"]);

  const noGraph = sessionEvidence({ actions: one });
  noGraph.graph.nodes = [];
  assert.deepEqual(failedChecks(evaluate("t1-rerun", { initial: created, sessions: [noGraph], chipExecutions: executionsOf(one) })).sort(), ["graph_and_audit:a1", "measured:CheckT1", "measurement_completed:a1"]);

  const timedOut = evaluate("t1-rerun", { initial: { ...created, settled: false, timedOut: true, finalText: "" }, sessions: [sessionEvidence({ actions: one })], chipExecutions: executionsOf(one) });
  assert.deepEqual(failedChecks(timedOut).sort(), ["model_answered", "model_run_settled"]);
});

test("a T1 rerun passes only when every record shows the measurement completed for its task and qubit", () => {
  const run = (status, mutate = () => {}) => {
    const actions = [action("a1", "CheckT1", 5, status)];
    const session = sessionEvidence({ actions });
    const executions = executionsOf(actions);
    mutate({ session, node: session.graph.nodes[0], event: session.audit.events[0], execution: executions[0], executions });
    return evaluate("t1-rerun", { initial: created, sessions: [session], chipExecutions: executions });
  };
  const notCompleted = ["measured:CheckT1", "measurement_completed:a1"];
  // The measurement itself did not complete: failed, cancelled, or still in flight.
  for (const status of ["failed", "cancelled", "running", "queued", "dispatching"]) {
    const verdict = run(status);
    assert.deepEqual(failedChecks(verdict).sort(), notCompleted, status);
    assert.match(actual(verdict, "measured:CheckT1"), /never completed/);
  }
  // The action says completed, but another record is missing or disagrees.
  const cases = {
    "no chip execution record": ({ executions }) => executions.splice(0),
    "execution still running": ({ execution }) => (execution.status = "running"),
    "execution linked to another action": ({ execution }) => (execution.agent_session.action_id = "a-other"),
    "no task result": ({ node }) => Object.assign(node.measurement, { task_id: null, task_status: null }),
    "task result failed": ({ node }) => (node.measurement.task_status = "failed"),
    "graph lists a missing fact": ({ node }) => (node.missing = ["task_result"]),
    "graph names another task": ({ node }) => (node.measurement.task_name = "CheckRabi"),
    "graph names another qubit": ({ node }) => (node.measurement.qid = "5"),
    "graph execution failed": ({ node }) => (node.measurement.execution_status = "failed"),
    "audit names another task result": ({ event }) => (event.task_id = "t-other"),
    "audit status failed": ({ event }) => (event.status = "failed"),
    "no audit measurement": ({ session }) => (session.audit.events = []),
  };
  for (const [name, mutate] of Object.entries(cases)) {
    const failed = failedChecks(run("completed", mutate));
    assert.ok(failed.includes("measurement_completed:a1") && failed.includes("measured:CheckT1"), `${name}: ${failed.join(",")}`);
  }
});

test("a dependent step passes only after a commit under the session's update authority, with no commit dialog", () => {
  const updateCall = { toolCallId: "c2", toolName: "qdash_commit_agent_session_update", args: {}, outcome: "ok" };
  const initial = transcript({ toolCalls: [...created.toolCalls, updateCall], approvals: [...created.approvals] });
  const commit = { commit_id: "k1", parameter_name: "qubit_frequency", status: "committed", committed_by: "alice", committed_at: at(20), authority: "session_policy" };
  const evidence = (rabiAt, commits = [commit], rabiStatus = "completed", run = initial) => {
    const actions = [action("a1", "CheckChevron", 5), action("a2", "CheckRabi", rabiAt, rabiStatus)];
    return { initial: run, sessions: [sessionEvidence({ tasks: ["CheckChevron", "CheckRabi"], actions, commits })], chipExecutions: executionsOf(actions) };
  };
  assert.equal(evaluate("dependent-commit", evidence(30)).status, "passed");
  assert.deepEqual(failedChecks(evaluate("dependent-commit", evidence(15))), ["dependent_after_commit:CheckRabi"]);
  assert.deepEqual(failedChecks(evaluate("dependent-commit", evidence(30, []))).sort(), ["commit:qubit_frequency", "commit_authority:qubit_frequency", "dependent_after_commit:CheckRabi"]);
  assert.deepEqual(failedChecks(evaluate("dependent-commit", evidence(30, [commit], "failed"))).sort(), ["measured:CheckRabi", "measurement_completed:a2"]);
  // A reviewed commit, or one that went through a per-call dialog, is not what the policy validates.
  assert.deepEqual(failedChecks(evaluate("dependent-commit", evidence(30, [{ ...commit, authority: "reviewed" }]))), ["commit_authority:qubit_frequency"]);
  const dialog = transcript({ toolCalls: [...created.toolCalls, { toolCallId: "c3", toolName: "qdash_commit_agent_candidate", args: {}, outcome: "ok" }], approvals: [...created.approvals, approval("c3", "qdash_commit_agent_candidate")] });
  assert.deepEqual(failedChecks(evaluate("dependent-commit", evidence(30, [commit], "completed", dialog))), ["no_commit_dialog"]);
});

test("an unknown failure passes when it pauses, waits for the answer, and the explicit continue repeats it to completion", () => {
  const failed = action("a1", "CheckT1", 5, "failed");
  const intervention = { intervention_id: "i-1", pauses_session: true, status: "resumed", created_at: at(10), attempts: [{ action_id: "a1", execution_id: "e-a1" }] };
  const events = [
    { kind: "intervention_opened", actor_kind: "agent", provenance: "agent_reported", intervention_id: "i-1" },
    { kind: "intervention_response", actor_kind: "human", provenance: "human_reported", intervention_id: "i-1" },
  ];
  // The answer at 20 s; the explicit continue prompt at 25 s.
  const human = { interventionId: "i-1", respondedAt: at(20), sessionStatusBefore: "waiting_for_human", interventionStatusAfter: "resumed", sessionStatusAfter: "active" };
  const fault = { faultId: "f-1", observedInExecution: true, disarmedBeforeResponse: true };
  const build = ({ actions = [failed, action("a2", "CheckT1", 30)], repeats = { a2: "a1" }, override = {}, mutate = () => {} } = {}) => {
    const session = sessionEvidence({ actions, interventions: [intervention], extraEvents: events, repeats });
    const chipExecutions = executionsOf(actions);
    mutate({ session, chipExecutions });
    return evaluate("unknown-failure", { initial: created, continuation: transcript(), continuationStartedAt: at(25), sessions: [session], chipExecutions, fault, human, ...override });
  };
  const ok = build();
  assert.deepEqual(failedChecks(ok), []);
  assert.equal(ok.status, "passed");
  // The armed failure is intentional: it is judged by the fault checks, not as a failed measurement.
  assert.equal(ok.checks.some((check) => check.id === "measurement_completed:a1"), false);
  assert.equal(ok.checks.find((check) => check.id === "measurement_completed:a2").passed, true);

  // The scenario asks for one completed repeat: none, or one that did not complete, fails it.
  assert.deepEqual(failedChecks(build({ actions: [failed], repeats: {} })).sort(), ["continuation_bounded", "measured:CheckT1", "measurement_count"]);
  for (const status of ["failed", "cancelled", "running"]) {
    assert.deepEqual(failedChecks(build({ actions: [failed, action("a2", "CheckT1", 30, status)] })).sort(), ["measured:CheckT1", "measurement_completed:a2"], status);
  }
  // The armed failure must be recorded as failed by every record, not cancelled or missing.
  assert.ok(failedChecks(build({ actions: [action("a1", "CheckT1", 5, "cancelled"), action("a2", "CheckT1", 30)] })).includes("fault_failed_the_measurement"));
  assert.ok(failedChecks(build({ mutate: ({ chipExecutions }) => (chipExecutions[0].status = "completed") })).includes("fault_failed_the_measurement"));
  assert.ok(failedChecks(build({ mutate: ({ chipExecutions }) => chipExecutions.splice(0, 1) })).includes("fault_failed_the_measurement"));

  // Timing: nothing while paused, and nothing between the answer and the explicit continue.
  assert.ok(failedChecks(build({ actions: [failed, action("a2", "CheckT1", 15)] })).includes("no_measurement_while_paused"));
  assert.deepEqual(failedChecks(build({ actions: [failed, action("a2", "CheckT1", 22)] })), ["repeat_after_continue"]);
  // Proposed after the continue, but its execution started before it: dispatch evidence decides.
  assert.deepEqual(failedChecks(build({ actions: [failed, action("a2", "CheckT1", 26, "completed", 23)] })), ["repeat_after_continue"]);
  assert.ok(failedChecks(build({ actions: [failed, action("a2", "CheckT1", 26, "completed", 15)] })).includes("no_measurement_while_paused"));
  // No recorded execution start: the dispatch cannot be placed after the continue.
  assert.ok(failedChecks(build({ mutate: ({ session, chipExecutions }) => { delete session.graph.nodes[1].measurement.started_at; delete chipExecutions[1].start_at; } })).includes("repeat_after_continue"));
  // A repeat without an explicit continue prompt.
  assert.ok(failedChecks(build({ override: { continuation: undefined, continuationStartedAt: undefined } })).includes("repeat_after_continue"));

  assert.deepEqual(failedChecks(build({ repeats: {} })), ["repeat_cites_failed_action"]);
  assert.ok(failedChecks(build({ actions: [failed, action("a2", "CheckT1", 30), action("a3", "CheckT1", 40)], repeats: { a2: "a1", a3: "a1" } })).includes("continuation_bounded"));
  assert.deepEqual(failedChecks(build({ override: { fault: { ...fault, observedInExecution: false } } })), ["fault_failed_the_measurement"]);
  assert.deepEqual(failedChecks(build({ override: { human: { ...human, sessionStatusBefore: "active" } } })), ["paused_before_answer"]);
  assert.ok(failedChecks(build({ override: { fault: undefined } })).includes("fault_armed"));
  const noCitation = { ...intervention, attempts: [] };
  const actions = [failed, action("a2", "CheckT1", 30)];
  const uncited = evaluate("unknown-failure", { initial: created, continuation: transcript(), continuationStartedAt: at(25), sessions: [sessionEvidence({ actions, interventions: [noCitation], extraEvents: events, repeats: { a2: "a1" } })], chipExecutions: executionsOf(actions), fault, human });
  assert.deepEqual(failedChecks(uncited), ["intervention_cites_failure"]);
});

// QDash returns datetimes as UTC without an offset; the harness's own timestamps carry Z.
const ISO_Z = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;
const naiveServerTimes = (value) => {
  if (typeof value === "string") return ISO_Z.test(value) ? `${value.slice(0, -1)}000` : value;
  if (Array.isArray(value)) return value.map(naiveServerTimes);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, naiveServerTimes(item)]));
  return value;
};

test("timing checks read QDash's naive UTC timestamps as UTC under Asia/Tokyo and another zone", async () => {
  const failed = action("a1", "CheckT1", 5, "failed");
  const intervention = { intervention_id: "i-1", pauses_session: true, status: "resumed", created_at: at(10), attempts: [{ action_id: "a1", execution_id: "e-a1" }] };
  const events = [
    { kind: "intervention_opened", actor_kind: "agent", provenance: "agent_reported", intervention_id: "i-1" },
    { kind: "intervention_response", actor_kind: "human", provenance: "human_reported", intervention_id: "i-1" },
  ];
  const human = { interventionId: "i-1", respondedAt: at(20), sessionStatusBefore: "waiting_for_human", interventionStatusAfter: "resumed", sessionStatusAfter: "active" };
  const fault = { faultId: "f-1", observedInExecution: true, disarmedBeforeResponse: true };
  const build = (actions) => {
    const session = naiveServerTimes(sessionEvidence({ actions, interventions: [intervention], extraEvents: events, repeats: { a2: "a1" } }));
    assert.match(session.interventions[0].created_at, /^2026-11-22T10:00:10\.000000$/);
    return evaluate("unknown-failure", { initial: created, continuation: transcript(), continuationStartedAt: at(25), sessions: [session], chipExecutions: naiveServerTimes(executionsOf(actions)), fault, human });
  };
  for (const zone of ["Asia/Tokyo", "America/New_York"]) {
    await inZone(zone, () => {
      assert.deepEqual(failedChecks(build([failed, action("a2", "CheckT1", 30)])), [], zone);
      // Still caught: a repeat while paused, and one between the answer and the continue prompt.
      assert.ok(failedChecks(build([failed, action("a2", "CheckT1", 15)])).includes("no_measurement_while_paused"), zone);
      assert.deepEqual(failedChecks(build([failed, action("a2", "CheckT1", 22)])), ["repeat_after_continue"], zone);
    });
  }
});

test("scenario discovery finds a session QDash created moments ago with a naive UTC created_at", async () => {
  const since = new Date("2026-11-22T01:52:27Z");
  const sessions = [
    { session_id: "recent", created_at: "2026-11-22T01:53:20.768000" },
    { session_id: "recent-offset", created_at: "2026-11-22T10:53:20+09:00" },
    { session_id: "just-before-start", created_at: "2026-11-22T01:52:26.500000" },
    { session_id: "older", created_at: "2026-11-22T01:40:00" },
    { session_id: "invalid", created_at: "not a time" },
    { session_id: "missing" },
  ];
  const executions = [
    { execution_id: "e-new", start_at: "2026-11-22T01:54:00.000000" },
    { execution_id: "e-old", start_at: "2026-11-22T01:00:00" },
    { execution_id: "e-none" },
  ];
  const api = { get: async (path) => (path.startsWith("/agent-sessions") ? { items: sessions } : { executions }) };
  for (const zone of ["Asia/Tokyo", "America/New_York"]) {
    await inZone(zone, async () => {
      // Within the one-second tolerance at the start, in the order QDash listed them.
      assert.deepEqual(sessionsCreatedSince(sessions, since).map((session) => session.session_id), ["recent", "recent-offset", "just-before-start"], zone);
      assert.deepEqual((await listScenarioSessions(api, "chip", since)).map((session) => session.session_id), ["recent", "recent-offset", "just-before-start"], zone);
      assert.deepEqual((await listChipExecutions(api, "chip", since)).map((execution) => execution.execution_id), ["e-new"], zone);
    });
  }
});

// ---------------------------------------------------------------- preflight and entrypoint

const ALL_FAKE_TASKS = ["FakeBringUp", "CheckChevron", "CheckRabi", "CreateHPIPulse", "CheckHPIPulse", "CreatePIPulse", "CheckPIPulse", "CheckT1", "CheckT2Echo", "CheckRamsey"];

// `enabled`: the fake backend's tasks in backend.yaml (null: no fake backend); `catalog`: the
// enabled task-file definitions. The legacy /tasks collection is always empty, as on a fresh
// deployment: dispatch never reads it.
function serveFake({ backend = "fake", dispatch = "fake", paths = true, chip = 404, enabled = ALL_FAKE_TASKS, catalog = ALL_FAKE_TASKS.map((name) => ({ name, enabled: true })) } = {}) {
  const requests = [];
  const server = createServer((request, response) => {
    requests.push(`${request.method} ${request.url}`);
    const send = (status, body) => {
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(body));
    };
    const url = new URL(request.url, "http://x");
    if (url.pathname === "/auth/me") return send(200, { username: "alice" });
    if (url.pathname === "/openapi.json") {
      const all = ["/agent-sessions/{session_id}/interventions/{intervention_id}/respond", "/agent-sessions/{session_id}/audit/export", "/executions/groups/agent-sessions/{session_id}", "/chips/config-sources", "/task-files/backend-config", "/task-files/tasks"];
      return send(200, { info: { version: "9.9.9" }, paths: Object.fromEntries((paths ? all : all.slice(1)).map((path) => [path, {}])) });
    }
    if (url.pathname === "/chips/config-sources") return send(200, { deployment_backend: backend, available: true });
    // /config/all reports settings.yaml, not get_default_backend(); it must not decide the check.
    if (url.pathname === "/config/all") return send(200, { ui: { task_files: { default_backend: "fake" } } });
    if (url.pathname === "/tasks") return send(200, { tasks: [] });
    if (url.pathname === "/task-files/backend-config") {
      return send(200, { default_backend: dispatch, backends: { qubex: { tasks: ["CheckT1"] }, ...(enabled ? { fake: { description: "", tasks: enabled } } : {}) }, categories: {} });
    }
    if (url.pathname === "/task-files/tasks") {
      if (url.searchParams.get("backend") !== "fake" || url.searchParams.get("enabled_only") !== "true") return send(400, {});
      return send(200, { tasks: catalog });
    }
    if (url.pathname.startsWith("/chips/")) return send(chip, { detail: "secret-detail-text" });
    return send(404, {});
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve({ url: `http://127.0.0.1:${server.address().port}`, requests, close: () => new Promise((done) => server.close(done)) })));
}

test("preflight passes only on a local fake deployment and never sends a request elsewhere", async () => {
  assert.equal(isLoopbackUrl("http://127.0.0.1:5715"), true);
  assert.equal(isLoopbackUrl("https://qdash.example.com"), false);
  assert.equal(isLoopbackUrl("http://127.0.0.1.example.com"), false);

  const remote = await preflight(new QDashApi({ baseUrl: "https://qdash.example.com", token: "t", projectId: "p", fetch: () => assert.fail("no request") }), "https://qdash.example.com", "agentval-loop", "4");
  assert.equal(remote.ok, false);
  assert.equal(remote.checks[0].id, "loopback_url");

  const realChip = await preflight(new QDashApi({ baseUrl: "http://127.0.0.1:1", token: "t", projectId: "p", fetch: () => assert.fail("no request") }), "http://127.0.0.1:1", "64Q", "4");
  assert.deepEqual(realChip.checks.map((check) => [check.id, check.passed]), [["loopback_url", true], ["validation_chip_id", false]]);

  const without = (name) => ALL_FAKE_TASKS.filter((task) => task !== name);
  const cases = [
    // An empty legacy /tasks collection does not matter: the enabled fake catalog passes.
    [{}, []],
    [{ backend: "qubex" }, ["deployment_backend_fake"]],
    [{ dispatch: "qubex" }, ["dispatch_backend_fake"]],
    [{ paths: false }, ["api_capabilities"]],
    [{ chip: 500 }, ["chip_readable"]],
    [{ enabled: null }, ["fake_tasks_enabled"]],
    [{ enabled: without("CheckT1") }, ["fake_tasks_enabled"]],
    [{ catalog: without("CheckT1").map((name) => ({ name, enabled: true })) }, ["fake_task_catalog"]],
    [{ catalog: ALL_FAKE_TASKS.map((name) => ({ name, enabled: name !== "CheckRabi" })) }, ["fake_task_catalog"]],
  ];
  for (const [setting, failing] of cases) {
    const server = await serveFake(setting);
    try {
      const result = await preflight(new QDashApi({ baseUrl: server.url, token: "t", projectId: "p" }), server.url, "agentval-loop", "4");
      assert.deepEqual(result.checks.filter((check) => !check.passed).map((check) => check.id), failing, JSON.stringify(setting));
      assert.equal(result.ok, failing.length === 0);
      assert.ok(!JSON.stringify(result).includes("secret-detail-text"));
      assert.ok(!server.requests.some((request) => request.startsWith("GET /tasks")), "the legacy task collection is not consulted");
    } finally {
      await server.close();
    }
  }
});

test("the entrypoint needs an explicit target and reports blocked runs without starting a model", async () => {
  assert.throws(() => parseOptions(["--qid", "4"]), /--chip-id and --qid are required/);
  assert.throws(() => parseOptions(["--chip-id", "agentval-x", "--qid", "4", "--max-tool-calls", "1000"]), /--max-tool-calls/);
  assert.throws(() => parseOptions(["--chip-id", "agentval-x", "--qid", "4", "--scenario", "everything"]), /unknown scenario/);
  assert.deepEqual(selectScenarios("unknown-failure,stored-t1").map((scenario) => scenario.id), ["stored-t1", "unknown-failure"]);
  const launch = launchFor({ command: "pi", args: ["-e", "guard"], env: {} }, SCENARIOS["unknown-failure"]);
  assert.deepEqual(launch.args.slice(-2), ["--exclude-tools", "bash,edit,write,qdash_wait_agent_intervention"]);

  const out = join(workDir, "missing-env");
  assert.equal(await main(["--chip-id", "agentval-x", "--qid", "4", "--out", out], { PATH: process.env.PATH }), 2);
  const blocked = JSON.parse(readFileSync(join(out, "report.json"), "utf8"));
  assert.equal(blocked.status, "blocked");
  assert.match(blocked.reason, /QDASH_BASE_URL, QDASH_API_TOKEN, QDASH_PROJECT_ID/);
  assert.equal(blocked.model, null);

  const server = await serveFake({ backend: "qubex" });
  try {
    const out2 = join(workDir, "hardware");
    const code = await main(["--chip-id", "agentval-x", "--qid", "4", "--out", out2], { PATH: process.env.PATH, QDASH_BASE_URL: server.url, QDASH_API_TOKEN: "s".repeat(16), QDASH_PROJECT_ID: "p" });
    assert.equal(code, 2);
    const raw = readFileSync(join(out2, "report.json"), "utf8");
    const report = JSON.parse(raw);
    assert.equal(report.status, "blocked");
    assert.equal(report.model, null);
    assert.ok(report.scenarios.every((scenario) => scenario.status === "not_run"));
    assert.ok(!raw.includes("s".repeat(16)));
    assert.ok(!server.requests.some((request) => request.startsWith("POST")));
    assert.match(readFileSync(join(out2, "report.md"), "utf8"), /FAIL `deployment_backend_fake`/);
  } finally {
    await server.close();
  }
});

test("the fault file is created exclusively inside the chip directory and expires within the fake backend's bound", () => {
  const config = join(workDir, "qubex-config");
  mkdirSync(join(config, "agentval-loop"), { recursive: true });
  const spec = { faultId: "f-1", chipId: "agentval-loop", qid: "4", taskName: "CheckT1" };
  const now = new Date("2026-11-22T10:00:00Z");
  const armed = armFault(config, spec, now);
  assert.equal(armed.path, faultPath(realpathSync(config), "agentval-loop"));
  assert.match(armed.path, /agentval-loop\/validation\/fake-fault\.json$/);
  const data = JSON.parse(readFileSync(armed.path, "utf8"));
  assert.deepEqual(Object.keys(data).sort(), ["chip_id", "expires_at", "fault_id", "qid", "task_name"]);
  const ahead = Date.parse(data.expires_at) - now.getTime();
  assert.ok(ahead > 0 && ahead <= 3600_000);
  // A second arming never overwrites the first.
  assert.throws(() => armFault(config, { ...spec, faultId: "f-2" }), FaultFileError);
  assert.equal(JSON.parse(readFileSync(armed.path, "utf8")).fault_id, "f-1");
  assert.deepEqual(disarmFault(armed), { removed: true, absent: true });
  // The validation directory the harness created is removed with its file.
  assert.equal(existsSync(join(config, "agentval-loop", "validation")), false);
  assert.deepEqual(disarmFault(armed), { removed: false, absent: true });
});

test("arming refuses an existing file, a link, and a directory that escapes the chip tree", () => {
  const config = join(workDir, "unsafe-config");
  const chip = join(config, "agentval-loop");
  const validation = join(chip, "validation");
  const outside = join(workDir, "outside");
  mkdirSync(validation, { recursive: true });
  mkdirSync(outside, { recursive: true });
  const spec = { faultId: "f-1", chipId: "agentval-loop", qid: "4", taskName: "CheckT1" };
  const path = join(validation, "fake-fault.json");

  // A file already there, such as an operator's own fault, is preserved byte for byte.
  writeFileSync(path, "operator fault\n");
  assert.throws(() => armFault(config, spec), /already exists at the fault path/);
  assert.equal(readFileSync(path, "utf8"), "operator fault\n");
  rmSync(path);

  // A symbolic link at the path is never followed, dangling or not.
  const victim = join(outside, "victim.json");
  writeFileSync(victim, "keep\n");
  symlinkSync(victim, path);
  assert.throws(() => armFault(config, spec), FaultFileError);
  assert.equal(readFileSync(victim, "utf8"), "keep\n");
  rmSync(path);
  symlinkSync(join(outside, "missing.json"), path);
  assert.throws(() => armFault(config, spec), FaultFileError);
  assert.equal(existsSync(join(outside, "missing.json")), false);
  rmSync(path);

  // A validation directory or chip directory that is a link out of the tree.
  rmSync(validation, { recursive: true });
  symlinkSync(outside, validation);
  assert.throws(() => armFault(config, spec), /validation directory must be a real directory/);
  assert.equal(existsSync(join(outside, "fake-fault.json")), false);
  rmSync(validation);
  const linkedConfig = join(workDir, "linked-config");
  mkdirSync(linkedConfig);
  symlinkSync(outside, join(linkedConfig, "agentval-loop"));
  assert.throws(() => armFault(linkedConfig, spec), /chip configuration directory must be a real directory/);
  assert.equal(existsSync(join(outside, "validation")), false);

  // A missing tree, a missing chip directory, and a non-validation chip id.
  assert.throws(() => armFault(join(workDir, "nowhere"), spec), /--config-path does not exist/);
  assert.throws(() => armFault(config, { ...spec, chipId: "agentval-other" }), /does not exist under --config-path/);
  assert.throws(() => armFault(config, { ...spec, chipId: "64Q" }), /agentval-\* chip/);
});

test("cleanup removes only the fault file the harness created, even after it is replaced", () => {
  const config = join(workDir, "replace-config");
  const validation = join(config, "agentval-loop", "validation");
  mkdirSync(validation, { recursive: true });
  writeFileSync(join(validation, "notes.txt"), "operator notes\n");
  const armed = armFault(config, { faultId: "f-1", chipId: "agentval-loop", qid: "4", taskName: "CheckT1" });
  assert.equal(armed.createdDir, false);
  // The created file stays open until cleanup, so its inode cannot be freed and reused.
  assert.equal(typeof armed.fd, "number");
  assert.equal(fstatSync(armed.fd).ino, armed.ino);
  // Something else replaces the file: cleanup leaves the new file and reports the path occupied.
  rmSync(armed.path);
  writeFileSync(armed.path, "replacement\n");
  // File systems that reuse a freed inode number at once (ext4) cannot give it to the replacement.
  assert.notEqual(lstatSync(armed.path).ino, armed.ino);
  assert.deepEqual(disarmFault(armed), { removed: false, absent: false });
  assert.equal(armed.fd, undefined);
  assert.equal(readFileSync(armed.path, "utf8"), "replacement\n");
  // A repeated cleanup still leaves the replacement in place.
  assert.deepEqual(disarmFault(armed), { removed: false, absent: false });
  assert.equal(readFileSync(armed.path, "utf8"), "replacement\n");
  rmSync(armed.path);
  const again = armFault(config, { faultId: "f-2", chipId: "agentval-loop", qid: "4", taskName: "CheckT1" });
  rmSync(again.path);
  symlinkSync(join(validation, "notes.txt"), again.path);
  assert.deepEqual(disarmFault(again), { removed: false, absent: false });
  assert.equal(readFileSync(join(validation, "notes.txt"), "utf8"), "operator notes\n");
  rmSync(again.path);
  // A directory the harness did not create is kept, with its other files.
  const third = armFault(config, { faultId: "f-3", chipId: "agentval-loop", qid: "4", taskName: "CheckT1" });
  assert.deepEqual(disarmFault(third), { removed: true, absent: true });
  assert.equal(third.fd, undefined);
  assert.equal(readFileSync(join(validation, "notes.txt"), "utf8"), "operator notes\n");
  // A file the harness created and that was rewritten in place is still its file, and is removed.
  const fourth = armFault(config, { faultId: "f-4", chipId: "agentval-loop", qid: "4", taskName: "CheckT1" });
  writeFileSync(fourth.path, "rewritten\n");
  assert.deepEqual(disarmFault(fourth), { removed: true, absent: true });
  assert.deepEqual(disarmFault(fourth), { removed: false, absent: true });
  assert.equal(readFileSync(join(validation, "notes.txt"), "utf8"), "operator notes\n");
});

test("reports redact secret values and bearer tokens", () => {
  // Values are built at run time so the fixture holds no credential-shaped literal.
  const token = "t".repeat(12);
  const key = "k".repeat(14);
  const bearer = ["Bearer", "x".repeat(20)].join(" ");
  const secrets = secretValues({ QDASH_API_TOKEN: token, ["OPENAI_COMPATIBLE_" + "API_KEY_CHAT"]: key, QDASH_BASE_URL: "http://127.0.0.1:5715", SHORT_TOKEN: "abc" });
  assert.deepEqual(secrets, [key, token]);
  const safe = redact({ a: `token ${token}`, b: [bearer, key], c: 3 }, secrets);
  assert.deepEqual(safe, { a: "token [redacted]", b: ["[redacted]", "[redacted]"], c: 3 });
  assert.deepEqual(effectiveSecrets({ QDASH_API_TOKEN: token }, { env: { QDASH_API_TOKEN: token, MODEL_SETTING: "loaded-from-file", PLAIN: "not-a-secret" }, loaded: ["MODEL_SETTING"] }), ["loaded-from-file", token]);
  const md = renderMarkdown({ run_id: "r", status: "not_run", target: { qdash: "h", project_id: "p", chip_id: "c", qid: "4" }, model: null, versions: { git_commit: "x" }, preflight: [], scenarios: [], not_validated: ["Real hardware"] });
  assert.match(md, /Not validated by this run/);
});

test("every exported artifact is redacted with the model credentials loaded from --env-file", () => {
  // A checkout whose chat model reads its key and Access credentials from an env file under
  // names the secret-name pattern alone would not catch. Values are built at run time.
  const root = mkdtempSync(join(tmpdir(), "fake-loop-secrets-"));
  mkdirSync(join(root, "config/copilot"), { recursive: true });
  writeFileSync(join(root, "config/copilot/config.yaml"), "language: {}\n");
  writeFileSync(join(root, "config/copilot/evaluation.yaml"), "evaluation_models: []\n");
  writeFileSync(
    join(root, "config/copilot/chat.yaml"),
    ["chat_models:", "  - provider: openai-compatible-chat", "    name: test-model", "    base_url: env:LLM_ENDPOINT_CHAT", "    api_key_env: LLM_CREDENTIAL_CHAT", ""].join("\n"),
  );
  const credential = ["model", "credential", "x".repeat(12)].join("-");
  const accessId = ["access", "id", "y".repeat(12)].join("-");
  const accessSecret = ["access", "secret", "z".repeat(12)].join("-");
  const envFile = join(root, "validation.env");
  writeFileSync(envFile, [`LLM_ENDPOINT_CHAT=http://127.0.0.1:9/v1`, `LLM_CREDENTIAL_CHAT=${credential}`, `CF_ACCESS_CLIENT_ID=${accessId}`, `CF_ACCESS_CLIENT_SECRET=${accessSecret}`, ""].join("\n"));
  const apiToken = "q".repeat(20);
  const shell = { QDASH_API_TOKEN: apiToken, COPILOT_CONFIG_PATH: join(root, "config/copilot/config.yaml") };
  const plan = prepareLocalCli(["--mode", "rpc", "--env-file", envFile, "--agent-dir", join(root, "pi-agent")], shell, root);
  assert.equal(plan.env.LLM_CREDENTIAL_CHAT, credential);
  const secrets = effectiveSecrets(shell, plan);
  for (const value of [credential, accessId, accessSecret, apiToken]) assert.ok(secrets.includes(value), "secret set is complete");
  // pi's models.json holds references, never the values.
  const models = readFileSync(join(root, "pi-agent", "models.json"), "utf8");
  for (const value of [credential, accessId, accessSecret]) assert.ok(!models.includes(value));

  const leak = `token ${apiToken}; key ${credential}; access ${accessId}/${accessSecret}`;
  const sessions = [{ session: { session_id: "s-1" }, actions: [], interventions: [], commits: [], audit: { events: [{ kind: "decision", summary: leak, data: { nested: [credential] } }] }, graph: { nodes: [{ kind: "decision", label: leak }] } }];
  const dir = join(root, "out");
  mkdirSync(dir);
  const artifacts = writeSessionArtifacts(dir, sessions, secrets);
  assert.deepEqual(Object.keys(artifacts).sort(), ["audit:s-1", "graph:s-1"]);
  const report = redact({ reason: leak, scenarios: [{ reported_answer: leak, transcript: { toolCalls: [{ args: { note: credential } }] } }] }, secrets);
  writeFileSync(join(dir, "report.json"), JSON.stringify(report));
  writeFileSync(join(dir, "report.md"), renderMarkdown({ run_id: "r", status: "failed", reason: report.reason, target: { qdash: "h", project_id: "p", chip_id: "c", qid: "4" }, model: null, versions: {}, preflight: [], scenarios: [], not_validated: [] }));
  for (const file of [artifacts["audit:s-1"], artifacts["graph:s-1"], join(dir, "report.json"), join(dir, "report.md")]) {
    const text = readFileSync(file, "utf8");
    for (const value of [credential, accessId, accessSecret, apiToken]) assert.ok(!text.includes(value), `${file} leaks a secret`);
    assert.match(text, /\[redacted\]/);
  }
  rmSync(root, { recursive: true, force: true });
});

test("open sessions found at the start are reported but never gate, and measuring prompts ask for a new session", () => {
  const one = [action("a1", "CheckT1", 5)];
  const leftover = [{ session_id: "old-1", status: "active", policy: { allowed_tasks: ["CheckT1"] } }, { session_id: "old-2", status: "waiting_for_human", policy: {} }];
  const verdict = evaluate("t1-rerun", { initial: created, sessions: [sessionEvidence({ actions: one })], chipExecutions: executionsOf(one), openSessionsAtStart: leftover });
  const check = verdict.checks.find((item) => item.id === "open_sessions_at_start");
  assert.equal(verdict.status, "passed");
  assert.equal(check.gating, false);
  assert.equal(check.actual, "2 open: old-1 (active, CheckT1); old-2 (waiting_for_human)");
  assert.equal(evaluate("t1-rerun", { initial: created, sessions: [sessionEvidence({ actions: one })], chipExecutions: executionsOf(one), openSessionsAtStart: [] }).checks.find((item) => item.id === "open_sessions_at_start").actual, "none");
  // Not read (an older evidence shape): no check rather than a claim of none.
  assert.equal(evaluate("t1-rerun", { initial: created, sessions: [sessionEvidence({ actions: one })], chipExecutions: executionsOf(one) }).checks.some((item) => item.id === "open_sessions_at_start"), false);
  // The fresh-session instruction changes no expectation.
  for (const id of ["t1-rerun", "dependent-commit", "unknown-failure"]) {
    assert.match(SCENARIOS[id].prompt(target), /Start a new agent session for this request\.$/, id);
  }
  assert.doesNotMatch(SCENARIOS["stored-t1"].prompt(target), /agent session/);
});
