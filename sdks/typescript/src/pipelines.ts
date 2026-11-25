import { call, dispatch, read, resultUnknown, writeOptions, type Context } from "./_http.js";
import type {
  CalibrationPipelineSpec,
  CalibrationPipelineSpecStepsItem,
  ExecutePipelineResponse,
  ExecutionResponseDetail,
  PipelineCatalogResponse,
  PipelineTargets,
  ReportedLaunchOrigin,
  ValidatePipelineResponse,
} from "./types.js";
import { calibrationSpec, type CalibrationOptions } from "./definitions.js";
import { Run, type Executions, type WaitOptions } from "./runs.js";
import { QDashPreflightError } from "./errors.js";

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
 * without one, in an automatic session created for it.
 */
export interface PipelineRecording {
  /**
   * The calibration session to record the run in: open, on the same chip, and created by
   * the signed-in user. Grouping grants nothing; the run is still the request itself.
   * Without it, the run joins an automatic session created for it.
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

interface RecordingFields {
  calibration_session_id?: string;
  idempotency_key?: string;
  decision_id?: string;
}

function recording(options: PipelineRecording | undefined): RecordingFields {
  if (!options) return {};
  const blank = (value: unknown) => typeof value !== "string" || !value.trim();
  if (blank(options.idempotencyKey) || (options.calibrationSessionId !== undefined && blank(options.calibrationSessionId))) {
    throw new TypeError("idempotencyKey, and calibrationSessionId when given, must be non-empty strings");
  }
  if (options.decisionId !== undefined && (blank(options.decisionId) || !options.calibrationSessionId)) {
    throw new TypeError("decisionId must be non-empty and needs calibrationSessionId");
  }
  return {
    ...(options.calibrationSessionId ? { calibration_session_id: options.calibrationSessionId } : {}),
    idempotency_key: options.idempotencyKey,
    ...(options.decisionId ? { decision_id: options.decisionId } : {}),
  };
}

/** A dispatched pipeline execution, returned by `Pipelines.execute`. */
export class PipelineRun {
  constructor(
    private readonly executions: Executions,
    /** The dispatch response as the API returned it. */
    readonly response: ExecutePipelineResponse,
  ) {}

  /** The execution the server created for the first step. */
  get executionId(): string {
    return this.response.execution_id;
  }

  /** The current execution detail; `QDashNotFoundError` before it exists. */
  get(): Promise<ExecutionResponseDetail> {
    return this.executions.get(this.executionId);
  }

  /**
   * Poll until the whole pipeline run ends and return the raw execution detail.
   * Its outcome is `detail.pipeline.status`, or `detail.status` without pipeline
   * progress. A failed or cancelled run is returned, not thrown.
   */
  wait(options: WaitOptions = {}): Promise<ExecutionResponseDetail> {
    return this.executions.wait(this.executionId, options);
  }
}

/** Calibration pipeline routes, reached as `qdash.pipelines`. */
export class Pipelines {
  constructor(
    private readonly context: Context,
    /** Execution reads of the session, shared by its run handles. */
    readonly executions: Executions,
  ) {}

  /** Step types, task names by type and the spec schema the server accepts. */
  catalog(options: { backendName?: string } = {}): Promise<PipelineCatalogResponse> {
    const query = options.backendName ? { backend_name: options.backendName } : {};
    return read(this.context.reads, (requestOptions) =>
      this.context.api.calibrationPipeline.getCalibrationPipelineCatalog(query, requestOptions),
    );
  }

  /**
   * Check a spec against the project, chip and backend without running it. The
   * server reports every problem, including preflight checks that read
   * calibration data, as data; `valid` is false when there is any. Sent once.
   */
  validate(spec: PipelineSpecInput, target: PipelineTarget): Promise<ValidatePipelineResponse> {
    return call(() =>
      this.context.api.calibrationPipeline.validateCalibrationPipeline(request(spec, target), writeOptions()),
    );
  }

  /**
   * Dispatch a spec as one execution, which measures on the hardware. The server
   * validates it again and answers 422 (`QDashValidationError`) with the same
   * problems. The run belongs to the session's project, or to the server's
   * default project for the user when none is configured. Returns once
   * dispatched; nothing waits. The request is sent once: a transport error or an
   * error status is thrown, never retried. A success answer that cannot be read throws
   * `QDashResultUnknownError`.
   *
   * With `recording`, the run is recorded under its key and session before it is
   * launched (see `PipelineRecording`). A named session is first looked up among the
   * signed-in user's sessions on the chip, without reading its detail; nothing is
   * dispatched when it is not found. A response that does not
   * echo the session, the recorded run or the decision throws
   * `QDashResultUnknownError`: the run may have started without them, so reconcile it
   * instead of retrying.
   * `options.reportedOrigin` records how the caller says it started the run.
   */
  async execute(
    spec: PipelineSpecInput,
    target: PipelineTarget,
    recordIn?: PipelineRecording,
    options: PipelineLaunchOptions = {},
  ): Promise<PipelineRun> {
    const recorded = recording(recordIn);
    const sessionId = recordIn?.calibrationSessionId;
    if (sessionId) {
      try {
        await this.preflightSession(sessionId, target.chipId);
      } catch (cause) {
        if (cause instanceof QDashPreflightError) throw cause;
        throw new QDashPreflightError(
          "Calibration session preflight failed; nothing dispatched. Check API connectivity, credentials and server compatibility.",
          { cause },
        );
      }
    }
    const answer = await dispatch("Pipeline", () =>
      this.context.api.calibrationPipeline
        .executeCalibrationPipeline(
          {
            ...request(spec, target),
            ...recorded,
            ...(options.reportedOrigin ? { reported_origin: options.reportedOrigin } : {}),
          },
          writeOptions(),
        )
        .withRawResponse(),
    );
    const response = answer.data;
    if (recordIn) {
      // A server that predates run recording ignores the fields and launches anyway.
      const runId = response?.pipeline_run_id;
      const isRecorded = typeof runId === "string" && !!runId.trim() && typeof response.calibration_session_id === "string";
      if (!isRecorded || (sessionId && response.calibration_session_id !== sessionId)) {
        throw resultUnknown(
          "Pipeline result unknown: the execution may have started without its association. " +
            "Do not retry automatically or use a new key; reconcile the execution first.",
          answer,
        );
      }
      // A server that drops the decision would record the run without its intent.
      // Compare with the decision that was sent: the caller may change `recordIn` meanwhile.
      const decisionId = recorded.decision_id;
      if (decisionId && response.decision_id !== decisionId) {
        throw resultUnknown(
          `Pipeline result unknown: the run may have been recorded without its decision ${decisionId}. ` +
            "Do not retry automatically or use a new key; reconcile the run in the calibration session audit first.",
          answer,
        );
      }
    }
    return new PipelineRun(this.executions, response);
  }

  /**
   * Prove the server records sessions before an associated write; nothing is sent otherwise.
   *
   * Reads the session list, never the session detail: reading the detail of an open automatic
   * session closes it when its work has ended, which would make the launch that follows fail.
   * The list has no side effects and arrived with the same server release as the recording
   * fields. Only the signed-in user's sessions on the chip are listed: the server starts work
   * only in those, and an idempotent replay is always in one. Closed sessions are included, so
   * a replay into one still reaches the server, which decides whether a run may start.
   */
  private async preflightSession(sessionId: string, chipId: string): Promise<void> {
    for (let skip = 0; skip <= MAX_SESSION_SKIP; skip += SESSION_PAGE) {
      const page = await read(this.context.reads, (requestOptions) =>
        this.context.api.calibrationSession.listCalibrationSessions(
          { chip_id: chipId, mine: true, limit: SESSION_PAGE, skip },
          requestOptions,
        ),
      );
      const items = Array.isArray(page?.items) ? page.items : undefined;
      if (!items) break;
      const found = items.find((session) => session?.calibration_session_id === sessionId);
      if (found) {
        if (found.chip_id === chipId) return;
        break;
      }
      if (page.has_more !== true || items.length === 0) break;
    }
    throw new QDashPreflightError(
      `Calibration session preflight failed: ${sessionId} is not a session of yours on chip ${chipId}, ` +
        "or the server cannot record sessions; nothing dispatched. Check the session and server compatibility.",
    );
  }
}

// Sessions read per page by the preflight, and the last offset the list accepts.
const SESSION_PAGE = 100;
const MAX_SESSION_SKIP = 10_000;

/** A dispatched calibration, returned by `Chip.calibrate`. */
export class CalibrationRun extends Run {
  constructor(
    executions: Executions,
    private readonly run: PipelineRun,
  ) {
    super(executions, run.executionId);
  }

  get response(): ExecutePipelineResponse {
    return this.run.response;
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
    return new CalibrationRun(this.pipelines.executions, run);
  }

  private target(options: CalibrationOptions): PipelineTarget {
    return { chipId: this.chipId, ...(options.backendName ? { backendName: options.backendName } : {}) };
  }
}
