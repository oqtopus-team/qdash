"use client";

import { useState, useCallback, useMemo } from "react";
import { Pencil, Save, X } from "lucide-react";

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
  editable?: boolean;
  onSave?: (params: Record<string, unknown>) => void;
  isSaving?: boolean;
  /** Map of param name -> manual override info. Shows strikethrough on original value. */
  overrides?: Record<string, ParameterOverride>;
}

type DatabaseUpdateStatus = "updated" | "not-updated" | "partial" | "unknown";

function getDatabaseUpdateStatus(parameters: Record<string, unknown>): DatabaseUpdateStatus {
  const flags = Object.values(parameters).flatMap((value) => {
    if (typeof value !== "object" || value === null || !("database_updated" in value)) return [];
    const flag = (value as Record<string, unknown>).database_updated;
    return typeof flag === "boolean" ? [flag] : [];
  });

  if (flags.length === 0) return "unknown";
  if (flags.every(Boolean)) return "updated";
  if (flags.every((flag) => !flag)) return "not-updated";
  return "partial";
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

/** Render a fully-expanded parameters table with optional inline editing. */
export function ParametersTable({
  title,
  parameters,
  parameterDefinitions,
  editable = false,
  onSave,
  isSaving = false,
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
  const [isEditing, setIsEditing] = useState(false);
  const [editedValues, setEditedValues] = useState<Record<string, string>>({});

  const startEditing = useCallback(() => {
    const initial: Record<string, string> = {};
    for (const [key, val] of entries) {
      const paramValue =
        typeof val === "object" && val !== null && "value" in val
          ? (val as Record<string, unknown>)
          : { value: val };
      // If there's an override, start with the overridden value
      const override = overrides?.[key];
      initial[key] = override ? String(override.currentValue) : String(paramValue.value ?? "");
    }
    setEditedValues(initial);
    setIsEditing(true);
  }, [entries, overrides]);

  const cancelEditing = useCallback(() => {
    setIsEditing(false);
    setEditedValues({});
  }, []);

  const handleSave = useCallback(() => {
    if (!onSave) return;
    const updated: Record<string, unknown> = {};
    for (const [key, val] of entries) {
      const original =
        typeof val === "object" && val !== null && "value" in val
          ? (val as Record<string, unknown>)
          : { value: val };
      const newValueStr = editedValues[key];
      const parsed = Number(newValueStr);
      const newValue = isNaN(parsed) ? newValueStr : parsed;
      updated[key] = { ...original, value: newValue };
    }
    onSave(updated);
    setIsEditing(false);
  }, [onSave, entries, editedValues]);

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
                {isEditing ? (
                  <input
                    type="text"
                    className="input input-xs input-bordered w-full max-w-[140px] font-mono"
                    value={editedValues[key] ?? ""}
                    onChange={(e) =>
                      setEditedValues((prev) => ({
                        ...prev,
                        [key]: e.target.value,
                      }))
                    }
                  />
                ) : override ? (
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
        {editable && onSave && (
          <div className="flex items-center gap-1">
            {isEditing ? (
              <>
                <button
                  onClick={handleSave}
                  disabled={isSaving}
                  className="btn btn-xs btn-primary gap-1"
                >
                  {isSaving ? (
                    <span className="loading loading-spinner loading-xs" />
                  ) : (
                    <Save className="w-3 h-3" />
                  )}
                  Save
                </button>
                <button
                  onClick={cancelEditing}
                  disabled={isSaving}
                  className="btn btn-xs btn-ghost gap-1"
                >
                  <X className="w-3 h-3" />
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={startEditing}
                className="btn btn-xs btn-ghost gap-1"
                title="Edit parameters"
              >
                <Pencil className="w-3 h-3" />
                Edit
              </button>
            )}
          </div>
        )}
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
