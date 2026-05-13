"use client";

import { useMemo } from "react";

interface MetricValue {
  value: number | null;
}

interface MetricRowInput {
  key: string;
  title: string;
  unit: string;
  type: "Qubit" | "Coupling";
  data: { [key: string]: MetricValue } | null;
  expectedTotal: number;
}

interface DashboardSummaryTableProps {
  rows: MetricRowInput[];
}

interface SummaryRow {
  key: string;
  title: string;
  unit: string;
  type: "Qubit" | "Coupling";
  coverage: string;
  median: string;
  min: string;
  max: string;
}

function fmt(value: number | null): string {
  if (value === null) return "N/A";
  const abs = Math.abs(value);
  if (abs >= 100) return value.toFixed(2);
  if (abs >= 10) return value.toFixed(3);
  if (abs >= 1) return value.toFixed(4);
  return value.toFixed(5);
}

export function DashboardSummaryTable({ rows }: DashboardSummaryTableProps) {
  const summaries: SummaryRow[] = useMemo(
    () =>
      rows.map((r) => {
        const values = Object.values(r.data ?? {})
          .map((v) => v.value)
          .filter((v): v is number => v !== null && v !== undefined);
        const sorted = [...values].sort((a, b) => a - b);
        const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : null;
        const min = values.length ? Math.min(...values) : null;
        const max = values.length ? Math.max(...values) : null;
        const total = r.expectedTotal || values.length;
        const coverage = total > 0 ? (values.length / total) * 100 : 0;
        return {
          key: r.key,
          title: r.title,
          unit: r.unit,
          type: r.type,
          coverage: `${coverage.toFixed(1)}% (${values.length}/${total})`,
          median: fmt(median),
          min: fmt(min),
          max: fmt(max),
        };
      }),
    [rows],
  );

  return (
    <div className="overflow-x-auto">
      <table className="table table-zebra table-sm">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Type</th>
            <th>Unit</th>
            <th>Coverage</th>
            <th>Median</th>
            <th>Min</th>
            <th>Max</th>
          </tr>
        </thead>
        <tbody>
          {summaries.map((row) => (
            <tr key={`${row.type}-${row.key}`}>
              <td className="font-medium">{row.title}</td>
              <td>
                <span
                  className={`badge badge-sm ${
                    row.type === "Qubit" ? "badge-primary" : "badge-secondary"
                  }`}
                >
                  {row.type}
                </span>
              </td>
              <td className="text-base-content/70">{row.unit}</td>
              <td className="tabular-nums">{row.coverage}</td>
              <td className="tabular-nums">{row.median}</td>
              <td className="tabular-nums">{row.min}</td>
              <td className="tabular-nums">{row.max}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
