import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MetricCell, MetricSeriesPoint } from "@/schemas";
import { chartTheme } from "@/lib/chartTheme";

import { MetricResultView } from "../render/MetricResultView";
import { buildSeriesTraces, describeCount, utcPlotTime } from "../render/seriesTraces";
import { parseTargets } from "../targets";
import { evaluateResponse, pairCell } from "./fixtures";

const plot = vi.hoisted(() => ({ calls: [] as Record<string, unknown>[] }));

vi.mock("@/components/charts/Plot", () => ({
  default: (props: Record<string, unknown>) => {
    plot.calls.push(props);
    return <div data-testid="plot" />;
  },
}));
vi.mock("@/hooks/useTopologyConfig", async () => {
  const { TOPOLOGY: topology } = await import("./fixtures");
  return { useTopologyConfig: () => topology };
});
vi.mock("@/hooks/useMetricsConfig", () => ({
  useMetricsConfig: () => ({ colorScale: { colors: ["#000000", "#ffffff"] } }),
}));

function point(
  day: number,
  value: number | null,
  count: number | null,
  overrides: Partial<MetricSeriesPoint> = {},
): MetricSeriesPoint {
  const start = `2026-11-${String(day).padStart(2, "0")}T00:00:00+00:00`;
  const end = `2026-11-${String(day + 1).padStart(2, "0")}T00:00:00+00:00`;
  return {
    timestamp: start,
    start,
    end,
    value,
    count,
    status: value === null ? (count ? "insufficient" : "no_data") : "ok",
    reason: value === null && !count ? "no observations" : null,
    ...overrides,
  };
}

const FORWARD = pairCell("0", "1", {
  label: "daily median",
  series: [point(12, 94, 3), point(13, null, 0), point(14, 97, 1), point(15, 96.5, 2)],
});
const REVERSE = pairCell("1", "0", {
  status: "missing",
  message: "No point has a value: 2 no_data",
  series: [point(12, null, 0), point(13, null, 0)],
});
const FAILED = pairCell("1", "2", { status: "error", message: "ZeroDivisionError" });

function trendResult(cells: MetricCell[]) {
  const base = evaluateResponse("pair", cells);
  return {
    ...base,
    metric: {
      ...base.metric,
      id: "zx90_daily_trend",
      title: "ZX90 trend",
      result: "series" as const,
    },
  };
}

afterEach(() => {
  cleanup();
  plot.calls.length = 0;
});

describe("series traces", () => {
  it("draw one categorical line per target with gaps as nulls that are never joined", () => {
    const traces = buildSeriesTraces([FORWARD, REVERSE, FAILED], "%", chartTheme(false));
    // Targets without any value are not drawn as flat or empty lines.
    expect(traces).toHaveLength(1);
    const [trace] = traces;
    expect(trace.name).toBe("Q0 → Q1 (%)");
    expect(trace.y).toEqual([94, null, 97, 96.5]);
    expect(trace.connectgaps).toBe(false);
    expect(trace.x[0]).toBe("2026-11-12 00:00:00");
    expect(trace.line.color).toBe(chartTheme(false).series[0]);
  });

  it("put the bin, value, unit and observation count in the tooltip", () => {
    const [trace] = buildSeriesTraces([FORWARD], "%", chartTheme(true));
    expect(trace.hovertemplate).toContain("<b>Q0 → Q1 (%)</b>");
    expect(trace.hovertemplate).toContain("%{y:.4~g} %");
    expect(trace.customdata[0]).toEqual([
      "2026-11-12 00:00 – 2026-11-13 00:00 UTC",
      "n = 3 observations",
      "",
    ]);
    expect(trace.customdata[1]).toEqual([
      "2026-11-13 00:00 – 2026-11-14 00:00 UTC",
      "n = 0 observations",
      "no observations",
    ]);
    // One observation is said as such rather than presented as a median of many.
    expect(trace.customdata[2][1]).toBe("n = 1 (one observation)");
    expect(describeCount(null)).toBe("observations not reported");
  });

  it("keep script text out of the tooltip markup and plot times in UTC", () => {
    const tagged = pairCell("0", "1", { series: [point(12, 1, 2, { reason: "<b>x</b>" })] });
    expect(buildSeriesTraces([tagged], "%", chartTheme(false))[0].customdata[0][2]).toBe(
      "&#60;b&#62;x&#60;/b&#62;",
    );
    expect(utcPlotTime("2026-11-16T08:30:00+09:00")).toBe("2026-11-15 23:30:00");
  });
});

describe("SeriesChart in MetricResultView", () => {
  it("charts the drawn targets and lists gaps, missing and failed targets with their reasons", () => {
    render(
      <MetricResultView
        result={trendResult([FORWARD, REVERSE, FAILED])}
        topologyId="t"
        view="timeseries"
      />,
    );
    expect(screen.getByTestId("plot")).toBeInTheDocument();
    const layout = plot.calls[0].layout as { xaxis: { title: { text: string } } };
    expect(layout.xaxis.title.text).toBe("Time (UTC)");
    const status = screen.getByRole("list", { name: "Series status" });
    expect(status).toHaveTextContent("Q0 → Q1: gaps — 1 without data");
    expect(status).toHaveTextContent("Q1 → Q0: Missing data — No point has a value: 2 no_data");
    expect(status).toHaveTextContent("Q1 → Q2: Error — ZeroDivisionError");
  });

  it("shows what a selected point rests on", () => {
    render(<MetricResultView result={trendResult([FORWARD])} topologyId="t" view="timeseries" />);
    const onClick = plot.calls[0].onClick as (event: unknown) => void;
    act(() => onClick({ points: [{ curveNumber: 0, pointIndex: 2 }] }));
    const details = screen.getByLabelText("Selected point");
    expect(details).toHaveTextContent("Q0 → Q1");
    expect(details).toHaveTextContent("2026-11-14 00:00 – 2026-11-15 00:00 UTC");
    expect(details).toHaveTextContent("97 %");
    expect(details).toHaveTextContent("n = 1 (one observation)");
  });

  it("drops a selected point when the result is evaluated again", () => {
    const first = trendResult([FORWARD]);
    const { rerender } = render(
      <MetricResultView result={first} topologyId="t" view="timeseries" />,
    );
    const onClick = plot.calls[0].onClick as (event: unknown) => void;
    act(() => onClick({ points: [{ curveNumber: 0, pointIndex: 2 }] }));
    expect(screen.getByLabelText("Selected point")).toHaveTextContent("97 %");
    // Another period, target set or a re-evaluation: the old point no longer applies.
    const later = trendResult([
      pairCell("0", "1", { series: [point(14, 91, 4)], label: "daily median" }),
    ]);
    rerender(<MetricResultView result={later} topologyId="t" view="timeseries" />);
    expect(screen.queryByLabelText("Selected point")).not.toBeInTheDocument();
    // The same result object keeps it.
    const latest = plot.calls[plot.calls.length - 1].onClick as (event: unknown) => void;
    act(() => latest({ points: [{ curveNumber: 0, pointIndex: 0 }] }));
    rerender(<MetricResultView result={later} topologyId="t" view="timeseries" />);
    expect(screen.getByLabelText("Selected point")).toHaveTextContent("91 %");
  });

  it("lists every point, gaps included, in a collapsed table with each target's inputs", () => {
    const reference = {
      metric: "zx90_gate_fidelity",
      target: "0-1",
      task_id: "t-1",
      execution_id: "e-1",
      timestamp: "2026-11-12T07:00:00+00:00",
      value: 0.94,
      unit: "a.u.",
    };
    const excluded = pairCell("0", "1", {
      label: "daily median",
      references: [reference],
      references_truncated: true,
      series: [
        point(12, 94, 3),
        point(13, null, 0, {
          status: "insufficient",
          reason: "0 of 2 observations valid; 2 outside 0-100 % left out",
        }),
      ],
    });
    render(
      <MetricResultView
        result={trendResult([excluded, REVERSE, FAILED])}
        topologyId="t"
        view="timeseries"
      />,
    );
    const summary = screen.getByText("Points as a table (4 points, gaps included)");
    const disclosure = summary.closest("details") as HTMLDetailsElement;
    // Collapsed by default, and the table is not built until it is opened.
    expect(disclosure.open).toBe(false);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    act(() => {
      disclosure.open = true;
      fireEvent(disclosure, new Event("toggle"));
    });
    const table = screen.getByRole("table", { name: "Points of Q0 → Q1" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(rows[2]).toHaveTextContent("2026-11-13 00:00 – 2026-11-14 00:00 UTC");
    expect(rows[2]).toHaveTextContent("Too few observations");
    expect(rows[2]).toHaveTextContent("0 of 2 observations valid; 2 outside 0-100 % left out");
    // A gap shows no fabricated value.
    expect(within(rows[2]).getAllByRole("cell")[2]).toHaveTextContent("–");
    expect(disclosure).toHaveTextContent("1 input (most recent only; earlier inputs were cut)");

    // An all-gap target is listed too; a failed target without points is not.
    const target = within(disclosure).getByRole("combobox");
    expect(
      within(target)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Q0 → Q1", "Q1 → Q0"]);
    fireEvent.change(target, { target: { value: "1>0" } });
    expect(screen.getByRole("table", { name: "Points of Q1 → Q0" })).toHaveTextContent("No data");

    fireEvent.change(target, { target: { value: "0>1" } });
    fireEvent.click(screen.getByRole("button", { name: "Inputs and checks" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(
      "1 input shown: the most recent only; earlier inputs were cut.",
    );
    expect(dialog).toHaveTextContent("zx90_gate_fidelity");
  });

  it("says when no selected target has a value instead of drawing an empty chart", () => {
    render(<MetricResultView result={trendResult([REVERSE])} topologyId="t" view="timeseries" />);
    expect(screen.queryByTestId("plot")).not.toBeInTheDocument();
    expect(screen.getByText("No values in this period")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Series status" })).toHaveTextContent("Missing data");
  });

  it("refuses to show a series as a map or table, and a scalar result as a chart", () => {
    render(<MetricResultView result={trendResult([FORWARD])} topologyId="t" view="map" />);
    expect(screen.getByRole("alert")).toHaveTextContent("needs the Chart view");
    expect(screen.queryByTestId("plot")).not.toBeInTheDocument();
    cleanup();
    render(
      <MetricResultView
        result={evaluateResponse("pair", [pairCell("0", "1", { value: 99 })])}
        topologyId="t"
        view="timeseries"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Show it as a map or a table");
  });
});

describe("parseTargets", () => {
  it("normalizes qubits and directed pairs and refuses everything else", () => {
    expect(parseTargets("Q00-Q01, 1>0", "pair")).toEqual({ keys: ["0>1", "1>0"], error: null });
    expect(parseTargets("Q05 6", "qubit")).toEqual({ keys: ["5", "6"], error: null });
    expect(parseTargets("", "pair").error).toBe("Select 1 to 16 directed pairs");
    expect(parseTargets("0>1 0-1", "pair").error).toBe("Q0 → Q1 is listed twice");
    expect(parseTargets("0>1", "qubit").error).toBe("“0>1” is not a qubit ID such as 5");
    const many = Array.from({ length: 17 }, (_, i) => String(i)).join(",");
    expect(parseTargets(many, "qubit").error).toBe("Select at most 16 qubits");
  });
});
