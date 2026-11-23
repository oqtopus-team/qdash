/**
 * Opt-in validation of the real-model calibration loop against a local fake-backend QDash.
 *
 *   QDASH_BASE_URL=http://127.0.0.1:5715 QDASH_API_TOKEN=... QDASH_PROJECT_ID=... \
 *     bun agent-runtime/validation/fake-loop/run.ts --chip-id agentval-loop --qid 4 \
 *       --create-chip --setup --config-path ../qdash/config/qubex-config
 *
 * The harness proves the target is a local fake deployment, prepares one qubit of a
 * disposable `agentval-*` chip, then sends each scenario's natural-language request to
 * the configured chat model in a pi CLI process (RPC mode) with the production
 * pi-qdash tools and skills. It answers pi's approval dialogs as the user, answers the
 * intervention as the expert, and judges each scenario from QDash's records. See
 * docs/developer-guide/copilot/agent-validation.md.
 *
 * Exit status: 0 every scenario passed, 1 a scenario failed, 2 blocked or not run.
 */

import { execFileSync } from "node:child_process";
import {
  closeSync,
  constants,
  existsSync,
  fstatSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  realpathSync,
  rmdirSync,
  unlinkSync,
  writeFileSync,
  writeSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { prepareLocalCli } from "../../src/local-cli.ts";
import { decideApproval } from "./approval.ts";
import {
  type BaselineEvidence,
  type CalibrationEvidence,
  evaluateScenario,
  type FaultEvidence,
  type HumanResponseEvidence,
  type ScenarioEvidence,
} from "./evaluate.ts";
import { GUARD_ENV, MAX_TOOL_CALLS_ENV } from "./guard-extension.ts";
import {
  ApiError,
  calibrationCapabilities,
  CHIP_ID_PATTERN,
  collectSession,
  createFakeChip,
  getCalibrationSession,
  getExecution,
  getQubit,
  type Json,
  listChipExecutions,
  listFlowRunExecutions,
  listScenarioCalibrationSessions,
  listOpenSessions,
  listScenarioSessions,
  preflight,
  QDashApi,
  respondToIntervention,
  runManualPipeline,
  runSetupTask,
  type SessionEvidence,
  waitForExecution,
} from "./qdash-api.ts";
import {
  effectiveSecrets,
  NOT_VALIDATED,
  REPORT_SCHEMA,
  redact,
  renderMarkdown,
  type ScenarioReport,
  type ValidationReport,
} from "./report.ts";
import { runPrompt, type RunTranscript } from "./rpc-driver.ts";
import { type Scenario, type ScenarioTarget, selectScenarios, SETUP_TASKS } from "./scenarios.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, "../../..");
const GUARD_PATH = join(HERE, "guard-extension.ts");

export interface Options {
  chipId: string;
  qid: string;
  scenarios: Scenario[];
  setup: boolean;
  createChip: boolean;
  envFile?: string;
  configPath?: string;
  out?: string;
  model?: string;
  turnTimeoutSeconds: number;
  maxToolCalls: number;
  setupTimeoutSeconds: number;
}

const USAGE = `usage: run.ts --chip-id agentval-<name> --qid <n> [--scenario all|id,...] [--create-chip] [--setup]
  [--config-path <deployment CONFIG_PATH>] [--env-file <path>] [--model provider/id] [--out <dir>]
  [--turn-timeout <s>] [--max-tool-calls <n>] [--setup-timeout <s>]`;

function bounded(value: string | undefined, name: string, fallback: number, max: number): number {
  if (value === undefined) return fallback;
  const number = Number(value);
  if (!Number.isInteger(number) || number < 1 || number > max) throw new Error(`${name} must be a whole number from 1 to ${max}`);
  return number;
}

export function parseOptions(argv: readonly string[]): Options {
  const values = new Map<string, string>();
  const flags = new Set<string>();
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--setup" || arg === "--create-chip") flags.add(arg);
    else if (arg.startsWith("--") && i + 1 < argv.length) values.set(arg, argv[++i]);
    else throw new Error(`unexpected argument ${arg}\n${USAGE}`);
  }
  const known = ["--chip-id", "--qid", "--scenario", "--env-file", "--config-path", "--out", "--model", "--turn-timeout", "--max-tool-calls", "--setup-timeout"];
  for (const key of values.keys()) if (!known.includes(key)) throw new Error(`unknown option ${key}\n${USAGE}`);
  const chipId = values.get("--chip-id");
  const qid = values.get("--qid");
  if (!chipId || !qid) throw new Error(`--chip-id and --qid are required; no default target is used\n${USAGE}`);
  return {
    chipId,
    qid,
    scenarios: selectScenarios(values.get("--scenario")),
    setup: flags.has("--setup"),
    createChip: flags.has("--create-chip"),
    envFile: values.get("--env-file"),
    configPath: values.get("--config-path"),
    out: values.get("--out"),
    model: values.get("--model"),
    turnTimeoutSeconds: bounded(values.get("--turn-timeout"), "--turn-timeout", 900, 1800),
    maxToolCalls: bounded(values.get("--max-tool-calls"), "--max-tool-calls", 40, 100),
    setupTimeoutSeconds: bounded(values.get("--setup-timeout"), "--setup-timeout", 600, 1800),
  };
}

function git(args: string[]): string | null {
  try {
    return execFileSync("git", args, { cwd: REPO_ROOT, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return null;
  }
}

function packageVersion(path: string): string | null {
  try {
    return String((JSON.parse(readFileSync(path, "utf8")) as { version?: string }).version ?? "") || null;
  } catch {
    return null;
  }
}

function collectVersions(apiVersion?: string): Record<string, string | null> {
  const status = git(["status", "--porcelain"]);
  return {
    git_commit: git(["rev-parse", "HEAD"]),
    git_worktree: status === null ? null : status === "" ? "clean" : "modified",
    pi_qdash: packageVersion(join(REPO_ROOT, "packages/pi-qdash/package.json")),
    pi_coding_agent: packageVersion(join(REPO_ROOT, "agent-runtime/node_modules/@earendil-works/pi-coding-agent/package.json")),
    qdash_api: apiVersion ?? null,
  };
}

const qubitValue = (qubit: Json, name: string): number | undefined => {
  const entry = ((qubit.data ?? {}) as Json)[name] as Json | undefined;
  return typeof entry?.value === "number" && Number.isFinite(entry.value) ? entry.value : undefined;
};

const sleep = (ms: number) => new Promise((resolveSleep) => setTimeout(resolveSleep, ms));

/** The fault file the fake backend reads (src/qdash/workflow/engine/backend/fake_faults.py). */
export function faultPath(configPath: string, chipId: string): string {
  return join(configPath, chipId, "validation", "fake-fault.json");
}

export interface FaultSpec {
  faultId: string;
  chipId: string;
  qid: string;
  taskName: string;
}

/**
 * A fault file the harness created, identified by its device and inode so cleanup removes only
 * that file. The descriptor stays open until cleanup: while it is open the inode cannot be freed,
 * so a file that replaces the fault file cannot be given the same inode number. Linux file
 * systems such as ext4 reuse a freed inode number at once.
 */
export interface ArmedFault {
  path: string;
  dev: number;
  ino: number;
  /** The open descriptor of the created file; `undefined` once cleanup has closed it. */
  fd: number | undefined;
  /** The harness created the `validation` directory, so cleanup may remove it when empty. */
  createdDir: boolean;
}

/** A fault file could not be armed safely; the scenario is blocked and nothing is overwritten. */
export class FaultFileError extends Error {}

const errorCode = (error: unknown): string | undefined => (error as NodeJS.ErrnoException | undefined)?.code;

/** Whether `path` is a real directory (false when absent); a link or other file type throws. */
function realDirectory(path: string, label: string): boolean {
  let stat;
  try {
    stat = lstatSync(path);
  } catch (error) {
    if (errorCode(error) === "ENOENT") return false;
    throw error;
  }
  if (stat.isSymbolicLink() || !stat.isDirectory()) throw new FaultFileError(`${label} must be a real directory, not a symbolic link or file`);
  return true;
}

/**
 * Create the fault file the fake backend reads, exclusively.
 *
 * The chip directory must already exist under the configuration tree as a real directory, and
 * the `validation` directory must be a real directory inside it (it is created when absent).
 * The file is created with O_EXCL and O_NOFOLLOW, so an existing file or a symbolic link at the
 * path is never followed or overwritten: arming fails and the scenario is blocked.
 */
export function armFault(configPath: string, spec: FaultSpec, now = new Date()): ArmedFault {
  if (!CHIP_ID_PATTERN.test(spec.chipId)) throw new FaultFileError("the fault file is written only for an agentval-* chip");
  let root: string;
  try {
    root = realpathSync(configPath);
  } catch {
    throw new FaultFileError("--config-path does not exist");
  }
  const chipDir = join(root, spec.chipId);
  if (!realDirectory(chipDir, "the chip configuration directory")) throw new FaultFileError("the chip configuration directory does not exist under --config-path");
  const dir = join(chipDir, "validation");
  let createdDir = false;
  if (!realDirectory(dir, "the chip's validation directory")) {
    try {
      mkdirSync(dir, { mode: 0o755 });
      createdDir = true;
    } catch (error) {
      if (errorCode(error) !== "EEXIST") throw error;
      realDirectory(dir, "the chip's validation directory");
    }
  }
  if (realpathSync(dir) !== dir) throw new FaultFileError("the chip's validation directory resolves outside the configuration tree");
  const path = faultPath(root, spec.chipId);
  const expires = new Date(now.getTime() + 15 * 60_000).toISOString();
  const content = `${JSON.stringify({ fault_id: spec.faultId, chip_id: spec.chipId, qid: spec.qid, task_name: spec.taskName, expires_at: expires }, null, 2)}\n`;
  let fd: number;
  try {
    fd = openSync(path, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o644);
  } catch (error) {
    if (createdDir) {
      try {
        rmdirSync(dir);
      } catch {
        // Leave a directory that is no longer empty.
      }
    }
    if (errorCode(error) === "EEXIST" || errorCode(error) === "ELOOP") {
      throw new FaultFileError("a file or link already exists at the fault path; it is left in place and no fault is armed");
    }
    throw error;
  }
  const stat = fstatSync(fd);
  const armed: ArmedFault = { path, dev: stat.dev, ino: stat.ino, fd, createdDir };
  try {
    writeSync(fd, content);
  } catch (error) {
    disarmFault(armed);
    throw error;
  }
  return armed;
}

/**
 * Remove the fault file only when it is still the file `armFault` created, then close its
 * descriptor. A file or link that replaced it is left in place. `absent` is whether nothing is
 * left at the path, which is what disarms the fault for the fake backend. A later call removes
 * nothing and reports only `absent`. When the check or the removal fails, the descriptor stays
 * open so a retry still recognizes the file. The check and the removal are separate path
 * operations, so a replacement made between them is not detected.
 */
export function disarmFault(armed: ArmedFault): { removed: boolean; absent: boolean } {
  let removed = false;
  if (armed.fd !== undefined) {
    let stat;
    try {
      stat = lstatSync(armed.path);
    } catch (error) {
      if (errorCode(error) !== "ENOENT") throw error;
    }
    if (stat?.isFile() && stat.dev === armed.dev && stat.ino === armed.ino) {
      unlinkSync(armed.path);
      removed = true;
    }
    const fd = armed.fd;
    armed.fd = undefined;
    closeSync(fd);
  }
  let absent = true;
  try {
    lstatSync(armed.path);
    absent = false;
  } catch (error) {
    if (errorCode(error) !== "ENOENT") throw error;
  }
  if (armed.createdDir && absent) {
    try {
      rmdirSync(dirname(armed.path));
    } catch {
      // Not empty, or no longer the directory the harness created: leave it.
    }
  }
  return { removed, absent };
}

/** Write a JSON artifact with every secret value removed. */
export function writeRedactedJson(path: string, value: unknown, secrets: readonly string[]): void {
  writeFileSync(path, `${JSON.stringify(redact(value, secrets), null, 2)}\n`);
}

/** Save each session's audit export and graph, redacted, and return their paths. */
export function writeSessionArtifacts(dir: string, sessions: readonly SessionEvidence[], secrets: readonly string[]): Record<string, string> {
  const artifacts: Record<string, string> = {};
  for (const item of sessions) {
    const id = String(item.session.session_id);
    if (!/^[A-Za-z0-9_-]{1,100}$/.test(id)) continue;
    const auditFile = join(dir, `audit-${id}.json`);
    const graphFile = join(dir, `graph-${id}.json`);
    writeRedactedJson(auditFile, item.audit, secrets);
    writeRedactedJson(graphFile, item.graph, secrets);
    artifacts[`audit:${id}`] = auditFile;
    artifacts[`graph:${id}`] = graphFile;
  }
  return artifacts;
}

async function settleSessionRuns(api: QDashApi, sessions: SessionEvidence[], timeoutMs: number): Promise<void> {
  const running = sessions.flatMap((item) => item.actions).filter((action) => ["dispatching", "queued", "running", "scheduled"].includes(String(action.execution_status)) && typeof action.execution_id === "string");
  for (const action of running) await waitForExecution(api, String(action.execution_id), timeoutMs);
}

async function gatherEvidence(api: QDashApi, options: Options, since: Date): Promise<{ sessions: SessionEvidence[]; executions: Json[] }> {
  let sessions = await Promise.all((await listScenarioSessions(api, options.chipId, since)).map((session) => collectSession(api, String(session.session_id))));
  await settleSessionRuns(api, sessions, 5 * 60_000);
  sessions = await Promise.all(sessions.map((item) => collectSession(api, String(item.session.session_id))));
  return { sessions, executions: await listChipExecutions(api, options.chipId, since) };
}

const OPEN_EXECUTION = new Set(["scheduled", "pending", "running", "cancelling"]);

/**
 * The calibration sessions the caller created on the chip during the scenario, with every
 * step execution of their pipeline runs settled and read in detail, and every chip execution
 * of the scenario read in detail too, so the list row and the detail can be compared.
 */
async function gatherCalibrationEvidence(api: QDashApi, options: Options, since: Date, chipExecutions: Json[], timeoutMs: number): Promise<Omit<CalibrationEvidence, "baseline">> {
  const read = async () => Promise.all((await listScenarioCalibrationSessions(api, options.chipId, since)).map((session) => getCalibrationSession(api, String(session.calibration_session_id))));
  let sessions = await read();
  const pending = sessions.flatMap((session) => ((session.pipeline_runs ?? []) as Json[]).flatMap((run) => ((run.executions ?? []) as Json[]).filter((execution) => OPEN_EXECUTION.has(String(execution.status)))));
  for (const execution of pending) await waitForExecution(api, String(execution.execution_id), timeoutMs);
  if (pending.length > 0) sessions = await read();
  const ids = new Set<string>(chipExecutions.map((execution) => String(execution.execution_id)));
  for (const session of sessions) {
    for (const run of (session.pipeline_runs ?? []) as Json[]) {
      for (const execution of (run.executions ?? []) as Json[]) ids.add(String(execution.execution_id));
      for (const step of (((run.pipeline ?? {}) as Json).steps ?? []) as Json[]) if (typeof step.execution_id === "string") ids.add(step.execution_id);
    }
  }
  const executionDetails: Record<string, Json> = {};
  for (const id of ids) {
    try {
      executionDetails[id] = await getExecution(api, id);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    }
  }
  return { sessions, executionDetails };
}

/** Run the scenario's manual baseline pipeline to its end, before the prompt. */
async function runBaseline(api: QDashApi, options: Options, scenario: Scenario, timeoutMs: number): Promise<{ flowRunId: string; status: string }> {
  const target: ScenarioTarget = { chipId: options.chipId, qid: options.qid };
  const started = await runManualPipeline(api, options.chipId, scenario.baseline!.spec(target));
  const status = await waitForExecution(api, started.executionId, timeoutMs);
  return { flowRunId: started.flowRunId, status };
}

async function readBaseline(api: QDashApi, options: Options, run: { flowRunId: string; status: string }): Promise<BaselineEvidence> {
  const listRows = await listFlowRunExecutions(api, options.chipId, run.flowRunId);
  const details = await Promise.all(listRows.map((row) => getExecution(api, String(row.execution_id))));
  return { flowRunId: run.flowRunId, status: run.status, listRows, details };
}

interface PiLaunch {
  command: string;
  args: string[];
  env: NodeJS.ProcessEnv;
}

/** Built-in tools no scenario needs: the model reads skills and calls QDash tools only. */
export const EXCLUDED_BUILTIN_TOOLS = ["bash", "edit", "write"];

export function launchFor(base: PiLaunch, scenario: Scenario): PiLaunch {
  const exclude = [...EXCLUDED_BUILTIN_TOOLS, ...(scenario.excludeTools ?? [])];
  return { ...base, args: [...base.args, "--exclude-tools", exclude.join(",")] };
}

async function runScenario(api: QDashApi, options: Options, launch: PiLaunch, scenario: Scenario, username: string, runId: string, outDir: string, secrets: readonly string[]): Promise<ScenarioReport> {
  const target: ScenarioTarget = { chipId: options.chipId, qid: options.qid };
  const report: ScenarioReport = { id: scenario.id, title: scenario.title, status: "not_run", prompts: [], session_ids: [], execution_ids: [], intervention_ids: [], commit_ids: [], checks: [], artifacts: {} };
  const scenarioDir = join(outDir, scenario.id);
  mkdirSync(scenarioDir, { recursive: true });

  let fault: FaultEvidence | undefined;
  let armed: ArmedFault | undefined;
  if (scenario.fault) {
    if (!options.configPath) {
      return { ...report, status: "blocked", reason: "--config-path must name the deployment's Qubex configuration tree, which holds the chip directory" };
    }
    fault = { faultId: `${runId}-${scenario.id}`, observedInExecution: false, disarmedBeforeResponse: false };
    try {
      armed = armFault(options.configPath, { faultId: fault.faultId, chipId: options.chipId, qid: options.qid, taskName: scenario.fault.taskName });
    } catch (error) {
      return { ...report, status: "blocked", reason: error instanceof FaultFileError ? error.message : "the fault file could not be created" };
    }
    report.fault_id = fault.faultId;
  }

  let baselineRun: { flowRunId: string; status: string } | undefined;
  if (scenario.expect.calibration) {
    const capable = await calibrationCapabilities(api);
    if (!capable.ok) return { ...report, status: "blocked", reason: `this QDash cannot record calibration sessions with reported origins: ${capable.detail}` };
  }
  if (scenario.baseline) {
    try {
      baselineRun = await runBaseline(api, options, scenario, options.setupTimeoutSeconds * 1000);
    } catch (error) {
      return { ...report, status: "blocked", reason: error instanceof ApiError ? `baseline pipeline: ${error.message}` : "the baseline pipeline could not run" };
    }
    if (baselineRun.status !== "completed") return { ...report, status: "blocked", reason: `the baseline pipeline ended ${baselineRun.status}` };
  }

  // Read before the scenario starts, so the report shows what an earlier scenario left open.
  const openSessionsAtStart = await listOpenSessions(api, options.chipId).catch(() => undefined);
  const startedAt = new Date();
  report.started_at = startedAt.toISOString();
  const storedT1 = scenario.id === "stored-t1" ? qubitValue(await getQubit(api, options.chipId, options.qid), "t1") : undefined;
  const scenarioLaunch = launchFor(launch, scenario);
  const approvedCounts: Record<string, number> = {};
  const onDialog = async (_request: unknown, call: { toolName: string; args: Record<string, unknown> } | undefined) => {
    if (!call) return { confirmed: false, reason: "unmatched dialog" };
    const sessions = await listScenarioSessions(api, options.chipId, startedAt).catch(() => []);
    // Read only when the scenario plans calibration writes; a failed read approves nothing.
    const calibrationSessions = scenario.approvals.createCalibrationSession || scenario.approvals.runPipeline
      ? await listScenarioCalibrationSessions(api, options.chipId, startedAt).catch(() => undefined)
      : [];
    if (calibrationSessions === undefined) return { confirmed: false, reason: "the scenario's calibration sessions could not be read" };
    const decision = decideApproval(call, {
      target,
      plan: scenario.approvals,
      scenarioSessionIds: new Set(sessions.map((session) => String(session.session_id))),
      scenarioCalibrationSessionIds: new Set(calibrationSessions.map((session) => String(session.calibration_session_id))),
      approvedCounts,
    });
    if (decision.approve) approvedCounts[call.toolName] = (approvedCounts[call.toolName] ?? 0) + 1;
    return { confirmed: decision.approve, reason: decision.reason };
  };
  const run = (prompt: string) => {
    report.prompts.push(prompt);
    return runPrompt({ ...scenarioLaunch, cwd: REPO_ROOT, prompt, timeoutMs: options.turnTimeoutSeconds * 1000, onDialog });
  };

  let initial: RunTranscript;
  let continuation: RunTranscript | undefined;
  let continuationStartedAt: string | undefined;
  let human: HumanResponseEvidence | undefined;
  try {
    initial = await run(scenario.prompt(target));
    if (scenario.fault && fault && armed) {
      const { sessions } = await gatherEvidence(api, options, startedAt);
      const session = sessions[0];
      const failed = session?.actions.find((action) => action.task_name === scenario.fault?.taskName && action.execution_status === "failed");
      if (failed && typeof failed.execution_id === "string") {
        const execution = await api.get<Json>(`/executions/${encodeURIComponent(failed.execution_id)}`);
        const tasks = Array.isArray(execution.task) ? (execution.task as Json[]) : [];
        fault.observedInExecution = [String(execution.message ?? ""), ...tasks.map((task) => String(task.message ?? ""))].some((text) => text.includes(fault!.faultId));
      }
      fault.disarmedBeforeResponse = disarmFault(armed).absent;
      const intervention = session?.interventions.find((item) => item.status === "open" && item.pauses_session === true);
      if (session && intervention && scenario.continuation) {
        const before = await api.get<Json>(`/agent-sessions/${encodeURIComponent(String(session.session.session_id))}`);
        const respondedAt = new Date().toISOString();
        await respondToIntervention(api, String(before.session_id), String(intervention.intervention_id), Number(before.state_version), scenario.continuation.guidance, `${runId}-${scenario.id}-answer`);
        const afterIntervention = await api.get<Json>(`/agent-sessions/${encodeURIComponent(String(before.session_id))}/interventions/${encodeURIComponent(String(intervention.intervention_id))}`);
        const afterSession = await api.get<Json>(`/agent-sessions/${encodeURIComponent(String(before.session_id))}`);
        human = {
          interventionId: String(intervention.intervention_id),
          respondedAt,
          sessionStatusBefore: String(before.status),
          interventionStatusAfter: String(afterIntervention.status),
          sessionStatusAfter: String(afterSession.status),
        };
        if (human.interventionStatusAfter === "resumed") {
          continuationStartedAt = new Date().toISOString();
          continuation = await run(scenario.continuation.prompt(target));
        }
      }
    }
  } finally {
    if (armed && !disarmFault(armed).absent) {
      report.reason = "a fault file the harness did not create is at the fault path; it was left in place";
    }
  }

  let { sessions, executions } = await gatherEvidence(api, options, startedAt);
  let calibration: CalibrationEvidence | undefined;
  if (scenario.expect.calibration) {
    const records = await gatherCalibrationEvidence(api, options, startedAt, executions, options.setupTimeoutSeconds * 1000);
    // Steps settled meanwhile: list the chip again so its rows show their final state.
    executions = await listChipExecutions(api, options.chipId, startedAt);
    calibration = { ...records, ...(baselineRun ? { baseline: await readBaseline(api, options, baselineRun) } : {}) };
    report.calibration_session_ids = records.sessions.map((session) => String(session.calibration_session_id));
  }
  const evidence: ScenarioEvidence = { scenario, target, username, startedAt: startedAt.toISOString(), initial, continuation, continuationStartedAt, sessions, chipExecutions: executions, openSessionsAtStart, storedT1, fault, human, calibration };
  const verdict = evaluateScenario(evidence);
  report.status = verdict.status;
  report.checks = verdict.checks;
  report.session_ids = sessions.map((item) => String(item.session.session_id));
  report.execution_ids = executions.map((execution) => String(execution.execution_id));
  report.intervention_ids = sessions.flatMap((item) => item.interventions.map((intervention) => String(intervention.intervention_id)));
  report.commit_ids = sessions.flatMap((item) => item.commits.map((commit) => String(commit.commit_id)));
  report.reported_answer = (continuation ?? initial).finalText.slice(0, 4000);
  report.transcript = { initial: { ...initial, finalText: undefined }, ...(continuation ? { continuation: { ...continuation, finalText: undefined } } : {}) };
  // Every exported artifact is redacted with the run's full secret set, like the report.
  report.artifacts = writeSessionArtifacts(scenarioDir, sessions, secrets);
  return report;
}

export async function main(argv: readonly string[], env: NodeJS.ProcessEnv = process.env): Promise<number> {
  const startedAt = new Date();
  const runId = `fakeloop-${startedAt.toISOString().replace(/[-:]/g, "").replace(/\..*/, "")}`;
  let options: Options;
  try {
    options = parseOptions(argv);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    return 2;
  }
  const outDir = resolve(options.out ?? join(REPO_ROOT, ".tmp", "agent-fake-loop", runId));
  mkdirSync(outDir, { recursive: true });
  // The shell's secrets now; the model credentials pi gets (from --env-file too) once loaded.
  let secrets = effectiveSecrets(env);
  const report: ValidationReport = {
    schema: REPORT_SCHEMA,
    run_id: runId,
    started_at: startedAt.toISOString(),
    finished_at: "",
    status: "not_run",
    versions: collectVersions(),
    model: null,
    target: { qdash: "", project_id: env.QDASH_PROJECT_ID ?? "", chip_id: options.chipId, qid: options.qid },
    limits: { turn_timeout_seconds: options.turnTimeoutSeconds, max_tool_calls: options.maxToolCalls, setup_timeout_seconds: options.setupTimeoutSeconds },
    preflight: [],
    setup: { ran: false, chip_created: false, executions: [] },
    scenarios: options.scenarios.map((scenario) => ({ id: scenario.id, title: scenario.title, status: "not_run", prompts: [], session_ids: [], execution_ids: [], intervention_ids: [], commit_ids: [], checks: [], artifacts: {} })),
    artifacts: { dir: outDir, report_json: join(outDir, "report.json"), report_md: join(outDir, "report.md") },
    not_validated: NOT_VALIDATED,
  };
  const finish = (status: ValidationReport["status"], reason?: string): number => {
    report.status = status;
    if (reason) report.reason = reason;
    report.finished_at = new Date().toISOString();
    const safe = redact(report, secrets);
    writeFileSync(report.artifacts.report_json, `${JSON.stringify(safe, null, 2)}\n`);
    writeFileSync(report.artifacts.report_md, renderMarkdown(safe));
    console.log(`[fake-loop] ${status}${reason ? `: ${redact(reason, secrets)}` : ""}`);
    console.log(`[fake-loop] report: ${report.artifacts.report_json}`);
    return status === "passed" ? 0 : status === "failed" ? 1 : 2;
  };

  const missing = ["QDASH_BASE_URL", "QDASH_API_TOKEN", "QDASH_PROJECT_ID"].filter((name) => !env[name]);
  if (missing.length > 0) return finish("blocked", `set ${missing.join(", ")} for the local fake deployment`);
  const baseUrl = String(env.QDASH_BASE_URL);
  try {
    report.target.qdash = new URL(baseUrl).host;
  } catch {
    return finish("blocked", "QDASH_BASE_URL is not a URL");
  }
  const api = new QDashApi({ baseUrl, token: String(env.QDASH_API_TOKEN), projectId: String(env.QDASH_PROJECT_ID) });

  const checked = await preflight(api, baseUrl, options.chipId, options.qid);
  report.preflight = checked.checks;
  report.versions = collectVersions(checked.apiVersion);
  if (!checked.ok || !checked.username) return finish("blocked", "the target could not be established as a local fake deployment");

  try {
    if (checked.chipExists === false) {
      if (!options.createChip) return finish("blocked", `chip ${options.chipId} does not exist; pass --create-chip to create it with the fake preset`);
      await createFakeChip(api, options.chipId);
      report.setup.chip_created = true;
    }
    await getQubit(api, options.chipId, options.qid);
  } catch (error) {
    return finish("blocked", error instanceof ApiError ? `chip setup: ${error.message}` : "chip setup failed");
  }

  if (options.setup) {
    report.setup.ran = true;
    for (const task of SETUP_TASKS) {
      try {
        const { executionId } = await runSetupTask(api, options.chipId, options.qid, task);
        const status = await waitForExecution(api, executionId, options.setupTimeoutSeconds * 1000);
        report.setup.executions.push({ task, execution_id: executionId, status });
        if (status !== "completed") return finish("blocked", `setup task ${task} ended ${status}`);
      } catch (error) {
        return finish("blocked", error instanceof ApiError ? `setup task ${task}: ${error.message}` : `setup task ${task} failed`);
      }
    }
  }
  const qubit = await getQubit(api, options.chipId, options.qid);
  const missingInputs = ["qubit_frequency", "t1"].filter((name) => qubitValue(qubit, name) === undefined);
  if (missingInputs.length > 0) return finish("blocked", `qubit ${options.qid} has no stored ${missingInputs.join(", ")}; run with --setup`);

  let launch: PiLaunch;
  try {
    const piArgs = ["--mode", "rpc", "--no-session", "--agent-dir", join(outDir, "pi-agent"), ...(options.envFile ? ["--env-file", options.envFile] : []), ...(options.model ? ["--model", options.model] : [])];
    const plan = prepareLocalCli(piArgs, env);
    secrets = effectiveSecrets(env, plan);
    report.model = { id: plan.model, source: plan.modelSource, profile: plan.profile ?? null };
    const pi = join(REPO_ROOT, "agent-runtime/node_modules/.bin/pi");
    launch = {
      command: existsSync(pi) ? pi : "pi",
      // The guard loads first so it sees each call before pi-qdash's approval gate.
      args: ["-e", GUARD_PATH, ...plan.args],
      env: { ...plan.env, [GUARD_ENV]: "1", [MAX_TOOL_CALLS_ENV]: String(options.maxToolCalls) },
    };
  } catch (error) {
    return finish("not_run", `the configured chat model is unavailable: ${error instanceof Error ? error.message : "unknown error"}`);
  }

  for (const [index, scenario] of options.scenarios.entries()) {
    try {
      report.scenarios[index] = await runScenario(api, options, launch, scenario, checked.username, runId, outDir, secrets);
    } catch (error) {
      report.scenarios[index] = { ...report.scenarios[index], status: "blocked", reason: error instanceof ApiError ? error.message : "the scenario stopped on an unexpected error" };
    }
    await sleep(1000);
  }
  const statuses = report.scenarios.map((scenario) => scenario.status);
  if (statuses.includes("failed")) return finish("failed");
  if (statuses.every((status) => status === "passed")) return finish("passed");
  return finish("blocked", "a scenario could not run");
}

if (import.meta.main) {
  main(process.argv.slice(2)).then((code) => process.exit(code));
}
