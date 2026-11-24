/**
 * Registered workflows of a project: flows saved to QDash, from the UI or
 * `qdash.api.flow.saveFlow`, with a deployment and a target chip. These reach the
 * server's `/flows` routes; nothing is uploaded, registered or run locally.
 */
import { dispatch, read, resultUnknown, writeOptions, type Context } from "./_http.js";
import { Run, type Executions } from "./runs.js";
import type { ExecuteFlowResponse, FlowSummary, GetFlowResponse } from "./types.js";

// The names the server accepts when a flow is saved; anything else is rejected
// before it becomes part of a request path.
const NAME = /^[A-Za-z0-9_]+$/;

function checkedName(name: string): string {
  if (typeof name !== "string" || !NAME.test(name)) {
    throw new TypeError(`workflow name must be letters, digits and underscores, got ${JSON.stringify(name)}`);
  }
  return name;
}

export interface WorkflowRunOptions {
  /** Override the saved `default_parameters` for this run only. */
  parameters?: Record<string, unknown>;
  /**
   * Add the run to this calibration session (open, on the run's chip, created by the
   * signed-in user). Without it, the run joins an automatic session created for it.
   */
  calibrationSessionId?: string;
  /** A retry with the same key returns the recorded run instead of starting another. */
  idempotencyKey?: string;
}

/** A dispatched workflow run. */
export class WorkflowRun extends Run {
  constructor(
    executions: Executions,
    readonly name: string,
    /** The dispatch response as the API returned it, including `flow_run_id`. */
    readonly response: ExecuteFlowResponse,
  ) {
    super(executions, response.execution_id);
  }

  /** The run's calibration session: the one named, an automatic one, or null. */
  get calibrationSessionId(): string | null {
    return this.response.calibration_session_id ?? null;
  }

  /** The run's record in that session; every step execution of the run carries it. */
  get calibrationRunId(): string | null {
    return this.response.calibration_run_id ?? null;
  }
}

/** A registered workflow as `Workflows.get` read it. */
export class Workflow {
  constructor(
    private readonly workflows: Workflows,
    /** The response as the API returned it, including the source `code`. */
    readonly detail: GetFlowResponse,
  ) {}

  get name(): string {
    return this.detail.name;
  }

  /** The chip the workflow was saved for. */
  get chipId(): string {
    return this.detail.chip_id;
  }

  get description(): string {
    return this.detail.description;
  }

  /** The saved parameters a run starts from, not every parameter the flow accepts. */
  get defaultParameters(): Record<string, unknown> {
    return { ...this.detail.default_parameters };
  }

  /** The same as `qdash.workflows.run(this.name, options)`. */
  run(options: WorkflowRunOptions = {}): Promise<WorkflowRun> {
    return this.workflows.run(this.name, options);
  }
}

/** The project's registered workflows, reached as `qdash.workflows`. */
export class Workflows {
  constructor(
    private readonly context: Context,
    private readonly executions: Executions,
  ) {}

  /** Summaries of the workflows registered in the session's project. */
  async list(): Promise<FlowSummary[]> {
    return (await read(this.context.reads, (requestOptions) => this.context.api.flow.listFlows(requestOptions))).flows;
  }

  /** The registered workflow `name`; `QDashNotFoundError` when there is none. */
  async get(name: string): Promise<Workflow> {
    const checked = checkedName(name);
    const detail = await read(this.context.reads, (requestOptions) => this.context.api.flow.getFlow({ name: checked }, requestOptions));
    return new Workflow(this, detail);
  }

  /**
   * Dispatch the registered workflow `name`. The server merges `parameters` over
   * the saved defaults and runs on the saved `chip_id` unless the merged
   * parameters carry one. Returns once dispatched. The request is sent once: a
   * transport error or an error status is thrown, never retried. A success answer
   * that cannot be read throws `QDashResultUnknownError`. With a session or
   * key, a response that does not echo the recorded run throws
   * `QDashResultUnknownError`: the run may have started without them, so reconcile
   * it instead of retrying.
   */
  async run(name: string, options: WorkflowRunOptions = {}): Promise<WorkflowRun> {
    const checked = checkedName(name);
    const { calibrationSessionId: id, idempotencyKey: key } = options;
    if ((id != null && (typeof id !== "string" || !id.trim())) || (key != null && (typeof key !== "string" || !key.trim()))) {
      throw new TypeError("calibrationSessionId and idempotencyKey must be non-empty when given");
    }
    const answer = await dispatch("Workflow", () =>
      this.context.api.flow
        .executeFlow(
          {
            name: checked,
            parameters: { ...(options.parameters ?? {}) },
            ...(id != null ? { calibration_session_id: id } : {}),
            ...(key != null ? { idempotency_key: key } : {}),
          },
          writeOptions(),
        )
        .withRawResponse(),
    );
    const response = answer.data;
    // A server that predates run recording ignores both fields and starts the flow anyway.
    if (
      (id != null || key != null) &&
      (typeof response?.calibration_run_id !== "string" || (id != null && response.calibration_session_id !== id))
    ) {
      throw resultUnknown(
        "Workflow result unknown: the run may have started without its calibration session or key. " +
          "Do not retry automatically; reconcile the execution first.",
        answer,
      );
    }
    return new WorkflowRun(this.executions, checked, response);
  }
}
