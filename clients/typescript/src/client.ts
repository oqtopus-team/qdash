import { setTimeout as sleep } from "node:timers/promises";

import { getQDashAPI } from "./generated/api.js";

import { QDashConfig } from "./config.js";
import { QDashApiError, QDashNotFoundError, QDashTimeoutError, QDashValidationError } from "./errors.js";
import type {
  AgentActionResponse,
  AgentDecisionAssessment,
  AgentDecisionNextAction,
  AgentDecisionResponse,
  AgentSessionAuditResponse,
  ListAgentDecisionsResponse,
  AgentCandidateSetCommitResponse,
  AgentCandidateCommitResponse,
  AgentCandidateResponse,
  AgentModelIdentity,
  AgentSessionPolicy,
  AgentActionType,
  AgentCandidateReference,
  AgentInterventionAttempt,
  AgentInterventionReason,
  AgentInterventionResponse,
  AgentSessionStatus,
  ListAgentInterventionsResponse,
  ListAgentSessionsResponse,
  FileTreeNode,
  ForumImageUploadResponse,
  ForumPostCreate,
  ForumPostResponse,
  ForumPostUpdate,
  ImpactResponse,
  LineageResponse,
  ListAgentActionsResponse,
  ListAgentCandidatesResponse,
  ListCouplingsResponse,
  ListFlowsResponse,
  DashboardCreateRequest,
  DashboardResponse,
  DashboardTemplatePreviewResponse,
  DashboardUpdateRequest,
  ListDashboardTemplatesResponse,
  ListDashboardsResponse,
  ListMetricScriptTemplatesResponse,
  ListMetricScriptsResponse,
  MetricScriptCatalogResponse,
  MetricScriptCreateRequest,
  MetricScriptDraftEvaluateRequest,
  MetricScriptEvaluateRequest,
  MetricScriptEvaluateResponse,
  MetricScriptResponse,
  MetricScriptUpdateRequest,
  MetricScriptValidateResponse,
  SuccessResponse,
  ListForumPostsResponse,
  ListQubitsResponse,
  ListSourceRootsResponse,
  SearchSourceResponse,
  SourceFileResponse,
  ProvenanceStatsResponse,
  QdashApiSchemasProjectProjectListResponse,
  SaveFlowRequest,
  SaveFlowResponse,
  AgentSessionResponse,
  StopAgentSessionResponse,
  CandidateGateResponse,
  ChipMetricsResponse,
  ChipResponse,
  DegradationTrendsResponse,
  ExecutionComparisonResponse,
  ExecutionLockStatusResponse,
  RecalibrationRecommendationResponse,
  RecentChangesResponse,
  CouplingResponse,
  ExecuteFlowResponse,
  ExecutionResponseDetail,
  FlowTemplate,
  FlowTemplateWithCode,
  GetFlowResponse,
  ListChipsResponse,
  ExecutionActivityResponse,
  ListExecutionsResponse,
  ListTaskKnowledgeResponse,
  ListTaskResponse,
  ProjectResponse,
  QubitResponse,
  TaskKnowledgeResponse,
  TaskResultListItem,
  TaskResultListResponse,
  TaskHistoryResponse,
  TaskResultResponse,
  TimeSeriesData,
  User,
} from "./models.js";
import { QDashTransport, type QueryValue, type TransportOptions } from "./transport.js";

type JsonObject = Record<string, unknown>;
type Query = Record<string, QueryValue>;

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

/** Most rows one `GET /task-results` request returns; the API rejects a larger `limit`. */
export const TASK_RESULTS_MAX_PAGE_SIZE = 100;
/** Most rows one `collectTaskResults` call reads across all its pages. */
export const TASK_RESULTS_MAX_COLLECT = 10_000;

/**
 * Filters and one page of `GET /task-results`. Rows come newest first
 * (`start_at` descending, then `task_id`).
 */
export interface ListTaskResultsOptions {
  chipId?: string;
  taskName?: string;
  /** Exact qubit (`"6"`) or coupling (`"6-7"`) ID as QDash stores it; not normalized. */
  qid?: string;
  executionId?: string;
  username?: string;
  status?: string;
  /** Inclusive lower bound on the task start time (ISO 8601). */
  startFrom?: string;
  /** Inclusive upper bound on the task start time (ISO 8601). */
  startTo?: string;
  /** Case-insensitive substring of the result message. */
  messageContains?: string;
  /** Planned step id (`invocation.step_id`). */
  stepId?: string;
  /** Planned call id (`invocation.call_id`). */
  callId?: string;
  /** Rows in this page: an integer from 1 to 100. The server default is 50. */
  limit?: number;
  /** Rows to skip before this page: an integer of 0 or more. */
  skip?: number;
  /** Cancels the request. */
  signal?: AbortSignal;
}

/** Options of `collectTaskResults`: the list filters, a required row cap, and a page size. */
export interface CollectTaskResultsOptions extends Omit<ListTaskResultsOptions, "limit"> {
  /** Most rows to return, an integer from 1 to 10000. Reading stops once this many are collected. */
  maxItems: number;
  /** Rows per request, an integer from 1 to 100. Defaults to 100. */
  pageSize?: number;
}

/**
 * Options of `listExecutions`. `GET /executions` lists one chip's executions;
 * it has no flow or status filter, so none is offered here.
 */
export interface ListExecutionsOptions {
  /** The chip whose executions to list. Required by the API. */
  chipId: string;
  /** Rows to skip, an integer of 0 or more. */
  skip?: number;
  /** Rows to return, an integer from 1 to 100 (the API default is 20). */
  limit?: number;
  /** Only executions started on this calendar day, YYYYMMDD. */
  date?: string;
  /** IANA time zone that defines the day for `date` (the API default is UTC). */
  timezone?: string;
}

/** Most executions `GET /executions` returns per request. */
export const EXECUTIONS_MAX_PAGE_SIZE = 100;

/** Options of `getQubitTaskHistory`: every result of one task for one qubit. */
export interface QubitTaskHistoryOptions {
  chipId: string;
  /** Qubit ID as QDash stores it (`"6"`). */
  qid: string;
  /** Task name, such as `"CheckT1"`. */
  task: string;
}

/** Options of `getCouplingTaskHistory`: every result of one task for one coupling. */
export interface CouplingTaskHistoryOptions {
  chipId: string;
  /** Coupling ID as QDash stores it (`"6-7"`). */
  couplingId: string;
  /** Task name, such as `"CrossResonance"`. */
  task: string;
}

/** Rows `collectTaskResults` read, newest first. */
export interface CollectedTaskResults {
  items: TaskResultListItem[];
  /** Rows matching the filters, as the last page reported. */
  total: number;
  /** Offset of the first returned row (the `skip` option). */
  skip: number;
  /** Requests made. */
  pages: number;
  /** True when matching rows remain or duplicate rows prevent confirming a complete read. */
  truncated: boolean;
  /** Rows per status over all rows matching the filters, as the last page reported. */
  status_counts: TaskResultListResponse["status_counts"];
}

export interface CreateAgentSessionOptions {
  chipId: string;
  policy: AgentSessionPolicy;
  expiresInSeconds?: number;
  skillName?: string;
  skillVersion?: string;
  skillHash?: string;
  /**
   * The provider and model the calling host ran the agent with, read from the host's own
   * runtime (never from the agent's tool arguments). QDash records it as client reported and
   * does not verify it; omit it when the host does not know it.
   */
  model?: AgentModelIdentity;
  /**
   * Create the session in this calibration session (open, on the same chip, created by the
   * signed-in user). It groups the session with the objective's other work; the policy stays
   * the only authority.
   */
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
  /**
   * An autonomous step, without a per-call approval. QDash then also requires that the
   * signed-in user created the `auto` session, and checks the running measurement, the
   * round budget, and repeats against its own records; a refused step is not recorded.
   */
  autonomous?: boolean;
  /** The finished identical action an autonomous step measures again on purpose. */
  repeatOfActionId?: string;
  /**
   * The provider and model the calling host ran the agent with, read from the host's own
   * runtime (never from the agent's tool arguments). QDash records it as client reported and
   * does not verify it; omit it when the host does not know it.
   */
  model?: AgentModelIdentity;
}

export interface ListAgentSessionsOptions {
  chipId?: string;
  /** Only sessions in these statuses, settled for expiry. */
  statuses?: AgentSessionStatus[];
  /** Only sessions the signed-in user created. */
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
  /** Recorded by an autonomous agent: QDash requires the signed-in creator of an `auto` session. */
  autonomous?: boolean;
  /**
   * The provider and model the calling host ran the agent with, read from the host's own
   * runtime (never from the agent's tool arguments). QDash records it as client reported and
   * does not verify it; omit it when the host does not know it.
   */
  model?: AgentModelIdentity;
}

export interface StopAgentSessionOptions {
  /** Key of this stop; repeating it returns the same outcome. */
  idempotencyKey: string;
  /** Why the session is stopped, for the audit (at most 2000 characters). */
  reason: string;
}

export interface RecordAgentDecisionOptions {
  idempotencyKey: string;
  /** How the agent judged the evidence; omit when it did not judge it. */
  assessment?: AgentDecisionAssessment;
  /** The agent's concise reasoning, citing the evidence (at most 2000 characters). */
  interpretation: string;
  nextAction: AgentDecisionNextAction;
  nextDetail?: string;
  evidenceActionIds?: string[];
  evaluationIds?: string[];
  nextActionId?: string;
  interventionId?: string;
  supersedesDecisionId?: string;
  /**
   * The provider and model the calling host ran the agent with, read from the host's own
   * runtime (never from the agent's tool arguments). QDash records it as client reported and
   * does not verify it; omit it when the host does not know it.
   */
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
   * For an execution that is one step of a pipeline run, wait for the whole
   * run rather than that step (default true). The returned detail's
   * `pipeline.status` then carries the run's outcome.
   */
  wholePipeline?: boolean;
  /**
   * Poll again when the execution is not listed yet (404) instead of throwing
   * `QDashNotFoundError` (default false). A dispatched run can briefly be unknown
   * to `GET /executions/{id}`; the timeout still applies.
   */
  notFoundAsPending?: boolean;
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

export interface QDashClientOptions extends TransportOptions {}

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

function pathPart(value: string): string {
  return encodeURIComponent(value);
}

function query(values: Record<string, QueryValue>): Query {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value != null));
}

const TASK_RESULTS_PAGE_HINT =
  "QDash returns at most 100 task results per request; use collectTaskResults({ maxItems }) or request further pages with skip";

/** Throw before any request when an optional option is not an integer within bounds. */
function checkInteger(
  name: string,
  value: number | undefined,
  minimum: number,
  maximum: number | undefined,
  hint?: string,
): void {
  if (value === undefined) return;
  if (Number.isInteger(value) && value >= minimum && (maximum === undefined || value <= maximum)) return;
  const range = maximum === undefined ? `${minimum} or more` : `from ${minimum} to ${maximum}`;
  throw new QDashValidationError(
    `${name} must be an integer ${range} (got ${String(value)})${hint ? `. ${hint}.` : "."}`,
    { payload: { field: name, value } },
  );
}

const EXECUTION_LIST_OPTIONS = new Set(["chipId", "skip", "limit", "date", "timezone"]);

function isIntegerIn(value: unknown, minimum: number, maximum?: number): boolean {
  return Number.isInteger(value) && (value as number) >= minimum && (maximum === undefined || (value as number) <= maximum);
}

/**
 * Why `listExecutions` options other than `chipId` cannot be sent, one message
 * per problem; empty when they can. `GET /executions` lists one chip's
 * executions by page (`skip`, `limit`) and start day (`date`, `timezone`)
 * only, so a supplied `flowName`, `status` or other option is a problem rather
 * than silently dropped. An option set to `undefined` counts as omitted. Callers
 * that resolve the chip later, such as a host that picks a default chip, can
 * check the rest first and send no request on a problem.
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

/** Throw `QDashValidationError` naming `field` when `value` is not a non-empty string. */
function requireText(field: string, value: unknown, purpose: string): string {
  if (typeof value === "string" && value.trim() !== "") return value;
  throw new QDashValidationError(`${field} is required to ${purpose}.`, { payload: { field, value } });
}

/** Throw before any request when a task-history call is given an option the route does not take. */
function checkTaskHistoryOptions(
  options: Readonly<Record<string, unknown>>,
  target: "qid" | "couplingId",
): void {
  const supplied = Object.keys(options).filter((key) => options[key] !== undefined);
  const problems: string[] = [];
  if (supplied.includes("date")) {
    problems.push(
      `date cannot filter a task history: it returns every result of the task for one target, newest first. Omit date, or use listTaskResults({ chipId, ${target === "qid" ? "qid" : "qid: couplingId"}, taskName, startFrom, startTo }) for one period`,
    );
  }
  const unknown = supplied.filter((key) => key !== "date" && !["chipId", "task", target].includes(key));
  if (unknown.length > 0) problems.push(`${unknown.join(", ")} ${unknown.length === 1 ? "is not an option" : "are not options"} of a task history`);
  if (problems.length > 0) {
    throw new QDashValidationError(`${problems.join("; ")}.`, { payload: { problems } });
  }
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
  if (problems.length > 0) {
    throw new QDashApiError(`Unexpected GET ${route} response: ${problems.join("; ")}`, { payload });
  }
  return body as TaskHistoryResponse;
}

function taskResultQuery(options: ListTaskResultsOptions): Query {
  return query({
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
  });
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
  if (problems.length > 0) {
    throw new QDashApiError(`Unexpected GET /task-results response: ${problems.join("; ")}`, { payload });
  }
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

export class QDashClient {
  readonly api: ReturnType<typeof getQDashAPI>;
  readonly config: QDashConfig;

  private readonly transport: QDashTransport;
  private readonly options: QDashClientOptions;

  constructor(config: QDashConfig, options: QDashClientOptions = {}) {
    this.config = config;
    this.options = options;
    this.transport = new QDashTransport(config, options);
    this.api = this.bindGeneratedApi(getQDashAPI());
  }

  static fromEnv(
    env: Record<string, string | undefined> = process.env,
    options: QDashClientOptions = {},
  ): QDashClient {
    return new QDashClient(QDashConfig.fromEnv(env), { ...options, env });
  }

  static async fromProfile(
    profile = "default",
    path?: string,
    options: QDashClientOptions = {},
  ): Promise<QDashClient> {
    const config = path
      ? await QDashConfig.fromFile(profile, path)
      : await QDashConfig.fromFile(profile);
    return new QDashClient(config, options);
  }

  /**
   * A new client that sends `projectId` as `X-Project-Id`. It keeps this client's
   * configuration and transport options (`fetch`, headers, environment); this
   * client and its configuration are unchanged. A username/password login is not
   * shared, so the new client logs in on its first request.
   */
  withProject(projectId: string): QDashClient {
    return new QDashClient(new QDashConfig({ ...this.config, projectId }), this.options);
  }

  /** The user QDash authenticated for this client's credentials. */
  async getCurrentUser(): Promise<User> {
    return this.get("/auth/me");
  }

  async listChips(): Promise<ListChipsResponse> {
    return this.get("/chips");
  }

  async getDefaultChip(): Promise<ChipResponse> {
    const { chips } = await this.listChips();
    if (chips.length === 0) throw new QDashNotFoundError("No chips are available");
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

  async getChipMetrics(chipId: string): Promise<ChipMetricsResponse> {
    return this.get(`/metrics/chips/${pathPart(chipId)}/metrics`);
  }

  async getMetricsConfig(): Promise<JsonObject> {
    return this.get("/metrics/config");
  }

  async listChipQubits(
    chipId: string,
    options: PaginationOptions = {},
  ): Promise<ListQubitsResponse> {
    return this.get(`/chips/${pathPart(chipId)}/qubits`, query({ limit: options.limit, offset: options.offset }));
  }

  async getChipQubit(chipId: string, qid: string): Promise<QubitResponse> {
    return this.get(`/chips/${pathPart(chipId)}/qubits/${pathPart(qid)}`);
  }

  async listChipCouplings(
    chipId: string,
    options: PaginationOptions = {},
  ): Promise<ListCouplingsResponse> {
    return this.get(`/chips/${pathPart(chipId)}/couplings`, query({ limit: options.limit, offset: options.offset }));
  }

  async getChipCoupling(chipId: string, couplingId: string): Promise<CouplingResponse> {
    return this.get(`/chips/${pathPart(chipId)}/couplings/${pathPart(couplingId)}`);
  }

  async getTaskResultsTimeseries(
    options: TaskResultsTimeseriesOptions,
  ): Promise<TimeSeriesData> {
    return this.get(
      "/task-results/timeseries",
      query({
        chip_id: options.chipId,
        parameter: options.parameter,
        start_at: options.startAt,
        end_at: options.endAt,
        tag: options.tag,
        qid: options.qid,
      }),
    );
  }

  /**
   * One page of task results. `limit` must be an integer from 1 to 100 and
   * `skip` an integer of 0 or more; other values throw `QDashValidationError`
   * before any request, never a silently smaller page. Use
   * `collectTaskResults` to read more than 100 rows.
   */
  async listTaskResults(options: ListTaskResultsOptions = {}): Promise<TaskResultListResponse> {
    checkInteger("limit", options.limit, 1, TASK_RESULTS_MAX_PAGE_SIZE, TASK_RESULTS_PAGE_HINT);
    checkInteger("skip", options.skip, 0, undefined);
    const payload = await this.transport.requestJson<unknown>("GET", "/task-results", {
      query: taskResultQuery(options),
      ...(options.signal ? { signal: options.signal } : {}),
    });
    return checkTaskResultPage(payload);
  }

  /**
   * Up to `maxItems` task results matching the filters, read in pages of at
   * most 100 from `skip` (default 0), newest first, with every filter on each
   * page. Reading stops at `maxItems`, at the last matching row, or at a short
   * page, with at most `ceil(maxItems / pageSize)` page reads. Duplicates can
   * therefore leave fewer than `maxItems` rows and set `truncated`.
   * A failed or cancelled page rejects the whole call; no partial result
   * is returned as complete. Pages are offsets, not a snapshot: a result
   * written while reading can shift rows, so rows are deduplicated by
   * `task_id`.
   */
  async collectTaskResults(options: CollectTaskResultsOptions): Promise<CollectedTaskResults> {
    const { maxItems, pageSize = TASK_RESULTS_MAX_PAGE_SIZE, ...filters } = options;
    checkInteger("maxItems", maxItems, 1, TASK_RESULTS_MAX_COLLECT);
    checkInteger("pageSize", pageSize, 1, TASK_RESULTS_MAX_PAGE_SIZE, TASK_RESULTS_PAGE_HINT);
    checkInteger("skip", filters.skip, 0, undefined);
    const start = filters.skip ?? 0;
    const items: TaskResultListItem[] = [];
    const seen = new Set<string>();
    let offset = start;
    let pages = 0;
    let last: TaskResultListResponse | undefined;
    const maxPages = Math.ceil(maxItems / pageSize);
    let duplicates = false;
    while (items.length < maxItems && pages < maxPages) {
      filters.signal?.throwIfAborted();
      const limit = Math.min(pageSize, maxItems - items.length);
      const page = await this.listTaskResults({ ...filters, skip: offset, limit });
      pages += 1;
      last = page;
      for (const item of page.items) {
        if (seen.has(item.task_id)) {
          duplicates = true;
          continue;
        }
        seen.add(item.task_id);
        items.push(item);
      }
      offset += page.items.length;
      if (page.items.length < limit || offset >= page.total) break;
    }
    const total = last?.total ?? 0;
    return {
      items,
      total,
      skip: start,
      pages,
      truncated: duplicates || offset < total,
      status_counts: last?.status_counts ?? {},
    };
  }

  /**
   * Every result of `task` for one qubit, newest first, keyed by task ID
   * (`GET /task-results/qubits/{qid}/history`). The route has no date or paging
   * filter: a missing `chipId`, `qid` or `task`, or a supplied `date` or other
   * option, throws `QDashValidationError` before any request; use
   * `listTaskResults` with `startFrom` and `startTo` for one period. A body
   * without `name` and a `data` object throws `QDashApiError`.
   */
  async getQubitTaskHistory(options: QubitTaskHistoryOptions): Promise<TaskHistoryResponse> {
    const chipId = requireText("chipId", options?.chipId, "read a task history");
    const qid = requireText("qid", options.qid, "read a qubit task history");
    const task = requireText("task", options.task, "read a task history");
    checkTaskHistoryOptions(options as unknown as Record<string, unknown>, "qid");
    const route = `/task-results/qubits/${pathPart(qid)}/history`;
    return checkTaskHistory(await this.get<unknown>(route, { chip_id: chipId, task }), route);
  }

  /**
   * Every result of `task` for one coupling, newest first, keyed by task ID
   * (`GET /task-results/couplings/{coupling_id}/history`), with the same checks
   * as `getQubitTaskHistory`.
   */
  async getCouplingTaskHistory(options: CouplingTaskHistoryOptions): Promise<TaskHistoryResponse> {
    const chipId = requireText("chipId", options?.chipId, "read a task history");
    const couplingId = requireText("couplingId", options.couplingId, "read a coupling task history");
    const task = requireText("task", options.task, "read a task history");
    checkTaskHistoryOptions(options as unknown as Record<string, unknown>, "couplingId");
    const route = `/task-results/couplings/${pathPart(couplingId)}/history`;
    return checkTaskHistory(await this.get<unknown>(route, { chip_id: chipId, task }), route);
  }

  async getTaskResult(taskId: string): Promise<TaskResultResponse> {
    return this.get(`/tasks/${pathPart(taskId)}/result`);
  }

  async listTasks(backend?: string): Promise<ListTaskResponse> {
    return this.get("/tasks", query({ backend }));
  }

  async listTaskKnowledge(): Promise<ListTaskKnowledgeResponse> {
    return this.get("/task-knowledge");
  }

  async getTaskKnowledge(taskName: string): Promise<TaskKnowledgeResponse> {
    return this.get(`/tasks/${pathPart(taskName)}/knowledge`);
  }

  async getTaskKnowledgeMarkdown(taskName: string): Promise<string> {
    return this.get(`/tasks/${pathPart(taskName)}/knowledge/markdown`);
  }

  /** Source trees the Copilot may read, with the revision of each when it is known. */
  async listSourceRoots(): Promise<ListSourceRootsResponse> {
    return this.get("/copilot/source/roots");
  }

  /** Literal search in source contents (`content`) or file paths (`path`). */
  async searchSource(options: SearchSourceOptions): Promise<SearchSourceResponse> {
    return this.get(
      "/copilot/source/search",
      query({
        query: options.query,
        root: options.root,
        path_prefix: options.pathPrefix,
        mode: options.mode,
        case_sensitive: options.caseSensitive,
        limit: options.limit,
      }),
    );
  }

  /** A numbered line range of one source file; without `root`, a traceback path is mapped. */
  async getSourceFile(options: GetSourceFileOptions): Promise<SourceFileResponse> {
    return this.get(
      "/copilot/source/file",
      query({
        path: options.path,
        root: options.root,
        start_line: options.startLine,
        end_line: options.endLine,
      }),
    );
  }

  async listProjects(): Promise<QdashApiSchemasProjectProjectListResponse> {
    return this.get("/projects");
  }

  async getProject(projectId: string): Promise<ProjectResponse> {
    return this.get(`/projects/${pathPart(projectId)}`);
  }

  async getFilesTree(): Promise<FileTreeNode[]> {
    const payload = await this.get<{ tree?: FileTreeNode[] } | FileTreeNode[]>(
      "/files/tree",
    );
    return Array.isArray(payload) ? payload : (payload.tree ?? []);
  }

  async getFileContent(path: string): Promise<JsonObject> {
    return this.get("/files/content", { path });
  }

  async saveFileContent(path: string, content: string): Promise<JsonObject> {
    return this.put("/files/content", { path, content });
  }

  async getGitStatus(): Promise<JsonObject> {
    return this.get("/files/git/status");
  }

  async listFlows(): Promise<ListFlowsResponse> {
    return this.get("/flows");
  }

  async getFlow(name: string): Promise<GetFlowResponse> {
    return this.get(`/flows/${pathPart(name)}`);
  }

  /** List flow templates, optionally only those written for one backend (e.g. "fake"). */
  async listFlowTemplates(backend?: string): Promise<FlowTemplate[]> {
    return this.get("/flows/templates", query({ backend }));
  }

  async getFlowTemplate(templateId: string): Promise<FlowTemplateWithCode> {
    return this.get(`/flows/templates/${pathPart(templateId)}`);
  }

  async saveFlow(request: SaveFlowRequest): Promise<SaveFlowResponse> {
    return this.post("/flows", request);
  }

  async executeFlow(name: string, parameters: JsonObject = {}): Promise<ExecuteFlowResponse> {
    return this.post(`/flows/${pathPart(name)}/execute`, { parameters });
  }

  /** Metric scripts visible to the caller (project-shared and their own), without source. */
  async listMetricScripts(): Promise<ListMetricScriptsResponse> {
    return this.get("/metric-scripts");
  }

  /** A metric script with its latest source, active (last-good) source and revisions. */
  async getMetricScript(scriptId: string): Promise<MetricScriptResponse> {
    return this.get(`/metric-scripts/${pathPart(scriptId)}`);
  }

  /** Starter metric scripts, with their source. */
  async listMetricScriptTemplates(): Promise<ListMetricScriptTemplatesResponse> {
    return this.get("/metric-scripts/templates");
  }

  /** The qubit and coupling metrics a script can read through `ctx.data`. */
  async getMetricScriptCatalog(): Promise<MetricScriptCatalogResponse> {
    return this.get("/metric-scripts/catalog");
  }

  /** Compile metric script source in a worker; nothing is saved. */
  async validateMetricScript(source: string): Promise<MetricScriptValidateResponse> {
    return this.post("/metric-scripts/validate", { source });
  }

  /** Evaluate one metric of unsaved source on a chip; nothing is saved. */
  async evaluateMetricScriptDraft(
    request: MetricScriptDraftEvaluateRequest,
  ): Promise<MetricScriptEvaluateResponse> {
    return this.post("/metric-scripts/evaluate", request);
  }

  /** Evaluate one metric of a saved script's validated revision (the active one by default). */
  async evaluateMetricScript(
    scriptId: string,
    request: MetricScriptEvaluateRequest,
  ): Promise<MetricScriptEvaluateResponse> {
    return this.post(`/metric-scripts/${pathPart(scriptId)}/evaluate`, request);
  }

  async createMetricScript(request: MetricScriptCreateRequest): Promise<MetricScriptResponse> {
    return this.post("/metric-scripts", request);
  }

  /** Update settings or save new source; invalid source keeps the last good revision active. */
  async updateMetricScript(
    scriptId: string,
    request: MetricScriptUpdateRequest,
  ): Promise<MetricScriptResponse> {
    return this.patch(`/metric-scripts/${pathPart(scriptId)}`, request);
  }

  /** Copy the active source of a visible script into a private script of the caller. */
  async copyMetricScript(scriptId: string): Promise<MetricScriptResponse> {
    return this.post(`/metric-scripts/${pathPart(scriptId)}/copy`);
  }

  async deleteMetricScript(scriptId: string): Promise<SuccessResponse> {
    return this.delete(`/metric-scripts/${pathPart(scriptId)}`);
  }

  async listDashboards(): Promise<ListDashboardsResponse> {
    return this.get("/dashboards");
  }

  async getDashboard(dashboardId: string): Promise<DashboardResponse> {
    return this.get(`/dashboards/${pathPart(dashboardId)}`);
  }

  async listDashboardTemplates(): Promise<ListDashboardTemplatesResponse> {
    return this.get("/dashboards/templates");
  }

  /** What a dashboard created from a template now would hold, including the shared scripts it adds. Writes nothing. */
  async previewDashboardTemplate(templateId: string): Promise<DashboardTemplatePreviewResponse> {
    return this.get(`/dashboards/templates/${pathPart(templateId)}/preview`);
  }

  async createDashboard(
    request: DashboardCreateRequest,
  ): Promise<DashboardResponse> {
    return this.post("/dashboards", request);
  }

  /** Update a dashboard; a provided `panels` list replaces the previous one. */
  async updateDashboard(
    dashboardId: string,
    request: DashboardUpdateRequest,
  ): Promise<DashboardResponse> {
    return this.patch(`/dashboards/${pathPart(dashboardId)}`, request);
  }

  /** Count a chip's executions per calendar day over the trailing window. */
  async getExecutionActivity(options: {
    chipId: string;
    days?: number;
    timezone?: string;
  }): Promise<ExecutionActivityResponse> {
    return this.get(
      "/executions/activity",
      query({ chip_id: options.chipId, days: options.days, timezone: options.timezone }),
    );
  }

  /**
   * One page of a chip's executions, newest first. A missing `chipId`, or any
   * problem `executionListProblems` reports (an unsupported filter such as
   * `flowName` or `status`, an out-of-range `limit` or `skip`, a malformed
   * `date`), throws `QDashValidationError` before any request.
   */
  async listExecutions(options: ListExecutionsOptions): Promise<ListExecutionsResponse> {
    requireText("chipId", options?.chipId, "list executions");
    const { chipId: _chipId, ...rest } = options;
    const problems = executionListProblems(rest);
    if (problems.length > 0) {
      throw new QDashValidationError(`${problems.join("; ")}.`, { payload: { problems } });
    }
    return this.get(
      "/executions",
      query({
        chip_id: options.chipId,
        skip: options.skip,
        limit: options.limit,
        date: options.date,
        timezone: options.timezone,
      }),
    );
  }

  async getExecution(executionId: string): Promise<ExecutionResponseDetail> {
    return this.get(`/executions/${pathPart(executionId)}`);
  }

  async getExecutionFigure(path: string): Promise<DownloadedFile> {
    const data = await this.transport.request<ArrayBuffer>({
      method: "GET",
      url: "/executions/figure",
      params: { path },
      responseType: "arraybuffer",
    });
    return {
      data,
      mediaType: mediaTypeForPath(path),
      filename: filenameFromPath(path),
    };
  }

  async downloadRawDataFile(path: string): Promise<DownloadedFile> {
    const data = await this.transport.request<ArrayBuffer>({
      method: "GET",
      url: "/files/raw-data",
      params: { path },
      responseType: "arraybuffer",
    });
    return {
      data,
      mediaType: mediaTypeForPath(path),
      filename: filenameFromPath(path),
    };
  }

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
    if (!path) {
      throw new QDashNotFoundError(`No figure at index ${index} for task result '${taskId}'`);
    }
    const file = await this.getExecutionFigure(path);
    return { ...file, path, figurePaths, jsonFigurePaths };
  }

  async waitForExecution(
    executionId: string,
    options: PollOptions = {},
  ): Promise<ExecutionResponseDetail> {
    const timeoutSeconds = options.timeoutSeconds ?? 600;
    const pollIntervalSeconds = options.pollIntervalSeconds ?? 0.5;
    this.validatePollOptions(timeoutSeconds, pollIntervalSeconds);
    const deadline = Date.now() + timeoutSeconds * 1_000;
    const terminal = new Set(["completed", "failed", "cancelled", "canceled", "crashed"]);
    const wholePipeline = options.wholePipeline ?? true;
    while (true) {
      let execution: ExecutionResponseDetail | undefined;
      try {
        execution = await this.getExecution(executionId);
      } catch (error) {
        if (!(options.notFoundAsPending && error instanceof QDashNotFoundError)) throw error;
      }
      if (execution) {
        // A pipeline step's own execution completes long before the run does.
        const status =
          wholePipeline && execution.pipeline ? execution.pipeline.status : execution.status;
        if (terminal.has(status.toLowerCase())) return execution;
      }
      if (Date.now() >= deadline) {
        throw new QDashTimeoutError(
          `Execution '${executionId}' did not reach a terminal state within ${timeoutSeconds} seconds`,
        );
      }
      await sleep(pollIntervalSeconds * 1_000);
    }
  }

  async createAgentSession(options: CreateAgentSessionOptions): Promise<AgentSessionResponse> {
    return this.post("/agent-sessions", {
      chip_id: options.chipId,
      policy: options.policy,
      expires_in_seconds: options.expiresInSeconds ?? 21_600,
      skill_name: options.skillName ?? "",
      skill_version: options.skillVersion ?? "",
      skill_hash: options.skillHash ?? "",
      ...(options.model ? { model: options.model } : {}),
      ...(options.calibrationSessionId ? { calibration_session_id: options.calibrationSessionId } : {}),
    });
  }

  /** The project's agent sessions, newest first, with expiry applied before filtering. */
  async listAgentSessions(options: ListAgentSessionsOptions = {}): Promise<AgentSessionResponse[]> {
    const payload = await this.get<ListAgentSessionsResponse>(
      "/agent-sessions",
      query({
        chip_id: options.chipId,
        status: options.statuses,
        mine: options.mine,
        limit: options.limit,
      }),
    );
    return payload.items;
  }

  async getAgentSession(sessionId: string): Promise<AgentSessionResponse> {
    return this.get(`/agent-sessions/${pathPart(sessionId)}`);
  }

  /**
   * End an active or paused session's authority on a person's request (`POST
   * /agent-sessions/{id}/stop`). The response is QDash's own account: whether this request
   * stopped it, and the operations that passed the session gate before and still run;
   * QDash does not cancel those.
   */
  async stopAgentSession(sessionId: string, options: StopAgentSessionOptions): Promise<StopAgentSessionResponse> {
    return this.post(`/agent-sessions/${pathPart(sessionId)}/stop`, {
      idempotency_key: options.idempotencyKey,
      reason: options.reason,
    });
  }

  async evaluateAgentCandidateGate(
    sessionId: string,
    parameterName: string,
    value: number,
  ): Promise<CandidateGateResponse> {
    return this.post(`/agent-sessions/${pathPart(sessionId)}/candidate-gate`, {
      parameter_name: parameterName,
      value,
    });
  }

  async submitAgentAction(
    sessionId: string,
    options: SubmitAgentActionOptions,
  ): Promise<AgentActionResponse> {
    return this.post(`/agent-sessions/${pathPart(sessionId)}/actions`, {
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
    });
  }

  /**
   * Dispatch one authorized agent action. The task runs like a Task Workbench run, on the
   * current calibration state; `sourceExecutionId` only records what it was decided from.
   */
  async executeAgentAction(
    sessionId: string,
    actionId: string,
    options: {
      sourceExecutionId?: string;
      updateParams?: boolean;
      reconfigure?: boolean;
      /** An autonomous dispatch: the signed-in creator of an `auto` session, nothing else running. */
      autonomous?: boolean;
    } = {},
  ): Promise<AgentActionResponse> {
    return this.post(
      `/agent-sessions/${pathPart(sessionId)}/actions/${pathPart(actionId)}/execute`,
      {
        ...(options.sourceExecutionId ? { source_execution_id: options.sourceExecutionId } : {}),
        update_params: options.updateParams ?? false,
        reconfigure: options.reconfigure ?? false,
        ...(options.autonomous ? { autonomous: true } : {}),
      },
    );
  }

  async getAgentAction(sessionId: string, actionId: string): Promise<AgentActionResponse> {
    return this.get(`/agent-sessions/${pathPart(sessionId)}/actions/${pathPart(actionId)}`);
  }

  /** A session's interventions, newest first: why the agent stopped and the expert's answer. */
  async listAgentInterventions(sessionId: string): Promise<AgentInterventionResponse[]> {
    const payload = await this.get<ListAgentInterventionsResponse>(
      `/agent-sessions/${pathPart(sessionId)}/interventions`,
    );
    return payload.items;
  }

  /**
   * Record that the agent stopped and needs a person. An active session pauses until an
   * expert answers in QDash; a repeated idempotency key returns the same record. The
   * request carries no plan checkpoint, so the expert's resume reactivates the session.
   */
  async createAgentIntervention(
    sessionId: string,
    options: CreateAgentInterventionOptions,
  ): Promise<AgentInterventionResponse> {
    return this.post(`/agent-sessions/${pathPart(sessionId)}/interventions`, {
      idempotency_key: options.idempotencyKey,
      reason: options.reason,
      summary: options.summary,
      question: options.question,
      ...(options.taskName ? { task_name: options.taskName } : {}),
      qids: options.qids ?? [],
      attempts: options.attempts ?? [],
      ...(options.previousInterventionId
        ? { previous_intervention_id: options.previousInterventionId }
        : {}),
      ...(options.autonomous ? { autonomous: true } : {}),
      ...(options.model ? { model: options.model } : {}),
    });
  }

  async getAgentIntervention(
    sessionId: string,
    interventionId: string,
  ): Promise<AgentInterventionResponse> {
    return this.get(
      `/agent-sessions/${pathPart(sessionId)}/interventions/${pathPart(interventionId)}`,
    );
  }

  /**
   * Append the agent's reading of a result and its next step to the session's audit. Only
   * the session's creator records decisions; recording changes no session state, so it works
   * in a paused or ended session too. A repeated idempotency key returns the same record.
   */
  async recordAgentDecision(
    sessionId: string,
    options: RecordAgentDecisionOptions,
  ): Promise<AgentDecisionResponse> {
    return this.post(`/agent-sessions/${pathPart(sessionId)}/decisions`, {
      idempotency_key: options.idempotencyKey,
      ...(options.assessment ? { assessment: options.assessment } : {}),
      interpretation: options.interpretation,
      next_action: options.nextAction,
      next_detail: options.nextDetail ?? "",
      evidence_action_ids: options.evidenceActionIds ?? [],
      evaluation_ids: options.evaluationIds ?? [],
      ...(options.nextActionId ? { next_action_id: options.nextActionId } : {}),
      ...(options.interventionId ? { intervention_id: options.interventionId } : {}),
      ...(options.supersedesDecisionId
        ? { supersedes_decision_id: options.supersedesDecisionId }
        : {}),
      ...(options.model ? { model: options.model } : {}),
    });
  }

  /** A session's recorded decisions, oldest first. */
  async listAgentDecisions(sessionId: string): Promise<AgentDecisionResponse[]> {
    const payload = await this.get<ListAgentDecisionsResponse>(
      `/agent-sessions/${pathPart(sessionId)}/decisions`,
    );
    return payload.items;
  }

  /** One page of a session's chronological audit; follow `next_cursor` until `complete`. */
  async getAgentSessionAudit(
    sessionId: string,
    options: AgentSessionAuditPageOptions = {},
  ): Promise<AgentSessionAuditResponse> {
    return this.get(
      `/agent-sessions/${pathPart(sessionId)}/audit`,
      query({ cursor: options.cursor, limit: options.limit }),
    );
  }

  /** The whole audit as versioned JSON; QDash refuses (413) rather than truncates it. */
  async exportAgentSessionAudit(sessionId: string): Promise<AgentSessionAuditResponse> {
    return this.get(`/agent-sessions/${pathPart(sessionId)}/audit/export`);
  }

  async listAgentActions(sessionId: string): Promise<AgentActionResponse[]> {
    const payload = await this.get<ListAgentActionsResponse>(
      `/agent-sessions/${pathPart(sessionId)}/actions`,
    );
    return payload.items;
  }

  async waitForAgentAction(
    sessionId: string,
    actionId: string,
    options: PollOptions = {},
  ): Promise<AgentActionResponse> {
    return this.pollAgentAction(sessionId, actionId, "operation_id", options);
  }

  async waitForAgentActionExecution(
    sessionId: string,
    actionId: string,
    options: PollOptions = {},
  ): Promise<AgentActionResponse> {
    return this.pollAgentAction(
      sessionId,
      actionId,
      "execution_id",
      { timeoutSeconds: 600, ...options },
    );
  }

  async listAgentActionCandidates(
    sessionId: string,
    actionId: string,
  ): Promise<AgentCandidateResponse[]> {
    const payload = await this.get<ListAgentCandidatesResponse>(
      `/agent-sessions/${pathPart(sessionId)}/actions/${pathPart(actionId)}/candidates`,
    );
    return payload.items;
  }

  async commitAgentActionCandidate(
    sessionId: string,
    actionId: string,
    parameterName: string,
    options: {
      idempotencyKey: string;
      expectedStateVersion: number;
      taskId: string;
      /** Commit under the session's approved parameter_updates authority; needs decisionId. */
      autonomous?: boolean;
      /** The recorded pass decision an autonomous commit rests on. */
      decisionId?: string;
    },
  ): Promise<AgentCandidateCommitResponse> {
    return this.post(
      `/agent-sessions/${pathPart(sessionId)}/actions/${pathPart(actionId)}/candidates/${pathPart(parameterName)}/commit`,
      {
        idempotency_key: options.idempotencyKey,
        expected_state_version: options.expectedStateVersion,
        task_id: options.taskId,
        // Sent only when set, so a reviewed request keeps its earlier shape.
        ...(options.autonomous ? { autonomous: true, decision_id: options.decisionId } : {}),
      },
    );
  }

  async commitAgentCandidateSet(
    sessionId: string,
    candidates: AgentCandidateReference[],
    options: { idempotencyKey: string; expectedStateVersion: number },
  ): Promise<AgentCandidateSetCommitResponse> {
    return this.post(`/agent-sessions/${pathPart(sessionId)}/candidate-set-commits`, {
      idempotency_key: options.idempotencyKey,
      expected_state_version: options.expectedStateVersion,
      candidates,
    });
  }

  async getAgentCandidateSetCommit(
    sessionId: string,
    commitId: string,
  ): Promise<AgentCandidateSetCommitResponse> {
    return this.get(
      `/agent-sessions/${pathPart(sessionId)}/candidate-set-commits/${pathPart(commitId)}`,
    );
  }

  async getAgentCandidateCommit(
    sessionId: string,
    commitId: string,
  ): Promise<AgentCandidateCommitResponse> {
    return this.get(`/agent-sessions/${pathPart(sessionId)}/commits/${pathPart(commitId)}`);
  }

  async applyAgentCandidateCommit(
    sessionId: string,
    commitId: string,
    options: {
      idempotencyKey: string;
      expectedStateVersion: number;
      pushToGithub?: boolean;
      /** Apply under the session's approved apply_backend authority; never pushes. */
      autonomous?: boolean;
    },
  ): Promise<AgentCandidateCommitResponse> {
    return this.post(
      `/agent-sessions/${pathPart(sessionId)}/commits/${pathPart(commitId)}/apply`,
      {
        idempotency_key: options.idempotencyKey,
        expected_state_version: options.expectedStateVersion,
        push_to_github: options.pushToGithub ?? false,
        ...(options.autonomous ? { autonomous: true } : {}),
      },
    );
  }

  async waitForAgentCandidateApply(
    sessionId: string,
    commitId: string,
    options: PollOptions = {},
  ): Promise<AgentCandidateCommitResponse> {
    const timeoutSeconds = options.timeoutSeconds ?? 300;
    const pollIntervalSeconds = options.pollIntervalSeconds ?? 0.5;
    this.validatePollOptions(timeoutSeconds, pollIntervalSeconds);
    const deadline = Date.now() + timeoutSeconds * 1_000;
    while (true) {
      const commit = await this.getAgentCandidateCommit(sessionId, commitId);
      if (commit.backend_status === "applied" || commit.backend_status === "failed") return commit;
      if (Date.now() >= deadline) {
        throw new Error(
          `Agent candidate commit '${commitId}' was not applied within ${timeoutSeconds} seconds`,
        );
      }
      await sleep(pollIntervalSeconds * 1_000);
    }
  }

  async listForumPosts(options: {
    category?: string;
    status?: string;
    chipId?: string;
    targetType?: string;
    targetId?: string;
    skip?: number;
    limit?: number;
  } = {}): Promise<ListForumPostsResponse> {
    return this.get(
      "/forum/posts",
      query({
        category: options.category,
        status: options.status,
        chip_id: options.chipId,
        target_type: options.targetType,
        target_id: options.targetId,
        skip: options.skip,
        limit: options.limit,
      }),
    );
  }

  async createForumPost(request: ForumPostCreate): Promise<ForumPostResponse> {
    return this.post("/forum/posts", request);
  }

  async getForumPost(postId: string): Promise<ForumPostResponse> {
    return this.get(`/forum/posts/${pathPart(postId)}`);
  }

  async updateForumPost(
    postId: string,
    request: ForumPostUpdate,
  ): Promise<ForumPostResponse> {
    return this.patch(`/forum/posts/${pathPart(postId)}`, request);
  }

  async getForumPostReplies(postId: string): Promise<ListForumPostsResponse> {
    return this.get(`/forum/posts/${pathPart(postId)}/replies`);
  }

  async uploadForumImage(image: Blob, filename: string): Promise<ForumImageUploadResponse> {
    const form = new FormData();
    form.append("file", image, filename);
    return this.post("/forum/upload-image", form);
  }

  async getProvenanceLineage(entityId: string): Promise<LineageResponse> {
    return this.get(`/provenance/lineage/${pathPart(entityId)}`);
  }

  async getProvenanceImpact(entityId: string): Promise<ImpactResponse> {
    return this.get(`/provenance/impact/${pathPart(entityId)}`);
  }

  async getProvenanceStats(): Promise<ProvenanceStatsResponse> {
    return this.get("/provenance/stats");
  }

  async getExecutionLockStatus(): Promise<ExecutionLockStatusResponse> {
    return this.get("/executions/lock-status");
  }

  async compareExecutions(
    executionIdBefore: string,
    executionIdAfter: string,
  ): Promise<ExecutionComparisonResponse> {
    return this.get(
      "/provenance/compare",
      query({
        execution_id_before: executionIdBefore,
        execution_id_after: executionIdAfter,
      }),
    );
  }

  async getRecentChanges(
    options: RecentChangesOptions = {},
  ): Promise<RecentChangesResponse> {
    return this.get(
      "/provenance/changes",
      query({
        parameter_names: options.parameterNames,
        within_hours: options.withinHours,
        limit: options.limit,
      }),
    );
  }

  async getDegradationTrends(
    options: DegradationTrendsOptions = {},
  ): Promise<DegradationTrendsResponse> {
    return this.get(
      "/provenance/degradation-trends",
      query({
        min_streak: options.minStreak,
        limit: options.limit,
        parameter_names: options.parameterNames,
      }),
    );
  }

  async getRecalibrationRecommendations(
    entityId: string,
    options: RecalibrationRecommendationsOptions = {},
  ): Promise<RecalibrationRecommendationResponse> {
    return this.get(
      `/provenance/recommendations/${pathPart(entityId)}`,
      query({ max_depth: options.maxDepth }),
    );
  }

  private bindGeneratedApi(
    api: ReturnType<typeof getQDashAPI>,
  ): ReturnType<typeof getQDashAPI> {
    const entries = Object.entries(api).map(([name, method]) => {
      const generated = method as (...args: unknown[]) => unknown;
      const bound = (...args: unknown[]) => {
        const optionIndex = Math.max(0, generated.length - 1);
        const callArgs = [...args];
        while (callArgs.length < optionIndex) callArgs.push(undefined);
        const supplied = callArgs[optionIndex];
        const options =
          typeof supplied === "object" && supplied !== null
            ? (supplied as Record<string, unknown>)
            : {};
        callArgs[optionIndex] = { ...options, qdashTransport: this.transport };
        return generated(...callArgs);
      };
      return [name, bound];
    });
    return Object.fromEntries(entries) as ReturnType<typeof getQDashAPI>;
  }

  private get<T>(path: string, requestQuery?: Query): Promise<T> {
    return this.transport.requestJson<T>("GET", path, { query: requestQuery });
  }

  private post<T>(path: string, body?: unknown): Promise<T> {
    return this.transport.requestJson<T>("POST", path, { body });
  }

  private put<T>(path: string, body?: unknown): Promise<T> {
    return this.transport.requestJson<T>("PUT", path, { body });
  }

  private patch<T>(path: string, body?: unknown): Promise<T> {
    return this.transport.requestJson<T>("PATCH", path, { body });
  }

  private delete<T>(path: string): Promise<T> {
    return this.transport.requestJson<T>("DELETE", path);
  }

  private async pollAgentAction(
    sessionId: string,
    actionId: string,
    field: "operation_id" | "execution_id",
    options: PollOptions,
  ): Promise<AgentActionResponse> {
    const timeoutSeconds = options.timeoutSeconds ?? 120;
    const pollIntervalSeconds = options.pollIntervalSeconds ?? 0.5;
    this.validatePollOptions(timeoutSeconds, pollIntervalSeconds);
    const deadline = Date.now() + timeoutSeconds * 1_000;
    while (true) {
      const action = await this.getAgentAction(sessionId, actionId);
      if (action.execution_status === "failed" || action[field] != null) return action;
      if (Date.now() >= deadline) {
        throw new Error(
          `Agent action '${actionId}' did not produce ${field} within ${timeoutSeconds} seconds`,
        );
      }
      await sleep(pollIntervalSeconds * 1_000);
    }
  }

  private validatePollOptions(timeoutSeconds: number, pollIntervalSeconds: number): void {
    if (timeoutSeconds < 0 || pollIntervalSeconds < 0) {
      throw new RangeError("Polling timeout and interval must be non-negative");
    }
  }
}
