import { call, dispatch, read, resultUnknown, writeOptions, type Context } from "./_http.js";
import type {
  CalibrationPipelineSpec,
  CalibrationPipelineSpecStepsItem,
  ExecutePipelineResponse,
  ExecutionResponseDetail,
  PipelineCatalogResponse,
  PipelinePlanResponse,
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

/** Where `Pipelines.executePlan` runs a stored plan, and the review it was approved as. */
export interface PipelinePlanTarget {
  /** Must be the plan's chip. */
  chipId: string;
  /** Must be the plan's backend when given. */
  backendName?: string;
  /**
   * The `review_digest` of the plan the person approved, taken from what they were shown
   * (never from model or user input). The server refuses a plan that no longer has it.
   */
  expectedReviewDigest: string;
}

/**
 * Check that a recorded dispatch is the one asked for: a response that does not echo the
 * session, the recorded run, the decision, or (for a plan) the plan and its review digest
 * may have started without them, so it is unknown rather than an error to retry.
 */
function checkRecorded(
  kind: string,
  answer: Parameters<typeof resultUnknown>[1] & { data: ExecutePipelineResponse },
  recorded: RecordingFields,
  sessionId: string | undefined,
  plan?: { planId: string; reviewDigest: string },
  requireRecording = true,
): void {
  const response = answer.data;
  const runId = response?.pipeline_run_id;
  const isRecorded = typeof runId === "string" && !!runId.trim() && typeof response.calibration_session_id === "string";
  if (requireRecording && (!isRecorded || (sessionId && response.calibration_session_id !== sessionId))) {
    throw resultUnknown(
      `${kind} result unknown: the execution may have started without its association. ` +
        "Do not retry automatically or use a new key; reconcile the execution first.",
      answer,
    );
  }
  // A server that drops the decision would record the run without its intent.
  const decisionId = recorded.decision_id;
  if (decisionId && response.decision_id !== decisionId) {
    throw resultUnknown(
      `${kind} result unknown: the run may have been recorded without its decision ${decisionId}. ` +
        "Do not retry automatically or use a new key; reconcile the run in the calibration session audit first.",
      answer,
    );
  }
  // A server that does not run plans by reference, or ran another review, answers without them.
  if (plan && (response.plan_id !== plan.planId || response.review_digest !== plan.reviewDigest)) {
    throw resultUnknown(
      `${kind} result unknown: the response does not confirm plan ${plan.planId} with review digest ` +
        `${plan.reviewDigest}. Do not retry automatically or use a new key; reconcile the execution first.`,
      answer,
    );
  }
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
   * Dispatch a hardware pipeline run. Each reached step creates an execution. The server
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
    if (sessionId) await preflightCalibrationSession(this.context, sessionId, target.chipId);
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
    // A server that predates run recording ignores the fields and launches anyway. The
    // decision compared is the one sent: the caller may change `recordIn` meanwhile.
    if (recordIn) checkRecorded("Pipeline", answer, recorded, sessionId);
    return new PipelineRun(this.executions, answer.data);
  }

  /**
   * Validate `spec` and store it as a plan to approve and run by reference. Nothing is run,
   * reserved or recorded in a session; an invalid spec is a `QDashValidationError` (422) with
   * its problems and stores nothing. The spec is checked as `validate` checks it, after every
   * default task list is written out, so a spec that omits `tasks` can be refused here
   * although `validate` accepts it (for example when the backend lacks a default task). The
   * plan holds the normalized spec with those task lists, the qubits its targets resolve to,
   * the resolved calls and its `review_digest`; it expires after 24 hours and is never renewed.
   *
   * `idempotencyKey` names this creation (one per tool call, for example) while the plan is
   * stored (until seven days after it expires): repeating it with the same request returns the
   * same plan (`replayed`), with another request is a `QDashConflictError`, and once the plan
   * expired is an error (410). After the plan is deleted, the same key creates a new plan with
   * a new ID that needs its own approval. Sent once; a transport error is thrown, and repeating
   * the call with the same key is then safe.
   */
  createPlan(
    spec: PipelineSpecInput,
    target: PipelineTarget,
    options: { idempotencyKey: string },
  ): Promise<PipelinePlanResponse> {
    if (typeof options?.idempotencyKey !== "string" || !options.idempotencyKey.trim()) {
      throw new TypeError("idempotencyKey must be a non-empty string");
    }
    return call(() =>
      this.context.api.calibrationPipeline.createCalibrationPipelinePlan(
        { ...request(spec, target), idempotency_key: options.idempotencyKey },
        writeOptions(),
      ),
    );
  }

  /**
   * A stored plan of the signed-in user, with its review content; `expired` says whether it
   * can still run. Another user's plan is `QDashNotFoundError`.
   */
  getPlan(planId: string): Promise<PipelinePlanResponse> {
    if (typeof planId !== "string" || !planId.trim()) throw new TypeError("planId must be a non-empty string");
    return read(this.context.reads, (requestOptions) =>
      this.context.api.calibrationPipeline.getCalibrationPipelinePlan({ plan_id: planId }, requestOptions),
    );
  }

  /**
   * Run a stored plan exactly as it was approved: the server refuses it when it expired, is
   * for another chip or backend, no longer has `expectedReviewDigest`, or resolves to other
   * content now. Recording, retries and errors are those of `execute`; a retry with the same
   * key returns the recorded run even after the plan expired. A response that does not echo
   * the plan and its review digest (and the session, run and decision of `recordIn`) throws
   * `QDashResultUnknownError`: reconcile instead of retrying.
   */
  async executePlan(
    planId: string,
    target: PipelinePlanTarget,
    recordIn?: PipelineRecording,
    options: PipelineLaunchOptions = {},
  ): Promise<PipelineRun> {
    if (typeof planId !== "string" || !planId.trim()) throw new TypeError("planId must be a non-empty string");
    const digest = target.expectedReviewDigest;
    if (typeof digest !== "string" || !digest.trim()) throw new TypeError("expectedReviewDigest must be a non-empty string");
    const recorded = recording(recordIn);
    const sessionId = recordIn?.calibrationSessionId;
    if (sessionId) await preflightCalibrationSession(this.context, sessionId, target.chipId);
    const answer = await dispatch("Pipeline plan", () =>
      this.context.api.calibrationPipeline
        .executeCalibrationPipelinePlan(
          {
            plan_id: planId,
            chip_id: target.chipId,
            expected_review_digest: digest,
            ...(target.backendName ? { backend_name: target.backendName } : {}),
            ...recorded,
            ...(options.reportedOrigin ? { reported_origin: options.reportedOrigin } : {}),
          },
          writeOptions(),
        )
        .withRawResponse(),
    );
    // The plan is always echoed: a server that ignored it may have run something else.
    checkRecorded(
      "Pipeline plan",
      answer,
      recorded,
      sessionId,
      { planId, reviewDigest: digest },
      recordIn !== undefined,
    );
    return new PipelineRun(this.executions, answer.data);
  }
}

// Sessions read per page by the preflight, and the last offset the list accepts.
const SESSION_PAGE = 100;
const MAX_SESSION_SKIP = 10_000;

/**
 * Prove the server records sessions before an associated write; nothing is sent otherwise.
 *
 * Reads the session list, never the session detail: reading the detail of an open automatic
 * session closes it when its work has ended, which would make the write that follows fail.
 * The list has no side effects and arrived with the same server release as the recording
 * fields. Only the signed-in user's sessions on the chip are listed: the server starts work
 * only in those, and an idempotent replay is always in one. Closed sessions are included, so
 * a replay into one still reaches the server, which decides whether work may start.
 * Any failure, including a failed read, is a `QDashPreflightError` whose `cause` is the
 * failure; a caller's abort rejects with the signal's reason.
 */
export async function preflightCalibrationSession(
  context: Context,
  sessionId: string,
  chipId: string,
  signal?: AbortSignal,
): Promise<void> {
  if (typeof sessionId !== "string" || !sessionId.trim()) {
    throw new QDashPreflightError("Calibration session preflight failed: the session ID is empty; nothing dispatched.");
  }
  try {
    for (let skip = 0; skip <= MAX_SESSION_SKIP; skip += SESSION_PAGE) {
      const page = await read({ ...context.reads, ...(signal ? { signal } : {}) }, (requestOptions) =>
        context.api.calibrationSession.listCalibrationSessions(
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
  } catch (cause) {
    if (signal?.aborted) throw signal.reason ?? cause;
    throw new QDashPreflightError(
      "Calibration session preflight failed; nothing dispatched. Check API connectivity, credentials and server compatibility.",
      { cause },
    );
  }
  throw new QDashPreflightError(
    `Calibration session preflight failed: ${sessionId} is not a session of yours on chip ${chipId}, ` +
      "or the server cannot record sessions; nothing dispatched. Check the session and server compatibility.",
  );
}

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
   * Start a calibration of `targets` on this chip. Each step reached creates an execution.
   * The server validates before dispatch.
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
