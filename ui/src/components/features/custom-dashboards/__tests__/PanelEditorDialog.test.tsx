import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DashboardPanelModel } from "@/schemas";

import { PanelEditorDialog } from "../PanelEditorDialog";
import { buildCollisionParams } from "../panelConfig";

const ADIABATIC_DEFAULT = Math.sqrt(0.05 / 2.474);

const CHECKS = [
  {
    kind: "Type0A",
    title: "Type0A — Qubit quality",
    description: "Qubit quality",
    target: "qubit",
    unit: "dimensionless",
    parameters: [{ name: "min_t1", default: 3000, min: 1, unit: "ns", label: "min_t1" }],
    legend: [],
  },
  {
    kind: "Type1A",
    title: "Type1A — GE–GE proximity",
    description: "GE–GE proximity",
    target: "pair",
    unit: "dimensionless",
    parameters: [
      { name: "cnot_time", default: 500, min: 1, unit: "ns", label: "cnot_time" },
      {
        name: "adiabatic_limit",
        default: ADIABATIC_DEFAULT,
        min: 0.000001,
        unit: "",
        label: "adiabatic_limit",
      },
    ],
    legend: [],
  },
];

vi.mock("@/client/collision-analysis/collision-analysis", () => ({
  useListCollisionChecks: () => ({ data: { data: { checks: CHECKS } }, isLoading: false }),
}));

vi.mock("@/hooks/useMetricsConfig", () => ({
  useMetricsConfig: () => ({
    qubitMetrics: [{ key: "t1", title: "T1", unit: "us", scale: 1 }],
    couplingMetrics: [{ key: "zx90_gate_fidelity", title: "ZX90", unit: "%", scale: 1 }],
  }),
}));

function renderEditor(panel: DashboardPanelModel | null = null) {
  const onSave = vi.fn();
  render(<PanelEditorDialog open panel={panel} onOpenChange={vi.fn()} onSave={onSave} />);
  return onSave;
}

describe("PanelEditorDialog", () => {
  afterEach(() => {
    cleanup();
  });

  it("stores only collision parameters that differ from their defaults", () => {
    const onSave = renderEditor();

    fireEvent.change(screen.getByLabelText("Panel type"), {
      target: { value: "collision_check" },
    });
    expect(screen.getByRole("button", { name: "Add panel" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Collision check"), { target: { value: "Type1A" } });

    // The rounded default is shown but never saved as an override.
    expect(screen.getByLabelText("adiabatic limit")).toHaveValue(
      Number(ADIABATIC_DEFAULT.toPrecision(6)),
    );
    fireEvent.change(screen.getByLabelText("cnot time (ns)"), { target: { value: "400" } });
    fireEvent.click(screen.getByLabelText("2 hops (next-nearest)"));
    fireEvent.click(screen.getByRole("button", { name: "Add panel" }));

    expect(onSave).toHaveBeenCalledWith({
      type: "collision_check",
      title: "",
      config: { check: "Type1A", params: { cnot_time: 400 }, hops: [1] },
    });
  });

  it("drops a stored override that is set back to its default", () => {
    const onSave = renderEditor({
      panel_id: "p1",
      type: "collision_check",
      title: "Proximity",
      layout: { x: 0, y: 0, w: 6, h: 4 },
      config: { check: "Type1A", params: { cnot_time: 400 }, hops: [1, 2], selection: "keep" },
    });

    const cnot = screen.getByLabelText("cnot time (ns)");
    expect(cnot).toHaveValue(400);
    fireEvent.change(cnot, { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(onSave).toHaveBeenCalledWith({
      type: "collision_check",
      title: "Proximity",
      config: { check: "Type1A", params: {}, hops: [1, 2], selection: "keep" },
    });
  });

  it("hides pair distances for qubit checks", () => {
    renderEditor();

    fireEvent.change(screen.getByLabelText("Panel type"), {
      target: { value: "collision_check" },
    });
    fireEvent.change(screen.getByLabelText("Collision check"), { target: { value: "Type0A" } });

    expect(screen.queryByLabelText("1 hop (coupled pairs)")).not.toBeInTheDocument();
    expect(screen.getByLabelText("min t1 (ns)")).toHaveValue(3000);
  });

  it("requires a metric for metric panels", () => {
    const onSave = renderEditor();

    expect(screen.getByRole("button", { name: "Add panel" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Metric"), { target: { value: "t1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add panel" }));

    expect(onSave).toHaveBeenCalledWith({
      type: "qubit_metric",
      title: "",
      config: { metric: "t1", selection_mode: "latest" },
    });
  });
});

describe("buildCollisionParams", () => {
  it("ignores blanks, invalid numbers and unknown names", () => {
    const check = CHECKS[1] as Parameters<typeof buildCollisionParams>[0];
    expect(
      buildCollisionParams(check, {
        cnot_time: "",
        adiabatic_limit: "abc",
        unknown: "3",
      }),
    ).toEqual({});
  });
});
