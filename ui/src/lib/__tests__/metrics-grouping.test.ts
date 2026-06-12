import { describe, it, expect } from "vitest";

import { groupMetricsByCategory } from "../metrics-grouping";

import type { MetricConfig } from "@/hooks/useMetricsConfig";

function metric(key: string): MetricConfig {
  return {
    key,
    title: key.toUpperCase(),
    unit: "μs",
    scale: 1,
    evaluationMode: "maximize",
  };
}

describe("groupMetricsByCategory", () => {
  it("returns an empty array for no metrics", () => {
    expect(groupMetricsByCategory([])).toEqual([]);
  });

  it("groups metrics that share a category", () => {
    const groups = groupMetricsByCategory([metric("t1"), metric("t2_echo")]);

    expect(groups).toEqual([
      {
        label: "Coherence",
        options: [
          { value: "t1", label: "T1" },
          { value: "t2_echo", label: "T2_ECHO" },
        ],
      },
    ]);
  });

  it("emits categories in the order they first appear", () => {
    const groups = groupMetricsByCategory([
      metric("qubit_frequency"),
      metric("t1"),
      metric("anharmonicity"),
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Frequency", "Coherence"]);
    // Later metric is appended to its first-seen category group.
    expect(groups[0].options.map((o) => o.value)).toEqual(["qubit_frequency", "anharmonicity"]);
  });

  it("places uncategorized metrics in an 'Other' group that is always last", () => {
    const groups = groupMetricsByCategory([
      metric("unknown_metric_a"),
      metric("t1"),
      metric("unknown_metric_b"),
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Coherence", "Other"]);
    expect(groups[1].options.map((o) => o.value)).toEqual([
      "unknown_metric_a",
      "unknown_metric_b",
    ]);
  });
});
