import { describe, expect, it } from "vitest";

import { selectUpcomingRuns, sortSchedulesByNextRun } from "@/lib/utils/flowSchedules";

/** Sorts the schedules and returns their flow names in the resulting order. */
function sortedFlowNames(schedules: Parameters<typeof sortSchedulesByNextRun>[0]): string[] {
  return sortSchedulesByNextRun(schedules).map((schedule) => schedule.flow_name);
}

describe("sortSchedulesByNextRun", () => {
  it("sorts schedules by next_run ascending", () => {
    const schedules = [
      { flow_name: "flow-b", next_run: "2026-06-01T00:00:00Z" },
      { flow_name: "flow-a", next_run: "2026-01-01T00:00:00Z" },
      { flow_name: "flow-c", next_run: "2026-03-01T00:00:00Z" },
    ] as const;

    expect(sortedFlowNames(schedules)).toEqual(["flow-a", "flow-c", "flow-b"]);
  });

  it("sorts schedules with no next_run last", () => {
    const schedules = [
      { flow_name: "flow-no-run", next_run: null },
      { flow_name: "flow-b", next_run: "2026-06-01T00:00:00Z" },
      { flow_name: "flow-a", next_run: "2026-01-01T00:00:00Z" },
    ] as const;

    expect(sortedFlowNames(schedules)).toEqual(["flow-a", "flow-b", "flow-no-run"]);
  });

  it("breaks ties by flow_name when next_run is equal", () => {
    const schedules = [
      { flow_name: "flow-c", next_run: "2026-01-01T00:00:00Z" },
      { flow_name: "flow-a", next_run: "2026-01-01T00:00:00Z" },
      { flow_name: "flow-b", next_run: "2026-01-01T00:00:00Z" },
    ] as const;

    expect(sortedFlowNames(schedules)).toEqual(["flow-a", "flow-b", "flow-c"]);
  });

  it("breaks ties by flow_name when next_run is missing for all", () => {
    const schedules = [
      { flow_name: "flow-c", next_run: null },
      { flow_name: "flow-a", next_run: null },
      { flow_name: "flow-b", next_run: null },
    ] as const;

    expect(sortedFlowNames(schedules)).toEqual(["flow-a", "flow-b", "flow-c"]);
  });

  it("does not mutate the input array", () => {
    const schedules = [
      { flow_name: "flow-b", next_run: "2026-06-01T00:00:00Z" },
      { flow_name: "flow-a", next_run: "2026-01-01T00:00:00Z" },
    ] as const;
    const original = [...schedules];

    sortSchedulesByNextRun(schedules);

    expect(schedules).toEqual(original);
  });
});

describe("selectUpcomingRuns", () => {
  const now = new Date("2026-01-01T00:00:00Z").getTime();

  it("keeps active future runs soonest first up to the limit", () => {
    const schedules = [
      { flow_name: "flow-c", next_run: "2026-01-03T00:00:00Z", active: true },
      { flow_name: "flow-a", next_run: "2026-01-01T01:00:00Z", active: true },
      { flow_name: "flow-b", next_run: "2026-01-02T00:00:00Z", active: true },
    ];

    expect(selectUpcomingRuns(schedules, 2, now).map((s) => s.flow_name)).toEqual([
      "flow-a",
      "flow-b",
    ]);
  });

  it("drops paused, past, and run-less entries", () => {
    const schedules = [
      { flow_name: "paused", next_run: "2026-01-02T00:00:00Z", active: false },
      { flow_name: "past", next_run: "2025-12-31T00:00:00Z", active: true },
      { flow_name: "definition", next_run: null, active: true },
      { flow_name: "upcoming", next_run: "2026-01-02T00:00:00Z", active: true },
    ];

    expect(selectUpcomingRuns(schedules, 5, now).map((s) => s.flow_name)).toEqual(["upcoming"]);
  });
});
