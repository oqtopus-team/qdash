"use client";

import { useMemo } from "react";

import {
  AnimatedCounter,
  AnimatedPercentage,
} from "@/components/ui/AnimatedCounter";

interface MetricDataItem {
  value: number | null;
  task_id?: string | null;
  execution_id?: string | null;
}

interface MetricsStatsCardsProps {
  metricData: { [key: string]: MetricDataItem } | null;
  title: string;
  unit: string;
  gridSize: number;
  metricType: "qubit" | "coupling";
}

export function MetricsStatsCards({
  metricData,
  title,
  unit,
  gridSize,
  metricType,
}: MetricsStatsCardsProps) {
  const stats = useMemo(() => {
    if (!metricData) {
      return {
        total: 0,
        withData: 0,
        coverage: 0,
        average: 0,
        min: 0,
        max: 0,
        stdDev: 0,
      };
    }

    const values = Object.values(metricData)
      .map((item) => item.value)
      .filter((v): v is number => v !== null && !isNaN(v));

    const total =
      metricType === "qubit" ? gridSize * gridSize : gridSize * gridSize * 2; // Approximate coupling count

    const withData = values.length;
    const coverage = total > 0 ? (withData / total) * 100 : 0;

    if (values.length === 0) {
      return {
        total,
        withData: 0,
        coverage: 0,
        average: 0,
        min: 0,
        max: 0,
        stdDev: 0,
      };
    }

    const sum = values.reduce((a, b) => a + b, 0);
    const average = sum / values.length;
    const min = Math.min(...values);
    const max = Math.max(...values);

    // Standard deviation
    const squaredDiffs = values.map((v) => Math.pow(v - average, 2));
    const avgSquaredDiff =
      squaredDiffs.reduce((a, b) => a + b, 0) / values.length;
    const stdDev = Math.sqrt(avgSquaredDiff);

    return {
      total,
      withData,
      coverage,
      average,
      min,
      max,
      stdDev,
    };
  }, [metricData, gridSize, metricType]);

  const getDecimals = (value: number): number => {
    if (value === 0) return 0;
    if (Math.abs(value) >= 1000) return 0;
    if (Math.abs(value) >= 1) return 2;
    return 3;
  };

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
      {/* Coverage */}
      <div className="stats shadow-sm bg-base-200">
        <div className="stat py-3 px-4">
          <div className="stat-title text-xs">Data Coverage</div>
          <div className="stat-value text-xl text-primary">
            <AnimatedPercentage
              value={stats.coverage}
              duration={800}
              decimals={1}
            />
          </div>
          <div className="stat-desc text-xs">
            <AnimatedCounter value={stats.withData} duration={600} /> /{" "}
            {stats.total} {metricType === "qubit" ? "qubits" : "couplings"}
          </div>
        </div>
      </div>

      {/* Average */}
      <div className="stats shadow-sm bg-base-200">
        <div className="stat py-3 px-4">
          <div className="stat-title text-xs">Average {title}</div>
          <div className="stat-value text-xl text-secondary">
            <AnimatedCounter
              value={stats.average}
              duration={800}
              decimals={getDecimals(stats.average)}
            />
          </div>
          <div className="stat-desc text-xs">{unit}</div>
        </div>
      </div>

      {/* Min */}
      <div className="stats shadow-sm bg-base-200">
        <div className="stat py-3 px-4">
          <div className="stat-title text-xs">Minimum</div>
          <div className="stat-value text-xl text-info">
            <AnimatedCounter
              value={stats.min}
              duration={800}
              decimals={getDecimals(stats.min)}
            />
          </div>
          <div className="stat-desc text-xs">{unit}</div>
        </div>
      </div>

      {/* Max */}
      <div className="stats shadow-sm bg-base-200">
        <div className="stat py-3 px-4">
          <div className="stat-title text-xs">Maximum</div>
          <div className="stat-value text-xl text-success">
            <AnimatedCounter
              value={stats.max}
              duration={800}
              decimals={getDecimals(stats.max)}
            />
          </div>
          <div className="stat-desc text-xs">{unit}</div>
        </div>
      </div>
    </div>
  );
}
