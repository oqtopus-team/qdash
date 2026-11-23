import { describe, expect, it } from "vitest";

import {
  correctionValuesFromPoint,
  sourceOutputName,
  spectroscopyCorrectionParameterNames,
} from "../SpectroscopyManualCorrection";

describe("spectroscopyCorrectionParameterNames", () => {
  it("offers only operational readout parameters for resonator spectroscopy", () => {
    expect(spectroscopyCorrectionParameterNames("CheckResonatorSpectroscopy")).toEqual([
      "readout_frequency",
      "readout_amplitude",
    ]);
  });

  it("offers only operational control parameters for qubit spectroscopy", () => {
    expect(spectroscopyCorrectionParameterNames("CheckQubitSpectroscopy")).toEqual([
      "control_frequency",
      "coarse_control_amplitude",
    ]);
  });

  it("offers nothing for unsupported tasks", () => {
    expect(spectroscopyCorrectionParameterNames("CheckT1")).toEqual([]);
  });
});

describe("sourceOutputName", () => {
  it("reads the measured frequency from the source output", () => {
    expect(sourceOutputName("CheckResonatorSpectroscopy", "readout_frequency")).toBe(
      "resonator_frequency",
    );
    expect(sourceOutputName("CheckQubitSpectroscopy", "control_frequency")).toBe(
      "coarse_qubit_frequency",
    );
  });

  it("falls back to the parameter itself", () => {
    expect(sourceOutputName("CheckResonatorSpectroscopy", "readout_amplitude")).toBe(
      "readout_amplitude",
    );
    expect(sourceOutputName("CheckT1", "t1")).toBe("t1");
  });
});

describe("correctionValuesFromPoint", () => {
  it("maps a resonator point to readout frequency and amplitude", () => {
    expect(
      correctionValuesFromPoint("CheckResonatorSpectroscopy", {
        x: 10.1,
        y: -20,
      }),
    ).toEqual({
      readout_frequency: "10.1",
      readout_amplitude: String(10 ** (-20 / 20)),
    });
  });

  it("maps a qubit point to control frequency and a capped coarse amplitude", () => {
    expect(correctionValuesFromPoint("CheckQubitSpectroscopy", { x: 7.5, y: -30 })).toEqual({
      control_frequency: "7.5",
      coarse_control_amplitude: String(10 ** (-20 / 20)),
    });
    expect(
      correctionValuesFromPoint("CheckQubitSpectroscopy", { x: 7.5, y: 0 })
        .coarse_control_amplitude,
    ).toBe("1");
  });

  it("returns nothing for unsupported tasks", () => {
    expect(correctionValuesFromPoint("CheckT1", { x: 1, y: 2 })).toEqual({});
  });
});
