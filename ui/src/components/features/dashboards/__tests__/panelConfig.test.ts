import { describe, expect, it } from "vitest";

import {
  metricScriptConfigError,
  readMetricScriptConfig,
  writeMetricScriptConfig,
} from "../panelConfig";

describe("readMetricScriptConfig", () => {
  it("reads a stored config", () => {
    const config = readMetricScriptConfig({
      config: {
        script_id: "ms_1",
        metric_id: "zx90_median",
        script_revision: 4,
        period: { kind: "absolute", start: "2026-11-01T00:00:00Z", end: "2026-11-15T00:00:00Z" },
        params: { min_samples: 5, mode: "strict", strict: true },
        view: "table",
        direction: "forward",
        hops: [1],
      },
    });
    expect(config).toEqual({
      script_id: "ms_1",
      metric_id: "zx90_median",
      script_revision: 4,
      period: { kind: "absolute", start: "2026-11-01T00:00:00Z", end: "2026-11-15T00:00:00Z" },
      params: { min_samples: 5, mode: "strict", strict: true },
      view: "table",
      direction: "forward",
      hops: [1],
    });
  });

  it("fills defaults for missing or malformed fields", () => {
    const config = readMetricScriptConfig({
      config: {
        script_id: 7,
        script_revision: 0,
        period: "last week",
        params: { bad: { nested: true }, nan: Number.NaN, ok: 2 },
        view: "chart",
        direction: "up",
        hops: [3],
      },
    });
    expect(config).toEqual({
      script_id: "",
      metric_id: "",
      script_revision: null,
      period: { kind: "relative", days: 14 },
      params: { ok: 2 },
      view: "map",
      direction: "both",
      hops: [1, 2],
    });
  });
});

describe("metricScriptConfigError", () => {
  const valid = readMetricScriptConfig({
    config: { script_id: "ms_1", metric_id: "m", script_revision: 1 },
  });

  it("accepts a complete config", () => {
    expect(metricScriptConfigError(valid)).toBeNull();
  });

  it("names the first missing piece", () => {
    expect(metricScriptConfigError({ ...valid, script_id: "" })).toBe("Choose a script");
    expect(metricScriptConfigError({ ...valid, script_revision: null })).toBe(
      "The script has no valid revision to pin",
    );
    expect(metricScriptConfigError({ ...valid, metric_id: "" })).toBe("Choose a metric");
    expect(metricScriptConfigError({ ...valid, hops: [] })).toBe(
      "Choose at least one pair distance",
    );
    expect(metricScriptConfigError({ ...valid, period: { kind: "relative", days: 401 } })).toBe(
      "Enter whole days between 1 and 400",
    );
    expect(
      metricScriptConfigError({
        ...valid,
        period: { kind: "absolute", start: "2026-11-02T00:00:00Z", end: "2026-11-01T00:00:00Z" },
      }),
    ).toBe("The period must end after it starts");
  });
});

describe("writeMetricScriptConfig", () => {
  it("writes only the fields the API accepts", () => {
    const config = readMetricScriptConfig({
      config: { script_id: "ms_1", metric_id: "m", script_revision: 2, legacy: "dropped" },
    });
    expect(Object.keys(writeMetricScriptConfig(config)).sort()).toEqual([
      "direction",
      "hops",
      "metric_id",
      "params",
      "period",
      "script_id",
      "script_revision",
      "view",
    ]);
  });
});
