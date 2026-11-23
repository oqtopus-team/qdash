"use client";

import { useMemo, useState } from "react";

import { ArrowDown, ArrowUp, ChevronsUpDown, Copy } from "lucide-react";

import type { MetricCell, MetricCellStatus, MetricScriptEvaluateResponse } from "@/schemas";
import { useToast } from "@/components/ui/Toast";
import { copyText } from "@/lib/utils/clipboard";

import { cellName, displayUnit, formatNumber, STATUS_LABELS } from "../format";

type SortKey = "key" | "value" | "status" | "count" | "label";
type SortOrder = "asc" | "desc";

const STATUS_ORDER: Record<MetricCellStatus, number> = { error: 0, missing: 1, empty: 2, ok: 3 };

const STATUS_BADGES: Record<MetricCellStatus, string> = {
  ok: "badge-ghost",
  missing: "badge-warning badge-soft",
  empty: "badge-ghost",
  error: "badge-error badge-soft",
};

const COLUMNS: ReadonlyArray<{ key: SortKey; label: string; numeric?: boolean }> = [
  { key: "key", label: "Target" },
  { key: "value", label: "Value", numeric: true },
  { key: "status", label: "Status" },
  { key: "count", label: "Count", numeric: true },
  { key: "label", label: "Label" },
];

function cellCount(cell: MetricCell): number | null {
  const count = cell.assessment?.count;
  return typeof count === "number" ? count : null;
}

/** Numeric order of a cell key: "5" before "12", "5>6" by source, then target. */
function keyParts(cell: MetricCell): number[] {
  if (cell.source && cell.target) return [Number(cell.source), Number(cell.target)];
  return [Number(cell.qid ?? cell.key)];
}

function compareKeys(a: MetricCell, b: MetricCell): number {
  const left = keyParts(a);
  const right = keyParts(b);
  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    const diff = (left[index] ?? 0) - (right[index] ?? 0);
    if (diff !== 0 && Number.isFinite(diff)) return diff;
  }
  return a.key.localeCompare(b.key);
}

/** Compare two cells by `key`; cells without a value sort last in either order. */
function compareCells(a: MetricCell, b: MetricCell, key: SortKey, order: SortOrder): number {
  const sign = order === "asc" ? 1 : -1;
  const nullable = (left: number | string | null, right: number | string | null) => {
    if (left === null && right === null) return 0;
    if (left === null) return 1;
    if (right === null) return -1;
    if (typeof left === "number" && typeof right === "number") return sign * (left - right);
    return sign * String(left).localeCompare(String(right));
  };
  let result = 0;
  switch (key) {
    case "key":
      result = sign * compareKeys(a, b);
      break;
    case "value":
      result = nullable(
        typeof a.value === "number" ? a.value : null,
        typeof b.value === "number" ? b.value : null,
      );
      break;
    case "status":
      result = sign * (STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);
      break;
    case "count":
      result = nullable(cellCount(a), cellCount(b));
      break;
    case "label":
      result = nullable(a.label || null, b.label || null);
      break;
  }
  return result || compareKeys(a, b);
}

function csvField(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/** CSV of the cells in the order given, one row per cell. */
export function resultToCsv(cells: readonly MetricCell[], unit: string): string {
  const header = ["key", "source", "target", "hops", "value", "unit", "status", "count", "label"];
  const rows = cells.map((cell) =>
    [
      cell.key,
      cell.source ?? "",
      cell.target ?? "",
      cell.hops != null ? String(cell.hops) : "",
      typeof cell.value === "number" ? String(cell.value) : "",
      typeof cell.value === "number" ? unit : "",
      cell.status,
      cellCount(cell)?.toString() ?? "",
      cell.label ?? cell.message ?? "",
    ]
      .map(csvField)
      .join(","),
  );
  return [header.join(","), ...rows].join("\n");
}

interface ResultTableProps {
  result: MetricScriptEvaluateResponse;
  /** Cells to list; defaults to all of the result's cells. */
  cells?: readonly MetricCell[];
  onSelectCell: (cell: MetricCell) => void;
}

/** Sortable list of every cell of a result, with CSV export. */
export function ResultTable({ result, cells = result.cells, onSelectCell }: ResultTableProps) {
  const toast = useToast();
  const [sort, setSort] = useState<{ key: SortKey; order: SortOrder }>({
    key: "key",
    order: "asc",
  });
  const unit = displayUnit(result.metric.unit);
  const sorted = useMemo(
    () => [...cells].sort((a, b) => compareCells(a, b, sort.key, sort.order)),
    [cells, sort],
  );

  const toggleSort = (key: SortKey) =>
    setSort((current) =>
      current.key === key
        ? { key, order: current.order === "asc" ? "desc" : "asc" }
        : { key, order: "asc" },
    );

  const handleCopy = async () => {
    try {
      await copyText(resultToCsv(sorted, result.metric.unit));
      toast.success("Copied as CSV");
    } catch {
      toast.error("Failed to copy the table");
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-base-content/60">
          {sorted.length} {sorted.length === 1 ? "row" : "rows"}
        </span>
        <button type="button" className="btn btn-ghost btn-xs" onClick={handleCopy}>
          <Copy data-icon="inline-start" aria-hidden="true" />
          Copy CSV
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto rounded-[var(--radius-box)] border border-base-content/10">
        <table className="table table-xs table-pin-rows" data-testid="result-table">
          <thead>
            <tr>
              {COLUMNS.map((column) => {
                const active = sort.key === column.key;
                const Icon = !active ? ChevronsUpDown : sort.order === "asc" ? ArrowUp : ArrowDown;
                return (
                  <th
                    key={column.key}
                    aria-sort={
                      active ? (sort.order === "asc" ? "ascending" : "descending") : undefined
                    }
                    className={column.numeric ? "text-right" : undefined}
                  >
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 font-medium"
                      onClick={() => toggleSort(column.key)}
                    >
                      {column.label}
                      <Icon className="h-3 w-3 opacity-60" aria-hidden="true" />
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((cell) => {
              const count = cellCount(cell);
              return (
                <tr
                  key={cell.key}
                  className="hover:bg-base-200 cursor-pointer"
                  data-cell-key={cell.key}
                  onClick={() => onSelectCell(cell)}
                >
                  <td className="whitespace-nowrap font-mono">
                    <button
                      type="button"
                      className="link link-hover"
                      onClick={(event) => {
                        event.stopPropagation();
                        onSelectCell(cell);
                      }}
                    >
                      {cellName(cell)}
                    </button>
                    {cell.hops ? (
                      <span className="ml-1 text-base-content/50">{cell.hops}h</span>
                    ) : null}
                  </td>
                  <td className="text-right font-mono tabular-nums whitespace-nowrap">
                    {typeof cell.value === "number" ? (
                      <>
                        {formatNumber(cell.value)}
                        {unit && <span className="ml-1 text-base-content/50">{unit}</span>}
                      </>
                    ) : (
                      <span className="text-base-content/40">–</span>
                    )}
                  </td>
                  <td>
                    <span className={`badge badge-xs ${STATUS_BADGES[cell.status]}`}>
                      {STATUS_LABELS[cell.status]}
                    </span>
                  </td>
                  <td className="text-right font-mono tabular-nums">{count ?? ""}</td>
                  <td className="max-w-64 truncate" title={cell.label ?? cell.message ?? ""}>
                    {cell.label ?? (
                      <span className="text-base-content/60">{cell.message ?? ""}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
