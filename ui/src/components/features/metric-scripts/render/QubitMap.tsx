"use client";

import { useMemo } from "react";

import type { MetricCell, MetricScriptEvaluateResponse } from "@/schemas";

import { cellName, cellValueText, displayUnit, STATUS_LABELS } from "../format";
import {
  createCellColoring,
  countByStatus,
  NOT_EVALUATED_COLOR,
  readableTextColor,
} from "./legend";
import { MapLegend } from "./MapLegend";

const NO_PALETTE: readonly string[] = [];
import { CELL, MuxBoxes, onActivate, useTopologyLayout } from "./topologyLayout";

/** Gap between qubit tiles. */
const QUBIT_GAP = 4;

function cellLabel(cell: MetricCell, unit: string): string {
  const value =
    typeof cell.value === "number" ? `${cellValueText(cell)}${unit ? ` ${unit}` : ""}` : null;
  const parts = [cellName(cell), value ?? STATUS_LABELS[cell.status]];
  if (cell.label) parts.push(cell.label);
  return parts.join(": ");
}

interface QubitMapProps {
  result: MetricScriptEvaluateResponse;
  topologyId: string;
  /** Metrics colour scale, used when the metric declares no legend. */
  palette?: readonly string[];
  onSelectCell: (cell: MetricCell) => void;
}

/** Chip topology with one tile per qubit, coloured by a qubit metric's result. */
export function QubitMap({
  result,
  topologyId,
  palette = NO_PALETTE,
  onSelectCell,
}: QubitMapProps) {
  const layout = useTopologyLayout(topologyId, QUBIT_GAP);
  const coloring = useMemo(() => createCellColoring(result, palette), [palette, result]);
  const unit = displayUnit(result.metric.unit);

  const cellsByQid = useMemo(() => {
    const map = new Map<string, MetricCell>();
    for (const cell of result.cells) map.set(String(Number(cell.qid ?? cell.key)), cell);
    return map;
  }, [result.cells]);

  if (layout.isLoading) {
    return <div className="skeleton h-full min-h-24 w-full" aria-label="Loading topology" />;
  }
  if (layout.positions.size === 0) {
    return (
      <p className="py-6 text-center text-sm text-base-content/60">
        The chip topology has no qubit positions to draw
      </p>
    );
  }

  const drawn = Array.from(layout.positions.keys());
  const missingQubits = drawn.filter((qid) => !cellsByQid.has(qid)).length;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="min-h-0 w-full flex-1"
        role="group"
        aria-label={`${result.metric.title} on ${result.chip_id}`}
        data-testid="qubit-map"
      >
        <MuxBoxes boxes={layout.muxBoxes} />
        {Array.from(layout.positions.entries()).map(([qid, pos]) => {
          const cell = cellsByQid.get(qid);
          const fill = cell ? coloring.colorOf(cell) : NOT_EVALUATED_COLOR;
          const ink = readableTextColor(fill);
          const content = (
            <>
              <rect
                x={pos.x}
                y={pos.y}
                width={CELL}
                height={CELL}
                rx={6}
                fill={fill}
                strokeWidth={2}
                className={
                  cell
                    ? "stroke-transparent group-hover:stroke-base-content group-focus-visible:stroke-base-content"
                    : "stroke-transparent"
                }
                data-testid={`metric-qubit-${qid}`}
                data-status={cell?.status ?? "none"}
              />
              <text
                x={pos.x + 3}
                y={pos.y + 3}
                dominantBaseline="hanging"
                fontSize={9}
                fill={ink}
                className="font-mono"
              >
                {qid}
              </text>
              <text
                x={pos.x + CELL / 2}
                y={pos.y + CELL / 2 + 5}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={11}
                fill={ink}
                className="font-mono"
              >
                {cell ? cellValueText(cell) : ""}
              </text>
            </>
          );
          if (!cell) {
            return (
              <g key={qid} data-qid={qid}>
                <title>{`Q${qid}: no result`}</title>
                {content}
              </g>
            );
          }
          const label = cellLabel(cell, unit);
          return (
            <g
              key={qid}
              data-qid={qid}
              role="button"
              tabIndex={0}
              aria-label={label}
              className="group cursor-pointer outline-none"
              onClick={() => onSelectCell(cell)}
              onKeyDown={onActivate(() => onSelectCell(cell))}
            >
              <title>{label}</title>
              {content}
            </g>
          );
        })}
      </svg>
      <MapLegend
        legend={result.legend}
        coloring={coloring}
        drawnColors={drawn.flatMap((qid) => {
          const cell = cellsByQid.get(qid);
          return cell ? [coloring.colorOf(cell)] : [];
        })}
        extra={missingQubits > 0 ? { [NOT_EVALUATED_COLOR]: missingQubits } : undefined}
        palette={palette}
        unit={result.metric.unit}
        statusCounts={countByStatus(result.cells)}
      />
    </div>
  );
}
