import { describe, expect, it } from "vitest";

import {
  agreementRate,
  diagnosisOf,
  diagnosisOutcome,
  diagnosisStatus,
  examplesLabel,
  modeLabel,
  diagnosisSuccess,
  diagnosisText,
  evaluatorLabel,
  fitAssessment,
  fitBadgeClass,
  fitLabel,
  formatDuration,
  outcomeBadgeClass,
  runIsActive,
  statusLabel,
} from "../evaluationDisplay";

describe("evaluationDisplay", () => {
  it("reads the diagnosis only when the answer was a JSON object", () => {
    expect(diagnosisOf({ output: { diagnosis: { fit_quality: "good" } } })).toEqual({
      fit_quality: "good",
    });
    expect(diagnosisOf({ output: { diagnosis: null } })).toBeNull();
    expect(diagnosisOf({ output: undefined })).toBeNull();
  });

  it("reads the fit assessment of Q4, and not the fit quality of older records", () => {
    expect(fitAssessment({ fit_reliability: { assessment: "Reliable", reason: "tight" } })).toBe(
      "reliable",
    );
    expect(fitAssessment({ fit_reliability: { assessment: "no fit" } })).toBe("no_fit");
    expect(fitAssessment({ fit_reliability: { assessment: null } })).toBeNull();
    expect(fitAssessment({ fit_quality: "good" })).toBeNull();
    expect(fitBadgeClass("reliable")).toBe("badge-success");
    expect(fitBadgeClass("unreliable")).toBe("badge-error");
    expect(fitBadgeClass("no_fit")).toBe("badge-warning");
    expect(fitBadgeClass(null)).toBe("badge-ghost");
    expect(fitLabel("reliable")).toBe("fit reliable");
    expect(fitLabel("no_fit")).toBe("no fit");
  });

  it("reads the outcome of Q2 and the status of Q6, with the success verdict as the fallback label", () => {
    expect(diagnosisOutcome({ experimental_conclusion: { classification: "suboptimal" } })).toBe(
      "suboptimal",
    );
    expect(diagnosisOutcome({ experimental_conclusion: "Rabi frequency 12.5 MHz." })).toBeNull();
    expect(outcomeBadgeClass("expected")).toBe("badge-success");
    expect(outcomeBadgeClass("apparatus")).toBe("badge-error");
    expect(diagnosisStatus({ calibration_diagnosis: { status: "NO_SIGNAL" } })).toBe("NO_SIGNAL");
    expect(diagnosisStatus({ calibration_diagnosis: { status: null } })).toBeNull();
    expect(statusLabel({ calibration_diagnosis: { status: "NO_SIGNAL" }, success: false })).toBe(
      "NO_SIGNAL",
    );
    expect(statusLabel({ success: true })).toBe("success");
    expect(statusLabel({ success: false })).toBe("not successful");
    expect(statusLabel({})).toBeNull();
  });

  it("only trusts a boolean success and renders each section's answer as text", () => {
    expect(diagnosisSuccess({ success: true })).toBe(true);
    expect(diagnosisSuccess({ success: "yes" })).toBeNull();
    expect(diagnosisText({ parameter_extraction: { f: 1.2 } }, "parameter_extraction")).toBe(
      '{\n  "f": 1.2\n}',
    );
    expect(diagnosisText({ experimental_conclusion: "" }, "experimental_conclusion")).toBeNull();
    // Older records keep their strings.
    expect(
      diagnosisText({ experimental_conclusion: "T1 is 26 us." }, "experimental_conclusion"),
    ).toBe("T1 is 26 us.");
    // A classification shows its reason, a status its range and notes.
    expect(
      diagnosisText(
        { experimental_conclusion: { classification: "expected", reason: "clean" } },
        "experimental_conclusion",
      ),
    ).toBe("clean");
    expect(
      diagnosisText(
        { fit_reliability: { assessment: "reliable", reason: "tight" } },
        "fit_reliability",
      ),
    ).toBe("tight");
    expect(
      diagnosisText(
        {
          calibration_diagnosis: {
            status: "LOW_CONTRAST",
            suggested_range: "(0, 200)",
            notes: "Weak.",
          },
        },
        "calibration_diagnosis",
      ),
    ).toBe("Suggested range: (0, 200)\nWeak.");
    expect(
      diagnosisText(
        { calibration_diagnosis: { status: "SUCCESS", suggested_range: null, notes: "Fine." } },
        "calibration_diagnosis",
      ),
    ).toBe("Fine.");
    // A plot description reads as lines.
    expect(
      diagnosisText(
        {
          technical_description: {
            plot_type: "scatter",
            x_axis: { label: "Duration (ns)", scale: "linear", range: [0, 200] },
            y_axis: { label: "Signal", scale: "linear" },
            main_features: "Damped cosine.",
          },
        },
        "technical_description",
      ),
    ).toBe("scatter plot\nx: Duration (ns) (linear) [0, 200]\ny: Signal (linear)\nDamped cosine.");
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
