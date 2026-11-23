/**
 * Registered workflows of a project: flows saved to QDash, from the UI or
 * `QDashClient.saveFlow`, with a deployment and a target chip. These reach the
 * server's `/flows` routes; nothing is uploaded, registered or run locally.
 */
import type { QDashClient } from "@oqtopus-team/qdash-client";
import type { ExecuteFlowResponse, FlowSummary, GetFlowResponse } from "@oqtopus-team/qdash-client/models";

import { runResult, waitForRun, type RunResult, type WaitOptions } from "./runs.js";

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
}

/** A dispatched workflow run. */
export class WorkflowRun {
  constructor(
    private readonly client: QDashClient,
    readonly name: string,
    /** The dispatch response as the API returned it, including `flow_run_id`. */
    readonly response: ExecuteFlowResponse,
  ) {}

  get executionId(): string {
    return this.response.execution_id;
  }

  /** The run's current state; `QDashNotFoundError` before it exists. */
  async get(): Promise<RunResult> {
    return runResult(this.executionId, await this.client.getExecution(this.executionId));
  }

  /** Poll until the whole run ends; a failed or cancelled run is returned. */
  async wait(options: WaitOptions = {}): Promise<RunResult> {
    return runResult(this.executionId, await waitForRun(this.client, this.executionId, options));
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
  constructor(private readonly client: QDashClient) {}

  /** Summaries of the workflows registered in the session's project. */
  async list(): Promise<FlowSummary[]> {
    return (await this.client.listFlows()).flows;
  }

  /** The registered workflow `name`; `QDashNotFoundError` when there is none. */
  async get(name: string): Promise<Workflow> {
    return new Workflow(this, await this.client.getFlow(checkedName(name)));
  }

  /**
   * Dispatch the registered workflow `name`. The server merges `parameters` over
   * the saved defaults and runs on the saved `chip_id` unless the merged
   * parameters carry one. Returns once dispatched.
   */
  async run(name: string, options: WorkflowRunOptions = {}): Promise<WorkflowRun> {
    const checked = checkedName(name);
    const response = await this.client.executeFlow(checked, { ...(options.parameters ?? {}) });
    return new WorkflowRun(this.client, checked, response);
  }
}
