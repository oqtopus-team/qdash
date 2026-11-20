"use client";

import { useMemo, useState } from "react";

import { CircleAlert, Hourglass, Map as MapIcon, RotateCcw, Table2 } from "lucide-react";

import type { MetricCell, MetricScriptEvaluateResponse, ScriptDiagnostic } from "@/schemas";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { formatDateTime } from "@/lib/utils/datetime";

import { describeMetricError } from "../errors";
import { displayUnit, STATUS_LABELS } from "../format";
import { formatResolvedPeriod } from "../periods";
import { CellDetailsDialog } from "./CellDetailsDialog";
import { countByStatus, createCellColoring } from "./legend";
import { matchesDirection, PairMap, type PairDirection } from "./PairMap";
import { QubitMap } from "./QubitMap";
import { ResultTable } from "./ResultTable";

export type ResultViewMode = "map" | "table";

/** One script location; a button that jumps there when the editor is open. */
export function DiagnosticLocation({
  diagnostic,
  onJumpToLine,
}: {
  diagnostic: ScriptDiagnostic;
  onJumpToLine?: (line: number, column?: number | null) => void;
}) {
  const line = diagnostic.line ?? null;
  const where = [
    line ? `Line ${line}${diagnostic.column ? `:${diagnostic.column}` : ""}` : null,
    diagnostic.function ? `${diagnostic.function}()` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
      {where &&
        (line && onJumpToLine ? (
          <button
            type="button"
            className="link link-hover shrink-0 font-mono text-xs"
            onClick={() => onJumpToLine(line, diagnostic.column)}
          >
            {where}
          </button>
        ) : (
          <span className="shrink-0 font-mono text-xs text-base-content/70">{where}</span>
        ))}
      <span className="min-w-0 whitespace-pre-wrap break-words">{diagnostic.message}</span>
    </span>
  );
}

interface MetricErrorAlertProps {
  error: unknown;
  fallback: string;
  onRetry?: () => void;
  onJumpToLine?: (line: number, column?: number | null) => void;
}

/**
 * A failed evaluation: a full queue (429) asks to retry; a worker failure (422) lists its
 * diagnostics and the captured output; anything else shows the API's message.
 */
function MetricErrorAlert({ error, fallback, onRetry, onJumpToLine }: MetricErrorAlertProps) {
  const described = describeMetricError(error, fallback);
  if (described.queueFull) {
    return (
      <div role="alert" className="alert alert-warning alert-soft text-sm">
        <Hourglass className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{described.message}. Other evaluations are running; try again in a few seconds.</span>
        {onRetry && (
          <button type="button" className="btn btn-sm" onClick={onRetry}>
            <RotateCcw data-icon="inline-start" aria-hidden="true" />
            Retry
          </button>
        )}
      </div>
    );
  }
  return (
    <div role="alert" className="alert alert-error alert-soft items-start text-sm">
      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="flex min-w-0 flex-col gap-2">
        <span className="whitespace-pre-wrap break-words font-medium">{described.message}</span>
        {described.diagnostics.length > 0 && (
          <ul className="flex flex-col gap-1">
            {described.diagnostics.map((diagnostic, index) => (
              <li key={`${diagnostic.line ?? "x"}-${index}`}>
                <DiagnosticLocation diagnostic={diagnostic} onJumpToLine={onJumpToLine} />
              </li>
            ))}
          </ul>
        )}
        {described.log && (
          <details>
            <summary className="cursor-pointer text-xs">Script output</summary>
            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-xs">
              {described.log}
            </pre>
          </details>
        )}
        {onRetry && described.status !== 422 && (
          <button type="button" className="btn btn-sm w-fit" onClick={onRetry}>
            <RotateCcw data-icon="inline-start" aria-hidden="true" />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

function ViewToggle({
  view,
  onViewChange,
}: {
  view: ResultViewMode;
  onViewChange: (view: ResultViewMode) => void;
}) {
  return (
    <div className="join" role="group" aria-label="Result view">
      <button
        type="button"
        aria-pressed={view === "map"}
        className={`btn btn-xs join-item ${view === "map" ? "btn-active" : ""}`}
        onClick={() => onViewChange("map")}
      >
        <MapIcon data-icon="inline-start" aria-hidden="true" />
        Map
      </button>
      <button
        type="button"
        aria-pressed={view === "table"}
        className={`btn btn-xs join-item ${view === "table" ? "btn-active" : ""}`}
        onClick={() => onViewChange("table")}
      >
        <Table2 data-icon="inline-start" aria-hidden="true" />
        Table
      </button>
    </div>
  );
}

interface MetricResultViewProps {
  result: MetricScriptEvaluateResponse | undefined;
  error?: unknown;
  isLoading?: boolean;
  isFetching?: boolean;
  topologyId: string;
  view: ResultViewMode;
  /** Shows a Map/Table toggle when set. */
  onViewChange?: (view: ResultViewMode) => void;
  direction?: PairDirection;
  /** Shows the pair-map direction toggle when set. */
  onDirectionChange?: (direction: PairDirection) => void;
  /** Pair distances to show; all when omitted. */
  hops?: readonly number[];
  onRetry?: () => void;
  onJumpToLine?: (line: number, column?: number | null) => void;
  /** Dashboard panels: hide the metric and period line, which the panel footer shows. */
  compact?: boolean;
  /** Shown before anything was evaluated. */
  emptyMessage?: string;
}

/**
 * One evaluated metric: a qubit map, pair map or table of its cells, with the period
 * actually used, notices for truncated output, and the details of a selected cell.
 */
export function MetricResultView({
  result,
  error,
  isLoading = false,
  isFetching = false,
  topologyId,
  view,
  onViewChange,
  direction = "both",
  onDirectionChange,
  hops,
  onRetry,
  onJumpToLine,
  compact = false,
  emptyMessage = "Nothing evaluated yet",
}: MetricResultViewProps) {
  const [selected, setSelected] = useState<MetricCell | null>(null);
  const { colorScale } = useMetricsConfig();
  const palette = colorScale.colors;
  const coloring = useMemo(
    () => (result ? createCellColoring(result, palette) : null),
    [palette, result],
  );

  const isPair = result?.metric.target === "pair";
  const shownCells = useMemo(() => {
    if (!result) return [];
    if (!isPair) return result.cells;
    return result.cells.filter(
      (cell) => (!hops || hops.includes(cell.hops ?? 1)) && matchesDirection(cell, direction),
    );
  }, [direction, hops, isPair, result]);
  const statusCounts = useMemo(() => countByStatus(shownCells), [shownCells]);

  if (error) {
    return (
      <MetricErrorAlert
        error={error}
        fallback="Failed to evaluate the metric"
        onRetry={onRetry}
        onJumpToLine={onJumpToLine}
      />
    );
  }
  if (isLoading) {
    return (
      <div className="flex h-full min-h-24 flex-col gap-2" aria-busy="true" aria-label="Evaluating">
        <div className="skeleton h-4 w-1/3" />
        <div className="skeleton min-h-0 flex-1" />
      </div>
    );
  }
  if (!result) {
    return (
      <p className="flex h-full min-h-16 items-center justify-center text-sm text-base-content/60">
        {emptyMessage}
      </p>
    );
  }

  const unit = displayUnit(result.metric.unit);
  const summary = (["ok", "missing", "empty", "error"] as const)
    .filter((status) => statusCounts[status] > 0)
    .map((status) => `${STATUS_LABELS[status]} ${statusCounts[status]}`)
    .join(" · ");

  return (
    <div className="flex h-full min-h-0 flex-col gap-2" aria-busy={isFetching}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-base-content/60">
        {!compact ? (
          <div className="flex min-w-0 flex-col">
            <span className="truncate font-medium text-base-content">
              {result.metric.title}
              {unit ? ` (${unit})` : ""}
            </span>
            <span className="truncate">
              {formatResolvedPeriod(result.start, result.end)} · evaluated{" "}
              {formatDateTime(result.evaluated_at)}
            </span>
          </div>
        ) : (
          <span className="truncate">{summary}</span>
        )}
        {onViewChange && <ViewToggle view={view} onViewChange={onViewChange} />}
      </div>
      {!compact && summary && <p className="text-xs text-base-content/60">{summary}</p>}
      {result.truncated && (
        <div role="status" className="alert alert-warning alert-soft px-3 py-1.5 text-xs">
          The script output was cut short, or a history request was clamped to the period cap.
        </div>
      )}
      <div className="min-h-0 flex-1">
        {view === "table" ? (
          <ResultTable result={result} cells={shownCells} onSelectCell={setSelected} />
        ) : isPair ? (
          <PairMap
            result={result}
            topologyId={topologyId}
            palette={palette}
            direction={direction}
            onDirectionChange={onDirectionChange}
            hops={hops}
            onSelectCell={setSelected}
          />
        ) : (
          <QubitMap
            result={result}
            topologyId={topologyId}
            palette={palette}
            onSelectCell={setSelected}
          />
        )}
      </div>
      {!compact && result.log && (
        <details className="text-xs">
          <summary className="cursor-pointer text-base-content/60">Script output</summary>
          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded-[var(--radius-field)] bg-base-200 p-2">
            {result.log}
          </pre>
        </details>
      )}
      <CellDetailsDialog
        cell={selected}
        metric={result.metric}
        color={selected && coloring ? coloring.colorOf(selected) : undefined}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </div>
  );
}
