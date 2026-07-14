import { setTimeout as sleep } from "node:timers/promises";

import { getQDashAPI } from "./generated/api.js";

import { QDashConfig } from "./config.js";
import { QDashNotFoundError } from "./errors.js";
import type {
  AgentActionResponse,
  AgentCampaignCommitResponse,
  AgentCandidateCommitResponse,
  AgentCandidateResponse,
  AgentSessionPolicy,
  AgentActionType,
  AgentCampaignCandidateReference,
  FileTreeNode,
  ForumPostCreate,
  ForumPostResponse,
  ForumPostUpdate,
  ImpactResponse,
  LineageResponse,
  ListAgentActionsResponse,
  ListAgentCandidatesResponse,
  ListCouplingsResponse,
  ListFlowsResponse,
  ListForumPostsResponse,
  ListQubitsResponse,
  ProvenanceStatsResponse,
  QdashApiSchemasProjectProjectListResponse,
  SaveFlowRequest,
  SaveFlowResponse,
  AgentSessionResponse,
  CandidateGateResponse,
  ChipMetricsResponse,
  ChipResponse,
  CouplingResponse,
  ExecuteFlowResponse,
  ExecutionResponseDetail,
  FlowTemplate,
  FlowTemplateWithCode,
  GetFlowResponse,
  ListChipsResponse,
  ListExecutionsResponse,
  ListTaskKnowledgeResponse,
  ListTaskResponse,
  ProjectResponse,
  QubitResponse,
  TaskKnowledgeResponse,
  TaskResultListResponse,
  TaskResultResponse,
  TimeSeriesData,
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
  modelName?: string;
}

export interface SubmitAgentActionOptions {
  idempotencyKey: string;
  expectedStateVersion: number;
  actionType: AgentActionType;
  taskName?: string | null;
  qids?: string[];
  parameterOverrides?: Record<string, number>;
  diagnosis?: string;
}

export interface PollOptions {
  timeoutSeconds?: number;
  pollIntervalSeconds?: number;
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

  constructor(config: QDashConfig, options: QDashClientOptions = {}) {
    this.config = config;
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

  async listFlowTemplates(): Promise<FlowTemplate[]> {
    return this.get("/flows/templates");
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

  async listExecutions(options: {
    flowName?: string;
    status?: string;
    skip?: number;
    limit?: number;
  } = {}): Promise<ListExecutionsResponse> {
    return this.get(
      "/executions",
      query({
        flow_name: options.flowName,
        status: options.status,
        skip: options.skip,
        limit: options.limit,
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
    while (true) {
      const execution = await this.getExecution(executionId);
      if (terminal.has(execution.status.toLowerCase())) return execution;
      if (Date.now() >= deadline) {
        throw new Error(
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
      model_name: options.modelName ?? "",
    });
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
    });
  }

  async executeAgentAction(
    sessionId: string,
    actionId: string,
    options: { sourceExecutionId: string; updateParams?: boolean; reconfigure?: boolean },
  ): Promise<AgentActionResponse> {
    return this.post(
      `/agent-sessions/${pathPart(sessionId)}/actions/${pathPart(actionId)}/execute`,
      {
        source_execution_id: options.sourceExecutionId,
        update_params: options.updateParams ?? false,
        reconfigure: options.reconfigure ?? false,
      },
    );
  }

  async getAgentAction(sessionId: string, actionId: string): Promise<AgentActionResponse> {
    return this.get(`/agent-sessions/${pathPart(sessionId)}/actions/${pathPart(actionId)}`);
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
    options: { idempotencyKey: string; expectedStateVersion: number; taskId: string },
  ): Promise<AgentCandidateCommitResponse> {
    return this.post(
      `/agent-sessions/${pathPart(sessionId)}/actions/${pathPart(actionId)}/candidates/${pathPart(parameterName)}/commit`,
      {
        idempotency_key: options.idempotencyKey,
        expected_state_version: options.expectedStateVersion,
        task_id: options.taskId,
      },
    );
  }

  async commitAgentCampaignCandidates(
    sessionId: string,
    candidates: AgentCampaignCandidateReference[],
    options: { idempotencyKey: string; expectedStateVersion: number },
  ): Promise<AgentCampaignCommitResponse> {
    return this.post(`/agent-sessions/${pathPart(sessionId)}/campaign-commits`, {
      idempotency_key: options.idempotencyKey,
      expected_state_version: options.expectedStateVersion,
      candidates,
    });
  }

  async getAgentCampaignCommit(
    sessionId: string,
    commitId: string,
  ): Promise<AgentCampaignCommitResponse> {
    return this.get(
      `/agent-sessions/${pathPart(sessionId)}/campaign-commits/${pathPart(commitId)}`,
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
    },
  ): Promise<AgentCandidateCommitResponse> {
    return this.post(
      `/agent-sessions/${pathPart(sessionId)}/commits/${pathPart(commitId)}/apply`,
      {
        idempotency_key: options.idempotencyKey,
        expected_state_version: options.expectedStateVersion,
        push_to_github: options.pushToGithub ?? false,
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

  async getProvenanceLineage(entityId: string): Promise<LineageResponse> {
    return this.get(`/provenance/lineage/${pathPart(entityId)}`);
  }

  async getProvenanceImpact(entityId: string): Promise<ImpactResponse> {
    return this.get(`/provenance/impact/${pathPart(entityId)}`);
  }

  async getProvenanceStats(): Promise<ProvenanceStatsResponse> {
    return this.get("/provenance/stats");
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
