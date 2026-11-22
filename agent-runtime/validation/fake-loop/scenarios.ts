/**
 * Scenario fixtures of the fake-backend agent loop validation.
 *
 * Each scenario is a natural-language request to the real model in pi, the
 * approvals the harness gives as the human in the loop, and what QDash's records
 * must show afterwards. The expectations are about server records (sessions,
 * actions, executions, commits, interventions); what the model says about the
 * result is kept as a reported interpretation and never decides a check.
 */

/** The four scenarios, in the order the harness runs them. */
export const SCENARIO_IDS = ["stored-t1", "t1-rerun", "dependent-commit", "unknown-failure"] as const;
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

/** What the harness, acting as the user, approves when pi asks. Everything else is declined. */
export interface ApprovalPlan {
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
