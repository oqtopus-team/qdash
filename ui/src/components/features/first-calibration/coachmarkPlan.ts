import type { ChipSetupMode } from "@/components/features/chip/chipSetupMode";
import { JOURNEY_QUERY_VALUE, type JourneyState } from "@/lib/firstCalibrationJourney";

import {
  JOURNEY_STEPS,
  executionHref,
  journeyNextAction,
  journeyShowsHardwareReadiness,
  journeyStepNumber,
  type JourneyProgress,
} from "./journeyProgress";

/**
 * Coachmarks of the first calibration journey: which control on the current page the guide
 * points at next. A plan is derived from the journey's server-backed progress and the route, so
 * the guide never keeps its own idea of where the user is.
 *
 * - `action` steps finish only through the real action (creating, saving, running, opening).
 * - `info` steps explain what is on screen and finish with Next.
 * - `wait` steps show that QDash is working; they have no Next and do not dim the page.
 */
type CoachmarkKind = "action" | "info" | "wait";

type CoachmarkSide = "top" | "right" | "bottom" | "left";
type CoachmarkAlign = "start" | "center" | "end";

export interface CoachmarkStep {
  /** Stable id within one journey stage; info steps are remembered as read by this id. */
  id: string;
  kind: CoachmarkKind;
  title: string;
  /** One concrete instruction. */
  description: string;
  /** Selectors of the control to point at; the first one on screen wins. */
  targets: readonly string[];
  /** Skip the step while none of its targets is on screen, instead of waiting for one. */
  optional?: boolean;
  /** The step is done once its input holds a value and the user has left the field. */
  doneWhenFilled?: boolean;
  /** Dim the page around the target; off for wait steps and controls inside a dialog. */
  dim: boolean;
  side?: CoachmarkSide;
  align?: CoachmarkAlign;
  /** Label of the Next button of an info step. */
  nextLabel?: string;
}

/** The journey event a plan records once the user has read its explanations. */
interface CoachmarkCompletion {
  /** Info steps that explain one thing; read at least one, then move past all of them. */
  stepIds: readonly string[];
  event: { type: "resultInspected"; executionId: string; taskId: string };
}

export interface CoachmarkPlan {
  /** "Step 2 of 5 · Review and run", or "Complete". */
  progressText: string;
  steps: CoachmarkStep[];
  /**
   * Set while the guide explains a result: the journey moves on once the explanation is over,
   * not when the result opens, so the progress shown matches what the guide is explaining.
   */
  completion?: CoachmarkCompletion;
}

export interface CoachmarkPlanInput {
  state: JourneyState;
  progress: JourneyProgress;
  setup: ChipSetupMode;
  pathname: string;
  /** The `journey` query value of the current URL. */
  journeyParam: string | null;
}

/** Selector of an element marked with `data-coachmark="<name>"`. */
function coachmarkTarget(name: string): string {
  return `[data-coachmark="${name}"]`;
}

function attributeValue(value: string): string {
  return value.replace(/["\\]/g, "\\$&");
}

/** Selector of an element marked for one task result, e.g. the figure of the inspected result. */
function taskTarget(name: string, taskId: string): string {
  return `${coachmarkTarget(name)}[data-task-id="${attributeValue(taskId)}"]`;
}

export const COACHMARK_TARGETS = {
  journeyAction: coachmarkTarget("journey-action"),
  hardwareReadiness: coachmarkTarget("hardware-readiness"),
  createChip: coachmarkTarget("create-chip"),
  chipIdInput: "#chip-id-input",
  createChipSubmit: coachmarkTarget("create-chip-submit"),
  flowTemplateReady: `${coachmarkTarget("flow-template")}[data-coachmark-ready="true"]`,
  flowSummaryReady: `${coachmarkTarget("flow-summary")}[data-coachmark-ready="true"]`,
  flowName: coachmarkTarget("flow-name"),
  flowSave: coachmarkTarget("flow-save"),
  /** Execute once the flow is loaded and QDash reports the run can start. */
  flowExecuteReady: `${coachmarkTarget("flow-execute")}[data-coachmark-ready="true"]`,
  flowExecuteConfirm: coachmarkTarget("flow-execute-confirm"),
  executionHeader: coachmarkTarget("execution-header"),
  executionTask: (taskId: string) => `.react-flow__node[data-id="${attributeValue(taskId)}"]`,
  resultFigure: (taskId: string) => taskTarget("task-result-figure", taskId),
  resultMetrics: (taskId: string) => taskTarget("task-result-metrics", taskId),
  closeResultPreview: '[aria-label="Close task result preview"]',
  chipOverview: (chipId: string) =>
    `${coachmarkTarget("chip-overview")}[data-chip-id="${attributeValue(chipId)}"]`,
} as const;

function flowPath(flowName: string): string {
  return `/workflow/${encodeURIComponent(flowName)}`;
}

function decodePath(path: string): string {
  try {
    return decodeURIComponent(path);
  } catch {
    return path;
  }
}

/** Whether the current pathname is `href`, however either is percent-encoded. */
function onPath(pathname: string, href: string): boolean {
  return decodePath(pathname) === decodePath(href);
}

function progressText(progress: JourneyProgress): string {
  if (progress.stage === "done") return "Complete";
  const step = journeyStepNumber(progress.stage);
  return `Step ${step} of ${JOURNEY_STEPS.length} · ${JOURNEY_STEPS[step - 1]?.label ?? ""}`;
}

/** The guide's next link, in the banner or on the Home card. */
function actionStep(id: string, title: string, description: string): CoachmarkStep {
  return {
    id,
    kind: "action",
    title,
    description,
    targets: [COACHMARK_TARGETS.journeyAction],
    dim: true,
    side: "bottom",
    align: "end",
  };
}

function runSteps(id: string, title: string, description: string): CoachmarkStep[] {
  return [
    {
      id: `${id}:confirm`,
      kind: "action",
      title: "Start the run",
      description: "Check the chip ID, then select Execute to start the calibration.",
      targets: [COACHMARK_TARGETS.flowExecuteConfirm],
      optional: true,
      dim: false,
      side: "top",
      align: "end",
    },
    {
      id: `${id}:execute`,
      kind: "action",
      title,
      description,
      // While Execute is disabled (availability still checking, target in use, or an error) the
      // step waits instead of pointing at a control that cannot start the run.
      targets: [COACHMARK_TARGETS.flowExecuteReady],
      dim: true,
      side: "bottom",
      align: "end",
    },
  ];
}

function chipSteps(input: CoachmarkPlanInput): CoachmarkStep[] {
  const { pathname, setup } = input;
  if (pathname === "/chip") {
    return [
      {
        id: "chip:name",
        kind: "action",
        title: "Name the chip",
        description: "Enter a unique chip ID. Its configuration directory takes the same name.",
        targets: [COACHMARK_TARGETS.chipIdInput],
        optional: true,
        doneWhenFilled: true,
        dim: false,
        side: "bottom",
        align: "start",
      },
      {
        id: "chip:create",
        kind: "action",
        title: "Create the chip",
        description:
          setup.kind === "fake"
            ? "Select Create Chip. The virtual device is configured for it; no hardware is contacted."
            : "Check the topology and configuration, then select Create Chip.",
        targets: [COACHMARK_TARGETS.createChipSubmit],
        optional: true,
        dim: false,
        side: "top",
        align: "end",
      },
      {
        id: "chip:open",
        kind: "action",
        title: "Open the chip form",
        description: "Select Create Chip to enter the ID of the chip to calibrate.",
        targets: [COACHMARK_TARGETS.createChip],
        dim: true,
        side: "bottom",
        align: "end",
      },
    ];
  }
  if (pathname === "/home" || pathname === "/") {
    return [
      actionStep(
        "chip:choose",
        "Choose a chip",
        "Continue with a chip in the list, or choose Create a new chip to make one.",
      ),
    ];
  }
  return [actionStep("chip:go", "Create a chip", "Select Create a chip to open the chip form.")];
}

function flowSteps(input: CoachmarkPlanInput, label: string | null): CoachmarkStep[] {
  const { state, progress, setup, pathname, journeyParam } = input;
  const chipId = state.chipId ?? "";
  if (progress.issue?.kind === "flowChipChanged") {
    if (!state.flowName || onPath(pathname, flowPath(state.flowName)) || !label) return [];
    return [
      actionStep(
        "flow:fix",
        "Fix the flow's chip",
        `Select ${label}, then set its chip back to ${chipId}.`,
      ),
    ];
  }
  if (pathname === "/workflow/new") {
    if (journeyParam !== JOURNEY_QUERY_VALUE) return [];
    return [
      {
        id: "flow:review",
        kind: "info",
        title: "Review the calibration",
        description:
          setup.kind === "fake"
            ? "The editor holds the Fake Backend Calibration. This summary lists its tasks in run order and the MUXes they target. A first run can use it unchanged."
            : `Choose a template for ${chipId} under Template, then check its tasks and targets. A first run can use it unchanged.`,
        // The summary of the code in the editor, or the template choice while no summary is shown.
        targets: [COACHMARK_TARGETS.flowSummaryReady, COACHMARK_TARGETS.flowTemplateReady],
        dim: true,
        side: "left",
        align: "start",
      },
      {
        id: "flow:name",
        kind: "info",
        title: "Name the flow",
        description:
          "Keep the suggested name or enter another with letters, digits and underscores.",
        targets: [COACHMARK_TARGETS.flowName],
        dim: true,
        side: "left",
        align: "start",
      },
      {
        id: "flow:save",
        kind: "action",
        title: "Save the flow",
        description: `Select Save Flow to save the calibration for ${chipId}. Nothing runs yet.`,
        targets: [COACHMARK_TARGETS.flowSave],
        dim: true,
        side: "bottom",
        align: "end",
      },
    ];
  }
  if (!label) return [];
  return [
    actionStep(
      "flow:go",
      "Open the calibration",
      `Select ${label} to open the calibration template for ${chipId}.`,
    ),
  ];
}

function progressSteps(input: CoachmarkPlanInput, label: string | null): CoachmarkStep[] {
  const { state, progress, pathname } = input;
  const { chipId, flowName, executionId } = state;
  if (!chipId || !executionId) return [];
  const issue = progress.issue;

  if (issue && issue.kind !== "loadFailed") {
    const title =
      issue.kind === "runFailed"
        ? "The run failed"
        : issue.kind === "runCancelled"
          ? "The run was cancelled"
          : "No result to inspect";
    if (flowName && onPath(pathname, flowPath(flowName))) {
      return runSteps("retry", title, "Select Execute to start a new run of this flow.");
    }
    return label
      ? [actionStep("retry:go", title, `Select ${label} to open the flow and start a new run.`)]
      : [];
  }
  if (issue) return [];

  if (onPath(pathname, executionHref(chipId, executionId))) {
    const tasks = progress.tasks;
    const counts =
      tasks && tasks.total > 0
        ? `${tasks.done} of ${tasks.total} tasks completed.`
        : "The run is starting.";
    return [
      {
        id: "progress:wait",
        kind: "wait",
        title: "Calibration running",
        description: `${counts} The guide continues when the run finishes.`,
        // The page header stays at the top, so the wait never scrolls the page.
        targets: [COACHMARK_TARGETS.executionHeader],
        dim: false,
        side: "bottom",
        align: "end",
      },
    ];
  }
  return label
    ? [actionStep("progress:go", "Follow the run", `Select ${label} to watch the tasks run.`)]
    : [];
}

/** Ids of the info steps that explain the recommended result's graph and fitted values. */
const RESULT_EXPLANATION_STEP_IDS = ["result:figure", "result:metrics"] as const;

/**
 * Explanations of the recommended result, shown wherever it is open: its page or the preview of
 * the run's graph. The result was read from the journey's run in this project, so a result of
 * another run or project with the same id is never explained.
 */
function resultExplanationSteps(taskId: string): CoachmarkStep[] {
  return [
    {
      id: "result:figure",
      kind: "info",
      title: "Read the graph",
      description: "The graph plots the measured data and the fitted curve.",
      targets: [COACHMARK_TARGETS.resultFigure(taskId)],
      optional: true,
      dim: true,
      side: "bottom",
      align: "start",
    },
    {
      id: "result:metrics",
      kind: "info",
      title: "Check the fitted values",
      description: "Output Parameters lists the values the fit produced for this qubit.",
      targets: [COACHMARK_TARGETS.resultMetrics(taskId)],
      optional: true,
      dim: true,
      side: "top",
      align: "start",
    },
  ];
}

function resultSteps(input: CoachmarkPlanInput, label: string | null): CoachmarkStep[] {
  const { state, progress, pathname } = input;
  const result = progress.recommendedResult;
  if (!result || !state.chipId || !state.executionId) return [];
  const steps: CoachmarkStep[] = resultExplanationSteps(result.taskId);
  const owner = result.qid.includes("-") ? `coupling ${result.qid}` : `qubit ${result.qid}`;
  const subject = result.qid ? `${result.name} node of ${owner}` : `${result.name} node`;
  if (onPath(pathname, executionHref(state.chipId, state.executionId))) {
    // The run's own page: wait for the task's node in the graph rather than sending the user
    // elsewhere, so the result opens in the normal preview.
    steps.push({
      id: "result:node",
      kind: "action",
      title: "Open a result",
      description: `Select the ${subject} to preview its graph and fitted values.`,
      targets: [COACHMARK_TARGETS.executionTask(result.taskId)],
      dim: true,
      side: "bottom",
      align: "center",
    });
    return steps;
  }
  if (label) {
    steps.push(
      actionStep(
        "result:go",
        "Open a result",
        `Select ${label} to see its graph and fitted values.`,
      ),
    );
  }
  return steps;
}

function resultCompletion(input: CoachmarkPlanInput): CoachmarkCompletion | undefined {
  const { state, progress } = input;
  const result = progress.recommendedResult;
  if (!result || !state.executionId) return undefined;
  return {
    stepIds: RESULT_EXPLANATION_STEP_IDS,
    event: { type: "resultInspected", executionId: state.executionId, taskId: result.taskId },
  };
}

function overviewSteps(input: CoachmarkPlanInput, label: string | null): CoachmarkStep[] {
  const { state, pathname } = input;
  if (!state.inspectedTaskId || pathname === "/chip") return [];
  // The result was explained in the step before; a preview left open is all that remains of it.
  const steps: CoachmarkStep[] = [
    {
      id: "overview:close-preview",
      kind: "action",
      title: "Close the preview",
      description: "Close the result preview to continue to the chip overview.",
      targets: [COACHMARK_TARGETS.closeResultPreview],
      optional: true,
      dim: true,
      side: "left",
      align: "start",
    },
  ];
  if (label) {
    steps.push(
      actionStep(
        "overview:go",
        "See the whole chip",
        `Select ${label} to see the calibrated values across ${state.chipId}.`,
      ),
    );
  }
  return steps;
}

function doneSteps(input: CoachmarkPlanInput): CoachmarkStep[] {
  const { state, pathname } = input;
  if (pathname !== "/chip" || !state.chipId) return [];
  return [
    {
      id: "done:overview",
      kind: "info",
      title: "Calibrated values on the chip",
      description: `Each tile shows the latest result of the selected task for a qubit of ${state.chipId}. Choose another task to compare.`,
      targets: [COACHMARK_TARGETS.chipOverview(state.chipId)],
      dim: true,
      side: "bottom",
      align: "start",
      nextLabel: "Done",
    },
  ];
}

/**
 * The coachmarks for the current page, or null when the guide has nothing to point at here:
 * no active journey, records still loading, or a load failure that only a reload fixes.
 *
 * The steps are ordered; the coachmark shows the first one that is not finished (see
 * `findCurrentCoachmark`). Hardware readiness always comes first on a hardware deployment.
 */
export function resolveCoachmarkPlan(input: CoachmarkPlanInput): CoachmarkPlan | null {
  const { state, progress, setup } = input;
  if (state.status !== "active" || progress.pending) return null;
  if (progress.issue?.kind === "loadFailed") return null;

  const plan = (steps: CoachmarkStep[], completion?: CoachmarkCompletion): CoachmarkPlan | null =>
    steps.length > 0
      ? { progressText: progressText(progress), steps, ...(completion ? { completion } : {}) }
      : null;

  if (
    journeyShowsHardwareReadiness(state, progress, setup) &&
    state.chipId &&
    state.hardwareConfirmedChipId !== state.chipId
  ) {
    return plan([
      {
        id: "hardware:confirm",
        kind: "action",
        title: "Confirm the hardware",
        description: `Check that the wiring and device parameters of ${state.chipId} match the connected hardware, then select the confirmation.`,
        targets: [COACHMARK_TARGETS.hardwareReadiness],
        dim: true,
        side: "bottom",
        align: "start",
      },
    ]);
  }

  const action = journeyNextAction(state, progress, setup);
  const label = action?.label ?? null;

  switch (progress.stage) {
    case "chip":
      return plan(chipSteps(input));
    case "flow":
      return plan(flowSteps(input, label));
    case "run":
      if (!state.flowName) return null;
      if (onPath(input.pathname, flowPath(state.flowName))) {
        return plan(
          runSteps("run", "Run the calibration", "Select Execute to review the run settings."),
        );
      }
      return label
        ? plan([
            actionStep("run:go", "Open your flow", `Select ${label} to open ${state.flowName}.`),
          ])
        : null;
    case "progress":
      return plan(progressSteps(input, label));
    case "results":
      return plan(resultSteps(input, label), resultCompletion(input));
    case "overview":
      return plan(overviewSteps(input, label));
    case "done":
      return plan(doneSteps(input));
  }
}
