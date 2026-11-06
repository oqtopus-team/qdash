import assert from "node:assert/strict";
import test from "node:test";

import {
  formatNumber,
  formatSettings,
  formatSweep,
  qcalContextText,
  recordedParameters,
  sweepsOf,
} from "../.test-dist/lib/qcal-evidence.js";

const RUN = {
  readout_duration: { unit: "ns", value_type: "float", value: 1024.0, description: "Readout pulse duration" },
  time_range: { unit: "ns", value_type: "range", value: [0, 401, 8], description: "Time range for Rabi oscillation" },
  shots: { unit: "a.u.", value_type: "int", value: 2048, description: "Number of shots" },
  interval: { unit: "ns", value_type: "int", value: 153600, description: "Time interval" },
};

test("recorded parameters keep value, unit and type; bare values are wrapped", () => {
  const params = recordedParameters({ ...RUN, bare: 3, flag: true, ignored: null });
  assert.deepEqual(params.time_range, { value: [0, 401, 8], unit: "ns", value_type: "range", description: "Time range for Rabi oscillation" });
  assert.deepEqual(params.bare, { value: 3, unit: "", value_type: "number", description: "" });
  assert.equal(params.ignored, undefined);
  assert.deepEqual(recordedParameters(undefined), {});
});

test("sweeps are read the way QDash expands them", () => {
  const sweeps = sweepsOf(
    recordedParameters({
      ...RUN,
      t1_range: { unit: "ns", value_type: "np.logspace", value: [2.0, 5.0, 51] },
      detuning: { unit: "GHz", value_type: "np.linspace", value: [-0.01, 0.01, 21] },
      arange: { unit: "", value_type: "np.arange", value: [0, 10001, 100] },
      amplitudes: { unit: "a.u.", value_type: "list", value: [0.1, 0.3, 0.2] },
      single: { unit: "", value_type: "list", value: [1] },
    }),
  );
  assert.deepEqual(
    sweeps.map((s) => [s.name, s.spacing, s.start, s.stop, s.points, s.step]),
    [
      ["time_range", "linear", 0, 400, 51, 8],
      ["t1_range", "log", 100, 100000, 51, undefined],
      ["detuning", "linear", -0.01, 0.01, 21, 0.001],
      ["arange", "linear", 0, 10000, 101, 100],
      ["amplitudes", "list", 0.1, 0.3, 3, undefined],
    ],
  );
});

test("sweeps and settings are written with units, a.u. left out", () => {
  const sweeps = sweepsOf(recordedParameters(RUN));
  assert.equal(formatSweep(sweeps[0]), "time_range 0 to 400 ns in steps of 8 ns (51 points)");
  assert.equal(
    formatSweep({ name: "t", unit: "ns", description: "", spacing: "log", start: 100, stop: 500000, points: 51 }),
    "t 100 to 500000 ns, 51 points log-spaced",
  );
  assert.equal(
    formatSweep({ name: "amp", unit: "a.u.", description: "", spacing: "list", start: 0.1, stop: 0.3, points: 3 }),
    "amp 0.1 to 0.3, 3 points",
  );
  assert.deepEqual(formatSettings(recordedParameters(RUN), new Set(["time_range"])), [
    "readout_duration 1024 ns",
    "shots 2048",
    "interval 153600 ns",
  ]);
  assert.equal(formatNumber(7.615393529), "7.615");
  assert.equal(formatNumber(0.016979), "0.01698");
  assert.equal(formatNumber(153600), "153600");
  assert.equal(formatNumber(1.5e-7), "1.5e-7");
  // Log-spaced endpoints are the integers they round to.
  assert.equal(formatNumber(10 ** 5.698970004336019), "500000");
  assert.equal(formatNumber(10 ** 2.0), "100");
  assert.equal(formatNumber(26.19000001), "26.19");
  assert.equal(
    formatSweep(sweepsOf(recordedParameters({ t: { unit: "ns", value_type: "np.logspace", value: [2.0, 5.698970004336019, 51] } }))[0]),
    "t 100 to 500000 ns, 51 points log-spaced",
  );
});

test("the context names the task and target, the sweep and the settings, and nothing fitted by default", () => {
  const text = qcalContextText({
    taskName: "CheckRabi",
    status: "completed",
    targetKind: "qubit",
    targetId: "4",
    chipId: "16Qv1",
    runParameters: recordedParameters(RUN),
    message: "CheckRabi is completed",
  });
  assert.equal(
    text,
    [
      "Task CheckRabi on qubit 4 (chip 16Qv1), status completed.",
      "Sweep: time_range 0 to 400 ns in steps of 8 ns (51 points).",
      "Settings: readout_duration 1024 ns; shots 2048; interval 153600 ns.",
      "Task message: CheckRabi is completed",
    ].join("\n"),
  );
  const withExtras = qcalContextText({
    taskName: "CheckRabi",
    targetKind: "system",
    targetId: "all",
    runParameters: {},
    inputParameters: recordedParameters({ control_amplitude: { value: 0.0169790343, unit: "a.u.", value_type: "float" } }),
    metrics: recordedParameters({ rabi_frequency: { value: 12.4881, unit: "MHz", value_type: "float" } }),
  });
  assert.equal(
    withExtras,
    ["Task CheckRabi on all.", "Calibration inputs: control_amplitude 0.01698.", "Fitted results: rabi_frequency 12.49 MHz."].join("\n"),
  );
});
