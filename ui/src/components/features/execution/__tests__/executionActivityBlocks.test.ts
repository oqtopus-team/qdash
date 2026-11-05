import { describe, expect, it } from "vitest";

import {
  activityBlockScale,
  activityBucketTitle,
  toActivityColumn,
} from "@/components/features/execution/executionActivityBlocks";
import type { ExecutionActivityDay } from "@/schemas";

function bucket(
  date: string,
  start: string,
  end: string,
  counts: Partial<Record<string, number>> = {},
): ExecutionActivityDay {
  const merged = { completed: 0, failed: 0, running: 0, scheduled: 0, cancelled: 0, other: 0 };
  Object.assign(merged, counts);
  return {
    date,
    start,
    end,
    ...merged,
    total: Object.values(merged).reduce((a, b) => a + b, 0),
  };
}

describe("activityBlockScale", () => {
  it("sizes blocks by each bucket's total, not by each status rounded up", () => {
    // 20 executions over six statuses fit 10 blocks of 2; rounding each status up would need 13.
    const busy = bucket("2026-11-04", "", "", {
      completed: 5,
      failed: 5,
      running: 3,
      scheduled: 3,
      cancelled: 3,
      other: 1,
    });

    expect(activityBlockScale([busy], 10)).toBe(2);
    expect(activityBlockScale([busy], 20)).toBe(1);
    expect(activityBlockScale([busy], 3)).toBe(10);
  });
});

describe("toActivityColumn", () => {
  it("shares blocks between statuses so the column is exactly total / scale tall", () => {
    const column = toActivityColumn(
      bucket("2026-11-04", "", "", { completed: 3, failed: 4, other: 1 }),
      5,
    );

    expect(
      column.blocks.map((block) =>
        block.segments.map((segment) => [segment.status, segment.executions, segment.partial]),
      ),
    ).toEqual([
      [
        ["completed", 3, true],
        ["failed", 2, true],
      ],
      [
        ["failed", 2, true],
        ["other", 1, true],
      ],
    ]);
    expect(column.blocks.map((block) => block.executions)).toEqual([5, 3]);
  });

  it("labels 6-hour buckets with local hours in the zone they were counted in", () => {
    // New York leaves DST on 2026-11-01, so the day's first 6-hour bucket lasts 7 hours.
    const first = toActivityColumn(
      bucket("2026-11-01", "2026-11-01T04:00:00Z", "2026-11-01T11:00:00Z"),
      1,
      "America/New_York",
    );
    const last = toActivityColumn(
      bucket("2026-11-01", "2026-11-01T23:00:00Z", "2026-11-02T05:00:00Z"),
      1,
      "America/New_York",
    );

    expect(first.hours).toBe("00:00–06:00");
    expect(last.hours).toBe("18:00–24:00");
    expect(activityBucketTitle(first, "6h")).toBe("Sun, Nov 1, 2026, 00:00–06:00");
    expect(activityBucketTitle(first, "day")).toBe("Sun, Nov 1, 2026");
  });
});
