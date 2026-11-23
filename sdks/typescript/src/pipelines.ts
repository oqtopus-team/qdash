import type { QDashClient } from "@oqtopus-team/qdash-client";
import type {
  CalibrationPipelineSpec,
  CalibrationPipelineSpecStepsItem,
  ExecutePipelineResponse,
  ExecutionResponseDetail,
  PipelineCatalogResponse,
  PipelineTargets,
  ReportedLaunchOrigin,
  ValidatePipelineResponse,
} from "@oqtopus-team/qdash-client/models";

import { calibrationSpec, type CalibrationOptions } from "./definitions.js";
import { runResult, waitForRun, type RunResult, type WaitOptions } from "./runs.js";

/**
 * A spec the pipeline routes accept: a typed version 2 spec, or any JSON object
 * (for example a stored version 1 spec), sent unchanged.
 */
export type PipelineSpecInput = CalibrationPipelineSpec | Record<string, unknown>;

export interface PipelineTarget {
  chipId: string;
  /** Defaults to the configured backend. */
  backendName?: string;
}

/**
 * How `Pipelines.execute` records a run, under one retry key: in a calibration session, or,
 * without one, in an automatic session when the server groups runs automatically, or in none.
 */
export interface PipelineRecording {
  /**
   * The calibration session to record the run in: open, on the same chip, and created by
   * the signed-in user. Grouping grants nothing; the run is still the request itself.
   * Without it, the run joins an automatic session when the server groups runs
   * automatically, or none.
   */
  calibrationSessionId?: string;
  /**
   * A retry with the same key and request returns the recorded run instead of starting
   * another; a run whose launch outcome is unknown is never launched again with it.
   */
  idempotencyKey: string;
  /**
   * The decision of that calibration session the run carries out: one recorded before the
   * dispatch with an experiment. QDash checks it belongs to the session and records the link
   * on the run, so its audit correlates intent and execution. It grants nothing.
   */
  decisionId?: string;
}

/** Options of `Pipelines.execute` beyond the spec, target, and recording. */
export interface PipelineLaunchOptions {
  /**
   * How the caller says it started the run, such as `{ source: "agent_tool", tool:
   * "qdash_run_pipeline", client: "pi-qdash" }`. QDash stores it as reported and never
   * verifies it; it grants nothing and the signed-in user stays responsible for the run.
   * Set it from the calling program, never from model or user input.
   */
  reportedOrigin?: ReportedLaunchOrigin;
}

function request(spec: PipelineSpecInput, target: PipelineTarget) {
  return {
    chip_id: target.chipId,
    // The request types `spec` as a plain JSON object so the server, not a 422 from
    // request parsing, reports problems; a typed spec is such an object.
    spec: spec as Record<string, unknown>,
    ...(target.backendName ? { backend_name: target.backendName } : {}),
  };
}

function recording(options: PipelineRecording | undefined) {
  if (!options) return {};
  if (!options.idempotencyKey || options.calibrationSessionId === "") {
    throw new TypeError("idempotencyKey, and calibrationSessionId when given, must be non-empty strings");
  }
  if (options.decisionId && !options.calibrationSessionId) {
    throw new TypeError("decisionId needs calibrationSessionId");
  }
  return {
    ...(options.calibrationSessionId ? { calibration_session_id: options.calibrationSessionId } : {}),
    idempotency_key: options.idempotencyKey,
    ...(options.decisionId ? { decision_id: options.decisionId } : {}),
  };
}

/** A dispatched pipeline execution, returned by `Pipelines.execute`. */
export class PipelineRun {
  /** The dispatch response as the API returned it. */
  readonly response: ExecutePipelineResponse;

  constructor(
    private readonly client: QDashClient,
    response: ExecutePipelineResponse,
  ) {
    this.response = response;
  }

  /** The execution the server created for the first step. */
  get executionId(): string {
    return this.response.execution_id;
  }

  /** The current execution detail; `QDashNotFoundError` before it exists. */
  get(): Promise<ExecutionResponseDetail> {
    return this.client.getExecution(this.executionId);
  }

  /**
   * Poll until the whole pipeline run ends and return the raw execution detail.
   * Its outcome is `detail.pipeline.status`, or `detail.status` without pipeline
   * progress. A failed or cancelled run is returned, not thrown.
   */
  wait(options: WaitOptions = {}): Promise<ExecutionResponseDetail> {
    return waitForRun(this.client, this.executionId, options);
  }
}

/** Calibration pipeline routes, reached as `qdash.pipelines`. */
export class Pipelines {
  constructor(private readonly client: QDashClient) {}

  /** Step types, task names by type and the spec schema the server accepts. */
  catalog(options: { backendName?: string } = {}): Promise<PipelineCatalogResponse> {
    return this.client.api.getCalibrationPipelineCatalog(
      options.backendName ? { backend_name: options.backendName } : undefined,
    );
  }

  /**
   * Check a spec against the project, chip and backend without running it. The
   * server reports every problem, including preflight checks that read
   * calibration data, as data; `valid` is false when there is any.
   */
  validate(spec: PipelineSpecInput, target: PipelineTarget): Promise<ValidatePipelineResponse> {
    return this.client.api.validateCalibrationPipeline(request(spec, target));
  }

  /**
   * Dispatch a spec as one execution, which measures on the hardware. The server
   * validates it again and answers 422 (`QDashValidationError`) with the same
   * problems. The run belongs to the session's project, or to the server's
   * default project for the user when none is configured. Returns once
   * dispatched; nothing waits. With `recording`, the run is recorded under
   * its key and session before it is launched (see `PipelineRecording`);
   * `options.reportedOrigin` records how the caller says it started the run.
   */
  async execute(
    spec: PipelineSpecInput,
    target: PipelineTarget,
    recordIn?: PipelineRecording,
    options: PipelineLaunchOptions = {},
  ): Promise<PipelineRun> {
    const response = await this.client.api.executeCalibrationPipeline({
      ...request(spec, target),
      ...recording(recordIn),
      ...(options.reportedOrigin ? { reported_origin: options.reportedOrigin } : {}),
    });
    return new PipelineRun(this.client, response);
  }
}

/** A dispatched calibration, returned by `Chip.calibrate`. */
export class CalibrationRun {
  constructor(private readonly run: PipelineRun) {}

  get executionId(): string {
    return this.run.executionId;
  }

  get response(): ExecutePipelineResponse {
    return this.run.response;
  }

  /** The run's current state; `QDashNotFoundError` before it exists. */
  async get(): Promise<RunResult> {
    return runResult(this.executionId, await this.run.get());
  }

  /** Poll until the whole calibration ends; see `PipelineRun.wait`. */
  async wait(options: WaitOptions = {}): Promise<RunResult> {
    return runResult(this.executionId, await this.run.wait(options));
  }
}

/** Calibration on one chip, reached as `qdash.chip(chipId)`; creating it sends nothing. */
export class Chip {
  readonly chipId: string;

  constructor(
    private readonly pipelines: Pipelines,
    chipId: string,
  ) {
    if (typeof chipId !== "string" || !chipId) {
      throw new TypeError("chipId must be a non-empty string");
    }
    this.chipId = chipId;
  }

  /**
   * Check a calibration of `targets` on this chip without running it. Takes the
   * same arguments as `calibrate`; nothing is dispatched.
   */
  validateCalibration(
    targets: PipelineTargets,
    steps: readonly CalibrationPipelineSpecStepsItem[],
    options: CalibrationOptions = {},
  ): Promise<ValidatePipelineResponse> {
    return this.pipelines.validate(calibrationSpec(targets, steps, options), this.target(options));
  }

  /**
   * Start a calibration of `targets` on this chip: `steps` run in order as one
   * pipeline execution. Does not call `validateCalibration` first; the server
   * validates before dispatch.
   */
  async calibrate(
    targets: PipelineTargets,
    steps: readonly CalibrationPipelineSpecStepsItem[],
    options: CalibrationOptions = {},
  ): Promise<CalibrationRun> {
    const run = await this.pipelines.execute(
      calibrationSpec(targets, steps, options),
      this.target(options),
    );
    return new CalibrationRun(run);
  }

  private target(options: CalibrationOptions): PipelineTarget {
    return { chipId: this.chipId, ...(options.backendName ? { backendName: options.backendName } : {}) };
  }
}
