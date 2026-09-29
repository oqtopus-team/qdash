import { describe, expect, it } from "vitest";

import { sortSchedulesByNextRun } from "@/lib/utils/flowSchedules";

describe("sortSchedulesByNextRun", () => {
  it("sorts schedules by next_run ascending", () => {
    const schedules = [
      { flow_name: "flow-b", next_run: "2026-06-01T00:00:00Z" },
      { flow_name: "flow-a", next_run: "2026-01-01T00:00:00Z" },
      { flow_name: "flow-c", next_run: "2026-03-01T00:00:00Z" },
    ] as const;

    expect(sortSchedulesByNextRun(schedules).map((schedule) => schedule.flow_name)).toEqual([
      "flow-a",
      "flow-c",
      "flow-b",
    ]);
  });

  it("sorts schedules with no next_run last", () => {
    const schedules = [
      { flow_name: "flow-no-run", next_run: null },
      { flow_name: "flow-b", next_run: "2026-06-01T00:00:00Z" },
      { flow_name: "flow-a", next_run: "2026-01-01T00:00:00Z" },
    ] as const;

    expect(sortSchedulesByNextRun(schedules).map((schedule) => schedule.flow_name)).toEqual([
      "flow-a",
      "flow-b",
      "flow-no-run",
    ]);
  });

  it("breaks ties by flow_name when next_run is equal", () => {
    const schedules = [
      { flow_name: "flow-c", next_run: "2026-01-01T00:00:00Z" },
      { flow_name: "flow-a", next_run: "2026-01-01T00:00:00Z" },
      { flow_name: "flow-b", next_run: "2026-01-01T00:00:00Z" },
    ] as const;

    expect(sortSchedulesByNextRun(schedules).map((schedule) => schedule.flow_name)).toEqual([
      "flow-a",
      "flow-b",
      "flow-c",
    ]);
  });

  it("breaks ties by flow_name when next_run is missing for all", () => {
    const schedules = [
      { flow_name: "flow-c", next_run: null },
      { flow_name: "flow-a", next_run: null },
      { flow_name: "flow-b", next_run: null },
    ] as const;

    expect(sortSchedulesByNextRun(schedules).map((schedule) => schedule.flow_name)).toEqual([
      "flow-a",
      "flow-b",
      "flow-c",
    ]);
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
