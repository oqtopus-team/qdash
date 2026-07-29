"use client";

import React from "react";

import { Crosshair, RotateCcw } from "lucide-react";

/** Units readable straight off a spectroscopy map: GHz on the x axis, dB on the y axis. */
const PICKABLE_UNITS = new Set(["GHz", "dB"]);

export interface OutputParameterEditRow {
  /** Empty for single-qubit tables, which show a Parameter column instead of a Qubit column. */
  qid: string;
  name: string;
  /** Effective value: the user's override when edited, otherwise the analyzed value. */
  value: string;
  unit?: string;
  /** Calibration DB value this would replace. */
  currentValue?: number | null;
  /** Value this parameter had when the source experiment ran. */
  snapshotValue?: number | null;
  /** Value the last analysis produced, shown when the user overrode it. */
  analyzedValue?: number;
  /** True when the value comes from the user, so it is sent as a manual input. */
  edited?: boolean;
  /** Name of the parameter this one is computed from; such rows are read-only. */
  derivedFrom?: string;
}

export interface OutputParameterTableProps {
  title: string;
  description?: string;
  /** Control shown on the title row, aligned right. */
  headerAction?: React.ReactNode;
  rows: OutputParameterEditRow[];
  /** When given, the "New" column becomes an input. */
  onChange?: (qid: string, name: string, value: string) => void;
  onReset?: (qid: string, name: string) => void;
  /** True for rows belonging to the target armed to receive the next picked point. */
  isPickTarget?: (row: OutputParameterEditRow) => boolean;
  /** Rows that can start a pick. Defaults to rows whose unit is readable off an axis. */
  canPick?: (row: OutputParameterEditRow) => boolean;
  onTogglePick?: (qid: string) => void;
  /** What a single pick fills, e.g. "frequency and power". */
  pickHint?: string;
  /** Column layout: qubit-per-row (grouped by parameter) or parameter-per-row. */
  showQubit?: boolean;
  emptyMessage?: string;
}

/**
 * Current / New / Delta table for calibration output parameters, shared by the spectroscopy
 * reanalysis panel and the per-task manual editor.
 */
export function OutputParameterTable({
  title,
  description,
  headerAction,
  rows,
  onChange,
  onReset,
  isPickTarget,
  canPick,
  onTogglePick,
  pickHint,
  showQubit = true,
  emptyMessage = "No output parameters.",
}: OutputParameterTableProps) {
  // Grouping by parameter puts the qubits of one quantity side by side, which is how they are
  // compared. Ungrouped tables (a single qubit) keep the plain Parameter column.
  const groups = showQubit ? groupRowsByParameter(rows) : null;
  // The run's own value and the DB value answer different questions, so both get a column.
  const showSnapshot = rows.some(
    (row) => row.snapshotValue !== undefined && row.snapshotValue !== null,
  );
  const columnCount = (showQubit ? 4 : 5) + (showSnapshot ? 1 : 0);

  const renderCells = (row: OutputParameterEditRow) => {
    const armed = isPickTarget?.(row) ?? false;
    const nextValue = parseFloatOrNull(row.value);
    const currentValue =
      row.currentValue !== null && row.currentValue !== undefined ? row.currentValue : null;
    const delta = nextValue !== null && currentValue !== null ? nextValue - currentValue : null;

    return (
      <>
        {showQubit ? (
          <td className="font-mono">{qidLabel(row.qid)}</td>
        ) : (
          <td className="font-medium">
            {row.name}
            {row.derivedFrom && (
              <span className="ml-2 font-normal text-base-content/60">
                derived from {row.derivedFrom}
              </span>
            )}
          </td>
        )}
        {showSnapshot && (
          <td className="font-mono text-base-content/70">
            {row.snapshotValue !== null && row.snapshotValue !== undefined
              ? formatOutputValue(row.snapshotValue)
              : "-"}
          </td>
        )}
        <td className="font-mono">
          {currentValue !== null ? formatOutputValue(currentValue) : "-"}
        </td>
        <td>
          {onChange && !row.derivedFrom ? (
            <div className="flex items-center gap-1">
              <input
                // Text, not number: a number input blanks out intermediate values
                // such as "9." while typing, and changes on stray wheel scrolls.
                type="text"
                inputMode="decimal"
                aria-label={row.qid ? `Q${row.qid} ${row.name}` : row.name}
                className={`input input-xs input-bordered w-40 font-mono ${
                  nextValue === null ? "input-warning" : armed || row.edited ? "input-primary" : ""
                }`}
                value={row.value}
                placeholder="type value"
                onChange={(e) => onChange(row.qid, row.name, e.target.value)}
              />
              {onTogglePick && (canPick ?? defaultCanPick)(row) && (
                <button
                  type="button"
                  className={`btn btn-xs gap-1 whitespace-nowrap ${
                    armed ? "btn-primary" : "btn-ghost"
                  }`}
                  title={pickHint ? `Fills ${pickHint} from one click` : undefined}
                  aria-pressed={armed}
                  onClick={() => onTogglePick(row.qid)}
                >
                  <Crosshair size={12} />
                  {armed ? "Click a plot point" : "Take from plot"}
                </button>
              )}
              {row.edited && (
                <button
                  type="button"
                  className="btn btn-ghost btn-xs px-1"
                  title={
                    row.analyzedValue !== undefined
                      ? `Back to ${formatOutputValue(row.analyzedValue)}`
                      : "Back to the snapshot value"
                  }
                  aria-label={`Revert ${row.name}`}
                  onClick={() => onReset?.(row.qid, row.name)}
                >
                  <RotateCcw size={12} />
                </button>
              )}
            </div>
          ) : (
            <span className="font-mono">
              {nextValue !== null ? formatOutputValue(nextValue) : "-"}
            </span>
          )}
        </td>
        <td className="font-mono">{delta !== null ? formatSignedOutputValue(delta) : "-"}</td>
        {!showQubit && <td>{row.unit || "-"}</td>}
      </>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="text-xs font-semibold">{title}</div>
        {headerAction}
      </div>
      {description && <p className="text-xs text-base-content/60 mb-1">{description}</p>}
      {rows.length === 0 ? (
        <div className="text-xs text-base-content/60">{emptyMessage}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="table table-zebra table-xs">
            <thead>
              <tr>
                {showQubit ? <th>Qubit</th> : <th>Parameter</th>}
                {showSnapshot && (
                  <th title="Value this parameter had when the experiment ran">Snapshot</th>
                )}
                <th title="Calibration DB value now">Current</th>
                <th>New</th>
                <th>Delta</th>
                {!showQubit && <th>Unit</th>}
              </tr>
            </thead>
            {groups ? (
              groups.map((group) => (
                <tbody key={group.name}>
                  <tr className="bg-base-200">
                    <th colSpan={columnCount} className="font-medium">
                      <ParameterGroupLabel group={group} />
                    </th>
                  </tr>
                  {group.rows.map((row) => (
                    <tr key={`${row.qid}-${row.name}`}>{renderCells(row)}</tr>
                  ))}
                </tbody>
              ))
            ) : (
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.qid}-${row.name}`}>{renderCells(row)}</tr>
                ))}
              </tbody>
            )}
          </table>
        </div>
      )}
    </div>
  );
}

function defaultCanPick(row: OutputParameterEditRow): boolean {
  return PICKABLE_UNITS.has(row.unit ?? "");
}

export interface OutputParameterGroup<T> {
  name: string;
  unit?: string;
  derivedFrom?: string;
  rows: T[];
}

export function ParameterGroupLabel({ group }: { group: OutputParameterGroup<{ name: string }> }) {
  return (
    <>
      {group.name}
      {group.unit ? ` (${group.unit})` : ""}
      {group.derivedFrom && (
        <span className="ml-2 font-normal text-base-content/60">
          derived from {group.derivedFrom}
        </span>
      )}
    </>
  );
}

/** Groups rows by parameter name, keeping the order in which the parameters first appear. */
export function groupRowsByParameter<
  T extends { name: string; unit?: string; derivedFrom?: string },
>(rows: T[]): OutputParameterGroup<T>[] {
  const groups: OutputParameterGroup<T>[] = [];
  const byName = new Map<string, OutputParameterGroup<T>>();

  for (const row of rows) {
    let group = byName.get(row.name);
    if (!group) {
      group = {
        name: row.name,
        unit: row.unit,
        derivedFrom: row.derivedFrom,
        rows: [],
      };
      byName.set(row.name, group);
      groups.push(group);
    }
    group.rows.push(row);
  }

  return groups;
}

/** Qubits read as "Q4"; couplings keep their "4-5" form. */
export function qidLabel(qid: string): string {
  return qid.includes("-") ? qid : `Q${qid}`;
}

export function formatOutputValue(value: number): string {
  return Number.isFinite(value) ? Number(value.toPrecision(12)).toString() : "";
}

export function formatSignedOutputValue(value: number): string {
  const formatted = formatOutputValue(value);
  if (formatted === "" || formatted === "0") return formatted;
  return value > 0 ? `+${formatted}` : formatted;
}

export function parseFloatOrNull(s: string): number | null {
  if (s === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}
