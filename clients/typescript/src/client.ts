import { setTimeout as sleep } from "node:timers/promises";

import { getQDashAPI } from "./generated/api.js";

import { QDashConfig } from "./config.js";
import { QDashNotFoundError, QDashTimeoutError } from "./errors.js";
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
  TaskResultListResponse,
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

export interface ListTaskResultsOptions {
  chipId?: string;
  taskName?: string;
  qid?: string;
  couplingId?: string;
  status?: string;
  startAt?: string;
  endAt?: string;
  limit?: number;
  skip?: number;
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

  async listTaskResults(options: ListTaskResultsOptions = {}): Promise<TaskResultListResponse> {
    return this.get(
      "/task-results",
      query({
        chip_id: options.chipId,
        task_name: options.taskName,
        qid: options.qid,
        coupling_id: options.couplingId,
        status: options.status,
        start_at: options.startAt,
        end_at: options.endAt,
        limit: options.limit,
        skip: options.skip,
      }),
    );
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

  async listExecutions(options: {
    flowName?: string;
    status?: string;
    skip?: number;
    limit?: number;
    /** Only executions started on this calendar day, YYYYMMDD. */
    date?: string;
    /** IANA time zone that defines the day for `date`. */
    timezone?: string;
  } = {}): Promise<ListExecutionsResponse> {
    return this.get(
      "/executions",
      query({
        flow_name: options.flowName,
        status: options.status,
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
