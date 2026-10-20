import { describe, expect, it } from "vitest";

import { answerShortfall, callLabel, meanDurationMs, runTimingLabel } from "../evaluationDisplay";

describe("answerShortfall", () => {
  it("names how the answer fell short of the diagnosis, or nothing", () => {
    expect(answerShortfall(undefined)).toBeNull();
    expect(answerShortfall({ parsed: true, complete: true, missing_keys: [] })).toBeNull();
    expect(answerShortfall({ parsed: false })?.label).toBe("prose");
    expect(
      answerShortfall({ parsed: true, complete: false, missing_keys: ["fit_quality", "success"] }),
    ).toEqual({ label: "incomplete", title: "Missing: fit_quality, success" });
    // A record made before the keys were reported is still marked.
    expect(answerShortfall({ parsed: true, complete: false })?.title).toMatch(/lacks/);
  });
});

describe("run timing", () => {
  it("gives the mean model time per completed evaluation, and the run's timing as text", () => {
    expect(meanDurationMs({ duration_ms_total: 60_000, completed_count: 0 })).toBeNull();
    expect(meanDurationMs({ duration_ms_total: 60_000, completed_count: 2 })).toBe(30_000);
    expect(
      runTimingLabel({ elapsed_ms: 90_000, duration_ms_total: 60_000, completed_count: 2 }),
    ).toBe("took 1.5 min · 30.0 s per evaluation");
    // Still running: no end-to-end time yet.
    expect(runTimingLabel({ duration_ms_total: 30_000, completed_count: 1 })).toBe(
      "30.0 s per evaluation",
    );
    expect(runTimingLabel({ duration_ms_total: 0, completed_count: 0 })).toBeNull();
  });

  it("labels one model call by its question, duration and how it ended", () => {
    expect(callLabel({ duration_ms: 195_000, stop_reason: "length", structured: true })).toBe(
      "3.3 min (length)",
    );
    expect(
      callLabel({
        question: "experimental_significance",
        duration_ms: 42_000,
        stop_reason: "stop",
      }),
    ).toBe("experimental_significance 42.0 s (stop)");
    expect(
      callLabel({ duration_ms: 12_000, stop_reason: "stop", structured: true, missing_keys: [] }),
    ).toBe("12.0 s (stop)");
    expect(
      callLabel({
        duration_ms: 12_000,
        stop_reason: "stop",
        structured: false,
        missing_keys: ["success"],
      }),
    ).toBe("12.0 s (stop, incomplete)");
  });
});
