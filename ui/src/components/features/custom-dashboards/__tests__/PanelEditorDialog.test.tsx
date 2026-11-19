import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DashboardPanelResponse, MetricInfo, MetricScriptSummary } from "@/schemas";

import { PanelEditorDialog } from "../PanelEditorDialog";

const ZX90: MetricInfo = {
  id: "zx90_median",
  title: "Median ZX90 gate fidelity",
  unit: "%",
  target: "pair",
  hops: [1],
  parameters: {
    min_samples: { default: 3, kind: "integer", min: 1, step: 1, label: "Minimum observations" },
  },
  has_legend: true,
};

const COLLISION: MetricInfo = {
  id: "type1a",
  title: "Type1A",
  unit: "dimensionless",
  target: "pair",
  hops: [1, 2],
  parameters: {
    window: { default: 0.5, kind: "number", min: 0, unit: "GHz", label: "window" },
    strict: { default: false, kind: "boolean", label: "Strict" },
  },
  has_legend: true,
};

function summary(overrides: Partial<MetricScriptSummary>): MetricScriptSummary {
  return {
    script_id: "ms_zx90",
    project_id: "project-1",
    name: "ZX90 median",
    description: "",
    visibility: "project",
    status: "valid",
    revision: 2,
    active_revision: 2,
    metrics: [ZX90],
    template_id: null,
    owner_username: "alice",
    owner_user_id: "user-alice",
    can_edit: true,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
    ...overrides,
  };
}

const SCRIPTS = [
  summary({}),
  summary({
    script_id: "ms_collision",
    name: "Collisions",
    visibility: "private",
    revision: 5,
    active_revision: 5,
    metrics: [COLLISION],
  }),
  summary({ script_id: "ms_broken", name: "Broken", status: "invalid", active_revision: null }),
];

vi.mock("@/client/metric-script/metric-script", () => ({
  useListMetricScripts: () => ({
    data: { data: { scripts: SCRIPTS, total: SCRIPTS.length } },
    isLoading: false,
  }),
  useGetMetricScript: (scriptId: string) => ({
    data:
      scriptId === "ms_collision"
        ? {
            data: {
              ...SCRIPTS[1],
              revisions: [
                { revision: 4, source: "", created_at: "", status: "valid", metrics: [COLLISION] },
              ],
            },
          }
        : undefined,
    isLoading: false,
  }),
}));

vi.mock("@/hooks/useMetricsConfig", () => ({
  useMetricsConfig: () => ({
    qubitMetrics: [{ key: "t1", title: "T1", unit: "us", scale: 1 }],
    couplingMetrics: [{ key: "zx90_gate_fidelity", title: "ZX90", unit: "%", scale: 1 }],
  }),
}));

function renderEditor(panel: DashboardPanelResponse | null = null, dashboardShared = false) {
  const onSave = vi.fn();
  render(
    <PanelEditorDialog
      open
      panel={panel}
      dashboardShared={dashboardShared}
      onOpenChange={vi.fn()}
      onSave={onSave}
    />,
  );
  return onSave;
}

describe("PanelEditorDialog", () => {
  afterEach(() => {
    cleanup();
  });

  it("pins a new metric script panel to the script's active revision", () => {
    const onSave = renderEditor();

    fireEvent.change(screen.getByLabelText("Panel type"), { target: { value: "metric_script" } });
    expect(screen.getByRole("button", { name: "Add panel" })).toBeDisabled();
    // Scripts without a valid revision cannot be chosen.
    expect(screen.queryByRole("option", { name: "Broken" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Script"), { target: { value: "ms_zx90" } });
    expect(screen.getByText("Pinned to r2")).toBeInTheDocument();
    // The only metric is chosen; its declared single hop hides the distance choice.
    expect(screen.getByLabelText("Metric")).toHaveValue("zx90_median");
    expect(screen.queryByLabelText("2 hops (next-nearest)")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Minimum observations"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Direction"), { target: { value: "forward" } });
    fireEvent.change(screen.getByLabelText("View"), { target: { value: "table" } });
    fireEvent.click(screen.getByRole("button", { name: "Add panel" }));

    expect(onSave).toHaveBeenCalledWith({
      type: "metric_script",
      title: "",
      config: {
        script_id: "ms_zx90",
        metric_id: "zx90_median",
        script_revision: 2,
        period: { kind: "relative", days: 14 },
        params: { min_samples: 5 },
        view: "table",
        direction: "forward",
        hops: [1],
      },
      script_name: "ZX90 median",
      latest_revision: 2,
    });
  });

  it("keeps the pinned revision of an existing panel and drops parameters set to default", () => {
    const onSave = renderEditor(
      {
        panel_id: "p1",
        type: "metric_script",
        title: "Collisions",
        layout: { x: 0, y: 0, w: 6, h: 4 },
        config: {
          script_id: "ms_collision",
          metric_id: "type1a",
          script_revision: 4,
          period: { kind: "relative", days: 7 },
          params: { window: 0.8 },
          view: "map",
          direction: "both",
          hops: [1, 2],
        },
        script_name: "Collisions",
        latest_revision: 5,
      },
      true,
    );

    expect(screen.getByText("Pinned to r4")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use active r5" })).toBeInTheDocument();
    // A private script cannot be used on a dashboard shared with the project.
    expect(screen.getByRole("status")).toHaveTextContent("This script is private");
    expect(screen.getByLabelText("window (GHz)")).toHaveValue(0.8);

    fireEvent.change(screen.getByLabelText("window (GHz)"), { target: { value: "0.5" } });
    fireEvent.click(screen.getByLabelText("Strict"));
    fireEvent.click(screen.getByLabelText("2 hops (next-nearest)"));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(onSave).toHaveBeenCalledWith({
      type: "metric_script",
      title: "Collisions",
      config: {
        script_id: "ms_collision",
        metric_id: "type1a",
        script_revision: 4,
        period: { kind: "relative", days: 7 },
        params: { strict: true },
        view: "map",
        direction: "both",
        hops: [1],
      },
      script_name: "Collisions",
      latest_revision: 5,
    });
  });

  it("blocks invalid parameters and periods", () => {
    renderEditor();
    fireEvent.change(screen.getByLabelText("Panel type"), { target: { value: "metric_script" } });
    fireEvent.change(screen.getByLabelText("Script"), { target: { value: "ms_zx90" } });

    fireEvent.change(screen.getByLabelText("Minimum observations"), { target: { value: "0" } });
    expect(screen.getByText("Must be at least 1")).toBeInTheDocument();
    expect(screen.getByText("Fix the highlighted parameters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add panel" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Minimum observations"), { target: { value: "2.5" } });
    expect(screen.getByText("Enter a whole number")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Minimum observations"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Days back from now"), { target: { value: "500" } });
    expect(screen.getAllByText("Enter whole days between 1 and 400").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Add panel" })).toBeDisabled();
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
      script_name: null,
      latest_revision: null,
    });
  });
});
