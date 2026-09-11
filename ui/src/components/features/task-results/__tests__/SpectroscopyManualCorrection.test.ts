import { describe, expect, it } from "vitest";

import { spectroscopyCorrectionParameterNames } from "../SpectroscopyManualCorrection";

describe("spectroscopyCorrectionParameterNames", () => {
  it("restores declared correction fields for failed qubit spectroscopy", () => {
    expect(
      spectroscopyCorrectionParameterNames("CheckQubitSpectroscopy", "failed", [], {}),
    ).toEqual([
      "coarse_qubit_frequency",
      "anharmonicity",
      "f01_repr_db",
      "f01_quality_level",
      "coarse_control_amplitude",
    ]);
  });

  it("keeps recorded fields and appends missing declarations after failure", () => {
    expect(
      spectroscopyCorrectionParameterNames(
        "CheckQubitSpectroscopy",
        "failed",
        ["coarse_qubit_frequency"],
        { f01_repr_db: { value: -30 } },
      ),
    ).toEqual([
      "coarse_qubit_frequency",
      "f01_repr_db",
      "anharmonicity",
      "f01_quality_level",
      "coarse_control_amplitude",
    ]);
  });

  it("does not add undeclared fields to a completed result", () => {
    expect(
      spectroscopyCorrectionParameterNames(
        "CheckQubitSpectroscopy",
        "completed",
        ["coarse_qubit_frequency"],
        {},
      ),
    ).toEqual(["coarse_qubit_frequency"]);
  });
});
