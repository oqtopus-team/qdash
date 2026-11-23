import { describe, expect, it } from "vitest";

import {
  calibrationSessionCrumbs,
  calibrationSessionDetailHref,
  calibrationSessionListHref,
  executionDetailHref,
  executionListHref,
  isExecutionDay,
  runIdFromHash,
  sessionReturnFromQuery,
} from "@/lib/executionArea";

const query = {
  from: "sessions",
  status: "all",
  origin: "all",
  mine: false,
  chip: null,
  page: 1,
  date: null,
  flat: false,
} as const;

describe("Execution area links", () => {
  it("keeps plain URLs for bookmarks, chat, and SDK links", () => {
    expect(executionListHref()).toBe("/execution");
    expect(calibrationSessionListHref()).toBe("/calibration-sessions");
    expect(calibrationSessionDetailHref("cs-1")).toBe("/calibration-sessions/cs-1");
    expect(calibrationSessionDetailHref("cs-1", "lab a")).toBe(
      "/calibration-sessions/cs-1?project=lab%20a",
    );
    // An unfiltered session list adds nothing to the page URL.
    expect(
      calibrationSessionDetailHref("cs-1", "lab-a", {
        from: "sessions",
        list: { status: "all", origin: "all", mine: false, chip: null, page: 1 },
      }),
    ).toBe("/calibration-sessions/cs-1?project=lab-a");
  });

  it("carries the session list's filters and page to the page and back", () => {
    const list = {
      status: "closed",
      origin: "automatic",
      mine: true,
      chip: "64Qv3",
      page: 3,
    } as const;
    expect(calibrationSessionDetailHref("cs-1", "lab-a", { from: "sessions", list })).toBe(
      "/calibration-sessions/cs-1?project=lab-a&chip=64Qv3&status=closed&origin=automatic&mine=true&page=3",
    );
    expect(calibrationSessionCrumbs({ from: "sessions", list }, "lab-a")).toEqual([
      { label: "Execution", href: "/execution?chip=64Qv3&project=lab-a" },
      {
        label: "Calibration sessions",
        href: "/calibration-sessions?chip=64Qv3&status=closed&origin=automatic&mine=true&page=3&project=lab-a",
      },
    ]);
  });

  it("returns a page opened from the Executions list to that list on the same chip", () => {
    const back = { from: "executions", list: { chip: "64Qv3" } } as const;
    expect(calibrationSessionDetailHref("cs-1", "lab-a", back)).toBe(
      "/calibration-sessions/cs-1?project=lab-a&from=executions&chip=64Qv3",
    );
    expect(calibrationSessionCrumbs(back, "lab-a")).toEqual([
      { label: "Execution", href: "/execution?chip=64Qv3&project=lab-a" },
    ]);
  });

  it("carries the Executions day, flat list and page through session and execution pages", () => {
    const list = { chip: "64Qv3", date: "20261120", flat: true, page: 2 };
    const sessionHref = calibrationSessionDetailHref("cs-1", "lab-a", {
      from: "executions",
      list,
    });
    expect(sessionHref).toBe(
      "/calibration-sessions/cs-1?project=lab-a&from=executions&chip=64Qv3&date=20261120&flat=true&page=2",
    );
    // What the session page reads back from that URL returns to the same list.
    const back = sessionReturnFromQuery({ ...query, ...list, from: "executions" });
    expect(back).toEqual({ from: "executions", list });
    expect(calibrationSessionCrumbs(back, "lab-a")).toEqual([
      {
        label: "Execution",
        href: "/execution?chip=64Qv3&date=20261120&flat=true&page=2&project=lab-a",
      },
    ]);
    expect(executionDetailHref("64Qv3", "ex-1", "lab-a", list)).toBe(
      "/execution/64Qv3/ex-1?project=lab-a&date=20261120&flat=true&page=2",
    );
    // The grouped latest runs on the first page are the defaults and add nothing.
    expect(executionDetailHref("64Qv3", "ex-1", "lab-a", { chip: "64Qv3", page: 1 })).toBe(
      "/execution/64Qv3/ex-1?project=lab-a",
    );
    expect(executionListHref({ chipId: "64Qv3", flat: false, date: null, page: 1 })).toBe(
      "/execution?chip=64Qv3",
    );
  });

  it("keeps each list's own filters when reading a session page's query", () => {
    // The session list ignores the Executions day and grouping.
    expect(
      sessionReturnFromQuery({
        ...query,
        status: "open",
        chip: "64Qv3",
        page: 2,
        date: "20261120",
        flat: true,
      }),
    ).toEqual({
      from: "sessions",
      list: { status: "open", origin: "all", mine: false, chip: "64Qv3", page: 2 },
    });
    // And the Executions list ignores the session filters.
    expect(
      sessionReturnFromQuery({ ...query, from: "executions", status: "closed", mine: true }),
    ).toEqual({ from: "executions", list: { chip: null, date: null, flat: false, page: 1 } });
    expect(sessionReturnFromQuery({ ...query, page: -3 }).list.page).toBe(1);
  });

  it("accepts only real calendar days", () => {
    expect(isExecutionDay("20261120")).toBe(true);
    expect(isExecutionDay("20240229")).toBe(true);
    for (const value of ["20230229", "20261340", "2026-11-20", "latest", "", "1969123"]) {
      expect(isExecutionDay(value)).toBe(false);
    }
    expect(executionListHref({ chipId: "64Qv3", date: "not-a-day", page: 2.5 })).toBe(
      "/execution?chip=64Qv3",
    );
  });

  it("reads a run only from a run fragment", () => {
    expect(runIdFromHash("#run-abc%20def")).toBe("abc def");
    expect(runIdFromHash("#run-")).toBeNull();
    expect(runIdFromHash("#other")).toBeNull();
    expect(runIdFromHash("#run-%E0%A4%A")).toBeNull();
    expect(runIdFromHash(`#run-${"x".repeat(129)}`)).toBeNull();
  });

  it("keeps every link on its own route whatever the chip value holds", () => {
    const hostile = "//evil.example/x?y=1#z";
    expect(executionListHref({ chipId: hostile, projectId: "lab-a" })).toBe(
      "/execution?chip=%2F%2Fevil.example%2Fx%3Fy%3D1%23z&project=lab-a",
    );
    expect(calibrationSessionDetailHref("../admin", "lab-a")).toBe(
      "/calibration-sessions/..%2Fadmin?project=lab-a",
    );
    // A value no chip ID has is dropped instead of carried.
    expect(executionListHref({ chipId: "x".repeat(129) })).toBe("/execution");
    expect(calibrationSessionListHref({ chip: "   ", page: 0 })).toBe("/calibration-sessions");
    expect(calibrationSessionListHref({ page: Number.NaN })).toBe("/calibration-sessions");
  });
});
