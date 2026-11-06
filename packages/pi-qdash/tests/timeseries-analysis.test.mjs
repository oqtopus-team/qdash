import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  investigationContextSummary,
  validateInvestigationContext,
} from "../.test-dist/lib/investigation-context.js";
import {
  compareTimeseries,
  inspectExternalCsv,
  loadExternalCsvSeries,
} from "../.test-dist/lib/timeseries-analysis.js";

test("loads explicitly mapped CSV columns with timezone, filters, and scaling", () => {
  const directory = mkdtempSync(join(tmpdir(), "pi-qdash-timeseries-"));
  try {
    const path = join(directory, "sensor.csv");
    writeFileSync(path, [
      "#DateTime,channel,value",
      "2026/8/5 21:00,A,1.20E-02",
      "2026/8/5 21:00,B,9.90E-02",
      "2026/8/5 21:01,A,1.21E-02",
    ].join("\n"));
    const inspection = inspectExternalCsv({
      path,
      timeColumn: "DateTime",
      timeFormat: "yyyy/M/d H:mm",
      timezoneOffsetMinutes: 540,
    }, directory);
    assert.deepEqual(inspection.headers, ["#DateTime", "channel", "value"]);
    assert.equal(inspection.time?.valid, 3);
    assert.equal(inspection.time?.medianCadenceMinutes, 1);
    assert.equal(inspection.columns.find((column) => column.column === "value")?.numeric, 3);

    const [series] = loadExternalCsvSeries({
      path,
      timeColumn: "DateTime",
      timeFormat: "yyyy/M/d H:mm",
      timezoneOffsetMinutes: 540,
      filters: { channel: ["A"] },
      valueColumns: [{ column: "value", label: "sensor A", unit: "mK", scale: 1000 }],
    }, directory);
    assert.equal(series.label, "sensor A");
    assert.equal(series.points.length, 2);
    assert.equal(series.points[0].at, Date.parse("2026-08-05T21:00:00+09:00"));
    assert.equal(series.points[0].value, 12);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("finds a shared period and inverse phase without metric-specific assumptions", () => {
  const start = Date.parse("2026-08-05T00:00:00Z");
  const period = 150;
  const points = Array.from({ length: 601 }, (_unused, minute) => ({
    at: start + minute * 60_000,
    value: Math.sin(2 * Math.PI * minute / period),
  }));
  const result = compareTimeseries([
    { label: "metric", source: "qdash", points },
    { label: "sensor", source: "csv", points: points.map((point) => ({ ...point, value: -point.value })) },
  ], {
    resampleMinutes: 1,
    detrend: "linear",
    normalize: "zscore",
    periodSearch: { minMinutes: 130, maxMinutes: 170, stepMinutes: 0.2 },
  });

  assert.ok((result.pairs[0].correlation ?? 0) < -0.999);
  assert.ok(Math.abs((result.periodicFits?.[0].periodMinutes ?? 0) - period) < 0.3);
  assert.ok(Math.abs(Math.abs(result.pairs[0].phaseDifferenceDegrees ?? 0) - 180) < 0.2);
  assert.ok((result.periodicFits?.[0].periodicExplainedFraction ?? 0) > 0.999);
});

test("validates reusable investigation context without metric-specific fields", () => {
  const context = validateInvestigationContext({
    name: "arbitrary comparison",
    startAt: "2026-08-05T00:00:00Z",
    endAt: "2026-08-06T00:00:00Z",
    timezoneOffsetMinutes: 540,
    tag: "experiment",
    qdashSeries: [{ parameter: "metric_a", qid: "1" }],
    csvSeries: [{
      path: "sensor.csv",
      timeColumn: "recorded_at",
      timeFormat: "yyyy/M/d H:mm",
      valueColumns: [{ column: "sensor_value", label: "sensor" }],
    }],
    analysis: {
      resampleMinutes: 2,
      smoothingWindowMinutes: 10,
      detrend: "linear",
      normalize: "zscore",
      periodSearch: { minMinutes: 60, maxMinutes: 240 },
    },
  });
  assert.equal(context.qdashSeries?.[0].parameter, "metric_a");
  assert.match(investigationContextSummary(context), /2 series/);
  assert.throws(() => validateInvestigationContext({
    timezoneOffsetMinutes: 900,
    qdashSeries: [{ parameter: "a" }, { parameter: "b" }],
  }), /-840 to 840/);
});

test("requires an explicit timezone for naive timestamps", () => {
  const directory = mkdtempSync(join(tmpdir(), "pi-qdash-timeseries-"));
  try {
    const path = join(directory, "sensor.csv");
    writeFileSync(path, "time,value\n2026/8/5 21:00,1\n2026/8/5 21:01,2\n");
    assert.throws(() => loadExternalCsvSeries({
      path,
      timeColumn: "time",
      timeFormat: "yyyy/M/d H:mm",
      valueColumns: [{ column: "value" }],
    }, directory), /require timezoneOffsetMinutes/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
