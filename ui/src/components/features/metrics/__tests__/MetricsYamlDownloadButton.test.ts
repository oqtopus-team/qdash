import { describe, expect, it } from "vitest";
import { parse } from "yaml";

import { buildMetricsYaml } from "@/components/features/metrics/MetricsYamlDownloadButton";

describe("buildMetricsYaml", () => {
  it("serializes special strings and sorted metric values as valid YAML", () => {
    const yaml = buildMetricsYaml(
      "chip:01",
      { key: "t1", title: "T1 # average", unit: "µs", scale: 1 },
      "latest",
      " last 7 days ",
      {
        "10": { value: 20 },
        "2": { value: 10 },
        skipped: { value: null },
      },
    );

    expect(parse(yaml)).toMatchObject({
      chip_id: "chip:01",
      metric: "t1",
      title: "T1 # average",
      unit: "µs",
      selection_mode: "latest",
      time_range: " last 7 days ",
      data: {
        "2": 10,
        "10": 20,
      },
    });
    expect(yaml.indexOf('"2"')).toBeLessThan(yaml.indexOf('"10"'));
  });

  it("includes finite standard deviations for average data", () => {
    const yaml = buildMetricsYaml(
      "chip-1",
      { key: "t2", title: "T2", unit: "µs", scale: 1 },
      "average",
      "30d",
      {
        q0: { value: 12, stddev: 0.5 },
        q1: { value: 14, stddev: Number.POSITIVE_INFINITY },
      },
    );

    expect(parse(yaml).data).toEqual({
      q0: { value: 12, stddev: 0.5 },
      q1: { value: 14, stddev: null },
    });
  });
});
