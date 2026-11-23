/**
 * Scenario fixtures of the fake-backend agent loop validation.
 *
 * Each scenario is a natural-language request to the real model in pi, the
 * approvals the harness gives as the human in the loop, and what QDash's records
 * must show afterwards. The expectations are about server records (sessions,
 * actions, executions, commits, interventions); what the model says about the
 * result is kept as a reported interpretation and never decides a check.
 */

/** The scenarios, in the order the harness runs them. */
export const SCENARIO_IDS = ["stored-t1", "t1-rerun", "dependent-commit", "unknown-failure", "purpose-pipeline"] as const;
export type ScenarioId = (typeof SCENARIO_IDS)[number];

/** The prerequisite chain the harness runs once on the disposable chip (`--setup`). */
export const SETUP_TASKS = [
  "FakeBringUp",
  "CheckChevron",
  "CheckRabi",
  "CreateHPIPulse",
  "CreatePIPulse",
  "CheckT1",
] as const;

/** Tasks the fake backend supports; a scenario never asks for anything else. */
export const FAKE_TASKS = new Set([
  "FakeBringUp",
  "CheckChevron",
  "CheckRabi",
  "CreateHPIPulse",
  "CheckHPIPulse",
  "CreatePIPulse",
  "CheckPIPulse",
  "CheckT1",
  "CheckT2Echo",
  "CheckRamsey",
]);

export interface ScenarioTarget {
  chipId: string;
  qid: string;
}

/** Update authority the user approves as part of the session (`policy.parameter_updates`). */
export interface UpdateGrantPlan {
  /** Parameters the session may grant; the proposed grant must name exactly these. */
  parameters: readonly string[];
  /** Tasks that may supply them; the proposed grant must stay inside these. */
  tasks: readonly string[];
  /** Whether a backend apply may be part of the grant. */
  applyBackend: boolean;
}

/**
 * A pipeline run the user approves (`qdash_run_pipeline`). Only a spec whose targets are
 * exactly the selected qubit, whose every step names its tasks explicitly within `tasks`, on
 * the default (fake) backend, recorded in a calibration session this scenario created.
 */
export interface PipelineRunPlan {
  tasks: readonly string[];
  /** Most task calls the whole spec may make on the qubit. */
  maxTaskCalls: number;
  /** Most runs approved in the scenario. */
  maxRuns: number;
}

/** What the harness, acting as the user, approves when pi asks. Everything else is declined. */
export interface ApprovalPlan {
  /** Approve `qdash_create_calibration_session` on the validation chip, at most `max` times. */
  createCalibrationSession?: { max: number };
  runPipeline?: PipelineRunPlan;
  /**
   * Approve `qdash_create_agent_session` when its scope stays inside these bounds. A session
   * that proposes parameter updates is approved only when `updates` allows exactly them;
   * without `updates`, any proposed grant is declined.
   */
  createSession?: { tasks: readonly string[]; maxActions: number; maxExpiresInSeconds: number; updates?: UpdateGrantPlan };
}

/** What QDash's records must show after the scenario. */
export interface ScenarioExpectation {
  /** Agent sessions the scenario may create. */
  sessions: { min: number; max: number };
  /** Tasks the scenario may measure, in any order. */
  allowedTasks: readonly string[];
  /** Measurements (dispatched `run_task` actions) the scenario must and may make. */
  measurements: { min: number; max: number };
  /** Tasks that must each be measured at least once. */
  requiredTasks?: readonly string[];
  /**
   * A candidate of this parameter must be committed under the session's approved update
   * authority, without a commit dialog, and precede this task's measurement.
   */
  commitBefore?: { parameter: string; task: string };
  /** The scenario must not commit candidates. */
  noCommits?: boolean;
  /**
   * Calibration session expectations. With this set, every execution on the chip during the
   * scenario must be a step of a pipeline run recorded in one of the scenario's calibration
   * sessions, instead of an agent session measurement.
   */
  calibration?: CalibrationExpectation;
}

/** What a purpose-level calibration scenario's records must show. */
export interface CalibrationExpectation {
  /** Calibration sessions the scenario may create. */
  sessions: { min: number; max: number };
  /** Pipeline runs recorded in them. */
  pipelineRuns: { min: number; max: number };
  /** Tasks the pipeline's step executions may run, on the selected qubit only. */
  pipelineTasks: readonly string[];
  /** The origin every run the model started must report: the pi-qdash tool's own constant. */
  reportedOrigin: { source: string; tool: string; client: string };
  /** The model must read the calibration session back after starting the run. */
  readBack: boolean;
}

/**
 * A pipeline the harness starts itself through the API before the model's turn, as a person
 * would without an agent: no calibration session and no reported origin. Its executions must
 * stay unassociated and unattributed.
 */
export interface BaselinePipeline {
  spec: (target: ScenarioTarget) => Record<string, unknown>;
}

/** The unknown-failure scenario's second half: expert answer, then an explicit continue. */
export interface ContinuationPlan {
  guidance: string;
  prompt: (target: ScenarioTarget) => string;
  /**
   * Repeats of the failed measurement the expert's answer asks for (at least `minRepeats`, at
   * most `maxRepeats`). Each must cite the failed action, complete, and be proposed and
   * dispatched only after the explicit continue prompt.
   */
  minRepeats: number;
  maxRepeats: number;
}

export interface Scenario {
  id: ScenarioId;
  title: string;
  prompt: (target: ScenarioTarget) => string;
  approvals: ApprovalPlan;
  expect: ScenarioExpectation;
  /** Arm the fake backend's validation fault for this task on the scenario qubit. */
  fault?: { taskName: string };
  continuation?: ContinuationPlan;
  /**
   * Tools hidden from the model in this scenario. The unknown-failure scenario hides the live
   * intervention wait so the turn ends and the continuation is the explicit one.
   */
  excludeTools?: readonly string[];
  /** A manual pipeline the harness runs before the prompt, as the unassociated baseline. */
  baseline?: BaselinePipeline;
}

/** The one-step pipeline the baseline and the purpose scenario both stay within. */
export const PURPOSE_PIPELINE_TASKS = ["CheckT1"] as const;

/** The origin `qdash_run_pipeline` reports (PIPELINE_TOOL_ORIGIN in pi-qdash). */
export const PIPELINE_TOOL_ORIGIN = { source: "agent_tool", tool: "qdash_run_pipeline", client: "pi-qdash" } as const;

export function baselinePipelineSpec({ qid }: ScenarioTarget): Record<string, unknown> {
  return {
    spec_version: 2,
    name: "agentval-baseline-t1",
    targets: { qids: [qid] },
    steps: [{ type: "CustomOneQubit", step_name: "baseline_t1", tasks: [{ name: "CheckT1" }] }],
  };
}

const SESSION_LIMITS = { maxActions: 4, maxExpiresInSeconds: 3600 };

/**
 * Scenarios share the disposable chip and qubit, so a session an earlier scenario (or an
 * earlier run) left active can cover a later goal. Reusing it would be legitimate for the
 * model but would make the scenario judge a session it did not create. Each measuring
 * prompt therefore asks for a new session, as a user who wants a fresh audit would; the
 * report lists the open sessions found at the start (`open_sessions_at_start`). Resuming an
 * existing session is not what these scenarios validate.
 */
export const FRESH_SESSION = "Start a new agent session for this request.";

export const SCENARIOS: Record<ScenarioId, Scenario> = {
  "stored-t1": {
    id: "stored-t1",
    title: "A question about the stored T1 is answered without measuring",
    prompt: ({ chipId, qid }) => `What is the T1 of qubit ${qid} on chip ${chipId}?`,
    approvals: {},
    expect: { sessions: { min: 0, max: 0 }, allowedTasks: [], measurements: { min: 0, max: 0 }, noCommits: true },
  },
  "t1-rerun": {
    id: "t1-rerun",
    title: "A requested T1 rerun measures only T1",
    prompt: ({ chipId, qid }) =>
      `Measure T1 again on qubit ${qid} of chip ${chipId}. The other parameters are already calibrated; only T1 needs a fresh measurement. Limit the agent session to four actions and an explicit one-hour expiry. ${FRESH_SESSION}`,
    approvals: { createSession: { tasks: ["CheckT1"], ...SESSION_LIMITS } },
    expect: {
      sessions: { min: 1, max: 1 },
      allowedTasks: ["CheckT1"],
      measurements: { min: 1, max: 1 },
      requiredTasks: ["CheckT1"],
      noCommits: true,
    },
  },
  "dependent-commit": {
    id: "dependent-commit",
    title: "Update authority approved with the session commits the value a dependent step needs, without a further approval",
    prompt: ({ chipId, qid }) =>
      `Recalibrate the qubit frequency of qubit ${qid} on chip ${chipId} with CheckChevron, then check CheckRabi with the new frequency. If the Chevron result is good, update the frequency without asking me again; if anything looks wrong, stop and ask me. Limit the agent session to four actions and an explicit one-hour expiry. ${FRESH_SESSION}`,
    approvals: {
      createSession: {
        tasks: ["CheckChevron", "CheckRabi"],
        ...SESSION_LIMITS,
        updates: { parameters: ["qubit_frequency"], tasks: ["CheckChevron"], applyBackend: false },
      },
    },
    expect: {
      sessions: { min: 1, max: 1 },
      allowedTasks: ["CheckChevron", "CheckRabi"],
      measurements: { min: 2, max: 3 },
      requiredTasks: ["CheckChevron", "CheckRabi"],
      commitBefore: { parameter: "qubit_frequency", task: "CheckRabi" },
    },
  },
  "unknown-failure": {
    id: "unknown-failure",
    title: "An unexplained failure pauses for an expert; after the answer, an explicit continue repeats it once to completion",
    prompt: ({ chipId, qid }) =>
      `Measure T1 again on qubit ${qid} of chip ${chipId}. Limit the agent session to four actions and an explicit one-hour expiry. ${FRESH_SESSION}`,
    approvals: { createSession: { tasks: ["CheckT1"], ...SESSION_LIMITS } },
    expect: {
      sessions: { min: 1, max: 1 },
      allowedTasks: ["CheckT1"],
      // The armed failure, then the one completed repeat the expert asks for.
      measurements: { min: 2, max: 2 },
      requiredTasks: ["CheckT1"],
      noCommits: true,
    },
    fault: { taskName: "CheckT1" },
    excludeTools: ["qdash_wait_agent_intervention"],
    continuation: {
      guidance:
        "The simulator fault behind the failed CheckT1 has been cleared. Repeat CheckT1 once on this qubit, citing the failed action; run no other task.",
      prompt: ({ chipId, qid }) =>
        `The expert answered the paused T1 calibration of qubit ${qid} on chip ${chipId}. Continue.`,
      minRepeats: 1,
      maxRepeats: 1,
    },
  },
  "purpose-pipeline": {
    id: "purpose-pipeline",
    title: "A purpose-level request is recorded as a calibration session whose pipeline steps link back with a reported tool origin; a manual pipeline stays unassociated",
    // The user states an objective and what they want to learn; which tools to call, how to
    // write the spec, and how to read the result back are the model's own choices.
    prompt: ({ chipId, qid }) =>
      `My objective on chip ${chipId}: re-check the T1 of qubit ${qid}. Keep this work together under one calibration objective in QDash so I can find it later. Run it as a calibration pipeline that measures only CheckT1 on qubit ${qid}, once. When it has finished, look the objective up again and tell me which executions belong to it and how each one was started: by an agent session, by a pipeline your tool launched, or manually.`,
    approvals: {
      createCalibrationSession: { max: 1 },
      runPipeline: { tasks: PURPOSE_PIPELINE_TASKS, maxTaskCalls: 2, maxRuns: 1 },
    },
    expect: {
      sessions: { min: 0, max: 0 },
      allowedTasks: [],
      measurements: { min: 0, max: 0 },
      noCommits: true,
      calibration: {
        sessions: { min: 1, max: 1 },
        pipelineRuns: { min: 1, max: 1 },
        pipelineTasks: PURPOSE_PIPELINE_TASKS,
        reportedOrigin: PIPELINE_TOOL_ORIGIN,
        readBack: true,
      },
    },
    baseline: { spec: baselinePipelineSpec },
  },
};

/** Parse `--scenario` values: `all` or a comma-separated list of ids, in run order. */
export function selectScenarios(value: string | undefined): Scenario[] {
  if (value === undefined || value === "all") return SCENARIO_IDS.map((id) => SCENARIOS[id]);
  const ids = value.split(",").map((part) => part.trim()).filter(Boolean);
  for (const id of ids) {
    if (!(SCENARIO_IDS as readonly string[]).includes(id)) throw new Error(`unknown scenario: ${id}`);
  }
  return SCENARIO_IDS.filter((id) => ids.includes(id)).map((id) => SCENARIOS[id]);
}
