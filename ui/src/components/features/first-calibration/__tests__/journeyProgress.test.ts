import { describe, expect, it } from "vitest";

import type { ChipSetupMode } from "@/components/features/chip/chipSetupMode";
import {
  deriveJourneyProgress,
  journeyNewFlowHref,
  journeyNextAction,
  journeyShowsHardwareReadiness,
  journeyStepStates,
  type JourneyServerState,
} from "@/components/features/first-calibration/journeyProgress";
import type { JourneyState } from "@/lib/firstCalibrationJourney";
import type { ExecutionResponseDetail, Task } from "@/schemas";

const FAKE: ChipSetupMode = {
  kind: "fake",
  configAvailable: true,
  preset: {
    preset_id: "fake",
    name: "Virtual fake device",
    description: "",
    topology_id: "square-lattice-mux-64",
    n_qubits: 64,
    mux_count: 16,
    workflow_template_id: "fake_calibration",
  },
};
const HARDWARE: ChipSetupMode = { kind: "hardware" };

const state: JourneyState = {
  version: 1,
  status: "active",
  chipId: "chip-a",
  flowName: "first_calibration",
  executionId: "20261105-001",
  hardwareConfirmedChipId: null,
  inspectedTaskId: null,
  chipOverviewSeen: false,
  startedAt: "2026-11-05T00:00:00.000Z",
  updatedAt: "2026-11-05T00:00:00.000Z",
};

function execution(status: string, tasks: Partial<Task>[], message = ""): ExecutionResponseDetail {
  return {
    name: "run",
    status,
    message,
    chip_id: "chip-a",
    task: tasks as Task[],
    note: {},
  };
}

function server(overrides: Partial<JourneyServerState> = {}): JourneyServerState {
  return {
    setup: FAKE,
    chipIds: new Set(["chip-a"]),
    chipsFailed: false,
    flow: { status: "ready", data: { chipId: "chip-a" } },
    execution: { status: "ready", data: execution("running", []) },
    ...overrides,
  };
}

describe("deriveJourneyProgress", () => {
  it("waits for the server instead of assuming a stage is done", () => {
    const progress = deriveJourneyProgress(state, server({ chipIds: null }));
    expect(progress).toMatchObject({
      stage: "chip",
      pending: true,
      issue: null,
    });
    expect(journeyNextAction(state, { ...progress, pending: true }, FAKE)).not.toBeNull();
  });

  it("sends a journey without a chip to chip creation", () => {
    const progress = deriveJourneyProgress(
      { ...state, chipId: null, flowName: null, executionId: null },
      server(),
    );
    expect(progress.stage).toBe("chip");
    expect(journeyNextAction(state, progress, FAKE)?.href).toBe("/chip?journey=create-chip");
  });

  it("opens the fake calibration template for the journey's chip", () => {
    const progress = deriveJourneyProgress(
      { ...state, flowName: null, executionId: null },
      server(),
    );
    expect(progress.stage).toBe("flow");
    expect(journeyNextAction(state, progress, FAKE)?.href).toBe(
      "/workflow/new?backend=fake&template=fake_calibration&chip_id=chip-a&journey=first-calibration",
    );
  });

  it("asks to prepare the flow again when it was deleted", () => {
    const progress = deriveJourneyProgress(state, server({ flow: { status: "missing" } }));
    expect(progress).toMatchObject({
      stage: "flow",
      issue: { kind: "flowMissing", flowName: "first_calibration" },
    });
    expect(journeyStepStates(progress).calibration).toBe("attention");
  });

  it("notices a flow whose chip no longer matches", () => {
    const progress = deriveJourneyProgress(
      state,
      server({ flow: { status: "ready", data: { chipId: "chip-b" } } }),
    );
    expect(progress.issue).toEqual({
      kind: "flowChipChanged",
      flowName: "first_calibration",
      flowChipId: "chip-b",
    });
  });

  it("does not offer the hardware run until the user confirms the configuration", () => {
    const beforeRun = { ...state, executionId: null };
    const progress = deriveJourneyProgress(beforeRun, server({ setup: HARDWARE }));
    expect(progress.stage).toBe("run");
    expect(journeyNextAction(beforeRun, progress, HARDWARE)).toBeNull();
    expect(
      journeyNextAction({ ...beforeRun, hardwareConfirmedChipId: "chip-a" }, progress, HARDWARE)
        ?.href,
    ).toBe("/workflow/first_calibration");
  });

  it("follows a running execution with its task counts", () => {
    const progress = deriveJourneyProgress(
      state,
      server({
        execution: {
          status: "ready",
          data: execution("running", [
            { name: "CheckT1", status: "completed", task_id: "t1" },
            { name: "CheckT2Echo", status: "running", task_id: "t2" },
          ]),
        },
      }),
    );
    expect(progress).toMatchObject({
      stage: "progress",
      issue: null,
      tasks: { done: 1, total: 2, current: "CheckT2Echo" },
    });
    expect(journeyNextAction(state, progress, FAKE)?.href).toBe("/execution/chip-a/20261105-001");
  });

  it.each([
    ["failed", { kind: "runFailed", message: "Box unreachable" }],
    ["cancelled", { kind: "runCancelled" }],
  ])("keeps a %s run on the progress step with a retry", (status, issue) => {
    const progress = deriveJourneyProgress(
      state,
      server({
        execution: {
          status: "ready",
          data: execution(
            status,
            [{ name: "CheckT1", status: "completed", task_id: "t1" }],
            "Box unreachable",
          ),
        },
      }),
    );
    expect(progress.stage).toBe("progress");
    expect(progress.issue).toEqual(issue);
    expect(progress.recommendedResult).toBeNull();
    expect(journeyNextAction(state, progress, FAKE)).toEqual({
      label: "Run again",
      href: "/workflow/first_calibration",
    });
  });

  it("does not reach the result step without a successful task result", () => {
    const progress = deriveJourneyProgress(
      state,
      server({
        execution: {
          status: "ready",
          data: execution("completed", [{ name: "CheckT1", status: "failed", task_id: "t1" }]),
        },
      }),
    );
    expect(progress).toMatchObject({
      stage: "progress",
      issue: { kind: "noResults" },
    });
  });

  it("recommends the CheckT1 result with a figure once the run succeeds", () => {
    const progress = deriveJourneyProgress(
      state,
      server({
        execution: {
          status: "ready",
          data: execution("completed", [
            {
              name: "CheckRabi",
              status: "completed",
              task_id: "rabi",
              figure_path: ["rabi.png"],
            },
            {
              name: "CheckT1",
              status: "completed",
              task_id: "t1-nofig",
              figure_path: [],
            },
            {
              name: "CheckT1",
              status: "completed",
              task_id: "t1",
              qid: "0",
              figure_path: ["t1.png"],
            },
          ]),
        },
      }),
    );
    expect(progress.stage).toBe("results");
    expect(progress.recommendedResult).toMatchObject({
      taskId: "t1",
      name: "CheckT1",
      hasFigure: true,
    });
    expect(journeyNextAction(state, progress, FAKE)?.href).toBe("/task-results/t1");
  });

  it("falls back to a completed result without figures", () => {
    const progress = deriveJourneyProgress(
      state,
      server({
        execution: {
          status: "ready",
          data: execution("completed", [
            { name: "CheckRabi", status: "completed", task_id: "rabi" },
          ]),
        },
      }),
    );
    expect(progress.recommendedResult).toMatchObject({
      taskId: "rabi",
      hasFigure: false,
    });
  });

  it("needs the result inspection and the chip overview to finish", () => {
    const succeeded = server({
      execution: {
        status: "ready",
        data: execution("completed", [{ name: "CheckT1", status: "completed", task_id: "t1" }]),
      },
    });
    expect(deriveJourneyProgress({ ...state, inspectedTaskId: "t1" }, succeeded).stage).toBe(
      "overview",
    );
    const done = deriveJourneyProgress(
      { ...state, inspectedTaskId: "t1", chipOverviewSeen: true },
      succeeded,
    );
    expect(done.stage).toBe("done");
    expect(Object.values(journeyStepStates(done))).toEqual(Array(5).fill("done"));
  });

  it("asks for a new run when the followed execution is gone", () => {
    const progress = deriveJourneyProgress(state, server({ execution: { status: "missing" } }));
    expect(progress).toMatchObject({
      stage: "run",
      issue: { kind: "executionMissing" },
    });
  });

  it("asks for hardware readiness before it links to the editor", () => {
    const chosen = { ...state, flowName: null, executionId: null };
    const progress = deriveJourneyProgress(chosen, server({ setup: HARDWARE }));
    expect(progress.stage).toBe("flow");
    expect(journeyShowsHardwareReadiness(chosen, progress, HARDWARE)).toBe(true);
    expect(journeyNextAction(chosen, progress, HARDWARE)).toBeNull();
    expect(
      journeyNextAction({ ...chosen, hardwareConfirmedChipId: "chip-a" }, progress, HARDWARE)?.href,
    ).toBe("/workflow/new?chip_id=chip-a&journey=first-calibration");
    expect(journeyShowsHardwareReadiness(chosen, progress, FAKE)).toBe(false);
  });

  it.each([
    ["an unknown deployment", { kind: "pending", failed: false } as ChipSetupMode],
    ["a failed deployment check", { kind: "pending", failed: true } as ChipSetupMode],
    [
      "a fake deployment without its preset",
      { kind: "fake", preset: null, configAvailable: true } as ChipSetupMode,
    ],
  ])("never guesses the editor path for %s", (_label, setup) => {
    const chosen = { ...state, flowName: null, executionId: null };
    const progress = deriveJourneyProgress(chosen, server({ setup }));
    expect(journeyNewFlowHref(setup, "chip-a")).toBeNull();
    expect(journeyNextAction(chosen, progress, setup)).toBeNull();
  });
});
