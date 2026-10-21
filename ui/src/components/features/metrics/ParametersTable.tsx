"use client";

import { useMemo } from "react";

import { getTaskParameterUiGroup } from "@/lib/utils/task-parameters";

/** Manual override info for a parameter. */
export interface ParameterOverride {
  /** The current (overridden) value in DB */
  currentValue: number | string;
  /** When the manual edit was made */
  editedAt?: string;
}

interface ParametersTableProps {
  title: string;
  parameters: Record<string, unknown>;
  parameterDefinitions?: Record<string, unknown>;
  /** Map of param name -> manual override info. Shows strikethrough on original value. */
  overrides?: Record<string, ParameterOverride>;
}

type DatabaseUpdateStatus = "updated" | "not-updated" | "partial" | "unknown";

interface DatabaseUpdate {
  parameter_name: string;
  previous_value?: unknown;
  updated_value?: unknown;
  updated: boolean;
}

function getDatabaseUpdates(value: unknown): DatabaseUpdate[] {
  if (typeof value !== "object" || value === null || !("database_updates" in value)) return [];
  const updates = (value as Record<string, unknown>).database_updates;
  if (!Array.isArray(updates)) return [];
  return updates.filter(
    (update): update is DatabaseUpdate =>
      typeof update === "object" &&
      update !== null &&
      typeof (update as Record<string, unknown>).parameter_name === "string" &&
      typeof (update as Record<string, unknown>).updated === "boolean",
  );
}

function getDatabaseUpdateStatus(parameters: Record<string, unknown>): DatabaseUpdateStatus {
  const flags = Object.values(parameters).flatMap((value) => {
    const updates = getDatabaseUpdates(value);
    if (updates.length > 0) return updates.map((update) => update.updated);
    if (typeof value !== "object" || value === null || !("database_updated" in value)) return [];
    const flag = (value as Record<string, unknown>).database_updated;
    return typeof flag === "boolean" ? [flag] : [];
  });

  if (flags.length === 0) return "unknown";
  if (flags.every(Boolean)) return "updated";
  if (flags.every((flag) => !flag)) return "not-updated";
  return "partial";
}

function getDatabaseUpdatesLabel(updates: DatabaseUpdate[]): string {
  if (updates.every((update) => update.updated)) return "Applied to calibration database";
  if (updates.every((update) => !update.updated)) return "Not applied to calibration database";
  return "Calibration database updates";
}

export function CalibrationUpdateStatusBadge({
  parameters,
}: {
  parameters: Record<string, unknown>;
}) {
  const status = getDatabaseUpdateStatus(parameters);
  if (status === "updated") {
    return (
      <span className="badge badge-sm badge-success" title="Output applied to calibration values">
        Calibration DB updated
      </span>
    );
  }
  if (status === "not-updated") {
    return (
      <span
        className="badge badge-sm badge-info badge-soft"
        title="Output recorded as measurement history without updating calibration values"
      >
        Measurement only
      </span>
    );
  }
  if (status === "partial") {
    return (
      <span className="badge badge-sm badge-warning" title="Only some outputs updated the database">
        Partially updated
      </span>
    );
  }
  return (
    <span className="badge badge-sm badge-ghost" title="Legacy result without update metadata">
      Update status unknown
    </span>
  );
}

function formatValue(v: unknown): string {
  if (typeof v === "number") return v.toFixed(6);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v ?? "N/A");
}

/** Render a fully-expanded parameters table with manual-edit markers. */
export function ParametersTable({
  title,
  parameters,
  parameterDefinitions,
  overrides,
}: ParametersTableProps) {
  const entries = useMemo(() => Object.entries(parameters), [parameters]);
  const { regularEntries, parameterGroups } = useMemo(() => {
    const regular: [string, unknown][] = [];
    const groups = new Map<string, { collapsed: boolean; entries: [string, unknown][] }>();
    for (const entry of entries) {
      const group = getTaskParameterUiGroup(parameterDefinitions?.[entry[0]] ?? entry[1]);
      if (!group) {
        regular.push(entry);
        continue;
      }
      const existing = groups.get(group.name);
      if (existing) {
        existing.entries.push(entry);
      } else {
        groups.set(group.name, { collapsed: group.collapsed, entries: [entry] });
      }
    }
    return { regularEntries: regular, parameterGroups: [...groups.entries()] };
  }, [entries, parameterDefinitions]);
  const showsDatabaseComparison = useMemo(
    () =>
      entries.some(
        ([, value]) =>
          typeof value === "object" &&
          value !== null &&
          "database_updated" in value &&
          (value as Record<string, unknown>).database_updated === true,
      ),
    [entries],
  );
  const renderTable = (tableEntries: [string, unknown][]) => (
    <table className="table table-zebra table-xs w-full">
      <thead>
        <tr>
          <th className="text-xs">Parameter</th>
          {showsDatabaseComparison && <th className="text-xs">Previous</th>}
          <th className="text-xs">{showsDatabaseComparison ? "New" : "Value"}</th>
          <th className="text-xs">Unit</th>
        </tr>
      </thead>
      <tbody>
        {tableEntries.map(([key, val]) => {
          const paramValue =
            typeof val === "object" && val !== null && "value" in val
              ? (val as Record<string, unknown>)
              : { value: val };
          const databaseUpdates = getDatabaseUpdates(paramValue);
          const override = overrides?.[key];
          return (
            <tr key={key}>
              <td className="font-medium text-xs">
                {key}
                {override && (
                  <span
                    className="ml-1 badge badge-xs badge-warning"
                    title={
                      override.editedAt
                        ? `Manually edited at ${override.editedAt}`
                        : "Manually edited"
                    }
                  >
                    edited
                  </span>
                )}
                {databaseUpdates.length > 0 && (
                  <div
                    className="mt-2 flex flex-wrap items-center gap-1.5"
                    aria-label={`Database destinations for ${key}`}
                  >
                    <span className="text-xs font-normal text-base-content/60">
                      {getDatabaseUpdatesLabel(databaseUpdates)}:
                    </span>
                    {databaseUpdates.map((update) => (
                      <span
                        key={`${key}:${update.parameter_name}`}
                        className={`badge badge-xs font-mono ${
                          update.updated ? "badge-success badge-soft" : "badge-ghost"
                        }`}
                      >
                        {update.parameter_name}
                      </span>
                    ))}
                  </div>
                )}
              </td>
              {showsDatabaseComparison && (
                <td className="font-mono text-xs bg-error/10 text-error">
                  <span className="line-through">
                    {paramValue.database_updated === true
                      ? formatValue(paramValue.previous_database_value)
                      : "-"}
                  </span>
                </td>
              )}
              <td
                className={`font-mono text-xs ${
                  showsDatabaseComparison ? "bg-success/10 text-success font-semibold" : ""
                }`}
              >
                {override ? (
                  <span className="flex items-center gap-1.5">
                    <span className="line-through text-base-content/40">
                      {formatValue(paramValue.value)}
                    </span>
                    <span className="text-warning font-semibold">
                      {formatValue(override.currentValue)}
                    </span>
                  </span>
                ) : (
                  formatValue(paramValue.value)
                )}
              </td>
              <td className="text-xs">{String(paramValue.unit ?? "-")}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  if (entries.length === 0) return null;

  return (
    <div className="border border-base-300 bg-base-100 rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-base-200 border-b border-base-300 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">{title}</span>
          <span className="badge badge-xs badge-ghost">{entries.length}</span>
          {title === "Output Parameters" && (
            <CalibrationUpdateStatusBadge parameters={parameters} />
          )}
        </div>
      </div>
      {regularEntries.length > 0 && renderTable(regularEntries)}
      {parameterGroups.map(([groupName, group]) => (
        <details
          key={groupName}
          className="collapse collapse-arrow rounded-none border-t border-base-300 bg-base-100"
          open={!group.collapsed}
        >
          <summary className="collapse-title min-h-0 px-3 py-2 text-xs font-semibold">
            <span className="flex items-center gap-2">
              {groupName}
              <span className="badge badge-xs badge-ghost">{group.entries.length}</span>
            </span>
          </summary>
          <div className="collapse-content px-0 pb-0">{renderTable(group.entries)}</div>
        </details>
      ))}
    </div>
  );
}
