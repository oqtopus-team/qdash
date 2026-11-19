import { describe, expect, it } from "vitest";

import type { ChipSetupMode } from "@/components/features/chip/chipSetupMode";
import {
  COACHMARK_TARGETS,
  resolveCoachmarkPlan,
  type CoachmarkPlanInput,
} from "@/components/features/first-calibration/coachmarkPlan";
import type { JourneyProgress } from "@/components/features/first-calibration/journeyProgress";
import type { JourneyState } from "@/lib/firstCalibrationJourney";

const FAKE: ChipSetupMode = {
  kind: "preset",
  backend: "fake",
  configAvailable: true,
  preset: {
    preset_id: "fake",
    n_qubits: 64,
    mux_count: 16,
    topology_id: "square-lattice-mux-64",
    workflow_template_id: "fake_calibration",
  } as never,
};
const HARDWARE: ChipSetupMode = { kind: "hardware" };

function state(overrides: Partial<JourneyState> = {}): JourneyState {
  return {
    version: 1,
    status: "active",
    chipId: null,
    flowName: null,
    executionId: null,
    hardwareConfirmedChipId: null,
    inspectedTaskId: null,
    chipOverviewSeen: false,
    startedAt: "2026-11-05T00:00:00.000Z",
    updatedAt: "2026-11-05T00:00:00.000Z",
    ...overrides,
  };
}

function progress(overrides: Partial<JourneyProgress> = {}): JourneyProgress {
  return {
    stage: "chip",
    pending: false,
    issue: null,
    tasks: null,
    recommendedResult: null,
    ...overrides,
  };
}

function plan(input: Partial<CoachmarkPlanInput>) {
  return resolveCoachmarkPlan({
    state: state(),
    progress: progress(),
    setup: FAKE,
    pathname: "/home",
    journeyParam: null,
    ...input,
  });
}

const ids = (input: Partial<CoachmarkPlanInput>) => plan(input)?.steps.map((step) => step.id);

const RESULT = { taskId: "task-1", name: "CheckT1", qid: "0", hasFigure: true };

describe("resolveCoachmarkPlan", () => {
  it("shows nothing for a paused journey or while records load", () => {
    expect(plan({ state: state({ status: "paused" }) })).toBeNull();
    expect(plan({ progress: progress({ pending: true }) })).toBeNull();
    expect(plan({ progress: progress({ issue: { kind: "loadFailed" } }) })).toBeNull();
  });

  it("walks the Create Chip dialog before the button that opens it", () => {
    const result = plan({ pathname: "/chip" });
    expect(result?.progressText).toBe("Step 1 of 5 · Prepare a chip");
    expect(result?.steps.map((step) => [step.id, step.kind, step.targets[0]])).toEqual([
      ["chip:name", "action", COACHMARK_TARGETS.chipIdInput],
      ["chip:create", "action", COACHMARK_TARGETS.createChipSubmit],
      ["chip:open", "action", COACHMARK_TARGETS.createChip],
    ]);
    // Steps inside the dialog never dim the page over the dialog.
    expect(result?.steps.slice(0, 2).every((step) => !step.dim && step.optional)).toBe(true);
    expect(result?.steps[0].doneWhenFilled).toBe(true);
  });

  it("explains the Qubex configuration in the Create Chip dialog on hardware only", () => {
    const result = plan({ pathname: "/chip", setup: HARDWARE });
    expect(result?.steps.map((step) => [step.id, step.kind, step.targets[0]])).toEqual([
      ["chip:name", "action", COACHMARK_TARGETS.chipIdInput],
      ["chip:config", "info", COACHMARK_TARGETS.chipConfig],
      ["chip:create", "action", COACHMARK_TARGETS.createChipSubmit],
      ["chip:open", "action", COACHMARK_TARGETS.createChip],
    ]);
    expect(result?.steps[1].optional).toBe(true);
    expect(result?.steps[1].dim).toBe(false);
  });

  it("points at the Home card on Home and at the banner elsewhere", () => {
    expect(ids({ pathname: "/home" })).toEqual(["chip:choose"]);
    expect(ids({ pathname: "/metrics" })).toEqual(["chip:go"]);
    expect(plan({ pathname: "/metrics" })?.steps[0].targets).toEqual([
      COACHMARK_TARGETS.journeyAction,
    ]);
  });

  it("asks for the hardware confirmation before anything else on hardware", () => {
    const flow = {
      state: state({ chipId: "chip-a" }),
      progress: progress({ stage: "flow" }),
    };
    expect(ids({ ...flow, setup: HARDWARE, pathname: "/home" })).toEqual(["hardware:confirm"]);
    expect(ids({ ...flow, setup: HARDWARE, pathname: "/chip" })).toEqual(["hardware:confirm"]);
    const confirmed = state({
      chipId: "chip-a",
      hardwareConfirmedChipId: "chip-a",
    });
    expect(
      ids({
        state: confirmed,
        progress: progress({ stage: "flow" }),
        setup: HARDWARE,
      }),
    ).toEqual(["flow:go"]);
  });

  it("guides the New Flow editor only when the guide opened it", () => {
    const flow = {
      state: state({ chipId: "chip-a" }),
      progress: progress({ stage: "flow" }),
    };
    expect(plan({ ...flow, pathname: "/workflow/new", journeyParam: null })).toBeNull();
    const steps = plan({
      ...flow,
      pathname: "/workflow/new",
      journeyParam: "first-calibration",
    })?.steps;
    expect(steps?.map((step) => [step.id, step.kind])).toEqual([
      ["flow:review", "info"],
      ["flow:name", "info"],
      ["flow:save", "action"],
    ]);
    // The review waits for the summary of the loaded code instead of skipping it.
    expect(steps?.[0].targets).toEqual([
      COACHMARK_TARGETS.flowSummaryReady,
      COACHMARK_TARGETS.flowTemplateReady,
    ]);
    expect(steps?.[0].optional).toBeFalsy();
    // A first run may use the template unchanged; nothing asks the user to edit it.
    expect(steps?.[0].description).toContain("unchanged");
  });

  it("asks to run the saved flow on its page, with the confirmation first", () => {
    const run = {
      state: state({ chipId: "chip-a", flowName: "first_calibration" }),
      progress: progress({ stage: "run" }),
    };
    expect(ids({ ...run, pathname: "/workflow/first_calibration" })).toEqual([
      "run:confirm",
      "run:execute",
    ]);
    const runSteps = plan({
      ...run,
      pathname: "/workflow/first_calibration",
    })?.steps;
    expect(runSteps?.every((step) => step.kind === "action")).toBe(true);
    // Execute is only pointed at once it is enabled: never while availability is pending.
    expect(runSteps?.[1].targets).toEqual([COACHMARK_TARGETS.flowExecuteReady]);
    expect(runSteps?.[1].optional).toBeFalsy();
    expect(ids({ ...run, pathname: "/workflow/other_flow" })).toEqual(["run:go"]);
  });

  it("waits without dimming on the running execution and links to it elsewhere", () => {
    const running = {
      state: state({
        chipId: "chip-a",
        flowName: "first_calibration",
        executionId: "exec-1",
      }),
      progress: progress({
        stage: "progress",
        tasks: { done: 3, failed: 0, total: 12, current: "CheckRabi" },
      }),
    };
    const wait = plan({
      ...running,
      pathname: "/execution/chip-a/exec-1",
    })?.steps;
    expect(wait).toHaveLength(1);
    expect(wait?.[0]).toMatchObject({ kind: "wait", dim: false });
    expect(wait?.[0].description).toContain("3 of 12 tasks completed.");
    expect(ids({ ...running, pathname: "/workflow/first_calibration" })).toEqual(["progress:go"]);
  });

  it("offers a new run of the same flow after a failure", () => {
    const failed = {
      state: state({
        chipId: "chip-a",
        flowName: "first_calibration",
        executionId: "exec-1",
      }),
      progress: progress({
        stage: "progress",
        issue: { kind: "runFailed", message: "boom" },
      }),
    };
    const onFlow = plan({ ...failed, pathname: "/workflow/first_calibration" });
    expect(onFlow?.steps.map((step) => step.id)).toEqual(["retry:confirm", "retry:execute"]);
    expect(onFlow?.steps[1].title).toBe("The run failed");
    const elsewhere = plan({ ...failed, pathname: "/execution/chip-a/exec-1" });
    expect(elsewhere?.steps.map((step) => step.id)).toEqual(["retry:go"]);
    expect(elsewhere?.steps[0].description).toContain("Run again");
  });

  it("explains the recommended result in the result step, then opens its node or links to it", () => {
    const results = {
      state: state({
        chipId: "chip-a",
        flowName: "first_calibration",
        executionId: "exec-1",
      }),
      progress: progress({ stage: "results", recommendedResult: RESULT }),
    };
    const onRun = plan({
      ...results,
      pathname: "/execution/chip-a/exec-1",
    });
    expect(onRun?.progressText).toBe("Step 4 of 5 · Inspect a result");
    const steps = onRun?.steps;
    expect(steps?.map((step) => [step.id, step.kind, step.optional ?? false])).toEqual([
      ["result:figure", "info", true],
      ["result:metrics", "info", true],
      ["result:node", "action", false],
    ]);
    expect(steps?.[0].targets).toEqual([COACHMARK_TARGETS.resultFigure("task-1")]);
    expect(steps?.[1].targets).toEqual([COACHMARK_TARGETS.resultMetrics("task-1")]);
    expect(steps?.[2].targets).toEqual(['.react-flow__node[data-id="task-1"]']);
    expect(steps?.[2].description).toContain("CheckT1 node of qubit 0");
    // The journey moves on once those explanations are over, with the recommended result.
    expect(onRun?.completion).toEqual({
      stepIds: ["result:figure", "result:metrics"],
      event: { type: "resultInspected", executionId: "exec-1", taskId: "task-1" },
    });
    expect(ids({ ...results, pathname: "/home" })).toEqual([
      "result:figure",
      "result:metrics",
      "result:go",
    ]);
  });

  it("leads from the inspected result to the chip overview without explaining it again", () => {
    const overview = {
      state: state({
        chipId: "chip-a",
        flowName: "first_calibration",
        executionId: "exec-1",
        inspectedTaskId: "task-1",
      }),
      progress: progress({ stage: "overview", recommendedResult: RESULT }),
    };
    const result = plan({
      ...overview,
      pathname: "/task-results/task-1",
    });
    expect(result?.progressText).toBe("Step 5 of 5 · Chip overview");
    expect(result?.completion).toBeUndefined();
    expect(result?.steps.map((step) => [step.id, step.kind])).toEqual([
      ["overview:close-preview", "action"],
      ["overview:go", "action"],
    ]);
    expect(plan({ ...overview, pathname: "/chip" })).toBeNull();
  });

  it("closes with the chip overview on the Chip page only", () => {
    const done = {
      state: state({
        chipId: "chip-a",
        flowName: "first_calibration",
        executionId: "exec-1",
        inspectedTaskId: "task-1",
        chipOverviewSeen: true,
      }),
      progress: progress({ stage: "done", recommendedResult: RESULT }),
    };
    const result = plan({ ...done, pathname: "/chip" });
    expect(result?.progressText).toBe("Complete");
    expect(result?.steps[0]).toMatchObject({
      id: "done:overview",
      kind: "info",
      nextLabel: "Done",
    });
    expect(plan({ ...done, pathname: "/home" })).toBeNull();
  });

  it("quotes ids in selectors so a record cannot break out of the attribute", () => {
    expect(COACHMARK_TARGETS.executionTask('a"]b')).toBe('.react-flow__node[data-id="a\\"]b"]');
  });
});
