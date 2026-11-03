import assert from "node:assert/strict";
import test from "node:test";

import { registerTimeseriesComparisonTool } from "../.test-dist/tools/timeseries.js";

test("comparison tool fills only omitted inputs from investigation context", async () => {
  const tools = new Map();
  const calls = [];
  const client = {
    async getTaskResultsTimeseries(query) {
      calls.push(query);
      const sign = query.qid === "1" ? 1 : -1;
      return {
        data: {
          [query.qid]: [0, 1, 2, 3].map((minute) => ({
            value: sign * minute,
            calibrated_at: `2026-08-05T00:0${minute}:00Z`,
            unit: "a.u.",
          })),
        },
      };
    },
  };
  registerTimeseriesComparisonTool({
    registerTool(tool) { tools.set(tool.name, tool); },
  }, {
    async makeClient() { return client; },
    async defaultChipId() { return "chip"; },
    investigationContext() {
      return {
        name: "preset",
        startAt: "2026-08-05T00:00:00Z",
        endAt: "2026-08-05T00:03:00Z",
        tag: "phase-check",
        qdashSeries: [
          { parameter: "arbitrary_metric", qid: "1" },
          { parameter: "arbitrary_metric", qid: "2" },
        ],
        analysis: { resampleMinutes: 1, detrend: "linear", normalize: "zscore" },
      };
    },
  });

  const result = await tools.get("qdash_compare_timeseries").execute(
    "test",
    {},
    undefined,
    undefined,
    { cwd: process.cwd() },
  );

  assert.equal(calls.length, 2);
  assert.equal(calls[0].startAt, "2026-08-05T00:00:00Z");
  assert.equal(calls[0].endAt, "2026-08-05T00:03:00Z");
  assert.equal(calls[0].tag, "phase-check");
  assert.equal(result.details.investigation, "preset");
  assert.equal(result.details.data.transforms.detrend, "linear");
  assert.equal(result.details.data.series.length, 2);
});

test("explicit comparison arguments can bypass investigation context", async () => {
  const tools = new Map();
  registerTimeseriesComparisonTool({ registerTool(tool) { tools.set(tool.name, tool); } }, {
    async makeClient() { throw new Error("QDash should not be called"); },
    async defaultChipId() { throw new Error("QDash should not be called"); },
    investigationContext() {
      return { qdashSeries: [{ parameter: "a" }, { parameter: "b" }] };
    },
  });
  await assert.rejects(() => tools.get("qdash_compare_timeseries").execute(
    "test",
    { useInvestigationContext: false },
    undefined,
    undefined,
    { cwd: process.cwd() },
  ), /At least two timeseries/);
});
