import type { ChipSetupMode } from "@/components/features/chip/chipSetupMode";
import type { ExecutionResponseDetail, Task } from "@/schemas";
import { isExecutionInProgress } from "@/lib/executionStatus";
import {
  JOURNEY_CREATE_CHIP_QUERY_VALUE,
  JOURNEY_QUERY_VALUE,
  type JourneyState,
} from "@/lib/firstCalibrationJourney";
import { newFlowTemplateHref } from "@/lib/flowTemplates";

/** Where the journey is, decided from server records rather than from clicks. */
export type JourneyStage = "chip" | "flow" | "run" | "progress" | "results" | "overview" | "done";

export type JourneyStepId = "chip" | "calibration" | "progress" | "result" | "overview";

export const JOURNEY_STEPS: readonly { id: JourneyStepId; label: string }[] = [
  { id: "chip", label: "Prepare a chip" },
  { id: "calibration", label: "Review and run" },
  { id: "progress", label: "Follow progress" },
  { id: "result", label: "Inspect a result" },
  { id: "overview", label: "Chip overview" },
];

const STEP_OF_STAGE: Record<JourneyStage, JourneyStepId | null> = {
  chip: "chip",
  flow: "calibration",
  run: "calibration",
  progress: "progress",
  results: "result",
  overview: "overview",
  done: null,
};

type JourneyIssue =
  | { kind: "chipMissing"; chipId: string }
  | { kind: "flowMissing"; flowName: string }
  | { kind: "flowChipChanged"; flowName: string; flowChipId: string }
  | { kind: "executionMissing"; executionId: string }
  | { kind: "runFailed"; message: string }
  | { kind: "runCancelled" }
  | { kind: "noResults" }
  | { kind: "loadFailed" };

/** A server record the journey points at, as far as the client knows it. */
export type RecordLookup<T> =
  | { status: "none" }
  | { status: "loading" }
  | { status: "missing" }
  | { status: "error" }
  | { status: "ready"; data: T };

export interface JourneyServerState {
  setup: ChipSetupMode;
  /** Chip ids of the project, or null while they load or after a failed load. */
  chipIds: ReadonlySet<string> | null;
  chipsFailed: boolean;
  flow: RecordLookup<{ chipId: string }>;
  execution: RecordLookup<ExecutionResponseDetail>;
}

interface JourneyTaskSummary {
  done: number;
  failed: number;
  total: number;
  current: string | null;
}

interface RecommendedResult {
  taskId: string;
  name: string;
  qid: string;
  hasFigure: boolean;
}

export interface JourneyProgress {
  stage: JourneyStage;
  /** The server has not answered yet, so the stage may still move forward. */
  pending: boolean;
  issue: JourneyIssue | null;
  tasks: JourneyTaskSummary | null;
  recommendedResult: RecommendedResult | null;
}

export type JourneyStepState = "done" | "current" | "attention" | "upcoming";

function summarizeTasks(tasks: readonly Task[]): JourneyTaskSummary {
  return {
    done: tasks.filter((task) => task.status === "completed").length,
    failed: tasks.filter((task) => task.status === "failed").length,
    total: tasks.length,
    current: tasks.find((task) => task.status === "running")?.name ?? null,
  };
}

function hasFigure(task: Task): boolean {
  return Array.isArray(task.figure_path) ? task.figure_path.length > 0 : Boolean(task.figure_path);
}

/**
 * The completed task result to open first: a CheckT1 with a figure when there is one, otherwise
 * any completed task with a figure, otherwise any completed task.
 */
function pickRecommendedResult(tasks: readonly Task[]): RecommendedResult | null {
  const completed = tasks.filter(
    (task): task is Task & { task_id: string } =>
      task.status === "completed" && typeof task.task_id === "string" && task.task_id !== "",
  );
  const pick =
    completed.find((task) => task.name === "CheckT1" && hasFigure(task)) ??
    completed.find((task) => hasFigure(task)) ??
    completed.find((task) => task.name === "CheckT1") ??
    completed[0];
  if (!pick) return null;
  return {
    taskId: pick.task_id,
    name: pick.name ?? "Task",
    qid: pick.qid ?? "",
    hasFigure: hasFigure(pick),
  };
}

function lookupPending<T>(lookup: RecordLookup<T>): boolean {
  return lookup.status === "loading";
}

/** Derive the journey stage from the stored ids and what the server says about them. */
export function deriveJourneyProgress(
  state: JourneyState,
  server: JourneyServerState,
): JourneyProgress {
  const base = { tasks: null, recommendedResult: null };

  if (!state.chipId) return { ...base, stage: "chip", pending: false, issue: null };
  if (server.chipIds === null) {
    return {
      ...base,
      stage: "chip",
      pending: !server.chipsFailed,
      issue: server.chipsFailed ? { kind: "loadFailed" } : null,
    };
  }
  if (!server.chipIds.has(state.chipId)) {
    return {
      ...base,
      stage: "chip",
      pending: false,
      issue: { kind: "chipMissing", chipId: state.chipId },
    };
  }

  if (!state.flowName) return { ...base, stage: "flow", pending: false, issue: null };
  const flow = server.flow;
  if (flow.status !== "ready") {
    const issue: JourneyIssue | null =
      flow.status === "missing"
        ? { kind: "flowMissing", flowName: state.flowName }
        : flow.status === "error"
          ? { kind: "loadFailed" }
          : null;
    return { ...base, stage: "flow", pending: lookupPending(flow), issue };
  }
  if (flow.data.chipId !== state.chipId) {
    return {
      ...base,
      stage: "flow",
      pending: false,
      issue: {
        kind: "flowChipChanged",
        flowName: state.flowName,
        flowChipId: flow.data.chipId,
      },
    };
  }

  if (!state.executionId) return { ...base, stage: "run", pending: false, issue: null };
  const execution = server.execution;
  if (execution.status !== "ready") {
    const issue: JourneyIssue | null =
      execution.status === "missing"
        ? { kind: "executionMissing", executionId: state.executionId }
        : execution.status === "error"
          ? { kind: "loadFailed" }
          : null;
    return {
      ...base,
      stage: execution.status === "missing" ? "run" : "progress",
      pending: lookupPending(execution),
      issue,
    };
  }

  const detail = execution.data;
  if (detail.chip_id && detail.chip_id !== state.chipId) {
    return {
      ...base,
      stage: "run",
      pending: false,
      issue: { kind: "executionMissing", executionId: state.executionId },
    };
  }
  const tasks = summarizeTasks(detail.task ?? []);
  const progress = { tasks, recommendedResult: null, pending: false };

  if (isExecutionInProgress(detail.status)) return { ...progress, stage: "progress", issue: null };
  if (detail.status === "failed") {
    return {
      ...progress,
      stage: "progress",
      issue: { kind: "runFailed", message: detail.message ?? "" },
    };
  }
  if (detail.status === "cancelled") {
    return { ...progress, stage: "progress", issue: { kind: "runCancelled" } };
  }
  const recommendedResult =
    detail.status === "completed" ? pickRecommendedResult(detail.task ?? []) : null;
  if (!recommendedResult) {
    // A completed run without one successful task result has nothing to inspect.
    return { ...progress, stage: "progress", issue: { kind: "noResults" } };
  }

  const done = { ...progress, recommendedResult, issue: null };
  if (!state.inspectedTaskId) return { ...done, stage: "results" };
  if (!state.chipOverviewSeen) return { ...done, stage: "overview" };
  return { ...done, stage: "done" };
}

/** Visible state of each step for a stage; an issue marks the current step for attention. */
export function journeyStepStates(
  progress: JourneyProgress,
): Record<JourneyStepId, JourneyStepState> {
  const currentStep = STEP_OF_STAGE[progress.stage];
  const currentIndex =
    currentStep === null
      ? JOURNEY_STEPS.length
      : JOURNEY_STEPS.findIndex((step) => step.id === currentStep);
  const states = {} as Record<JourneyStepId, JourneyStepState>;
  JOURNEY_STEPS.forEach((step, index) => {
    states[step.id] =
      index < currentIndex
        ? "done"
        : index === currentIndex
          ? progress.issue
            ? "attention"
            : "current"
          : "upcoming";
  });
  return states;
}

export function journeyStepNumber(stage: JourneyStage): number {
  const step = STEP_OF_STAGE[stage];
  return step === null
    ? JOURNEY_STEPS.length
    : JOURNEY_STEPS.findIndex((item) => item.id === step) + 1;
}

export interface JourneyAction {
  label: string;
  href: string;
}

export function executionHref(chipId: string, executionId: string): string {
  return `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(executionId)}`;
}

function flowHref(flowName: string): string {
  return `/workflow/${encodeURIComponent(flowName)}`;
}

export function chipOverviewHref(chipId: string): string {
  return `/chip?${new URLSearchParams({ chip: chipId }).toString()}`;
}

/**
 * New Flow editor opened for the journey: on the fake template on a fake deployment, and with the
 * template choice left to the user on hardware. Null while the deployment kind is unknown, or on a
 * fake deployment that does not offer its preset, so the guide never guesses a hardware path.
 */
export function journeyNewFlowHref(setup: ChipSetupMode, chipId: string): string | null {
  if (setup.kind === "fake") {
    if (!setup.preset) return null;
    const href = newFlowTemplateHref("fake", setup.preset.workflow_template_id, chipId);
    return `${href}&journey=${JOURNEY_QUERY_VALUE}`;
  }
  if (setup.kind !== "hardware") return null;
  const params = new URLSearchParams({
    chip_id: chipId,
    journey: JOURNEY_QUERY_VALUE,
  });
  return `/workflow/new?${params.toString()}`;
}

/** Whether a hardware deployment still waits for the user to confirm the journey's chip. */
function awaitsHardwareConfirmation(state: JourneyState, setup: ChipSetupMode): boolean {
  return setup.kind === "hardware" && state.hardwareConfirmedChipId !== state.chipId;
}

/**
 * Whether the guide shows the hardware readiness check now: on a hardware deployment, from the
 * moment the chip is chosen until the run starts, so it comes before the editor and the run.
 */
export function journeyShowsHardwareReadiness(
  state: JourneyState,
  progress: JourneyProgress,
  setup: ChipSetupMode,
): boolean {
  return (
    setup.kind === "hardware" &&
    state.chipId !== null &&
    !progress.pending &&
    !progress.issue &&
    (progress.stage === "flow" || progress.stage === "run")
  );
}

/**
 * The one action that moves the journey on, or null when the user acts on the current page
 * (for example, when the hardware readiness confirmation is still open).
 */
export function journeyNextAction(
  state: JourneyState,
  progress: JourneyProgress,
  setup: ChipSetupMode,
): JourneyAction | null {
  const { chipId, flowName, executionId } = state;
  switch (progress.stage) {
    case "chip":
      return {
        label: "Create a chip",
        href: `/chip?journey=${JOURNEY_CREATE_CHIP_QUERY_VALUE}`,
      };
    case "flow": {
      if (!chipId) return null;
      if (progress.issue?.kind === "flowChipChanged" && flowName) {
        return { label: "Open the flow", href: flowHref(flowName) };
      }
      if (awaitsHardwareConfirmation(state, setup)) return null;
      const href = journeyNewFlowHref(setup, chipId);
      return href ? { label: "Review the calibration", href } : null;
    }
    case "run":
      if (!flowName || setup.kind === "pending") return null;
      if (awaitsHardwareConfirmation(state, setup)) return null;
      return { label: "Open the flow to run it", href: flowHref(flowName) };
    case "progress":
      if (!chipId || !executionId) return null;
      if (progress.issue && progress.issue.kind !== "loadFailed" && flowName) {
        return { label: "Run again", href: flowHref(flowName) };
      }
      return {
        label: "Follow progress",
        href: executionHref(chipId, executionId),
      };
    case "results":
      if (!progress.recommendedResult) return null;
      return {
        label: `Open ${progress.recommendedResult.name} result`,
        href: `/task-results/${encodeURIComponent(progress.recommendedResult.taskId)}`,
      };
    case "overview":
      return chipId ? { label: "Open the chip overview", href: chipOverviewHref(chipId) } : null;
    case "done":
      return null;
  }
}

/** One short sentence on what to do at this stage. */
export function journeyStageHint(
  state: JourneyState,
  progress: JourneyProgress,
  setup: ChipSetupMode,
): string {
  const issue = progress.issue;
  if (issue) {
    switch (issue.kind) {
      case "chipMissing":
        return `Chip ${issue.chipId} no longer exists. Create a chip or pick another one on Home.`;
      case "flowMissing":
        return `Flow ${issue.flowName} no longer exists. Prepare the calibration again.`;
      case "flowChipChanged":
        return `Flow ${issue.flowName} now targets chip ${issue.flowChipId}. Set its chip back to ${state.chipId} or prepare a new flow.`;
      case "executionMissing":
        return "The run this guide followed is no longer available. Run the flow again.";
      case "runFailed":
        return issue.message
          ? `The run failed: ${issue.message}`
          : "The run failed. Open it to see which tasks failed, then run again.";
      case "runCancelled":
        return "The run was cancelled. Run the flow again when you are ready.";
      case "noResults":
        return "The run finished without a successful task result. Check it, then run again.";
      case "loadFailed":
        return "QDash could not load the guide's records. Reload the page to try again.";
    }
  }
  if ((progress.stage === "flow" || progress.stage === "run") && setup.kind === "pending") {
    return setup.failed
      ? "QDash could not check how this deployment runs calibrations. Try again on Home."
      : "Checking how this deployment runs calibrations.";
  }
  if (progress.stage === "flow" && setup.kind === "fake" && !setup.preset) {
    return "This deployment runs the fake backend but does not offer its virtual device. Ask an administrator to check the API configuration.";
  }
  switch (progress.stage) {
    case "chip":
      return "Create the chip to calibrate, or pick an existing one on Home.";
    case "flow":
      if (awaitsHardwareConfirmation(state, setup)) {
        return `Confirm that the configuration of ${state.chipId} matches the hardware before you prepare the calibration.`;
      }
      return setup.kind === "fake"
        ? `Review the Fake Backend Calibration for ${state.chipId}, then save it as a flow.`
        : `Pick a calibration template for ${state.chipId}, review it, then save it as a flow.`;
    case "run":
      return awaitsHardwareConfirmation(state, setup)
        ? "Confirm that the chip configuration matches the hardware before you run."
        : `Open ${state.flowName}, select Execute and confirm to start the run.`;
    case "progress":
      return progress.tasks && progress.tasks.total > 0
        ? `Running: ${progress.tasks.done} of ${progress.tasks.total} tasks completed.`
        : "The run is starting.";
    case "results":
      return "Open a completed result to see its graph and fitted values.";
    case "overview":
      return `See the calibrated values across ${state.chipId}.`;
    case "done":
      return "You ran a calibration and inspected its results.";
  }
}
