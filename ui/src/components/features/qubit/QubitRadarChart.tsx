"use client";

import { useMemo } from "react";

import { PlotCard } from "@/components/charts/PlotCard";
import { ErrorCard } from "@/components/ui/ErrorCard";

interface QubitParameter {
  name: string;
  value: number;
  unit: string;
  maxValue: number; // For normalization to 0-100 scale
  color: string;
  icon: string;
}

interface TaskDataEntry {
  output_parameters?: Record<string, unknown> | null;
}

interface QubitRadarChartProps {
  qubitId: string;
  taskData: Record<string, TaskDataEntry | null>;
  isLoading?: boolean;
  error?: Error | null;
}

// Parameter configuration for radar chart display
const PARAMETER_CONFIG = {
  t1: {
    name: "T1 Coherence",
    unit: "µs",
    maxValue: 200, // 200µs is excellent T1
    color: "#ff6b6b",
    icon: "⏰",
    extractValue: (data: TaskDataEntry) => {
      const param = data?.output_parameters?.t1;
      if (typeof param === "number") return param;
      if (typeof param === "object" && param !== null && "value" in param) {
        const val = (param as { value?: unknown }).value;
        if (typeof val === "number") return val;
      }
      return null;
    },
  },
  t2_echo: {
    name: "T2 Echo",
    unit: "µs",
    maxValue: 400, // 400µs is excellent T2 Echo
    color: "#4ecdc4",
    icon: "📡",
    extractValue: (data: TaskDataEntry) => {
      const param = data?.output_parameters?.t2_echo;
      if (typeof param === "number") return param;
      if (typeof param === "object" && param !== null && "value" in param) {
        const val = (param as { value?: unknown }).value;
        if (typeof val === "number") return val;
      }
      return null;
    },
  },
  t2_star: {
    name: "T2 Star",
    unit: "µs",
    maxValue: 100, // 100µs is excellent T2*
    color: "#45b7d1",
    icon: "✨",
    extractValue: (data: TaskDataEntry) => {
      const param = data?.output_parameters?.t2_star;
      if (typeof param === "number") return param;
      if (typeof param === "object" && param !== null && "value" in param) {
        const val = (param as { value?: unknown }).value;
        if (typeof val === "number") return val;
      }
      return null;
    },
  },
  gate_fidelity: {
    name: "Gate Fidelity",
    unit: "",
    maxValue: 1.0, // 100% fidelity
    color: "#96ceb4",
    icon: "🎯",
    extractValue: (data: TaskDataEntry) => {
      const param = data?.output_parameters?.average_gate_fidelity;
      if (typeof param === "number") return param;
      if (typeof param === "object" && param !== null && "value" in param) {
        const val = (param as { value?: unknown }).value;
        if (typeof val === "number") return val;
      }
      return null;
    },
  },
  readout_fidelity: {
    name: "Readout Fidelity",
    unit: "",
    maxValue: 1.0, // 100% fidelity
    color: "#feca57",
    icon: "📊",
    extractValue: (data: TaskDataEntry) => {
      const param = data?.output_parameters?.average_readout_fidelity;
      if (typeof param === "number") return param;
      if (typeof param === "object" && param !== null && "value" in param) {
        const val = (param as { value?: unknown }).value;
        if (typeof val === "number") return val;
      }
      return null;
    },
  },
};

// Task name mapping
const TASK_MAPPING = {
  t1: "CheckT1",
  t2_echo: "CheckT2Echo",
  t2_star: "CheckRamsey",
  gate_fidelity: "RandomizedBenchmarking",
  readout_fidelity: "ReadoutClassification",
};

export function QubitRadarChart({
  qubitId,
  taskData,
  isLoading = false,
  error,
}: QubitRadarChartProps) {
  // Extract and normalize parameters
  const radarData = useMemo(() => {
    const parameters: QubitParameter[] = [];

    Object.entries(PARAMETER_CONFIG).forEach(([key, config]) => {
      const taskName = TASK_MAPPING[key as keyof typeof TASK_MAPPING];
      const data = taskData[taskName];

      if (data) {
        const rawValue = config.extractValue(data);
        if (rawValue !== null && !isNaN(rawValue) && rawValue > 0) {
          // Normalize to 0-100 scale for radar chart
          const normalizedValue = Math.min(
            (rawValue / config.maxValue) * 100,
            100,
          );

          parameters.push({
            name: config.name,
            value: normalizedValue,
            unit: config.unit,
            maxValue: config.maxValue,
            color: config.color,
            icon: config.icon,
          });
        }
      }
    });

    return parameters;
  }, [taskData]);

  // Generate radar chart data for Plotly
  const plotData = useMemo(() => {
    if (radarData.length === 0) return [];

    // Create the radar chart trace
    const trace = {
      type: "scatterpolar" as const,
      r: [...radarData.map((p) => p.value), radarData[0]?.value], // Close the polygon
      theta: [...radarData.map((p) => p.name), radarData[0]?.name], // Close the polygon
      fill: "toself" as const,
      fillcolor: "rgba(79, 172, 254, 0.2)",
      line: {
        color: "rgba(79, 172, 254, 1)",
        width: 3,
      },
      marker: {
        color: "rgba(79, 172, 254, 1)",
        size: 8,
        symbol: "circle",
      },
      name: `Qubit ${qubitId}`,
      hovertemplate: "%{theta}<br>Score: %{r:.1f}/100<extra></extra>",
      mode: "lines+markers" as const,
    };

    return [trace];
  }, [radarData, qubitId]);

  // Layout configuration for radar chart
  const layout = useMemo(
    () => ({
      polar: {
        radialaxis: {
          visible: true,
          range: [0, 100],
          ticksuffix: "",
          tickmode: "linear" as const,
          tick0: 0,
          dtick: 20,
          showticklabels: true,
          tickfont: { size: 12, color: "#666" },
          gridcolor: "rgba(128, 128, 128, 0.2)",
          linecolor: "rgba(128, 128, 128, 0.3)",
        },
        angularaxis: {
          tickfont: { size: 14, color: "#333" },
          rotation: 90, // Start from top
          direction: "clockwise" as const,
        },
        bgcolor: "rgba(0,0,0,0)",
      },
      showlegend: false,
      title: {
        text: `Qubit ${qubitId} Performance Radar`,
        font: { size: 18, color: "#333" },
        x: 0.5,
        xanchor: "center" as const,
      },
      margin: { t: 80, r: 80, b: 50, l: 80 },
      plot_bgcolor: "rgba(0,0,0,0)",
      paper_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Arial, sans-serif" },
    }),
    [qubitId],
  );

  // Calculate overall score (average of all parameters)
  const overallScore = useMemo(() => {
    if (radarData.length === 0) return 0;
    return Math.round(
      radarData.reduce((sum, p) => sum + p.value, 0) / radarData.length,
    );
  }, [radarData]);

  // Get performance rank based on overall score
  const getPerformanceRank = (score: number) => {
    if (score >= 90)
      return { rank: "S", color: "text-yellow-500", bg: "bg-yellow-100" };
    if (score >= 80)
      return { rank: "A", color: "text-green-500", bg: "bg-green-100" };
    if (score >= 70)
      return { rank: "B", color: "text-blue-500", bg: "bg-blue-100" };
    if (score >= 60)
      return { rank: "C", color: "text-purple-500", bg: "bg-purple-100" };
    if (score >= 50)
      return { rank: "D", color: "text-orange-500", bg: "bg-orange-100" };
    return { rank: "F", color: "text-red-500", bg: "bg-red-100" };
  };

  const performanceRank = getPerformanceRank(overallScore);

  if (error) {
    return (
      <ErrorCard
        title="Radar Chart Error"
        message={
          (error as Error)?.message || "Failed to load qubit performance data"
        }
        onRetry={() => window.location.reload()}
      />
    );
  }

  if (radarData.length === 0 && !isLoading) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <div className="text-center py-12">
            <div className="text-6xl mb-4">🤖</div>
            <div className="text-xl font-semibold mb-2">
              No Performance Data
            </div>
            <div className="text-base-content/60">
              Run calibration experiments to see qubit performance radar
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Performance Summary Card */}
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-4">
              <div className="text-4xl">🤖</div>
              <div>
                <h2 className="text-2xl font-bold">
                  Qubit {qubitId} Performance
                </h2>
                <p className="text-base-content/60">
                  Quantum bit capability analysis
                </p>
              </div>
            </div>
            <div className="text-center">
              <div
                className={`text-6xl font-bold ${performanceRank.color} mb-2`}
              >
                {performanceRank.rank}
              </div>
              <div
                className={`badge badge-lg ${performanceRank.bg} ${performanceRank.color} font-semibold`}
              >
                {overallScore}/100
              </div>
            </div>
          </div>

          {/* Parameter Details */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {radarData.map((param, index) => (
              <div key={index} className="stat bg-base-200 rounded-lg p-4">
                <div className="stat-figure text-2xl">{param.icon}</div>
                <div className="stat-title text-sm font-medium">
                  {param.name}
                </div>
                <div
                  className="stat-value text-lg"
                  style={{ color: param.color }}
                >
                  {param.value.toFixed(1)}/100
                </div>
                <div className="stat-desc text-xs">
                  Raw:{" "}
                  {((param.value / 100) * param.maxValue).toFixed(
                    param.unit ? 2 : 4,
                  )}
                  {param.unit}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Radar Chart */}
      <PlotCard
        title=""
        plotData={plotData}
        layout={layout}
        isLoading={isLoading}
        hasData={radarData.length > 0}
        emptyStateMessage="No performance data available"
        config={{
          toImageButtonOptions: {
            format: "svg",
            filename: `qubit_${qubitId}_radar`,
            height: 600,
            width: 800,
            scale: 2,
          },
        }}
      />

      {/* Performance Tips */}
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <h3 className="text-lg font-semibold mb-4">
            🎯 Performance Analysis
          </h3>
          <div className="space-y-3">
            {overallScore >= 90 && (
              <div className="alert alert-success">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="stroke-current shrink-0 h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>
                  <strong>Excellent Performance!</strong> This qubit is
                  performing at the highest level across all parameters.
                </span>
              </div>
            )}
            {overallScore >= 70 && overallScore < 90 && (
              <div className="alert alert-info">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="stroke-current shrink-0 h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>
                  <strong>Good Performance.</strong> This qubit shows solid
                  performance with room for optimization.
                </span>
              </div>
            )}
            {overallScore < 70 && (
              <div className="alert alert-warning">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="stroke-current shrink-0 h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"
                  />
                </svg>
                <span>
                  <strong>Performance Issues Detected.</strong> Consider
                  recalibration or hardware inspection.
                </span>
              </div>
            )}
          </div>

          <div className="mt-4 text-sm text-base-content/70">
            <div className="font-medium mb-2">Parameter Scoring:</div>
            <ul className="list-disc list-inside space-y-1 ml-4">
              <li>
                T1 Coherence: Normalized to 200µs maximum (energy relaxation
                time)
              </li>
              <li>
                T2 Echo/Star: Normalized to 400µs/100µs respectively (dephasing
                times)
              </li>
              <li>
                Gate Fidelity: Percentage of successful quantum operations
              </li>
              <li>Readout Fidelity: Accuracy of quantum state measurement</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
