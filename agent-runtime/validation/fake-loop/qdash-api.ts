/**
 * The QDash requests of the validation harness: preflight, setup, the expert's
 * answer, and the evidence the evaluator reads.
 *
 * Errors carry the method, path, and status only. A response body may quote
 * input or server internals, so it never reaches the report.
 */

import { parseServerTimestamp } from "../../../packages/pi-qdash/extensions/lib/server-time.ts";

import { FAKE_TASKS } from "./scenarios.ts";

export interface ApiConfig {
  baseUrl: string;
  token: string;
  projectId: string;
  /** Request timeout in milliseconds. */
  timeoutMs?: number;
  fetch?: typeof fetch;
}

export class ApiError extends Error {
  constructor(
    readonly method: string,
    readonly path: string,
    readonly status: number | "transport",
  ) {
    super(`${method} ${path} failed (${status})`);
  }
}

export type Json = Record<string, unknown>;

/** Only a local deployment may be validated; anything else could be shared or real hardware. */
export function isLoopbackUrl(value: string): boolean {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return false;
  return ["127.0.0.1", "localhost", "[::1]", "::1"].includes(url.hostname);
}

/** A validation chip id: a fixed prefix keeps every real chip out of reach. */
export const CHIP_ID_PATTERN = /^agentval-[a-z0-9][a-z0-9-]{0,40}$/;

export class QDashApi {
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly config: ApiConfig) {
    this.fetchImpl = config.fetch ?? fetch;
  }

  async request<T = Json>(method: string, path: string, body?: unknown): Promise<T> {
    const url = new URL(path.replace(/^\//, ""), this.config.baseUrl.endsWith("/") ? this.config.baseUrl : `${this.config.baseUrl}/`);
    let response: Response;
    try {
      response = await this.fetchImpl(url, {
        method,
        headers: {
          Authorization: `Bearer ${this.config.token}`,
          "X-Project-Id": this.config.projectId,
          Accept: "application/json",
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: AbortSignal.timeout(this.config.timeoutMs ?? 30_000),
      });
    } catch {
      throw new ApiError(method, path.split("?")[0], "transport");
    }
    if (!response.ok) {
      await response.body?.cancel().catch(() => {});
      throw new ApiError(method, path.split("?")[0], response.status);
    }
    return (await response.json()) as T;
  }

  get<T = Json>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  post<T = Json>(path: string, body: unknown): Promise<T> {
    return this.request<T>("POST", path, body);
  }
}

export interface PreflightCheck {
  id: string;
  passed: boolean;
  detail: string;
}

export interface PreflightResult {
  ok: boolean;
  checks: PreflightCheck[];
  username?: string;
  apiVersion?: string;
  chipExists?: boolean;
}

/** Endpoints the scenarios need; an older QDash without them cannot be validated. */
export const REQUIRED_PATHS = [
  "/agent-sessions/{session_id}/interventions/{intervention_id}/respond",
  "/agent-sessions/{session_id}/audit/export",
  "/executions/groups/agent-sessions/{session_id}",
  "/chips/config-sources",
  "/task-files/backend-config",
  "/task-files/tasks",
];

/**
 * Establish, from the server's own answers, that the target is a fake deployment
 * this harness may use. Every check must pass; a failed or unanswered check
 * blocks the run.
 */
export async function preflight(api: QDashApi, baseUrl: string, chipId: string, qid: string): Promise<PreflightResult> {
  const checks: PreflightCheck[] = [];
  const add = (id: string, passed: boolean, detail: string) => {
    checks.push({ id, passed, detail });
    return passed;
  };
  const attempt = async <T>(id: string, run: () => Promise<T>): Promise<T | undefined> => {
    try {
      return await run();
    } catch (error) {
      add(id, false, error instanceof ApiError ? error.message : "request failed");
      return undefined;
    }
  };
  const result: PreflightResult = { ok: false, checks };

  if (!add("loopback_url", isLoopbackUrl(baseUrl), "QDASH_BASE_URL must point at a local deployment (127.0.0.1, localhost, ::1)")) return result;
  if (!add("validation_chip_id", CHIP_ID_PATTERN.test(chipId), "the chip id must match agentval-<name>")) return result;
  if (!add("qid_format", /^\d{1,2}$/.test(qid) && Number(qid) < 64, "the qubit id must be a qubit of the 64-qubit fake device, such as 4")) return result;

  const me = await attempt("signed_in", () => api.get<Json>("/auth/me"));
  if (!me) return result;
  result.username = typeof me.username === "string" ? me.username : undefined;
  add("signed_in", result.username !== undefined, "the token belongs to a QDash user");

  const openapi = await attempt("api_capabilities", () => api.get<Json>("/openapi.json"));
  if (!openapi) return result;
  const paths = (openapi.paths ?? {}) as Json;
  const missing = REQUIRED_PATHS.filter((path) => !(path in paths));
  add("api_capabilities", missing.length === 0, missing.length === 0 ? "intervention, audit, and graph endpoints present" : `missing ${missing.join(", ")}`);
  const info = (openapi.info ?? {}) as Json;
  result.apiVersion = typeof info.version === "string" ? info.version : undefined;

  const sources = await attempt("deployment_backend_fake", () => api.get<Json>("/chips/config-sources"));
  if (sources) {
    add("deployment_backend_fake", sources.deployment_backend === "fake", `chip configuration reports deployment backend ${String(sources.deployment_backend)}`);
  }
  // Agent dispatch resolves a task with resolve_catalog_task
  // (src/qdash/api/services/catalog_task_run.py): no backend named, so get_default_backend();
  // the task must be enabled for that backend in backend.yaml (is_task_available) and listed
  // in the enabled task-file catalog (TaskFileService.list_task_info(enabled_only=True)).
  // /task-files/backend-config reports get_default_backend() and the enabled tasks per backend;
  // /task-files/tasks lists the same catalog. Neither reads the legacy /tasks collection.
  const backendConfig = await attempt("dispatch_backend_fake", () => api.get<Json>("/task-files/backend-config"));
  if (backendConfig) {
    const backend = backendConfig.default_backend;
    add("dispatch_backend_fake", backend === "fake", `agent dispatch uses the default backend ${String(backend)}`);
    const fake = ((backendConfig.backends ?? {}) as Json).fake as Json | undefined;
    const enabled = new Set(Array.isArray(fake?.tasks) ? (fake.tasks as unknown[]).filter((name): name is string => typeof name === "string") : []);
    const absent = [...FAKE_TASKS].filter((name) => !enabled.has(name));
    add(
      "fake_tasks_enabled",
      fake !== undefined && absent.length === 0,
      fake === undefined ? "backend.yaml defines no fake backend" : absent.length === 0 ? "every scenario task is enabled for the fake backend" : `not enabled: ${absent.join(", ")}`,
    );
  }
  const catalog = await attempt("fake_task_catalog", () => api.get<Json>("/task-files/tasks?backend=fake&enabled_only=true"));
  if (catalog) {
    const listed = new Set(
      ((Array.isArray(catalog.tasks) ? catalog.tasks : []) as Json[])
        .filter((task) => task.enabled !== false && typeof task.name === "string")
        .map((task) => task.name as string),
    );
    const absent = [...FAKE_TASKS].filter((name) => !listed.has(name));
    add("fake_task_catalog", absent.length === 0, absent.length === 0 ? "every scenario task has an enabled fake task definition" : `no enabled task definition: ${absent.join(", ")}`);
  }

  try {
    await api.get(`/chips/${encodeURIComponent(chipId)}`);
    result.chipExists = true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) result.chipExists = false;
    else add("chip_readable", false, error instanceof ApiError ? error.message : "request failed");
  }
  result.ok = checks.every((check) => check.passed);
  return result;
}

/**
 * Create the disposable chip with the `fake` preset. QDash accepts the preset only
 * on a fake deployment, so a created chip is a second, server-side proof.
 */
export async function createFakeChip(api: QDashApi, chipId: string): Promise<Json> {
  return api.post("/chips", { chip_id: chipId, size: 64, topology_id: "square-lattice-mux-64", config: { preset: "fake" } });
}

/** The chip's qubit record, which proves the qubit is part of its topology. */
export async function getQubit(api: QDashApi, chipId: string, qid: string): Promise<Json> {
  return api.get(`/chips/${encodeURIComponent(chipId)}/qubits/${encodeURIComponent(qid)}`);
}

const TERMINAL = new Set(["completed", "failed", "cancelled", "canceled", "crashed", "skipped"]);

/** Poll an execution until it reaches a terminal status or the deadline passes. */
export async function waitForExecution(
  api: QDashApi,
  executionId: string,
  timeoutMs: number,
  pollMs = 3000,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    let status = "unknown";
    try {
      const execution = await api.get<Json>(`/executions/${encodeURIComponent(executionId)}`);
      status = String(execution.status ?? "unknown").toLowerCase();
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    }
    if (TERMINAL.has(status)) return status;
    if (Date.now() >= deadline) return `timeout:${status}`;
    await sleep(pollMs);
  }
}

/** Run one prerequisite task on the fake backend and keep its outputs as the current calibration. */
export async function runSetupTask(api: QDashApi, chipId: string, qid: string, taskName: string): Promise<{ executionId: string }> {
  const response = await api.post<Json>(`/tasks/${encodeURIComponent(taskName)}/execute`, {
    chip_id: chipId,
    qid,
    backend_name: "fake",
    update_calibration_parameters: true,
  });
  return { executionId: String(response.execution_id) };
}

/** The evidence of one session, read from QDash after the scenario. */
export interface SessionEvidence {
  session: Json;
  actions: Json[];
  interventions: Json[];
  commits: Json[];
  audit: Json;
  graph: Json;
}

function list(value: unknown, key: string): Json[] {
  if (Array.isArray(value)) return value as Json[];
  const items = (value as Json | undefined)?.[key];
  return Array.isArray(items) ? (items as Json[]) : [];
}

/**
 * The caller's sessions on the chip created at or after `since`. QDash returns
 * `created_at` without an offset; it is UTC (see `parseServerTimestamp`). A
 * session whose `created_at` is not a valid timestamp is left out.
 */
export function sessionsCreatedSince(sessions: readonly Json[], since: Date): Json[] {
  return sessions.filter((session) => parseServerTimestamp(session.created_at) >= since.getTime() - 1000);
}

export async function listScenarioSessions(api: QDashApi, chipId: string, since: Date): Promise<Json[]> {
  return sessionsCreatedSince(list(await api.get(`/agent-sessions?mine=true&limit=100&chip_id=${encodeURIComponent(chipId)}`), "items"), since);
}

/** Session statuses in which a session can still take steps or is paused for an expert. */
export const OPEN_SESSION_STATUSES: ReadonlySet<string> = new Set(["active", "waiting_for_human"]);

/** The caller's open sessions on the chip, whenever they were created. */
export async function listOpenSessions(api: QDashApi, chipId: string): Promise<Json[]> {
  const sessions = list(await api.get(`/agent-sessions?mine=true&limit=100&chip_id=${encodeURIComponent(chipId)}`), "items");
  return sessions.filter((session) => OPEN_SESSION_STATUSES.has(String(session.status)));
}

export async function collectSession(api: QDashApi, sessionId: string): Promise<SessionEvidence> {
  const base = `/agent-sessions/${encodeURIComponent(sessionId)}`;
  const [session, actions, interventions, audit, graph] = await Promise.all([
    api.get(base),
    api.get(`${base}/actions`),
    api.get(`${base}/interventions`),
    api.get(`${base}/audit/export`),
    api.get(`/executions/groups/agent-sessions/${encodeURIComponent(sessionId)}`),
  ]);
  const commitIds = [
    ...new Set(
      list(audit, "events")
        .filter((event) => event.kind === "candidate_commit" && typeof event.commit_id === "string")
        .map((event) => event.commit_id as string),
    ),
  ];
  const commits = await Promise.all(commitIds.map((id) => api.get(`${base}/commits/${encodeURIComponent(id)}`)));
  return {
    session,
    actions: list(actions, "items"),
    interventions: list(interventions, "items"),
    commits,
    audit,
    graph,
  };
}

/** Executions on the disposable chip that started at or after `since`. */
export async function listChipExecutions(api: QDashApi, chipId: string, since: Date): Promise<Json[]> {
  const response = await api.get(`/executions?chip_id=${encodeURIComponent(chipId)}&limit=100`);
  return list(response, "executions").filter((execution) => {
    const started = parseServerTimestamp(execution.start_at);
    return Number.isFinite(started) && started >= since.getTime() - 1000;
  });
}

/** The expert's answer, given by the harness as the signed-in project editor. */
export async function respondToIntervention(
  api: QDashApi,
  sessionId: string,
  interventionId: string,
  expectedStateVersion: number,
  guidance: string,
  idempotencyKey: string,
): Promise<Json> {
  return api.post(
    `/agent-sessions/${encodeURIComponent(sessionId)}/interventions/${encodeURIComponent(interventionId)}/respond`,
    { idempotency_key: idempotencyKey, expected_state_version: expectedStateVersion, decision: "resume", guidance },
  );
}

// ------------------------------------------------------------- calibration sessions

/**
 * Whether the deployment records calibration sessions and the origin a pipeline caller
 * reports. A scenario that needs them is blocked on an older revision rather than failed.
 */
export async function calibrationCapabilities(api: QDashApi): Promise<{ ok: boolean; detail: string }> {
  const openapi = await api.get<Json>("/openapi.json");
  const paths = (openapi.paths ?? {}) as Json;
  const needed = ["/calibration-sessions", "/calibration-sessions/{calibration_session_id}", "/calibration-pipelines/execute"];
  const missing = needed.filter((path) => !(path in paths));
  const schemas = (((openapi.components ?? {}) as Json).schemas ?? {}) as Json;
  const request = ((schemas.ExecutePipelineRequest ?? {}) as Json).properties as Json | undefined;
  const summary = ((schemas.ExecutionResponseSummary ?? {}) as Json).properties as Json | undefined;
  if (!request || !("reported_origin" in request)) missing.push("ExecutePipelineRequest.reported_origin");
  if (!summary || !("calibration_session" in summary) || !("reported_origin" in summary)) missing.push("ExecutionResponseSummary.calibration_session/reported_origin");
  return missing.length === 0 ? { ok: true, detail: "calibration sessions and reported origins present" } : { ok: false, detail: `missing ${missing.join(", ")}` };
}

/** The caller's calibration sessions on the chip created at or after `since`. */
export async function listScenarioCalibrationSessions(api: QDashApi, chipId: string, since: Date): Promise<Json[]> {
  return sessionsCreatedSince(list(await api.get(`/calibration-sessions?mine=true&limit=100&chip_id=${encodeURIComponent(chipId)}`), "items"), since);
}

export async function getCalibrationSession(api: QDashApi, calibrationSessionId: string): Promise<Json> {
  return api.get(`/calibration-sessions/${encodeURIComponent(calibrationSessionId)}`);
}

export async function getExecution(api: QDashApi, executionId: string): Promise<Json> {
  return api.get(`/executions/${encodeURIComponent(executionId)}`);
}

/**
 * Start a pipeline as a person would through the API: no calibration session and no reported
 * origin. Used only for the unassociated baseline on the validation chip.
 */
export async function runManualPipeline(api: QDashApi, chipId: string, spec: Record<string, unknown>): Promise<{ executionId: string; flowRunId: string }> {
  if (!CHIP_ID_PATTERN.test(chipId)) throw new Error("a manual pipeline runs only on an agentval-* chip");
  const response = await api.post<Json>("/calibration-pipelines/execute", { chip_id: chipId, spec });
  return { executionId: String(response.execution_id), flowRunId: String(response.flow_run_id) };
}

/** Every execution of a pipeline flow run on the chip, newest first, from the chip's list. */
export async function listFlowRunExecutions(api: QDashApi, chipId: string, flowRunId: string): Promise<Json[]> {
  const response = await api.get(`/executions?chip_id=${encodeURIComponent(chipId)}&limit=100`);
  return list(response, "executions").filter((execution) => ((execution.note ?? {}) as Json).flow_run_id === flowRunId);
}
