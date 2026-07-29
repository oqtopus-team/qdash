"use client";

import { useMemo } from "react";

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
  /** Map of param name -> manual override info. Shows strikethrough on original value. */
  overrides?: Record<string, ParameterOverride>;
}

function formatValue(v: unknown): string {
  if (typeof v === "number") return v.toFixed(6);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v ?? "N/A");
}

/**
 * Read-only view of a parameter dict, used for input, run and output parameters alike.
 *
 * Editing lives on the task-result page, where values can be tied to the task result they
 * came from; see OutputParametersEditor.
 */
export function ParametersTable({ title, parameters, overrides }: ParametersTableProps) {
  const entries = useMemo(() => Object.entries(parameters), [parameters]);

  if (entries.length === 0) return null;

  return (
    <div className="border border-base-300 bg-base-100 rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-base-200 border-b border-base-300 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">{title}</span>
          <span className="badge badge-xs badge-ghost">{entries.length}</span>
        </div>
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
    </div>
  );
}
