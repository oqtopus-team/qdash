import { describe, it, expect } from "vitest";

import { groupMetricsByCategory } from "../metrics-grouping";

import type { MetricConfig } from "@/hooks/useMetricsConfig";

function metric(key: string, category?: string): MetricConfig {
  return {
    key,
    title: key.toUpperCase(),
    unit: "μs",
    scale: 1,
    category,
    evaluationMode: "maximize",
  };
}

describe("groupMetricsByCategory", () => {
  it("returns an empty array for no metrics", () => {
    expect(groupMetricsByCategory([])).toEqual([]);
  });

  it("groups metrics that share a category", () => {
    const groups = groupMetricsByCategory([
      metric("t1", "Coherence"),
      metric("t2_echo", "Coherence"),
    ]);

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
      metric("qubit_frequency", "Frequency"),
      metric("t1", "Coherence"),
      metric("anharmonicity", "Frequency"),
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Frequency", "Coherence"]);
    // Later metric is appended to its first-seen category group.
    expect(groups[0].options.map((o) => o.value)).toEqual(["qubit_frequency", "anharmonicity"]);
  });

  it("places uncategorized metrics in an 'Other' group that is always last", () => {
    const groups = groupMetricsByCategory([
      metric("hpi_length"),
      metric("t1", "Coherence"),
      metric("hpi_amplitude", "  "),
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Coherence", "Other"]);
    expect(groups[1].options.map((o) => o.value)).toEqual(["hpi_length", "hpi_amplitude"]);
  });
});
