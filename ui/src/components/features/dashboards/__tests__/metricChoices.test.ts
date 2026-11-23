import { describe, expect, it } from "vitest";

import type { MetricInfo, MetricScriptSummary } from "@/schemas";

import {
  choiceValue,
  findChoiceOption,
  metricChoiceGroups,
  parseChoiceValue,
  scriptMetricLabel,
} from "../metricChoices";

const PAIR: MetricInfo = { id: "zx90_median", title: "Median ZX90", unit: "%", target: "pair" };
const QUBIT: MetricInfo = { id: "ratio", title: "T2 / T1", unit: "dimensionless", target: "qubit" };

function script(overrides: Partial<MetricScriptSummary>): MetricScriptSummary {
  return {
    script_id: "ms_a",
    project_id: "p",
    name: "Script A",
    description: "",
    visibility: "project",
    status: "valid",
    revision: 3,
    active_revision: 3,
    metrics: [PAIR, QUBIT],
    template_id: null,
    owner_username: "alice",
    owner_user_id: "u",
    can_edit: true,
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

describe("metricChoices", () => {
  it("round-trips choice values", () => {
    const choices = [
      { kind: "qubit_metric", metric: "t1" },
      { kind: "coupling_metric", metric: "zx90_gate_fidelity" },
      { kind: "metric_script", script_id: "ms_a1b2", metric_id: "zx90_median" },
    ] as const;
    for (const choice of choices) {
      expect(parseChoiceValue(choiceValue(choice))).toEqual(choice);
    }
    expect(parseChoiceValue("")).toBeNull();
    expect(parseChoiceValue("metric_script|ms_a|")).toBeNull();
    expect(parseChoiceValue("other|x")).toBeNull();
  });

  it("labels script metrics with unit and target", () => {
    expect(scriptMetricLabel(PAIR)).toBe("Median ZX90 (%) · per pair");
    expect(scriptMetricLabel(QUBIT)).toBe("T2 / T1 · per qubit");
  });

  it("groups chip metrics first, then scripts with a valid revision", () => {
    const groups = metricChoiceGroups({
      qubitMetrics: [{ key: "t1", title: "T1", unit: "us" }],
      couplingMetrics: [],
      scripts: [
        script({}),
        script({ script_id: "ms_private", name: "Mine", visibility: "private" }),
        script({ script_id: "ms_broken", name: "Broken", active_revision: null }),
      ],
    });

    expect(groups.map((group) => group.label)).toEqual([
      "Qubit metrics",
      "Script A",
      "Mine (private)",
    ]);
    expect(groups[0].options[0]).toMatchObject({
      label: "T1 (us)",
      choice: { kind: "qubit_metric" },
    });
    expect(groups[1].options.map((option) => option.label)).toEqual([
      "Median ZX90 (%) · per pair",
      "T2 / T1 · per qubit",
    ]);
  });

  it("lists the pinned catalog for the edited script and keeps an unavailable script's metric", () => {
    const pinnedOnly: MetricInfo = { id: "old", title: "Old metric", unit: "", target: "qubit" };
    const groups = metricChoiceGroups({
      qubitMetrics: [],
      couplingMetrics: [],
      scripts: [script({})],
      pinnedCatalog: { script_id: "ms_a", metrics: [pinnedOnly] },
    });
    expect(groups).toHaveLength(1);
    expect(groups[0].options.map((option) => option.choice)).toEqual([
      { kind: "metric_script", script_id: "ms_a", metric_id: "old" },
    ]);

    const gone = metricChoiceGroups({
      qubitMetrics: [],
      couplingMetrics: [],
      scripts: [],
      pinnedCatalog: { script_id: "ms_gone", metrics: [PAIR], label: "Deleted (unavailable)" },
    });
    expect(gone[0].label).toBe("Deleted (unavailable)");
    expect(
      findChoiceOption(gone, {
        kind: "metric_script",
        script_id: "ms_gone",
        metric_id: "zx90_median",
      }),
    ).toBeDefined();
    expect(findChoiceOption(gone, null)).toBeUndefined();
  });
});
