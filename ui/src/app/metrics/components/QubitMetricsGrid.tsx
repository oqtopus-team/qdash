"use client";

import React, { useMemo, useState } from "react";

import { TaskFigure } from "@/app/components/TaskFigure";

interface MetricValue {
  value: number | null;
  task_id?: string | null;
  execution_id?: string | null;
}

interface QubitMetricsGridProps {
  metricData: { [key: string]: MetricValue } | null;
  title: string;
  unit: string;
  colorScale: {
    min: number;
    max: number;
    colors: string[];
  };
  gridSize?: number;
  chipId: string;
  selectedDate: string;
}

interface SelectedQubitInfo {
  qid: string;
  metric: MetricValue;
}

const MUX_SIZE = 2; // 2x2 qubits per MUX

// Calculate grid position for a qubit based on MUX layout
function getQubitGridPosition(
  qid: string,
  gridSize: number,
): { row: number; col: number } {
  const qidNum = parseInt(qid.replace("Q", ""));
  const muxIndex = Math.floor(qidNum / 4);
  const muxRow = Math.floor(muxIndex / (gridSize / MUX_SIZE));
  const muxCol = muxIndex % (gridSize / MUX_SIZE);
  const localIndex = qidNum % 4;
  const localRow = Math.floor(localIndex / 2);
  const localCol = localIndex % 2;

  return {
    row: muxRow * MUX_SIZE + localRow,
    col: muxCol * MUX_SIZE + localCol,
  };
}

export function QubitMetricsGrid({
  metricData,
  title,
  unit,
  colorScale,
  gridSize = 8,
  chipId,
  selectedDate: _selectedDate,
}: QubitMetricsGridProps) {
  // Region selection state
  const [regionSelectionEnabled, setRegionSelectionEnabled] = useState(false);
  const [zoomMode, setZoomMode] = useState<"full" | "region">("full");
  const [selectedRegion, setSelectedRegion] = useState<{
    row: number;
    col: number;
  } | null>(null);
  const [hoveredRegion, setHoveredRegion] = useState<{
    row: number;
    col: number;
  } | null>(null);

  // Modal state
  const [selectedQubitInfo, setSelectedQubitInfo] =
    useState<SelectedQubitInfo | null>(null);

  const regionSize = 4; // 4×4 qubits per region
  const numRegions = Math.floor(gridSize / regionSize);

  // Calculate color for a value with auto-adjusted scale
  const getColor = (
    value: number | null,
    autoMin: number,
    autoMax: number,
  ): string => {
    if (value === null || value === undefined) {
      return "bg-base-300/50";
    }

    const { colors } = colorScale;
    // Use auto-adjusted min/max if colorScale has min=max=0
    const effectiveMin =
      colorScale.min === 0 && colorScale.max === 0 ? autoMin : colorScale.min;
    const effectiveMax =
      colorScale.min === 0 && colorScale.max === 0 ? autoMax : colorScale.max;

    const normalized = Math.max(
      0,
      Math.min(1, (value - effectiveMin) / (effectiveMax - effectiveMin)),
    );
    const colorIndex = Math.floor(normalized * (colors.length - 1));
    return colors[colorIndex];
  };

  // Calculate statistics
  const stats = useMemo(() => {
    if (!metricData) return null;

    const values = Object.values(metricData)
      .map((m) => m.value)
      .filter((v): v is number => v !== null && v !== undefined);

    if (values.length === 0) return null;

    const sum = values.reduce((a, b) => a + b, 0);
    const avg = sum / values.length;
    const sortedValues = [...values].sort((a, b) => a - b);
    const min = sortedValues[0];
    const max = sortedValues[sortedValues.length - 1];
    const median = sortedValues[Math.floor(sortedValues.length / 2)];

    return {
      count: values.length,
      avg,
      min,
      max,
      median,
    };
  }, [metricData]);

  if (!metricData || !stats) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-base-content/60">No data available</div>
      </div>
    );
  }

  // Calculate displayed grid size based on zoom mode
  const displayGridSize = zoomMode === "region" ? regionSize : gridSize;
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Header with statistics */}
      <div className="space-y-2">
        <h2 className="text-xl md:text-2xl font-bold">{title}</h2>
        <div className="flex flex-wrap gap-4 md:gap-6 text-xs md:text-sm">
          <div>
            <span className="text-base-content/60">Count: </span>
            <span className="font-semibold">{stats.count}</span>
          </div>
          <div>
            <span className="text-base-content/60">Avg: </span>
            <span className="font-semibold">
              {stats.avg.toFixed(2)} {unit}
            </span>
          </div>
          <div>
            <span className="text-base-content/60">Min: </span>
            <span className="font-semibold">
              {stats.min.toFixed(2)} {unit}
            </span>
          </div>
          <div>
            <span className="text-base-content/60">Max: </span>
            <span className="font-semibold">
              {stats.max.toFixed(2)} {unit}
            </span>
          </div>
          <div>
            <span className="text-base-content/60">Median: </span>
            <span className="font-semibold">
              {stats.median.toFixed(2)} {unit}
            </span>
          </div>
        </div>
      </div>

      {/* Zoom mode toggle - only show in full view mode */}
      {zoomMode === "full" && (
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium">Region Zoom:</label>
          <input
            type="checkbox"
            checked={regionSelectionEnabled}
            onChange={(e) => setRegionSelectionEnabled(e.target.checked)}
            className="toggle toggle-sm toggle-primary"
          />
          <span className="text-xs text-base-content/70">
            {regionSelectionEnabled
              ? "Enabled - Click a region to zoom"
              : "Disabled"}
          </span>
        </div>
      )}

      {/* Back button when in region mode */}
      {zoomMode === "region" && selectedRegion && (
        <div className="flex items-center gap-4">
          <button
            onClick={() => {
              setZoomMode("full");
              setSelectedRegion(null);
            }}
            className="btn btn-sm btn-ghost"
          >
            ← Back to Full View
          </button>
          <span className="text-sm text-base-content/70">
            Region {selectedRegion.row + 1},{selectedRegion.col + 1} (Qubits{" "}
            {displayGridStart.row * gridSize + displayGridStart.col} -{" "}
            {(displayGridStart.row + regionSize - 1) * gridSize +
              displayGridStart.col +
              regionSize -
              1}
            )
          </span>
        </div>
      )}

      {/* Grid display */}
      <div className="flex-1 p-2 md:p-4 relative">
        <div
          className="grid gap-1 md:gap-2 lg:gap-3 p-3 md:p-4 lg:p-6 bg-base-200/50 rounded-xl max-w-full"
          style={{
            gridTemplateColumns: `repeat(${displayGridSize}, minmax(0, 1fr))`,
          }}
        >
          {Array.from({ length: displayGridSize * displayGridSize }).map(
            (_, index) => {
              const localRow = Math.floor(index / displayGridSize);
              const localCol = index % displayGridSize;
              const actualRow = displayGridStart.row + localRow;
              const actualCol = displayGridStart.col + localCol;

              // Find which qubit should be at this grid position
              const qid = Object.keys(metricData || {}).find((key) => {
                const pos = getQubitGridPosition(key, gridSize);
                return pos.row === actualRow && pos.col === actualCol;
              });

              const metric = qid ? metricData?.[qid] : null;
              const value = metric?.value ?? null;

              // Empty cell if no qubit at this position
              if (!qid) {
                return (
                  <div
                    key={index}
                    className="aspect-square bg-base-300/50 rounded-lg"
                  />
                );
              }

              return (
                <button
                  key={qid}
                  onClick={() =>
                    metric && setSelectedQubitInfo({ qid, metric })
                  }
                  className={`aspect-square rounded-lg shadow-md flex flex-col items-center justify-center transition-all hover:shadow-xl hover:scale-105 relative group cursor-pointer ${
                    value !== null && value !== undefined
                      ? getColor(value, stats.min, stats.max)
                      : "bg-base-300/50"
                  }`}
                >
                  {/* QID Label - always visible */}
                  <div
                    className={`absolute top-0.5 left-0.5 md:top-1 md:left-1 backdrop-blur-sm px-1 py-0.5 md:px-2 rounded text-[0.6rem] md:text-xs font-bold shadow-sm ${
                      value !== null && value !== undefined
                        ? "bg-black/30 text-white"
                        : "bg-base-content/20 text-base-content"
                    }`}
                  >
                    {qid}
                  </div>

                  {/* Value Display */}
                  {value !== null && value !== undefined && (
                    <div className="flex flex-col items-center justify-center h-full pt-3 md:pt-4">
                      <div className="text-sm md:text-base lg:text-lg font-bold text-white drop-shadow-md">
                        {value.toFixed(2)}
                      </div>
                      <div className="text-[0.6rem] md:text-xs text-white/90 font-medium drop-shadow">
                        {unit}
                      </div>
                    </div>
                  )}

                  {/* No data indicator */}
                  {(value === null || value === undefined) && (
                    <div className="flex flex-col items-center justify-center h-full pt-3 md:pt-4">
                      <div className="text-xs text-base-content/40 font-medium">
                        N/A
                      </div>
                    </div>
                  )}

                  {/* Hover tooltip */}
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-base-100 text-base-content text-sm rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
                    {value !== null && value !== undefined
                      ? `${qid}: ${value.toFixed(4)} ${unit}`
                      : `${qid}: No data`}
                  </div>
                </button>
              );
            },
          )}
        </div>

        {/* Region selection overlay - only when enabled and in full view mode */}
        {zoomMode === "full" && regionSelectionEnabled && (
          <div className="absolute inset-0 pointer-events-none">
            <div className="relative w-full h-full p-2 md:p-4">
              <div className="relative w-full h-full p-3 md:p-4 lg:p-6">
                <div
                  className="grid gap-1 md:gap-2 lg:gap-3 w-full h-full"
                  style={{ gridTemplateColumns: `repeat(${numRegions}, 1fr)` }}
                >
                  {Array.from({ length: numRegions * numRegions }).map(
                    (_, index) => {
                      const regionRow = Math.floor(index / numRegions);
                      const regionCol = index % numRegions;
                      const isHovered =
                        hoveredRegion?.row === regionRow &&
                        hoveredRegion?.col === regionCol;

                      return (
                        <button
                          key={index}
                          className={`pointer-events-auto transition-all duration-200 rounded-lg ${
                            isHovered
                              ? "bg-primary/20 border-2 border-primary"
                              : "bg-transparent border-2 border-transparent hover:border-primary/50"
                          }`}
                          onMouseEnter={() =>
                            setHoveredRegion({ row: regionRow, col: regionCol })
                          }
                          onMouseLeave={() => setHoveredRegion(null)}
                          onClick={() => {
                            setSelectedRegion({
                              row: regionRow,
                              col: regionCol,
                            });
                            setZoomMode("region");
                          }}
                          title={`Zoom to region (${regionRow + 1}, ${regionCol + 1})`}
                        />
                      );
                    },
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Qubit Detail Modal */}
      {selectedQubitInfo && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
          onClick={() => setSelectedQubitInfo(null)}
        >
          <div
            className="bg-base-100 rounded-xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold">
                  Qubit {selectedQubitInfo.qid}
                </h2>
                <p className="text-base-content/70 mt-1">
                  {title}:{" "}
                  {selectedQubitInfo.metric.value !== null
                    ? `${selectedQubitInfo.metric.value.toFixed(4)} ${unit}`
                    : "No data"}
                </p>
              </div>
              <button
                onClick={() => setSelectedQubitInfo(null)}
                className="btn btn-ghost btn-sm btn-circle"
              >
                ✕
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-auto p-6">
              <div className="space-y-4">
                <div className="stats shadow w-full">
                  <div className="stat">
                    <div className="stat-title">Qubit ID</div>
                    <div className="stat-value text-2xl">
                      {selectedQubitInfo.qid}
                    </div>
                  </div>
                  <div className="stat">
                    <div className="stat-title">{title}</div>
                    <div className="stat-value text-2xl">
                      {selectedQubitInfo.metric.value !== null
                        ? `${selectedQubitInfo.metric.value.toFixed(2)} ${unit}`
                        : "N/A"}
                    </div>
                  </div>
                </div>

                {/* Task Figure - Display calibration result */}
                {selectedQubitInfo.metric.task_id && (
                  <div className="card bg-base-200 shadow-sm">
                    <div className="card-body">
                      <h3 className="card-title text-sm">Calibration Result</h3>
                      <div className="relative h-96 w-full">
                        <TaskFigure
                          taskId={selectedQubitInfo.metric.task_id}
                          chipId={chipId}
                          qid={selectedQubitInfo.qid}
                          className="w-full h-full object-contain"
                        />
                      </div>
                      <div className="text-xs text-base-content/60 mt-2">
                        Task ID: {selectedQubitInfo.metric.task_id}
                        {selectedQubitInfo.metric.execution_id && (
                          <span className="ml-2">
                            • Execution ID:{" "}
                            {selectedQubitInfo.metric.execution_id}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {!selectedQubitInfo.metric.task_id && (
                  <div className="alert alert-info">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      className="stroke-current shrink-0 w-6 h-6"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    <span>
                      No calibration figure available for this metric. Click
                      "View Details" to see full qubit analysis.
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-base-300 flex justify-end gap-2">
              <button
                onClick={() => setSelectedQubitInfo(null)}
                className="btn btn-ghost"
              >
                Close
              </button>
              <a
                href={`/chip/${chipId}/qubit/${selectedQubitInfo.qid}`}
                className="btn btn-primary"
              >
                View Details
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
