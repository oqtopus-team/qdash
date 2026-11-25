/**
 * The QDash operations pi-qdash tools call, on one `@oqtopus-team/qdash-sdk` session.
 *
 * Every request goes through the session: its generated client (`qdash.api`) for the routes it
 * models, and `qdash.fetch` for downloads and arbitrary GETs. The session carries the auth,
 * the project (`X-Project-Id`), the Cloudflare Access headers, the timeout and the fetch, so
 * all tools of one call share one sign-in and one project. Reads go through `qdash.read`
 * (sent again after a transient failure, up to the config's `readAttempts`); writes through
 * `qdash.send` (sent once). Failures are the SDK's errors: `QDashNotFoundError` for 404,
 * `QDashAuthError` for 401 and 403, and so on, each with `statusCode` and `payload`.
 *
 * The methods keep the names, arguments, checks and results the tools relied on, including
 * the polling loops of the waiting tools and the guarded creation of an agent session in a
 * calibration session.
 */
import { setTimeout as sleep } from "node:timers/promises";

import {
  QDash,
  QDashApiError,
  QDashNotFoundError,
  QDashResultUnknownError,
  QDashTimeoutError,
  QDashValidationError,
  type QDashApi,
  type QDashCallOptions,
  type QDashConfig,
  type QDashQueryValue,
} from "@oqtopus-team/qdash-sdk";

type JsonObject = Record<string, unknown>;

export type AgentActionResponse = QDashApi.AgentActionResponse;
export type AgentActionType = QDashApi.AgentActionType;
export type AgentCandidateCommitResponse = QDashApi.AgentCandidateCommitResponse;
export type AgentCandidateReference = QDashApi.AgentCandidateReference;
export type AgentCandidateResponse = QDashApi.AgentCandidateResponse;
export type AgentCandidateSetCommitResponse = QDashApi.AgentCandidateSetCommitResponse;
export type AgentDecisionAssessment = QDashApi.AgentDecisionAssessment;
export type AgentDecisionNextAction = QDashApi.AgentDecisionNextAction;
export type AgentDecisionResponse = QDashApi.AgentDecisionResponse;
export type AgentInterventionAttempt = QDashApi.AgentInterventionAttempt;
export type AgentInterventionReason = QDashApi.AgentInterventionReason;
export type AgentInterventionResponse = QDashApi.AgentInterventionResponse;
export type AgentModelIdentity = QDashApi.AgentModelIdentity;
export type AgentSessionAuditResponse = QDashApi.AgentSessionAuditResponse;
export type AgentSessionPolicy = QDashApi.AgentSessionPolicy;
export type AgentSessionResponse = QDashApi.AgentSessionResponse;
export type AgentSessionStatus = QDashApi.AgentSessionStatus;
export type ChipResponse = QDashApi.ChipResponse;
export type CooldownResponse = QDashApi.CooldownResponse;
export type ExecutionResponseDetail = QDashApi.ExecutionResponseDetail;
export type StopAgentSessionResponse = QDashApi.StopAgentSessionResponse;
export type TaskHistoryResponse = QDashApi.TaskHistoryResponse;
export type TaskResultListResponse = QDashApi.TaskResultListResponse;
export type TaskResultResponse = QDashApi.TaskResultResponse;

/** Most rows one `GET /task-results` request returns; the API rejects a larger `limit`. */
export const TASK_RESULTS_MAX_PAGE_SIZE = 100;
/** Most executions `GET /executions` returns per request. */
export const EXECUTIONS_MAX_PAGE_SIZE = 100;

export interface PaginationOptions {
  limit?: number;
  offset?: number;
}

export interface TaskResultsTimeseriesOptions {
  chipId: string;
  parameter: string;
  startAt: string;
  endAt: string;
  tag?: string;
  qid?: string;
}

export interface SearchSourceOptions {
  query: string;
  root?: string;
  pathPrefix?: string;
  mode?: "content" | "path";
  caseSensitive?: boolean;
  limit?: number;
}

export interface GetSourceFileOptions {
  path: string;
  root?: string;
  startLine?: number;
  endLine?: number;
}

/** Filters and one page of `GET /task-results`, newest first. */
export interface ListTaskResultsOptions {
  chipId?: string;
  taskName?: string;
  /** Exact qubit (`"6"`) or coupling (`"6-7"`) ID as QDash stores it; not normalized. */
  qid?: string;
  executionId?: string;
  username?: string;
  status?: string;
  startFrom?: string;
  startTo?: string;
  messageContains?: string;
  stepId?: string;
  callId?: string;
  /** Rows in this page: an integer from 1 to 100. The server default is 50. */
  limit?: number;
  /** Rows to skip before this page: an integer of 0 or more. */
  skip?: number;
  /** Cancels the request. */
  signal?: AbortSignal;
}

/** Options of `listExecutions`: one chip's executions by page and start day. */
export interface ListExecutionsOptions {
  chipId: string;
  skip?: number;
  limit?: number;
  /** Only executions started on this calendar day, YYYYMMDD. */
  date?: string;
  /** IANA time zone that defines the day for `date` (the API default is UTC). */
  timezone?: string;
}

export interface QubitTaskHistoryOptions {
  chipId: string;
  qid: string;
  task: string;
}

export interface CouplingTaskHistoryOptions {
  chipId: string;
  couplingId: string;
  task: string;
}

export interface CreateAgentSessionOptions {
  chipId: string;
  policy: AgentSessionPolicy;
  expiresInSeconds?: number;
  skillName?: string;
  skillVersion?: string;
  skillHash?: string;
  /** The provider and model the host ran the agent with, from the host's own runtime. */
  model?: AgentModelIdentity;
  /** Create the session in this calibration session (open, on the same chip, of the user). */
  calibrationSessionId?: string;
}

export interface SubmitAgentActionOptions {
  idempotencyKey: string;
  expectedStateVersion: number;
  actionType: AgentActionType;
  taskName?: string | null;
  qids?: string[];
  parameterOverrides?: Record<string, number>;
  diagnosis?: string;
  autonomous?: boolean;
  repeatOfActionId?: string;
  model?: AgentModelIdentity;
}

export interface ListAgentSessionsOptions {
  chipId?: string;
  statuses?: AgentSessionStatus[];
  mine?: boolean;
  limit?: number;
}

export interface CreateAgentInterventionOptions {
  idempotencyKey: string;
  reason: AgentInterventionReason;
  summary: string;
  question: string;
  taskName?: string;
  qids?: string[];
  attempts?: AgentInterventionAttempt[];
  previousInterventionId?: string;
  autonomous?: boolean;
  model?: AgentModelIdentity;
}

export interface StopAgentSessionOptions {
  idempotencyKey: string;
  reason: string;
}

export interface RecordAgentDecisionOptions {
  idempotencyKey: string;
  assessment?: AgentDecisionAssessment;
  interpretation: string;
  nextAction: AgentDecisionNextAction;
  nextDetail?: string;
  evidenceActionIds?: string[];
  evaluationIds?: string[];
  nextActionId?: string;
  interventionId?: string;
  supersedesDecisionId?: string;
  model?: AgentModelIdentity;
}

export interface AgentSessionAuditPageOptions {
  cursor?: string;
  limit?: number;
}

export interface PollOptions {
  timeoutSeconds?: number;
  pollIntervalSeconds?: number;
  /**
   * For an execution that is one step of a pipeline run, wait for the whole run rather than
   * that step (default true).
   */
  wholePipeline?: boolean;
  /** Poll again while the execution is not listed yet (404) instead of throwing (default false). */
  notFoundAsPending?: boolean;
  /** Stops the wait between polls and cancels a read in flight; rejects with the signal's reason. */
  signal?: AbortSignal;
}

export interface DownloadedFile {
  data: ArrayBuffer;
  mediaType: string;
  filename?: string;
}

export interface TaskResultFigureOptions {
  index?: number;
  preferJson?: boolean;
}

export interface RecentChangesOptions {
  parameterNames?: string[];
  withinHours?: number;
  limit?: number;
}

export interface DegradationTrendsOptions {
  minStreak?: number;
  limit?: number;
  parameterNames?: string[];
}

export interface RecalibrationRecommendationsOptions {
  maxDepth?: number;
}

export interface ForumPostListOptions {
  category?: string;
  status?: string;
  chipId?: string;
  targetType?: string;
  targetId?: string;
  skip?: number;
  limit?: number;
}

const TASK_RESULTS_PAGE_HINT =
  "QDash returns at most 100 task results per request; request further pages with skip";

const EXECUTION_TERMINAL = new Set(["completed", "failed", "cancelled", "canceled", "crashed"]);

/** Request options for a generated call, without undefined members. */
function defined<T extends Record<string, unknown>>(values: T): T {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined && value !== null)) as T;
}

/** Throw before any request when an optional option is not an integer within bounds. */
function checkInteger(name: string, value: number | undefined, minimum: number, maximum: number | undefined, hint?: string): void {
  if (value === undefined) return;
  if (Number.isInteger(value) && value >= minimum && (maximum === undefined || value <= maximum)) return;
  const range = maximum === undefined ? `${minimum} or more` : `from ${minimum} to ${maximum}`;
  throw new QDashValidationError(`${name} must be an integer ${range} (got ${String(value)})${hint ? `. ${hint}.` : "."}`, {
    body: { field: name, value },
  });
}

const EXECUTION_LIST_OPTIONS = new Set(["chipId", "skip", "limit", "date", "timezone"]);

function isIntegerIn(value: unknown, minimum: number, maximum?: number): boolean {
  return Number.isInteger(value) && (value as number) >= minimum && (maximum === undefined || (value as number) <= maximum);
}

/**
 * Why `listExecutions` options other than `chipId` cannot be sent, one message per problem;
 * empty when they can. `GET /executions` lists one chip's executions by page (`skip`, `limit`)
 * and start day (`date`, `timezone`) only, so a supplied `flowName`, `status` or other option
 * is a problem rather than silently dropped. An option set to `undefined` counts as omitted.
 */
export function executionListProblems(options: Readonly<Record<string, unknown>>): string[] {
  const problems: string[] = [];
  const supplied = (key: string) => options[key] !== undefined;
  const unsupported = ["flowName", "status"].filter(supplied);
  if (unsupported.length > 0) {
    problems.push(
      `${unsupported.join(" and ")} cannot filter executions: QDash lists a chip's executions only by page (skip, limit) and day (date, timezone); filter the returned rows by flow_name or status instead`,
    );
  }
  const unknown = Object.keys(options).filter(
    (key) => supplied(key) && key !== "flowName" && key !== "status" && !EXECUTION_LIST_OPTIONS.has(key),
  );
  if (unknown.length > 0) problems.push(`${unknown.join(", ")} ${unknown.length === 1 ? "is not an option" : "are not options"} of listExecutions`);
  if (supplied("limit") && !isIntegerIn(options.limit, 1, EXECUTIONS_MAX_PAGE_SIZE)) {
    problems.push(`limit must be an integer from 1 to ${EXECUTIONS_MAX_PAGE_SIZE} (got ${JSON.stringify(options.limit)})`);
  }
  if (supplied("skip") && !isIntegerIn(options.skip, 0)) {
    problems.push(`skip must be an integer of 0 or more (got ${JSON.stringify(options.skip)})`);
  }
  if (supplied("date") && !(typeof options.date === "string" && /^\d{8}$/.test(options.date))) {
    problems.push(`date must be YYYYMMDD (got ${JSON.stringify(options.date)})`);
  }
  if (supplied("timezone") && !(typeof options.timezone === "string" && options.timezone.trim() !== "")) {
    problems.push(`timezone must be a non-empty IANA time zone name (got ${JSON.stringify(options.timezone)})`);
  }
  return problems;
}

function requireText(field: string, value: unknown, purpose: string): string {
  if (typeof value === "string" && value.trim() !== "") return value;
  throw new QDashValidationError(`${field} is required to ${purpose}.`, { body: { field, value } });
}

function checkTaskHistoryOptions(options: Readonly<Record<string, unknown>>, target: "qid" | "couplingId"): void {
  const supplied = Object.keys(options).filter((key) => options[key] !== undefined);
  const problems: string[] = [];
  if (supplied.includes("date")) {
    problems.push(
      `date cannot filter a task history: it returns every result of the task for one target, newest first. Omit date, or use listTaskResults({ chipId, ${target === "qid" ? "qid" : "qid: couplingId"}, taskName, startFrom, startTo }) for one period`,
    );
  }
  const unknown = supplied.filter((key) => key !== "date" && !["chipId", "task", target].includes(key));
  if (unknown.length > 0) problems.push(`${unknown.join(", ")} ${unknown.length === 1 ? "is not an option" : "are not options"} of a task history`);
  if (problems.length > 0) throw new QDashValidationError(`${problems.join("; ")}.`, { body: { problems } });
}

/** The history, or an error naming what is wrong; never an empty history in place of a malformed one. */
function checkTaskHistory(payload: unknown, route: string): TaskHistoryResponse {
  const body = payload as Partial<TaskHistoryResponse> | null;
  const problems: string[] = [];
  if (!body || typeof body !== "object" || Array.isArray(body)) problems.push("the body is not an object");
  else {
    if (typeof body.name !== "string") problems.push("name is not a string");
    if (!body.data || typeof body.data !== "object" || Array.isArray(body.data)) problems.push("data is not an object");
    else if (Object.values(body.data).some((entry) => !entry || typeof entry !== "object" || Array.isArray(entry))) {
      problems.push("a data entry is not an object");
    }
  }
  if (problems.length > 0) throw new QDashApiError(`Unexpected GET ${route} response: ${problems.join("; ")}`, { body: payload });
  return body as TaskHistoryResponse;
}

/** The page, or an error naming what is missing; never an empty page in place of a malformed one. */
function checkTaskResultPage(payload: unknown): TaskResultListResponse {
  const page = payload as Partial<TaskResultListResponse> | null;
  const problems: string[] = [];
  if (!page || typeof page !== "object") problems.push("the body is not an object");
  else {
    if (!Array.isArray(page.items)) problems.push("items is not an array");
    else if (page.items.some((item) => !item || typeof item.task_id !== "string")) problems.push("an item has no task_id");
    if (!Number.isInteger(page.total)) problems.push("total is not an integer");
  }
  if (problems.length > 0) throw new QDashApiError(`Unexpected GET /task-results response: ${problems.join("; ")}`, { body: payload });
  return page as TaskResultListResponse;
}

function filenameFromPath(path: string): string | undefined {
  return path.split("/").filter(Boolean).at(-1);
}

function mediaTypeForPath(path: string): string {
  const lower = path.toLowerCase();
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".gif")) return "image/gif";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".json")) return "application/json";
  return "application/octet-stream";
}

/** A response body as JSON when it parses, else as text; undefined when empty. */
async function responseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function checkPollOptions(timeoutSeconds: number, pollIntervalSeconds: number): void {
  if (timeoutSeconds < 0 || pollIntervalSeconds < 0) {
    throw new RangeError("Polling timeout and interval must be non-negative");
  }
}

function pause(seconds: number, signal: AbortSignal | undefined): Promise<void> {
  return sleep(seconds * 1_000, undefined, signal ? { signal } : {}).then(
    () => undefined,
    (error: unknown) => {
      throw signal?.aborted ? (signal.reason ?? error) : error;
    },
  );
}

/** Whether a record is one of `QDashApi`'s responses as an object. */
function isRecord(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * The QDash operations of pi-qdash on one SDK session. Creating it sends no request.
 */
export class QDashConnection {
  /** The SDK session every request of this connection goes through. */
  readonly qdash: QDash;

  constructor(qdash: QDash) {
    this.qdash = qdash;
  }

  /** The session's settings: base URL, project, timeout, read attempts; never sent anywhere else. */
  get config(): QDashConfig {
    return this.qdash.config;
  }

  /** The generated client of the whole API, with this connection's auth and project. */
  get api(): QDash["api"] {
    return this.qdash.api;
  }

  /** A connection to `projectId` with this session's fetch and sign-in; this one is unchanged. */
  withProject(projectId: string): QDashConnection {
    return new QDashConnection(this.qdash.withProject(projectId));
  }

  private read<T>(request: (options: QDashCallOptions) => Promise<T>, signal?: AbortSignal): Promise<T> {
    return this.qdash.read(request, signal ? { signal } : {});
  }

  private send<T>(request: (options: QDashCallOptions) => Promise<T>): Promise<T> {
    return this.qdash.send(request);
  }

  /**
   * A read-only GET of any API path, for routes the generated client does not model; the body
   * as JSON when it parses, else as text. Query values that are null or undefined are left out.
   */
  async rawGet<T = unknown>(path: string, query?: Readonly<Record<string, QDashQueryValue>>): Promise<T> {
    const response = await this.qdash.fetch(path, query ? { query } : {});
    return (await responseBody(response)) as T;
  }

  /** The user QDash authenticated for this connection's credentials. */
  getCurrentUser(): Promise<QDashApi.User> {
    return this.read((o) => this.api.auth.getCurrentUser(o));
  }

  listChips(): Promise<QDashApi.ListChipsResponse> {
    return this.read((o) => this.api.chip.listChips(o));
  }

  /** The newest installed active chip, else the newest chip; `QDashNotFoundError` without chips. */
  async getDefaultChip(): Promise<ChipResponse> {
    const { chips } = await this.listChips();
    if (!chips || chips.length === 0) throw new QDashNotFoundError("No chips are available");
    const active = chips.filter((chip) => chip.activity_status === "active");
    const candidates = active.length > 0 ? active : chips;
    return candidates.reduce((latest, chip) => {
      const latestTime = latest.installed_at ? Date.parse(latest.installed_at) : 0;
      const chipTime = chip.installed_at ? Date.parse(chip.installed_at) : 0;
      return chipTime > latestTime ? chip : latest;
    });
  }

  async getDefaultChipId(): Promise<string> {
    return (await this.getDefaultChip()).chip_id;
  }

  getChipMetrics(chipId: string): Promise<QDashApi.ChipMetricsResponse> {
    return this.read((o) => this.api.metrics.getChipMetrics({ chip_id: chipId }, o));
  }

  getMetricsConfig(): Promise<JsonObject> {
    return this.read((o) => this.api.metrics.getMetricsConfig(o));
  }

  listChipQubits(chipId: string, options: PaginationOptions = {}): Promise<QDashApi.ListQubitsResponse> {
    return this.read((o) => this.api.chip.listChipQubits(defined({ chip_id: chipId, limit: options.limit, offset: options.offset }), o));
  }

  getChipQubit(chipId: string, qid: string): Promise<QDashApi.QubitResponse> {
    return this.read((o) => this.api.chip.getChipQubit({ chip_id: chipId, qid }, o));
  }

  listChipCouplings(chipId: string, options: PaginationOptions = {}): Promise<QDashApi.ListCouplingsResponse> {
    return this.read((o) => this.api.chip.listChipCouplings(defined({ chip_id: chipId, limit: options.limit, offset: options.offset }), o));
  }

  getChipCoupling(chipId: string, couplingId: string): Promise<QDashApi.CouplingResponse> {
    return this.read((o) => this.api.chip.getChipCoupling({ chip_id: chipId, coupling_id: couplingId }, o));
  }

  getTaskResultsTimeseries(options: TaskResultsTimeseriesOptions): Promise<QDashApi.TimeSeriesData> {
    return this.read((o) =>
      this.api.taskResult.getTimeseriesTaskResults(
        defined({
          chip_id: options.chipId,
          parameter: options.parameter,
          start_at: options.startAt,
          end_at: options.endAt,
          tag: options.tag,
          qid: options.qid,
        }),
        o,
      ),
    );
  }

  /**
   * One page of task results. `limit` must be an integer from 1 to 100 and `skip` an integer
   * of 0 or more; other values throw `QDashValidationError` before any request. A body without
   * `items` and an integer `total` throws `QDashApiError`.
   */
  async listTaskResults(options: ListTaskResultsOptions = {}): Promise<TaskResultListResponse> {
    checkInteger("limit", options.limit, 1, TASK_RESULTS_MAX_PAGE_SIZE, TASK_RESULTS_PAGE_HINT);
    checkInteger("skip", options.skip, 0, undefined);
    const payload = await this.read(
      (o) =>
        this.api.taskResult.listTaskResults(
          defined({
            chip_id: options.chipId,
            task_name: options.taskName,
            qid: options.qid,
            execution_id: options.executionId,
            username: options.username,
            status: options.status,
            start_from: options.startFrom,
            start_to: options.startTo,
            message_contains: options.messageContains,
            step_id: options.stepId,
            call_id: options.callId,
            limit: options.limit,
            skip: options.skip,
          }),
          o,
        ),
      options.signal,
    );
    return checkTaskResultPage(payload);
  }

  /**
   * Every result of `task` for one qubit, newest first, keyed by task ID. A missing argument,
   * or a supplied `date` or other option, throws `QDashValidationError` before any request.
   */
  async getQubitTaskHistory(options: QubitTaskHistoryOptions): Promise<TaskHistoryResponse> {
    const chipId = requireText("chipId", options?.chipId, "read a task history");
    const qid = requireText("qid", options.qid, "read a qubit task history");
    const task = requireText("task", options.task, "read a task history");
    checkTaskHistoryOptions(options as unknown as Record<string, unknown>, "qid");
    const payload = await this.read((o) => this.api.taskResult.getQubitTaskHistory({ qid, chip_id: chipId, task }, o));
    return checkTaskHistory(payload, `/task-results/qubits/${encodeURIComponent(qid)}/history`);
  }

  /** Every result of `task` for one coupling, with the same checks as `getQubitTaskHistory`. */
  async getCouplingTaskHistory(options: CouplingTaskHistoryOptions): Promise<TaskHistoryResponse> {
    const chipId = requireText("chipId", options?.chipId, "read a task history");
    const couplingId = requireText("couplingId", options.couplingId, "read a coupling task history");
    const task = requireText("task", options.task, "read a task history");
    checkTaskHistoryOptions(options as unknown as Record<string, unknown>, "couplingId");
    const payload = await this.read((o) =>
      this.api.taskResult.getCouplingTaskHistory({ coupling_id: couplingId, chip_id: chipId, task }, o),
    );
    return checkTaskHistory(payload, `/task-results/couplings/${encodeURIComponent(couplingId)}/history`);
  }

  getLatestQubitTaskResults(chipId: string, task: string): Promise<QDashApi.LatestTaskResultResponse> {
    return this.read((o) => this.api.taskResult.getLatestQubitTaskResults({ chip_id: chipId, task }, o));
  }

  getLatestCouplingTaskResults(chipId: string, task: string): Promise<QDashApi.LatestTaskResultResponse> {
    return this.read((o) => this.api.taskResult.getLatestCouplingTaskResults({ chip_id: chipId, task }, o));
  }

  getTaskResult(taskId: string): Promise<TaskResultResponse> {
    return this.read((o) => this.api.task.getTaskResult({ task_id: taskId }, o));
  }

  getTaskNote(taskId: string): Promise<QDashApi.NoteModel> {
    return this.read((o) => this.api.note.getTaskNote({ task_id: taskId }, o));
  }

  listTasks(backend?: string): Promise<QDashApi.ListTaskResponse> {
    return this.read((o) => this.api.task.listTasks(defined({ backend }), o));
  }

  listTaskKnowledge(): Promise<QDashApi.ListTaskKnowledgeResponse> {
    return this.read((o) => this.api.task.listTaskKnowledge(o));
  }

  getTaskKnowledge(taskName: string): Promise<QDashApi.TaskKnowledgeResponse> {
    return this.read((o) => this.api.task.getTaskKnowledge({ task_name: taskName }, o));
  }

  /** The task's knowledge as Markdown text, exactly as QDash serves it. */
  getTaskKnowledgeMarkdown(taskName: string): Promise<string> {
    return this.read((o) => this.api.task.getTaskKnowledgeMarkdown({ task_name: taskName }, o));
  }

  /** Source trees the Agent may read, with the revision of each when it is known. */
  listSourceRoots(): Promise<QDashApi.ListSourceRootsResponse> {
    return this.read((o) => this.api.agent.listAgentSourceRoots(o));
  }

  /** Literal search in source contents (`content`) or file paths (`path`). */
  searchSource(options: SearchSourceOptions): Promise<QDashApi.SearchSourceResponse> {
    return this.read((o) =>
      this.api.agent.searchAgentSource(
        defined({
          query: options.query,
          root: options.root,
          path_prefix: options.pathPrefix,
          mode: options.mode,
          case_sensitive: options.caseSensitive,
          limit: options.limit,
        }),
        o,
      ),
    );
  }

  /** A numbered line range of one source file; without `root`, a traceback path is mapped. */
  getSourceFile(options: GetSourceFileOptions): Promise<QDashApi.SourceFileResponse> {
    return this.read((o) =>
      this.api.agent.getAgentSourceFile(
        defined({ path: options.path, root: options.root, start_line: options.startLine, end_line: options.endLine }),
        o,
      ),
    );
  }

  listProjects(): Promise<QDashApi.QdashApiSchemasProjectProjectListResponse> {
    return this.read((o) => this.api.projects.listProjects(o));
  }

  getProject(projectId: string): Promise<QDashApi.ProjectResponse> {
    return this.read((o) => this.api.projects.getProject({ project_id: projectId }, o));
  }

  /** The config file tree (`GET /config/files/tree`). */
  async getFilesTree(): Promise<QDashApi.FileTreeNode[]> {
    const payload: unknown = await this.read((o) => this.api.file.getFileTree(o));
    if (Array.isArray(payload)) return payload as QDashApi.FileTreeNode[];
    const tree = isRecord(payload) ? payload.tree : undefined;
    return Array.isArray(tree) ? (tree as QDashApi.FileTreeNode[]) : [];
  }

  /** One config file (`GET /config/files/content`). */
  getFileContent(path: string): Promise<JsonObject> {
    return this.read((o) => this.api.file.getFileContent({ path }, o));
  }

  /** The config repository's git status (`GET /config/files/git/status`). */
  getGitStatus(): Promise<JsonObject> {
    return this.read((o) => this.api.file.getGitStatus(o));
  }

  listFlows(): Promise<QDashApi.ListFlowsResponse> {
    return this.read((o) => this.api.flow.listFlows(o));
  }

  getFlow(name: string): Promise<QDashApi.GetFlowResponse> {
    return this.read((o) => this.api.flow.getFlow({ name }, o));
  }

  listFlowTemplates(backend?: string): Promise<QDashApi.FlowTemplate[]> {
    return this.read((o) => this.api.flow.listFlowTemplates(defined({ backend }), o));
  }

  getFlowTemplate(templateId: string): Promise<QDashApi.FlowTemplateWithCode> {
    return this.read((o) => this.api.flow.getFlowTemplate({ template_id: templateId }, o));
  }

  listFlowHelperFiles(): Promise<string[]> {
    return this.read((o) => this.api.flow.listFlowHelperFiles(o));
  }

  getFlowHelperFile(filename: string): Promise<string> {
    return this.read((o) => this.api.flow.getFlowHelperFile({ filename }, o));
  }

  saveFlow(request: QDashApi.SaveFlowRequest): Promise<QDashApi.SaveFlowResponse> {
    return this.send((o) => this.api.flow.saveFlow(request, o));
  }

  listMetricScripts(): Promise<QDashApi.ListMetricScriptsResponse> {
    return this.read((o) => this.api.metricScript.listMetricScripts(o));
  }

  getMetricScript(scriptId: string): Promise<QDashApi.MetricScriptResponse> {
    return this.read((o) => this.api.metricScript.getMetricScript({ script_id: scriptId }, o));
  }

  listMetricScriptTemplates(): Promise<QDashApi.ListMetricScriptTemplatesResponse> {
    return this.read((o) => this.api.metricScript.listMetricScriptTemplates(o));
  }

  getMetricScriptCatalog(): Promise<QDashApi.MetricScriptCatalogResponse> {
    return this.read((o) => this.api.metricScript.getMetricScriptCatalog(o));
  }

  /** Compile metric script source in a worker; nothing is saved. */
  validateMetricScript(source: string): Promise<QDashApi.MetricScriptValidateResponse> {
    return this.send((o) => this.api.metricScript.validateMetricScript({ source }, o));
  }

  /** Evaluate one metric of unsaved source on a chip; nothing is saved. */
  evaluateMetricScriptDraft(request: QDashApi.MetricScriptDraftEvaluateRequest): Promise<QDashApi.MetricScriptEvaluateResponse> {
    return this.send((o) => this.api.metricScript.evaluateMetricScriptDraft(request, o));
  }

  /** Evaluate one metric of a saved script's validated revision (the active one by default). */
  evaluateMetricScript(
    scriptId: string,
    request: Omit<QDashApi.MetricScriptEvaluateRequest, "script_id">,
  ): Promise<QDashApi.MetricScriptEvaluateResponse> {
    return this.send((o) => this.api.metricScript.evaluateMetricScript({ ...request, script_id: scriptId }, o));
  }

  listDashboards(): Promise<QDashApi.ListDashboardsResponse> {
    return this.read((o) => this.api.dashboard.listDashboards(o));
  }

  getDashboard(dashboardId: string): Promise<QDashApi.DashboardResponse> {
    return this.read((o) => this.api.dashboard.getDashboard({ dashboard_id: dashboardId }, o));
  }

  listDashboardTemplates(): Promise<QDashApi.ListDashboardTemplatesResponse> {
    return this.read((o) => this.api.dashboard.listDashboardTemplates(o));
  }

  /** What a dashboard created from a template now would hold. Writes nothing. */
  previewDashboardTemplate(templateId: string): Promise<QDashApi.DashboardTemplatePreviewResponse> {
    return this.read((o) => this.api.dashboard.previewDashboardTemplate({ template_id: templateId }, o));
  }

  createDashboard(request: QDashApi.DashboardCreateRequest): Promise<QDashApi.DashboardResponse> {
    return this.send((o) => this.api.dashboard.createDashboard(request, o));
  }

  /** Update a dashboard; a provided `panels` list replaces the previous one. */
  updateDashboard(dashboardId: string, request: Omit<QDashApi.DashboardUpdateRequest, "dashboard_id">): Promise<QDashApi.DashboardResponse> {
    return this.send((o) => this.api.dashboard.updateDashboard({ ...request, dashboard_id: dashboardId }, o));
  }

  listCryostats(): Promise<QDashApi.ListCryostatsResponse> {
    return this.read((o) => this.api.cryostat.listCryostats(o));
  }

  getCryostat(cryoId: string): Promise<QDashApi.CryostatResponse> {
    return this.read((o) => this.api.cryostat.getCryostat({ cryo_id: cryoId }, o));
  }

  listCooldowns(options: { cryoId?: string; chipId?: string } = {}): Promise<QDashApi.ListCooldownsResponse> {
    return this.read((o) => this.api.cooldown.listCooldowns(defined({ cryo_id: options.cryoId, chip_id: options.chipId }), o));
  }

  getCooldown(cooldownId: string): Promise<CooldownResponse> {
    return this.read((o) => this.api.cooldown.getCooldown({ cooldown_id: cooldownId }, o));
  }

  listCooldownWiringEvents(
    cooldownId: string,
    options: { limit?: number; skip?: number } = {},
  ): Promise<QDashApi.ListCooldownWiringEventsResponse> {
    return this.read((o) =>
      this.api.cooldownWiring.listCooldownWiringEvents(defined({ cooldown_id: cooldownId, limit: options.limit, skip: options.skip }), o),
    );
  }

  /**
   * One page of a chip's executions, newest first. A missing `chipId`, or any problem
   * `executionListProblems` reports, throws `QDashValidationError` before any request.
   */
  listExecutions(options: ListExecutionsOptions): Promise<QDashApi.ListExecutionsResponse> {
    requireText("chipId", options?.chipId, "list executions");
    const { chipId: _chipId, ...rest } = options;
    const problems = executionListProblems(rest);
    if (problems.length > 0) throw new QDashValidationError(`${problems.join("; ")}.`, { body: { problems } });
    return this.read((o) =>
      this.api.execution.listExecutions(
        defined({ chip_id: options.chipId, skip: options.skip, limit: options.limit, date: options.date, timezone: options.timezone }),
        o,
      ),
    );
  }

  getExecution(executionId: string, signal?: AbortSignal): Promise<ExecutionResponseDetail> {
    return this.read((o) => this.api.execution.getExecution({ execution_id: executionId }, o), signal);
  }

  getExecutionLockStatus(): Promise<QDashApi.ExecutionLockStatusResponse> {
    return this.read((o) => this.api.execution.getExecutionLockStatus(o));
  }

  /** A stored figure or artifact, as bytes, by its path. */
  async getExecutionFigure(path: string): Promise<DownloadedFile> {
    const response = await this.qdash.fetch("/executions/figure", { query: { path }, headers: { Accept: "*/*" } });
    return { data: await response.arrayBuffer(), mediaType: mediaTypeForPath(path), filename: filenameFromPath(path) };
  }

  /** A figure of a task result: the PNG at `index` (default 0), or its JSON with `preferJson`. */
  async getTaskResultFigure(
    taskId: string,
    options: TaskResultFigureOptions = {},
  ): Promise<DownloadedFile & { path: string; figurePaths: string[]; jsonFigurePaths: string[] }> {
    const task = await this.getTaskResult(taskId);
    const figurePaths = task.figure_path ?? [];
    const jsonFigurePaths = task.json_figure_path ?? [];
    const paths = options.preferJson && jsonFigurePaths.length > 0 ? jsonFigurePaths : figurePaths;
    const index = options.index ?? 0;
    const path = paths[index];
    if (!path) throw new QDashNotFoundError(`No figure at index ${index} for task result '${taskId}'`);
    const file = await this.getExecutionFigure(path);
    return { ...file, path, figurePaths, jsonFigurePaths };
  }

  /**
   * Poll an execution until it, or with `wholePipeline` (default true) its whole pipeline run,
   * reaches a terminal status; the run is never cancelled. `QDashTimeoutError` after
   * `timeoutSeconds` (default 600), polling every `pollIntervalSeconds` (default 0.5).
   */
  async waitForExecution(executionId: string, options: PollOptions = {}): Promise<ExecutionResponseDetail> {
    const timeoutSeconds = options.timeoutSeconds ?? 600;
    const pollIntervalSeconds = options.pollIntervalSeconds ?? 0.5;
    checkPollOptions(timeoutSeconds, pollIntervalSeconds);
    const deadline = Date.now() + timeoutSeconds * 1_000;
    const wholePipeline = options.wholePipeline ?? true;
    while (true) {
      let execution: ExecutionResponseDetail | undefined;
      try {
        execution = await this.getExecution(executionId, options.signal);
      } catch (error) {
        if (!(options.notFoundAsPending && error instanceof QDashNotFoundError)) throw error;
      }
      if (execution) {
        // A pipeline step's own execution completes long before the run does.
        const status = wholePipeline && execution.pipeline ? execution.pipeline.status : execution.status;
        if (EXECUTION_TERMINAL.has(String(status).toLowerCase())) return execution;
      }
      if (Date.now() >= deadline) {
        throw new QDashTimeoutError(`Execution '${executionId}' did not reach a terminal state within ${timeoutSeconds} seconds`);
      }
      await pause(pollIntervalSeconds, options.signal);
    }
  }

  /**
   * Create an agent session. With `calibrationSessionId`, the calibration session is first
   * checked to be the user's on the chip (`QDashPreflightError`, nothing created otherwise), and
   * an answer that does not show the session admitted into it throws
   * `QDashResultUnknownError`: a session may exist without its admission, so reconcile it
   * instead of creating another.
   */
  async createAgentSession(options: CreateAgentSessionOptions): Promise<AgentSessionResponse> {
    const calibrationSessionId = options.calibrationSessionId;
    if (calibrationSessionId !== undefined) {
      await this.qdash.preflightCalibrationSession(calibrationSessionId, options.chipId);
    }
    const result = await this.send((o) =>
      this.api.agentSession.createAgentSession(
        {
          chip_id: options.chipId,
          policy: options.policy,
          expires_in_seconds: options.expiresInSeconds ?? 21_600,
          skill_name: options.skillName ?? "",
          skill_version: options.skillVersion ?? "",
          skill_hash: options.skillHash ?? "",
          ...(options.model ? { model: options.model } : {}),
          ...(calibrationSessionId !== undefined ? { calibration_session_id: calibrationSessionId } : {}),
        },
        o,
      ),
    );
    if (
      calibrationSessionId !== undefined &&
      (!isRecord(result) || result.calibration_session_id !== calibrationSessionId || result.calibration_admission !== "admitted")
    ) {
      throw new QDashResultUnknownError(
        "Agent session creation result unknown: a session may exist without its requested admission. Do not retry automatically or run actions; reconcile the session first.",
        { body: result },
      );
    }
    return result;
  }

  /** The project's agent sessions, newest first, with expiry applied before filtering. */
  async listAgentSessions(options: ListAgentSessionsOptions = {}): Promise<AgentSessionResponse[]> {
    const payload = await this.read((o) =>
      this.api.agentSession.listAgentSessions(
        defined({ chip_id: options.chipId, status: options.statuses, mine: options.mine, limit: options.limit }),
        o,
      ),
    );
    return payload.items;
  }

  getAgentSession(sessionId: string, signal?: AbortSignal): Promise<AgentSessionResponse> {
    return this.read((o) => this.api.agentSession.getAgentSession({ session_id: sessionId }, o), signal);
  }

  /** End an active or paused session's authority on a person's request; QDash cancels nothing running. */
  stopAgentSession(sessionId: string, options: StopAgentSessionOptions): Promise<StopAgentSessionResponse> {
    return this.send((o) =>
      this.api.agentSession.stopAgentSession(
        { session_id: sessionId, idempotency_key: options.idempotencyKey, reason: options.reason },
        o,
      ),
    );
  }

  submitAgentAction(sessionId: string, options: SubmitAgentActionOptions): Promise<AgentActionResponse> {
    return this.send((o) =>
      this.api.agentSession.submitAgentAction(
        {
          session_id: sessionId,
          idempotency_key: options.idempotencyKey,
          expected_state_version: options.expectedStateVersion,
          action_type: options.actionType,
          task_name: options.taskName ?? null,
          qids: options.qids ?? [],
          parameter_overrides: options.parameterOverrides ?? {},
          diagnosis: options.diagnosis ?? "",
          ...(options.autonomous ? { autonomous: true } : {}),
          ...(options.repeatOfActionId ? { repeat_of_action_id: options.repeatOfActionId } : {}),
          ...(options.model ? { model: options.model } : {}),
        },
        o,
      ),
    );
  }

  /** Dispatch one authorized agent action; `sourceExecutionId` only records what it was decided from. */
  executeAgentAction(
    sessionId: string,
    actionId: string,
    options: { sourceExecutionId?: string; updateParams?: boolean; reconfigure?: boolean; autonomous?: boolean } = {},
  ): Promise<AgentActionResponse> {
    return this.send((o) =>
      this.api.agentSession.executeAgentAction(
        {
          session_id: sessionId,
          action_id: actionId,
          ...(options.sourceExecutionId ? { source_execution_id: options.sourceExecutionId } : {}),
          update_params: options.updateParams ?? false,
          reconfigure: options.reconfigure ?? false,
          ...(options.autonomous ? { autonomous: true } : {}),
        },
        o,
      ),
    );
  }

  getAgentAction(sessionId: string, actionId: string, signal?: AbortSignal): Promise<AgentActionResponse> {
    return this.read((o) => this.api.agentSession.getAgentAction({ session_id: sessionId, action_id: actionId }, o), signal);
  }

  /** A session's interventions, newest first. */
  async listAgentInterventions(sessionId: string, signal?: AbortSignal): Promise<AgentInterventionResponse[]> {
    const payload = await this.read((o) => this.api.agentSession.listAgentInterventions({ session_id: sessionId }, o), signal);
    return payload.items;
  }

  /** Record that the agent stopped and needs a person; a repeated key returns the same record. */
  createAgentIntervention(sessionId: string, options: CreateAgentInterventionOptions): Promise<AgentInterventionResponse> {
    return this.send((o) =>
      this.api.agentSession.createAgentIntervention(
        {
          session_id: sessionId,
          idempotency_key: options.idempotencyKey,
          reason: options.reason,
          summary: options.summary,
          question: options.question,
          ...(options.taskName ? { task_name: options.taskName } : {}),
          qids: options.qids ?? [],
          attempts: options.attempts ?? [],
          ...(options.previousInterventionId ? { previous_intervention_id: options.previousInterventionId } : {}),
          ...(options.autonomous ? { autonomous: true } : {}),
          ...(options.model ? { model: options.model } : {}),
        },
        o,
      ),
    );
  }

  getAgentIntervention(sessionId: string, interventionId: string, signal?: AbortSignal): Promise<AgentInterventionResponse> {
    return this.read(
      (o) => this.api.agentSession.getAgentIntervention({ session_id: sessionId, intervention_id: interventionId }, o),
      signal,
    );
  }

  /** Append the agent's reading of a result and its next step to the session's audit. */
  recordAgentDecision(sessionId: string, options: RecordAgentDecisionOptions): Promise<AgentDecisionResponse> {
    return this.send((o) =>
      this.api.agentSession.recordAgentDecision(
        {
          session_id: sessionId,
          idempotency_key: options.idempotencyKey,
          ...(options.assessment ? { assessment: options.assessment } : {}),
          interpretation: options.interpretation,
          next_action: options.nextAction,
          next_detail: options.nextDetail ?? "",
          evidence_action_ids: options.evidenceActionIds ?? [],
          evaluation_ids: options.evaluationIds ?? [],
          ...(options.nextActionId ? { next_action_id: options.nextActionId } : {}),
          ...(options.interventionId ? { intervention_id: options.interventionId } : {}),
          ...(options.supersedesDecisionId ? { supersedes_decision_id: options.supersedesDecisionId } : {}),
          ...(options.model ? { model: options.model } : {}),
        },
        o,
      ),
    );
  }

  /** A session's recorded decisions, oldest first. */
  async listAgentDecisions(sessionId: string, signal?: AbortSignal): Promise<AgentDecisionResponse[]> {
    const payload = await this.read((o) => this.api.agentSession.listAgentDecisions({ session_id: sessionId }, o), signal);
    return payload.items;
  }

  /** One page of a session's chronological audit; follow `next_cursor` until `complete`. */
  getAgentSessionAudit(sessionId: string, options: AgentSessionAuditPageOptions = {}): Promise<AgentSessionAuditResponse> {
    return this.read((o) =>
      this.api.agentSession.getAgentSessionAudit(defined({ session_id: sessionId, cursor: options.cursor, limit: options.limit }), o),
    );
  }

  async listAgentActions(sessionId: string, signal?: AbortSignal): Promise<AgentActionResponse[]> {
    const payload = await this.read((o) => this.api.agentSession.listAgentActions({ session_id: sessionId }, o), signal);
    return payload.items;
  }

  /** Poll an action until it has an operation ID or failed (default 120 s). */
  waitForAgentAction(sessionId: string, actionId: string, options: PollOptions = {}): Promise<AgentActionResponse> {
    return this.pollAgentAction(sessionId, actionId, "operation_id", { ...options, timeoutSeconds: options.timeoutSeconds ?? 120 });
  }

  /** Poll an action until it has an execution ID or failed (default 600 s). */
  waitForAgentActionExecution(sessionId: string, actionId: string, options: PollOptions = {}): Promise<AgentActionResponse> {
    return this.pollAgentAction(sessionId, actionId, "execution_id", { ...options, timeoutSeconds: options.timeoutSeconds ?? 600 });
  }

  async listAgentActionCandidates(sessionId: string, actionId: string): Promise<AgentCandidateResponse[]> {
    const payload = await this.read((o) =>
      this.api.agentSession.listAgentActionCandidates({ session_id: sessionId, action_id: actionId }, o),
    );
    return payload.items;
  }

  commitAgentActionCandidate(
    sessionId: string,
    actionId: string,
    parameterName: string,
    options: { idempotencyKey: string; expectedStateVersion: number; taskId: string; autonomous?: boolean; decisionId?: string },
  ): Promise<AgentCandidateCommitResponse> {
    return this.send((o) =>
      this.api.agentSession.commitAgentActionCandidate(
        {
          session_id: sessionId,
          action_id: actionId,
          parameter_name: parameterName,
          idempotency_key: options.idempotencyKey,
          expected_state_version: options.expectedStateVersion,
          task_id: options.taskId,
          // Sent only when set, so a reviewed request keeps its earlier shape.
          ...(options.autonomous ? { autonomous: true, decision_id: options.decisionId ?? null } : {}),
        },
        o,
      ),
    );
  }

  commitAgentCandidateSet(
    sessionId: string,
    candidates: AgentCandidateReference[],
    options: { idempotencyKey: string; expectedStateVersion: number },
  ): Promise<AgentCandidateSetCommitResponse> {
    return this.send((o) =>
      this.api.agentSession.commitAgentCandidateSet(
        {
          session_id: sessionId,
          idempotency_key: options.idempotencyKey,
          expected_state_version: options.expectedStateVersion,
          candidates,
        },
        o,
      ),
    );
  }

  getAgentCandidateCommit(sessionId: string, commitId: string): Promise<AgentCandidateCommitResponse> {
    return this.read((o) => this.api.agentSession.getAgentCandidateCommit({ session_id: sessionId, commit_id: commitId }, o));
  }

  applyAgentCandidateCommit(
    sessionId: string,
    commitId: string,
    options: { idempotencyKey: string; expectedStateVersion: number; pushToGithub?: boolean; autonomous?: boolean },
  ): Promise<AgentCandidateCommitResponse> {
    return this.send((o) =>
      this.api.agentSession.applyAgentCandidateCommit(
        {
          session_id: sessionId,
          commit_id: commitId,
          idempotency_key: options.idempotencyKey,
          expected_state_version: options.expectedStateVersion,
          push_to_github: options.pushToGithub ?? false,
          ...(options.autonomous ? { autonomous: true } : {}),
        },
        o,
      ),
    );
  }

  /** Poll a candidate commit until its backend apply is `applied` or `failed` (default 300 s). */
  async waitForAgentCandidateApply(sessionId: string, commitId: string, options: PollOptions = {}): Promise<AgentCandidateCommitResponse> {
    const timeoutSeconds = options.timeoutSeconds ?? 300;
    const pollIntervalSeconds = options.pollIntervalSeconds ?? 0.5;
    checkPollOptions(timeoutSeconds, pollIntervalSeconds);
    const deadline = Date.now() + timeoutSeconds * 1_000;
    while (true) {
      const commit = await this.getAgentCandidateCommit(sessionId, commitId);
      if (commit.backend_status === "applied" || commit.backend_status === "failed") return commit;
      if (Date.now() >= deadline) {
        throw new Error(`Agent candidate commit '${commitId}' was not applied within ${timeoutSeconds} seconds`);
      }
      await pause(pollIntervalSeconds, options.signal);
    }
  }

  listForumPosts(options: ForumPostListOptions = {}): Promise<QDashApi.ListForumPostsResponse> {
    return this.read((o) =>
      this.api.forum.listForumPosts(
        defined({
          category: options.category,
          status: options.status,
          chip_id: options.chipId,
          target_type: options.targetType,
          target_id: options.targetId,
          skip: options.skip,
          limit: options.limit,
        }) as QDashApi.ListForumPostsRequest,
        o,
      ),
    );
  }

  createForumPost(request: QDashApi.ForumPostCreate): Promise<QDashApi.ForumPostResponse> {
    return this.send((o) => this.api.forum.createForumPost(request, o));
  }

  getForumPost(postId: string): Promise<QDashApi.ForumPostResponse> {
    return this.read((o) => this.api.forum.getForumPost({ post_id: postId }, o));
  }

  updateForumPost(postId: string, request: Omit<QDashApi.ForumPostUpdate, "post_id">): Promise<QDashApi.ForumPostResponse> {
    return this.send((o) => this.api.forum.updateForumPost({ ...request, post_id: postId }, o));
  }

  getForumPostReplies(postId: string): Promise<QDashApi.ForumPostResponse[]> {
    return this.read((o) => this.api.forum.getForumPostReplies({ post_id: postId }, o));
  }

  uploadForumImage(image: Blob, filename: string): Promise<QDashApi.ForumImageUploadResponse> {
    return this.send((o) =>
      this.api.forum.uploadForumImage({ file: { data: image, filename, ...(image.type ? { contentType: image.type } : {}) } }, o),
    );
  }

  getProvenanceLineage(entityId: string): Promise<QDashApi.LineageResponse> {
    return this.read((o) => this.api.provenance.getProvenanceLineage({ entity_id: entityId }, o));
  }

  getProvenanceImpact(entityId: string): Promise<QDashApi.ImpactResponse> {
    return this.read((o) => this.api.provenance.getProvenanceImpact({ entity_id: entityId }, o));
  }

  getProvenanceStats(): Promise<QDashApi.ProvenanceStatsResponse> {
    return this.read((o) => this.api.provenance.getProvenanceStats(o));
  }

  getParameterHistory(options: { parameterName: string; qid: string; limit?: number }): Promise<QDashApi.ParameterHistoryResponse> {
    return this.read((o) =>
      this.api.provenance.getParameterHistory(defined({ parameter_name: options.parameterName, qid: options.qid, limit: options.limit }), o),
    );
  }

  compareExecutions(executionIdBefore: string, executionIdAfter: string): Promise<QDashApi.ExecutionComparisonResponse> {
    return this.read((o) =>
      this.api.provenance.compareExecutions({ execution_id_before: executionIdBefore, execution_id_after: executionIdAfter }, o),
    );
  }

  getRecentChanges(options: RecentChangesOptions = {}): Promise<QDashApi.RecentChangesResponse> {
    return this.read((o) =>
      this.api.provenance.getRecentChanges(
        defined({ parameter_names: options.parameterNames, within_hours: options.withinHours, limit: options.limit }),
        o,
      ),
    );
  }

  getDegradationTrends(options: DegradationTrendsOptions = {}): Promise<QDashApi.DegradationTrendsResponse> {
    return this.read((o) =>
      this.api.provenance.getDegradationTrends(
        defined({ min_streak: options.minStreak, limit: options.limit, parameter_names: options.parameterNames }),
        o,
      ),
    );
  }

  getRecalibrationRecommendations(
    entityId: string,
    options: RecalibrationRecommendationsOptions = {},
  ): Promise<QDashApi.RecalibrationRecommendationResponse> {
    return this.read((o) =>
      this.api.provenance.getRecalibrationRecommendations(defined({ entity_id: entityId, max_depth: options.maxDepth }), o),
    );
  }

  listCalibrationSessions(request: QDashApi.ListCalibrationSessionsRequest = {}): Promise<QDashApi.ListCalibrationSessionsResponse> {
    return this.read((o) =>
      this.api.calibrationSession.listCalibrationSessions(
        defined({
          chip_id: request.chip_id,
          status: request.status,
          origin: request.origin,
          mine: request.mine,
          limit: request.limit,
          skip: request.skip,
        }),
        o,
      ),
    );
  }

  createCalibrationSession(request: QDashApi.CreateCalibrationSessionRequest): Promise<QDashApi.CalibrationSessionResponse> {
    return this.send((o) => this.api.calibrationSession.createCalibrationSession(request, o));
  }

  /** A calibration session with its runs; reading an ended automatic session's detail closes it. */
  getCalibrationSession(calibrationSessionId: string): Promise<QDashApi.CalibrationSessionDetailResponse> {
    return this.read((o) => this.api.calibrationSession.getCalibrationSession({ calibration_session_id: calibrationSessionId }, o));
  }

  recordCalibrationDecision(
    calibrationSessionId: string,
    request: Omit<QDashApi.RecordCalibrationDecisionRequest, "calibration_session_id">,
  ): Promise<QDashApi.CalibrationDecisionResponse> {
    return this.send((o) =>
      this.api.calibrationSession.recordCalibrationDecision({ ...request, calibration_session_id: calibrationSessionId }, o),
    );
  }

  getCalibrationSessionAudit(
    calibrationSessionId: string,
    options: { cursor?: string; limit?: number } = {},
  ): Promise<QDashApi.CalibrationSessionAuditResponse> {
    return this.read((o) =>
      this.api.calibrationSession.getCalibrationSessionAudit(
        defined({ calibration_session_id: calibrationSessionId, cursor: options.cursor, limit: options.limit }),
        o,
      ),
    );
  }

  private async pollAgentAction(
    sessionId: string,
    actionId: string,
    field: "operation_id" | "execution_id",
    options: PollOptions,
  ): Promise<AgentActionResponse> {
    const timeoutSeconds = options.timeoutSeconds ?? 120;
    const pollIntervalSeconds = options.pollIntervalSeconds ?? 0.5;
    checkPollOptions(timeoutSeconds, pollIntervalSeconds);
    const deadline = Date.now() + timeoutSeconds * 1_000;
    while (true) {
      const action = await this.getAgentAction(sessionId, actionId, options.signal);
      if (action.execution_status === "failed" || action[field] != null) return action;
      if (Date.now() >= deadline) {
        throw new Error(`Agent action '${actionId}' did not produce ${field} within ${timeoutSeconds} seconds`);
      }
      await pause(pollIntervalSeconds, options.signal);
    }
  }
}
