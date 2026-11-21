import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DashboardPanelResponse, MetricInfo, MetricScriptSummary } from "@/schemas";

import { choiceValue } from "../metricChoices";
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

const TREND: MetricInfo = {
  id: "zx90_daily_trend",
  title: "ZX90 gate fidelity trend",
  unit: "%",
  target: "pair",
  result: "series",
  hops: [1],
  parameters: {
    interval: { default: "day", kind: "choice", choices: ["day", "week"], label: "Time bin (UTC)" },
  },
  has_legend: false,
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
  summary({
    script_id: "ms_trend",
    name: "ZX90 trend",
    revision: 1,
    active_revision: 1,
    metrics: [TREND],
  }),
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

const ZX90_CHOICE = choiceValue({
  kind: "metric_script",
  script_id: "ms_zx90",
  metric_id: "zx90_median",
});

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

function collisionPanel(): DashboardPanelResponse {
  return {
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
  };
}

describe("PanelEditorDialog", () => {
  afterEach(() => {
    cleanup();
  });

  it("lists chip metrics and script metrics by source, without scripts lacking a valid revision", () => {
    renderEditor();

    const show = screen.getByLabelText("Show");
    const groups = within(show)
      .getAllByRole("group")
      .map((group) => group.getAttribute("label"));
    expect(groups).toEqual([
      "Qubit metrics",
      "Coupling metrics",
      "ZX90 median",
      "Collisions (private)",
      "ZX90 trend",
    ]);
    expect(screen.queryByRole("group", { name: "Broken" })).not.toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Median ZX90 gate fidelity (%) · per pair" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add panel" })).toBeDisabled();
    expect(screen.getByText("Choose a metric")).toBeInTheDocument();
  });

  it("adds a script metric with a period and view, pinned to the active revision", () => {
    const onSave = renderEditor();

    fireEvent.change(screen.getByLabelText("Show"), { target: { value: ZX90_CHOICE } });
    // The title follows the metric; period and view are in the main form.
    expect(screen.getByLabelText("Title")).toHaveValue("Median ZX90 gate fidelity");
    expect(screen.getByLabelText("Days back from now")).toHaveValue(14);
    expect(screen.getByLabelText("View")).toHaveValue("map");
    // A single declared hop hides the distance choice; the pin is in the advanced section.
    expect(screen.queryByLabelText("2 hops (next-nearest)")).not.toBeInTheDocument();
    expect(screen.getByTestId("panel-revision")).toHaveTextContent("pinned to r2");
    expect(
      screen.queryByRole("button", { name: "Use updated definition" }),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Minimum observations"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Direction"), { target: { value: "forward" } });
    fireEvent.change(screen.getByLabelText("View"), { target: { value: "table" } });
    fireEvent.click(screen.getByRole("button", { name: "Add panel" }));

    expect(onSave).toHaveBeenCalledWith({
      type: "metric_script",
      title: "Median ZX90 gate fidelity",
      config: {
        script_id: "ms_zx90",
        metric_id: "zx90_median",
        script_revision: 2,
        period: { kind: "relative", days: 14 },
        params: { min_samples: 5 },
        view: "table",
        targets: [],
        direction: "forward",
        hops: [1],
      },
      script_name: "ZX90 median",
      latest_revision: 2,
    });
  });

  it("spells out the chosen metric and keeps the actions outside the scrolling fields", () => {
    renderEditor();

    const show = screen.getByLabelText("Show");
    fireEvent.change(show, { target: { value: ZX90_CHOICE } });

    // The closed select can clip a long name; the full choice and its source stay readable.
    const described = document.getElementById(show.getAttribute("aria-describedby") ?? "");
    expect(described).toHaveTextContent("Median ZX90 gate fidelity (%) · per pair · ZX90 median");
    expect(show).toHaveAttribute("title", "Median ZX90 gate fidelity (%) · per pair");

    const body = screen.getByTestId("panel-editor-body");
    expect(body).toContainElement(show);
    expect(body).not.toContainElement(screen.getByRole("button", { name: "Add panel" }));
    expect(body).not.toContainElement(screen.getByRole("button", { name: "Cancel" }));
  });

  it("keeps a typed title when the metric changes", () => {
    renderEditor();

    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Fidelity watch" } });
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: ZX90_CHOICE } });

    expect(screen.getByLabelText("Title")).toHaveValue("Fidelity watch");
  });

  it("keeps the pinned revision of an existing panel until the update is requested", () => {
    const onSave = renderEditor(collisionPanel(), true);

    // The pinned catalog is listed, with stored parameters visible in the open advanced section.
    expect(screen.getByLabelText("Show")).toHaveValue(
      choiceValue({ kind: "metric_script", script_id: "ms_collision", metric_id: "type1a" }),
    );
    expect(screen.getByTestId("panel-revision")).toHaveTextContent("pinned to r4 · active r5");
    expect(screen.getByRole("button", { name: "Use updated definition" })).toBeInTheDocument();
    expect(screen.getByLabelText("window (GHz)")).toHaveValue(0.8);
    // A private script cannot be used on a dashboard shared with the project.
    const alerts = screen.getAllByRole("status");
    expect(alerts[0]).toHaveTextContent("This metric comes from a private script");
    expect(
      within(alerts[0]).getByRole("link", { name: "Open the script's settings" }),
    ).toHaveAttribute("href", "/dashboards/scripts/ms_collision#metric-script-settings");

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
        targets: [],
        direction: "both",
        hops: [1],
      },
      script_name: "Collisions",
      latest_revision: 5,
    });
  });

  it("charts a series metric for typed targets only, with no map or table offered", () => {
    const onSave = renderEditor();
    expect(
      screen.getByRole("option", { name: "ZX90 gate fidelity trend (%) · per pair · time series" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Show"), {
      target: {
        value: choiceValue({
          kind: "metric_script",
          script_id: "ms_trend",
          metric_id: "zx90_daily_trend",
        }),
      },
    });

    const view = screen.getByLabelText("View");
    expect(view).toHaveValue("timeseries");
    expect(view).toBeDisabled();
    expect(within(view).queryByRole("option", { name: "Map" })).not.toBeInTheDocument();
    // Map-only settings are hidden; nothing defaults to every pair of the chip.
    expect(screen.queryByLabelText("Direction")).not.toBeInTheDocument();
    expect(screen.getByText("Select 1 to 16 directed pairs")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add panel" })).toBeDisabled();

    const targets = screen.getByLabelText("Directed pairs");
    fireEvent.change(targets, { target: { value: "0>1, 5" } });
    expect(screen.getAllByText("“5” is not a directed pair such as 0>1").length).toBeGreaterThan(0);
    fireEvent.change(targets, { target: { value: "Q00-Q01, 1>0" } });

    // A fixed range over 400 days would chart the clamped-away bins as gaps: refused here.
    fireEvent.change(screen.getByLabelText("Period"), { target: { value: "absolute" } });
    fireEvent.change(screen.getByLabelText("Start"), { target: { value: "2025-01-01T00:00" } });
    fireEvent.change(screen.getByLabelText("End"), { target: { value: "2026-11-01T00:00" } });
    // Shown at the field and as the reason the footer action is disabled.
    expect(screen.getAllByText(/A time series covers at most 400 days/)).toHaveLength(2);
    expect(screen.getByLabelText("Start")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Add panel" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Start"), { target: { value: "2026-10-01T00:00" } });
    expect(screen.queryByText(/A time series covers at most 400 days/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add panel" }));

    expect(onSave.mock.calls[0][0].config).toMatchObject({
      script_id: "ms_trend",
      metric_id: "zx90_daily_trend",
      script_revision: 1,
      view: "timeseries",
      targets: ["0>1", "1>0"],
      period: { kind: "absolute" },
    });
  });

  it("moves the pin only on Use updated definition", () => {
    const onSave = renderEditor(collisionPanel());

    fireEvent.click(screen.getByRole("button", { name: "Use updated definition" }));
    expect(screen.getByTestId("panel-revision")).toHaveTextContent("pinned to r5");
    expect(
      screen.queryByRole("button", { name: "Use updated definition" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onSave.mock.calls[0][0].config).toMatchObject({
      script_id: "ms_collision",
      metric_id: "type1a",
      script_revision: 5,
      params: { window: 0.8 },
    });
  });

  it("blocks invalid parameters and periods", () => {
    renderEditor();
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: ZX90_CHOICE } });

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

  it("saves a chip metric with its value selection and no period", () => {
    const onSave = renderEditor();

    fireEvent.change(screen.getByLabelText("Show"), {
      target: { value: choiceValue({ kind: "qubit_metric", metric: "t1" }) },
    });
    expect(screen.queryByLabelText("Days back from now")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Value selection"), { target: { value: "best" } });
    fireEvent.click(screen.getByRole("button", { name: "Add panel" }));

    expect(onSave).toHaveBeenCalledWith({
      type: "qubit_metric",
      title: "T1",
      config: { metric: "t1", selection_mode: "best" },
      script_name: null,
      latest_revision: null,
    });
  });

  it("opens an existing coupling metric panel on its metric", () => {
    renderEditor({
      panel_id: "p2",
      type: "coupling_metric",
      title: "",
      layout: { x: 0, y: 0, w: 6, h: 4 },
      config: { metric: "zx90_gate_fidelity", selection_mode: "average" },
    });

    expect(screen.getByLabelText("Show")).toHaveValue(
      choiceValue({ kind: "coupling_metric", metric: "zx90_gate_fidelity" }),
    );
    expect(screen.getByLabelText("Value selection")).toHaveValue("average");
  });

  it("switches to a note with the keyboard-reachable panel kind radios", () => {
    const onSave = renderEditor();

    fireEvent.click(screen.getByRole("radio", { name: "Note" }));
    expect(screen.queryByLabelText("Show")).not.toBeInTheDocument();
    expect(screen.getByText("Write the note content")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Write Markdown"), {
      target: { value: "Review rule" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add panel" }));

    expect(onSave).toHaveBeenCalledWith({
      type: "markdown",
      title: "",
      config: { content: "Review rule" },
      script_name: null,
      latest_revision: null,
    });
  });
});
