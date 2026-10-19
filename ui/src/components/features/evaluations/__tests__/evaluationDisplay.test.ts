import { describe, expect, it } from "vitest";

import {
  agreementRate,
  diagnosisOf,
  examplesLabel,
  modeLabel,
  diagnosisSuccess,
  diagnosisText,
  evaluatorLabel,
  fitQuality,
  fitQualityBadgeClass,
  formatDuration,
  runIsActive,
} from "../evaluationDisplay";

describe("evaluationDisplay", () => {
  it("reads the diagnosis only when the answer was a JSON object", () => {
    expect(diagnosisOf({ output: { diagnosis: { fit_quality: "good" } } })).toEqual({
      fit_quality: "good",
    });
    expect(diagnosisOf({ output: { diagnosis: null } })).toBeNull();
    expect(diagnosisOf({ output: undefined })).toBeNull();
  });

  it("reduces the fit quality to its first word", () => {
    expect(fitQuality({ fit_quality: "Good, the fit follows the data" })).toBe("good");
    expect(fitQuality({ fit_quality: "marginal (noisy tail)" })).toBe("marginal");
    expect(fitQuality({ fit_quality: 3 })).toBeNull();
    expect(fitQualityBadgeClass("poor")).toBe("badge-error");
    expect(fitQualityBadgeClass(null)).toBe("badge-ghost");
  });

  it("only trusts a boolean success and prints structured fields as JSON", () => {
    expect(diagnosisSuccess({ success: true })).toBe(true);
    expect(diagnosisSuccess({ success: "yes" })).toBeNull();
    expect(diagnosisText({ parameter_extraction: { f: 1.2 } }, "parameter_extraction")).toBe(
      '{\n  "f": 1.2\n}',
    );
    expect(diagnosisText({ experimental_conclusion: "" }, "experimental_conclusion")).toBeNull();
  });

  it("labels the evaluator with its version and checkout commit", () => {
    expect(
      evaluatorLabel({
        name: "@orangekame3/pi-qcaleval",
        version: "0.0.1",
        commit: "042e454323b2",
      }),
    ).toBe("@orangekame3/pi-qcaleval@0.0.1 (042e454323b2)");
    expect(evaluatorLabel({ name: "x", version: "1.0.0" })).toBe("x@1.0.0");
    expect(evaluatorLabel(null)).toBeNull();
  });

  it("names the two axes of a run in the user's terms", () => {
    expect(modeLabel("direct")).toBe("Fixed prompt");
    expect(modeLabel("planner")).toBe("Via Copilot");
    expect(examplesLabel(false)).toBe("Zero-shot");
    expect(examplesLabel(true)).toBe("In-context");
  });

  it("formats durations and agreement", () => {
    expect(formatDuration(32858)).toBe("32.9 s");
    expect(formatDuration(120_000)).toBe("2.0 min");
    expect(formatDuration(undefined)).toBeNull();
    expect(agreementRate({ agree_count: 3, disagree_count: 1 })).toBe(0.75);
    expect(agreementRate({ agree_count: 0, disagree_count: 0 })).toBeNull();
    expect(runIsActive({ status: "completed", pending_count: 0 })).toBe(false);
    expect(runIsActive({ status: "running", pending_count: 2 })).toBe(true);
  });
});
