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
  valueCount: number;
  total: number;
  coveragePct: number;
  median: string;
  min: string;
  max: string;
}

function fmt(value: number | null): string {
  if (value === null) return "—";
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
        const middle = Math.floor(sorted.length / 2);
        const median = sorted.length
          ? sorted.length % 2 === 0
            ? (sorted[middle - 1] + sorted[middle]) / 2
            : sorted[middle]
          : null;
        const min = values.length ? Math.min(...values) : null;
        const max = values.length ? Math.max(...values) : null;
        const total = r.expectedTotal || values.length;
        const coverage = total > 0 ? (values.length / total) * 100 : 0;
        return {
          key: r.key,
          title: r.title,
          unit: r.unit,
          type: r.type,
          valueCount: values.length,
          total,
          coveragePct: coverage,
          median: fmt(median),
          min: fmt(min),
          max: fmt(max),
        };
      }),
    [rows],
  );

  return (
    <div className="overflow-x-auto rounded-lg border border-base-300">
      <table className="table table-sm">
        <caption className="sr-only">
          Metric coverage and distribution statistics for the selected data scope
        </caption>
        <thead>
          <tr className="bg-base-200/70 text-xs uppercase tracking-wide text-base-content/60">
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
            <tr key={`${row.type}-${row.key}`} className="hover:bg-base-200/45">
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
              <td className="min-w-40">
                <div className="flex items-center gap-2">
                  <progress
                    className="progress progress-primary h-1.5 w-20"
                    value={row.coveragePct}
                    max="100"
                    aria-label={`${row.title} coverage`}
                  />
                  <span className="whitespace-nowrap text-xs tabular-nums">
                    {row.coveragePct.toFixed(1)}% ({row.valueCount}/{row.total})
                  </span>
                </div>
              </td>
              <td className="font-medium tabular-nums">{row.median}</td>
              <td className="tabular-nums text-base-content/70">{row.min}</td>
              <td className="tabular-nums text-base-content/70">{row.max}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
