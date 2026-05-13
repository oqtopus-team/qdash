"use client";

import { useState, useCallback, useMemo } from "react";
import { Pencil, Save, X } from "lucide-react";

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
  editable?: boolean;
  onSave?: (params: Record<string, unknown>) => void;
  isSaving?: boolean;
  /** Map of param name -> manual override info. Shows strikethrough on original value. */
  overrides?: Record<string, ParameterOverride>;
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
  editable = false,
  onSave,
  isSaving = false,
  overrides,
}: ParametersTableProps) {
  const entries = useMemo(() => Object.entries(parameters), [parameters]);
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

  if (entries.length === 0) return null;

  return (
    <div className="border border-base-300 bg-base-100 rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-base-200 border-b border-base-300 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">{title}</span>
          <span className="badge badge-xs badge-ghost">{entries.length}</span>
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
      <table className="table table-zebra table-xs w-full">
        <thead>
          <tr>
            <th className="text-xs">Parameter</th>
            <th className="text-xs">Value</th>
            <th className="text-xs">Unit</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([key, val]) => {
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
                <td className="font-mono text-xs">
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
    </div>
  );
}
