import { describe, expect, it } from "vitest";

import {
  applyJourneyEvent,
  journeyStorageKey,
  parseJourneyState,
  suggestJourneyFlowName,
  type JourneyState,
} from "@/lib/firstCalibrationJourney";

const NOW = "2026-11-05T00:00:00.000Z";
const LATER = "2026-11-05T01:00:00.000Z";

function started(chipId: string | null = null): JourneyState {
  const state = applyJourneyEvent(null, { type: "start", chipId, now: NOW });
  if (!state) throw new Error("start must create a journey");
  return state;
}

function ranOnce(): JourneyState {
  let state: JourneyState | null = started("chip-a");
  state = applyJourneyEvent(state, {
    type: "flowSaved",
    flowName: "first_calibration",
    chipId: "chip-a",
    now: NOW,
  });
  state = applyJourneyEvent(state, {
    type: "runStarted",
    flowName: "first_calibration",
    chipId: "chip-a",
    executionId: "20261105-001",
    now: NOW,
  });
  if (!state) throw new Error("journey expected");
  return state;
}

describe("journeyStorageKey", () => {
  it("separates users and projects, including ids that contain the separator", () => {
    const keys = new Set([
      journeyStorageKey("alice", "project-1"),
      journeyStorageKey("alice", "project-2"),
      journeyStorageKey("bob", "project-1"),
      journeyStorageKey("alice:project-1", "x"),
    ]);
    expect(keys.size).toBe(4);
  });
});

describe("parseJourneyState", () => {
  it("round-trips a stored journey", () => {
    const state = ranOnce();
    expect(parseJourneyState(JSON.stringify(state))).toEqual(state);
  });

  it.each([
    ["no record", null],
    ["broken JSON", "{not json"],
    ["an array", "[]"],
    ["another version", JSON.stringify({ ...started(), version: 2 })],
    ["an unknown status", JSON.stringify({ ...started(), status: "completed" })],
    ["an invalid flow name", JSON.stringify({ ...ranOnce(), flowName: "../evil" })],
    ["a numeric chip id", JSON.stringify({ ...started(), chipId: 42 })],
    ["an execution without a flow", JSON.stringify({ ...ranOnce(), flowName: null })],
    [
      "an overview without an inspected result",
      JSON.stringify({ ...ranOnce(), chipOverviewSeen: true }),
    ],
  ])("treats %s as no journey", (_label, raw) => {
    expect(parseJourneyState(raw)).toBeNull();
  });
});

describe("applyJourneyEvent", () => {
  it("ignores events before a journey starts", () => {
    expect(
      applyJourneyEvent(null, { type: "chipSelected", chipId: "chip-a", now: NOW }),
    ).toBeNull();
  });

  it("follows only the journey's own chip, flow and execution", () => {
    const state = ranOnce();

    expect(
      applyJourneyEvent(state, {
        type: "flowSaved",
        flowName: "other",
        chipId: "chip-b",
        now: LATER,
      }),
    ).toBe(state);
    expect(
      applyJourneyEvent(state, {
        type: "runStarted",
        flowName: "routine_flow",
        chipId: "chip-a",
        executionId: "20261105-099",
        now: LATER,
      }),
    ).toBe(state);
    expect(
      applyJourneyEvent(state, {
        type: "resultInspected",
        executionId: "20261105-099",
        taskId: "task-x",
        now: LATER,
      }),
    ).toBe(state);
  });

  it("follows a retry of the same flow and forgets the earlier inspection", () => {
    let state: JourneyState | null = applyJourneyEvent(ranOnce(), {
      type: "resultInspected",
      executionId: "20261105-001",
      taskId: "task-1",
      now: LATER,
    });
    expect(state?.inspectedTaskId).toBe("task-1");

    state = applyJourneyEvent(state, {
      type: "runStarted",
      flowName: "first_calibration",
      chipId: "chip-a",
      executionId: "20261105-002",
      now: LATER,
    });
    expect(state).toMatchObject({ executionId: "20261105-002", inspectedTaskId: null });
  });

  it("drops the later stages when another chip is chosen", () => {
    const state = applyJourneyEvent(ranOnce(), {
      type: "chipSelected",
      chipId: "chip-b",
      now: LATER,
    });
    expect(state).toMatchObject({ chipId: "chip-b", flowName: null, executionId: null });
  });

  it("counts the chip overview only after a result was inspected", () => {
    const beforeInspection = ranOnce();
    expect(
      applyJourneyEvent(beforeInspection, {
        type: "chipOverviewSeen",
        chipId: "chip-a",
        now: LATER,
      }),
    ).toBe(beforeInspection);

    const inspected = applyJourneyEvent(beforeInspection, {
      type: "resultInspected",
      executionId: "20261105-001",
      taskId: "task-1",
      now: LATER,
    });
    expect(
      applyJourneyEvent(inspected, { type: "chipOverviewSeen", chipId: "chip-a", now: LATER })
        ?.chipOverviewSeen,
    ).toBe(true);
  });

  it("keeps the hardware confirmation tied to the chip it was given for", () => {
    const state = applyJourneyEvent(started("chip-a"), {
      type: "hardwareConfirmed",
      chipId: "chip-a",
      confirmed: true,
      now: LATER,
    });
    expect(state?.hardwareConfirmedChipId).toBe("chip-a");
    expect(
      applyJourneyEvent(state, {
        type: "hardwareConfirmed",
        chipId: "chip-b",
        confirmed: true,
        now: LATER,
      }),
    ).toBe(state);
  });
});

describe("suggestJourneyFlowName", () => {
  it("never suggests the name of an existing flow", () => {
    expect(suggestJourneyFlowName([])).toBe("first_calibration");
    expect(suggestJourneyFlowName(["first_calibration", "first_calibration_2"])).toBe(
      "first_calibration_3",
    );
  });
});
