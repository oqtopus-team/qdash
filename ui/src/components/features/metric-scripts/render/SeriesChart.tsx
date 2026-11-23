"use client";

import { useMemo, useState } from "react";

import type { Data, PlotMouseEvent } from "plotly.js";

import type { MetricCell, MetricScriptEvaluateResponse, MetricSeriesPoint } from "@/schemas";
import Plot from "@/components/charts/Plot";
import { EmptyState } from "@/components/ui/EmptyState";
import { useIsDarkTheme } from "@/contexts/ThemeContext";
import { chartTheme } from "@/lib/chartTheme";

import { cellName, countLabel, displayUnit, formatNumber, STATUS_LABELS } from "../format";
import {
  buildSeriesTraces,
  describeBin,
  describeCount,
  describeGaps,
  plottedCells,
} from "./seriesTraces";

const POINT_STATUS_LABELS: Record<MetricSeriesPoint["status"], string> = {
  ok: "Value",
  no_data: "No data",
  insufficient: "Too few observations",
};

interface SelectedPoint {
  cell: MetricCell;
  point: MetricSeriesPoint;
}

/** A selected point and the result it was picked from; a new result drops the selection. */
interface Selection extends SelectedPoint {
  result: MetricScriptEvaluateResponse;
}

function pointValueText(point: MetricSeriesPoint, unit: string): string {
  return point.status === "ok" && typeof point.value === "number"
    ? `${formatNumber(point.value)}${unit ? ` ${unit}` : ""}`
    : "–";
}

/**
 * Every point of one target as a table, gaps included: the only way to read a gap's bin,
 * count and reason, since a gap has no marker to hover or select.
 */
function PointTable({ cell, unit }: { cell: MetricCell; unit: string }) {
  const points = cell.series ?? [];
  return (
    <div className="max-h-64 overflow-auto rounded-[var(--radius-box)] border border-base-content/10">
      <table className="table table-xs table-pin-rows">
        <caption className="sr-only">Points of {cellName(cell)}</caption>
        <thead>
          <tr>
            <th scope="col">Time bin (UTC)</th>
            <th scope="col">Status</th>
            <th scope="col" className="text-right">
              Value
            </th>
            <th scope="col" className="text-right">
              n
            </th>
            <th scope="col">Note</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.timestamp}>
              <td className="whitespace-nowrap font-mono">{describeBin(point)}</td>
              <td className={point.status === "ok" ? undefined : "text-base-content/70"}>
                {POINT_STATUS_LABELS[point.status]}
              </td>
              <td className="text-right font-mono tabular-nums whitespace-nowrap">
                {pointValueText(point, unit)}
              </td>
              <td className="text-right font-mono tabular-nums">
                {typeof point.count === "number" ? point.count : "–"}
              </td>
              <td className="break-words">{point.reason ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Collapsed by default: a table of every point of one selected target, with the target's
 * inputs one click away. The table is only built while the disclosure is open.
 */
function PointsDisclosure({
  cells,
  unit,
  onSelectCell,
}: {
  cells: MetricCell[];
  unit: string;
  onSelectCell?: (cell: MetricCell) => void;
}) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);
  const cell = cells.find((item) => item.key === chosen) ?? cells[0];
  if (!cell) return null;
  const total = cells.reduce((sum, item) => sum + (item.series?.length ?? 0), 0);
  return (
    <details
      className="text-xs"
      open={open}
      onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer text-base-content/60">
        Points as a table ({countLabel(total, "point")}, gaps included)
      </summary>
      {open && (
        <div className="mt-1 flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            {cells.length > 1 && (
              <label className="flex items-center gap-1.5">
                <span className="text-base-content/60">Target</span>
                <select
                  className="select select-xs w-auto"
                  value={cell.key}
                  onChange={(event) => setChosen(event.target.value)}
                >
                  {cells.map((item) => (
                    <option key={item.key} value={item.key}>
                      {cellName(item)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <span className="text-base-content/60">
              {countLabel(cell.references?.length ?? 0, "input")}
              {cell.references_truncated ? " (most recent only; earlier inputs were cut)" : ""}
            </span>
            {onSelectCell && (
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                onClick={() => onSelectCell(cell)}
              >
                Inputs and checks
              </button>
            )}
          </div>
          <PointTable cell={cell} unit={unit} />
        </div>
      )}
    </details>
  );
}

/** What a selected point rests on: its bin, value, count, status and the script's reason. */
function PointDetails({ selected, unit }: { selected: SelectedPoint; unit: string }) {
  const { cell, point } = selected;
  return (
    <dl
      className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 rounded-[var(--radius-field)] bg-base-200 px-3 py-2 text-xs"
      aria-label="Selected point"
    >
      <dt className="text-base-content/60">Target</dt>
      <dd>{cellName(cell)}</dd>
      <dt className="text-base-content/60">Time bin</dt>
      <dd>{describeBin(point)}</dd>
      <dt className="text-base-content/60">{POINT_STATUS_LABELS[point.status]}</dt>
      <dd>
        {point.status === "ok" && typeof point.value === "number"
          ? pointValueText(point, unit)
          : "Gap: not drawn and not joined to its neighbours"}
      </dd>
      <dt className="text-base-content/60">Observations</dt>
      <dd>{describeCount(point.count)}</dd>
      {point.reason && (
        <>
          <dt className="text-base-content/60">Note</dt>
          <dd className="break-words">{point.reason}</dd>
        </>
      )}
    </dl>
  );
}

/**
 * A series metric's result: one line per selected target, in categorical colors with the
 * target and unit in the legend. Gaps break the line; nothing is interpolated. Targets
 * without a value, or that failed, are listed with their status and message instead of
 * being drawn, and selecting a point shows what it rests on. A collapsed table lists every
 * point, gaps included, with each target's inputs.
 */
export function SeriesChart({
  result,
  onSelectCell,
}: {
  result: MetricScriptEvaluateResponse;
  /** Opens the details (inputs, checks) of one target. */
  onSelectCell?: (cell: MetricCell) => void;
}) {
  const isDark = useIsDarkTheme();
  const theme = chartTheme(isDark);
  const unit = displayUnit(result.metric.unit);
  const traces = useMemo(
    () => buildSeriesTraces(result.cells, unit, theme),
    [result.cells, theme, unit],
  );
  const drawn = useMemo(() => plottedCells(result.cells), [result.cells]);
  const notDrawn = result.cells.filter((cell) => !drawn.includes(cell));
  const tabulated = result.cells.filter((cell) => (cell.series ?? []).length > 0);
  const [selection, setSelection] = useState<Selection | null>(null);
  // A point picked from an earlier result (another period, target set or evaluation) is
  // not shown against the new one.
  const selected = selection?.result === result ? selection : null;

  const handleClick = (event: PlotMouseEvent) => {
    const clicked = event.points?.[0];
    if (!clicked) return;
    const cell = drawn[clicked.curveNumber];
    const point = cell?.series?.[clicked.pointIndex];
    if (cell && point) setSelection({ result, cell, point });
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {traces.length === 0 ? (
        <div className="flex min-h-24 flex-1 items-center justify-center">
          <EmptyState
            size="sm"
            emoji="chart"
            title="No values in this period"
            description="No selected target has a point with a value; see the reasons below."
          />
        </div>
      ) : (
        <div className="min-h-40 flex-1" data-testid="series-chart">
          <Plot
            data={traces as unknown as Data[]}
            layout={{
              autosize: true,
              margin: { l: 56, r: 16, t: 8, b: 40 },
              hovermode: "closest",
              showlegend: true,
              legend: { orientation: "h", y: -0.18 },
              xaxis: { type: "date", title: { text: "Time (UTC)" } },
              yaxis: {
                title: { text: unit ? `${result.metric.title} (${unit})` : result.metric.title },
              },
            }}
            config={{ displayModeBar: false, responsive: true }}
            useResizeHandler
            style={{ width: "100%", height: "100%" }}
            onClick={handleClick}
          />
        </div>
      )}
      {selected && <PointDetails selected={selected} unit={unit} />}
      {(notDrawn.length > 0 || drawn.some((cell) => describeGaps(cell.series ?? []))) && (
        <ul
          className="flex max-h-28 flex-col gap-0.5 overflow-auto text-xs"
          aria-label="Series status"
        >
          {drawn.map((cell) => {
            const gaps = describeGaps(cell.series ?? []);
            return gaps ? (
              <li key={cell.key} className="text-base-content/60">
                {cellName(cell)}: gaps — {gaps}
              </li>
            ) : null;
          })}
          {notDrawn.map((cell) => (
            <li
              key={cell.key}
              className={cell.status === "error" ? "text-error" : "text-base-content/70"}
            >
              {cellName(cell)}: {STATUS_LABELS[cell.status]}
              {cell.message ? ` — ${cell.message}` : ""}
            </li>
          ))}
        </ul>
      )}
      {tabulated.length > 0 && (
        <PointsDisclosure
          key={tabulated.map((cell) => cell.key).join(",")}
          cells={tabulated}
          unit={unit}
          onSelectCell={onSelectCell}
        />
      )}
    </div>
  );
}
