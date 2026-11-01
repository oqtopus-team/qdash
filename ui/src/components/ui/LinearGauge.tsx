"use client";

import { Target } from "lucide-react";

interface LinearGaugeProps {
  value: number; // 0-100
  current: number;
  total: number;
  className?: string;
  label?: string;
}

export function LinearGauge({
  value,
  current,
  total,
  className = "",
  label = "Data Coverage",
}: LinearGaugeProps) {
  // Coverage is measured data: show the actual value without counting through false states.
  const coverage = Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 0;

  // Color based on value
  const getBarColor = (val: number) => {
    if (val >= 95) return "progress-success";
    if (val >= 80) return "progress-info";
    if (val >= 50) return "progress-warning";
    return "progress-error";
  };

  const getTextColor = (val: number) => {
    if (val >= 95) return "text-success";
    if (val >= 80) return "text-info";
    if (val >= 50) return "text-warning";
    return "text-error";
  };

  const getBadge = (val: number): { text: string } | null => {
    if (val >= 100) return { text: "Perfect" };
    if (val >= 95) return { text: "Gold" };
    if (val >= 80) return { text: "Silver" };
    if (val >= 50) return { text: "Bronze" };
    return null;
  };

  const badge = getBadge(coverage);
  const remaining = total - current;

  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-2 ${className}`}>
      <span className="text-xs text-base-content/60 whitespace-nowrap">{label}</span>

      {/* Gauge bar */}
      <progress
        className={`progress h-2 min-w-24 max-w-32 flex-1 ${getBarColor(coverage)}`}
        value={coverage}
        max={100}
        aria-label={label}
        aria-valuetext={`${coverage.toFixed(1)}%, ${current} of ${total}`}
      />

      {/* Percentage and count */}
      <span
        className={`text-sm font-medium tabular-nums whitespace-nowrap ${getTextColor(coverage)}`}
      >
        {coverage.toFixed(1)}%
      </span>
      <span className="text-xs text-base-content/50 tabular-nums whitespace-nowrap">
        ({current}/{total})
      </span>

      {/* Badge or remaining */}
      {current === 0 ? (
        <span className="text-xs text-base-content/40 whitespace-nowrap">No data</span>
      ) : badge ? (
        <span className="text-xs text-base-content/60 whitespace-nowrap">{badge.text}</span>
      ) : (
        <span className="flex items-center gap-1 text-xs text-base-content/50 tabular-nums whitespace-nowrap">
          <Target className="h-3.5 w-3.5" aria-hidden="true" />
          {remaining} to go
        </span>
      )}
    </div>
  );
}
