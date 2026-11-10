import { isCompactActivityDate } from "@/lib/utils/datetime";
import { afterEach, describe, expect, it } from "vitest";

import {
  activityStatusTotals,
  activityWindowSummary,
  longActivityDate,
} from "@/components/features/execution/executionActivityBlocks";
import {
  ACTIVITY_LEVEL_CLASSES,
  activityLevel,
  buildActivityHeatmap,
  formatCompactActivityDate,
} from "@/components/features/execution/executionActivityLevels";

const ZERO = { completed: 0, failed: 0, running: 0, scheduled: 0, cancelled: 0, other: 0 };

function bucket(date: string, counts: Partial<Record<string, number>> = {}) {
  const merged = { ...ZERO, ...counts };
  return {
    date,
    start: `${date}T00:00:00Z`,
    end: `${date}T00:00:00Z`,
    ...merged,
    total: Object.values(merged).reduce((a, b) => a + b, 0),
  };
}

/** `length` consecutive days ending on `end`, YYYY-MM-DD, with the given counts. */
function window(
  end: string,
  length: number,
  counts: Record<string, Partial<Record<string, number>>> = {},
) {
  const last = Date.parse(`${end}T00:00:00Z`);
  return Array.from({ length }, (_, offset) => {
    const date = new Date(last - (length - 1 - offset) * 86_400_000).toISOString().slice(0, 10);
    return bucket(date, counts[date]);
  });
}

const originalTz = process.env.TZ;
afterEach(() => {
  process.env.TZ = originalTz;
});

describe("activityLevel", () => {
  it("maps counts to fixed buckets 0, 1–4, 5–19, 20–99 and 100+", () => {
    const levels = [0, 1, 4, 5, 19, 20, 99, 100, 5000].map(activityLevel);
    expect(levels).toEqual([0, 1, 1, 2, 2, 3, 3, 4, 4]);
  });

  it("gives the same count the same level and color whatever the window holds", () => {
    const quiet = buildActivityHeatmap(window("2026-11-02", 30, { "2026-11-01": { failed: 7 } }));
    const busy = buildActivityHeatmap(
      window("2026-11-02", 365, {
        "2026-11-01": { completed: 7 },
        "2026-06-01": { completed: 900 },
      }),
    );
    const quietDay = quiet.days.find((day) => day.date === "2026-11-01")!;
    const busyDay = busy.days.find((day) => day.date === "2026-11-01")!;

    expect(quietDay.level).toBe(2);
    expect(busyDay.level).toBe(quietDay.level);
    expect(ACTIVITY_LEVEL_CLASSES[busyDay.level]).toBe(ACTIVITY_LEVEL_CLASSES[quietDay.level]);
  });
});

describe("buildActivityHeatmap", () => {
  it("lays days out in Sunday-first week columns, padding days outside the window", () => {
    // 2026-10-28 is a Wednesday and 2026-11-02 a Monday.
    const { days, weeks } = buildActivityHeatmap(window("2026-11-02", 6));

    expect(days).toHaveLength(6);
    expect(weeks).toHaveLength(2);
    expect(weeks[0].map((day) => day?.date ?? null)).toEqual([
      null,
      null,
      null,
      "2026-10-28",
      "2026-10-29",
      "2026-10-30",
      "2026-10-31",
    ]);
    expect(weeks[1].map((day) => day?.date ?? null)).toEqual([
      "2026-11-01",
      "2026-11-02",
      null,
      null,
      null,
      null,
      null,
    ]);
  });

  it("keeps empty days as zero-count, level-0 cells with exact status counts", () => {
    const { days } = buildActivityHeatmap(
      window("2026-11-02", 3, { "2026-11-02": { completed: 2, other: 1 } }),
    );

    expect(days.map((day) => [day.compact, day.total, day.level])).toEqual([
      ["20261031", 0, 0],
      ["20261101", 0, 0],
      ["20261102", 3, 1],
    ]);
    expect(days[2].counts.filter((item) => item.count > 0)).toEqual([
      { key: "completed", label: "Completed", count: 2 },
      { key: "other", label: "Other", count: 1 },
    ]);
  });

  it("reads server calendar dates without shifting them into the browser's zone", () => {
    process.env.TZ = "Pacific/Honolulu";
    const west = buildActivityHeatmap(window("2026-11-02", 3));
    process.env.TZ = "Asia/Tokyo";
    const east = buildActivityHeatmap(window("2026-11-02", 3));

    for (const layout of [west, east]) {
      expect(layout.days.map((day) => [day.date, day.weekday])).toEqual([
        ["2026-10-31", 6],
        ["2026-11-01", 0],
        ["2026-11-02", 1],
      ]);
    }
  });

  it("labels each month on the week it starts, and a first partial month only with room", () => {
    // 2026-08-05 to 2026-11-02: Sep 1, Oct 1 and Nov 1 start in weeks 3, 8 and 13.
    const { monthLabels } = buildActivityHeatmap(window("2026-11-02", 90));
    expect(monthLabels).toEqual([
      { week: 0, label: "Aug" },
      { week: 4, label: "Sep" },
      { week: 8, label: "Oct" },
      { week: 13, label: "Nov" },
    ]);

    // Starting 2026-10-25 leaves one week of October before November; only Nov is named.
    const short = buildActivityHeatmap(window("2026-11-02", 9));
    expect(short.monthLabels).toEqual([{ week: 1, label: "Nov" }]);
  });
});

describe("date and summary formatting", () => {
  it("formats YYYYMMDD filters as dates and rejects other values", () => {
    expect(formatCompactActivityDate("20261101", longActivityDate)).toBe("Sun, Nov 1, 2026");
    expect(isCompactActivityDate("20261101")).toBe(true);
    expect(isCompactActivityDate("latest")).toBe(false);
    expect(isCompactActivityDate("2026-11-01")).toBe(false);
  });

  it("summarizes a window with failed and in-progress counts only when present", () => {
    const busy = activityStatusTotals([
      bucket("2026-11-01", { completed: 3, failed: 1, running: 2 }),
    ]);
    const calm = activityStatusTotals([bucket("2026-11-01", { completed: 3 })]);

    expect(activityWindowSummary(busy, 30)).toBe("6 in the last 30 days, 1 failed, 2 in progress.");
    expect(activityWindowSummary(calm, 365)).toBe("3 in the last 365 days.");
  });
});
