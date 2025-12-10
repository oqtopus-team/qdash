"use client";

import React, { useMemo, useState } from "react";

import { QubitMetricHistoryModal } from "./QubitMetricHistoryModal";

interface MetricValue {
  value: number | null;
  task_id?: string | null;
  execution_id?: string | null;
}

interface QubitMetricsGridProps {
  metricData: { [key: string]: MetricValue } | null;
  title: string;
  metricKey: string;
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
  metricKey,
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

  // Helper function to interpolate between two hex colors
  const interpolateColor = (
    color1: string,
    color2: string,
    factor: number,
  ): string => {
    const c1 = parseInt(color1.slice(1), 16);
    const c2 = parseInt(color2.slice(1), 16);

    const r1 = (c1 >> 16) & 0xff;
    const g1 = (c1 >> 8) & 0xff;
    const b1 = c1 & 0xff;

    const r2 = (c2 >> 16) & 0xff;
    const g2 = (c2 >> 8) & 0xff;
    const b2 = c2 & 0xff;

    const r = Math.round(r1 + (r2 - r1) * factor);
    const g = Math.round(g1 + (g2 - g1) * factor);
    const b = Math.round(b1 + (b2 - b1) * factor);

    return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
  };

  // Calculate color for a value with auto-adjusted scale and smooth interpolation
  const getColor = (
    value: number | null,
    autoMin: number,
    autoMax: number,
  ): string | null => {
    if (value === null || value === undefined) {
      return null; // Will use CSS class instead
    }

    const { colors } = colorScale;
    if (colors.length === 0) return null;

    // Use auto-adjusted min/max if colorScale has min=max=0
    const effectiveMin =
      colorScale.min === 0 && colorScale.max === 0 ? autoMin : colorScale.min;
    const effectiveMax =
      colorScale.min === 0 && colorScale.max === 0 ? autoMax : colorScale.max;

    // Handle edge case where min === max
    if (effectiveMin === effectiveMax) {
      return colors[colors.length - 1];
    }

    const normalized = Math.max(
      0,
      Math.min(1, (value - effectiveMin) / (effectiveMax - effectiveMin)),
    );

    // Calculate position in color array with smooth interpolation
    const position = normalized * (colors.length - 1);
    const lowerIndex = Math.floor(position);
    const upperIndex = Math.min(lowerIndex + 1, colors.length - 1);
    const factor = position - lowerIndex;

    // If factor is 0 or indices are the same, return exact color
    if (factor === 0 || lowerIndex === upperIndex) {
      return colors[lowerIndex];
    }

    // Interpolate between two adjacent colors
    return interpolateColor(colors[lowerIndex], colors[upperIndex], factor);
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
          className="grid gap-1 md:gap-2 lg:gap-3 p-3 md:p-4 lg:p-6 bg-base-200/50 rounded-xl max-w-full relative"
          style={{
            gridTemplateColumns: `repeat(${displayGridSize}, minmax(0, 1fr))`,
          }}
        >
          {/* MUX highlight overlay */}
          <div className="absolute inset-0 pointer-events-none p-3 md:p-4 lg:p-6">
            <div
              className="grid gap-1 md:gap-2 lg:gap-3 w-full h-full"
              style={{
                gridTemplateColumns: `repeat(${Math.floor(displayGridSize / MUX_SIZE)}, minmax(0, 1fr))`,
              }}
            >
              {Array.from({
                length: Math.pow(Math.floor(displayGridSize / MUX_SIZE), 2),
              }).map((_, muxIndex) => {
                const muxRow = Math.floor(
                  muxIndex / Math.floor(displayGridSize / MUX_SIZE),
                );
                const muxCol =
                  muxIndex % Math.floor(displayGridSize / MUX_SIZE);
                const isEvenMux = (muxRow + muxCol) % 2 === 0;

                return (
                  <div
                    key={muxIndex}
                    className={`rounded-lg relative ${
                      isEvenMux
                        ? "bg-primary/5 border border-primary/10"
                        : "bg-secondary/5 border border-secondary/10"
                    }`}
                    style={{
                      gridColumn: `span 1`,
                      gridRow: `span 1`,
                    }}
                  >
                    {/* MUX number label - positioned absolutely relative to grid container */}
                  </div>
                );
              })}
            </div>
          </div>
          {/* MUX labels overlay - hidden on mobile in full view */}
          <div
            className={`absolute inset-0 pointer-events-none p-3 md:p-4 lg:p-6 z-10 ${
              zoomMode === "full" ? "hidden md:block" : ""
            }`}
          >
            <div
              className="grid gap-1 md:gap-2 lg:gap-3 w-full h-full"
              style={{
                gridTemplateColumns: `repeat(${Math.floor(displayGridSize / MUX_SIZE)}, minmax(0, 1fr))`,
              }}
            >
              {Array.from({
                length: Math.pow(Math.floor(displayGridSize / MUX_SIZE), 2),
              }).map((_, muxIndex) => (
                <div key={muxIndex} className="relative">
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[0.5rem] md:text-xs font-bold text-base-content/60 bg-base-100/90 backdrop-blur-sm px-1.5 py-0.5 rounded shadow-sm border border-base-content/10">
                    MUX{muxIndex}
                  </div>
                </div>
              ))}
            </div>
          </div>
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

              const bgColor = getColor(value, stats.min, stats.max);

              return (
                <button
                  key={qid}
                  onClick={() =>
                    metric && setSelectedQubitInfo({ qid, metric })
                  }
                  className={`aspect-square rounded-lg shadow-md flex flex-col items-center justify-center transition-all hover:shadow-xl hover:scale-105 relative group cursor-pointer ${
                    !bgColor ? "bg-base-300/50" : ""
                  }`}
                  style={{
                    backgroundColor: bgColor || undefined,
                  }}
                >
                  {/* QID Label - hidden on mobile in full view, shown in region zoom or on desktop */}
                  <div
                    className={`absolute top-0.5 left-0.5 md:top-1 md:left-1 backdrop-blur-sm px-1 py-0.5 md:px-2 rounded text-[0.6rem] md:text-xs font-bold shadow-sm ${
                      zoomMode === "full" ? "hidden md:block" : ""
                    } ${
                      value !== null && value !== undefined
                        ? "bg-black/30 text-white"
                        : "bg-base-content/20 text-base-content"
                    }`}
                  >
                    {qid}
                  </div>

                  {/* Value Display */}
                  {value !== null && value !== undefined && (
                    <div className="flex flex-col items-center justify-center h-full">
                      <div className="text-[0.6rem] sm:text-sm md:text-base lg:text-lg font-bold text-white drop-shadow-md">
                        {value.toFixed(2)}
                      </div>
                      {/* Unit - hidden on mobile in full view */}
                      <div
                        className={`text-[0.5rem] md:text-xs text-white/90 font-medium drop-shadow ${
                          zoomMode === "full" ? "hidden md:block" : ""
                        }`}
                      >
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
          <div className="absolute inset-0 pointer-events-none p-3 md:p-4 lg:p-6 z-20">
            <div
              className="grid gap-1 md:gap-2 lg:gap-3 w-full h-full"
              style={{
                gridTemplateColumns: `repeat(${gridSize}, minmax(0, 1fr))`,
                gridTemplateRows: `repeat(${gridSize}, minmax(0, 1fr))`,
              }}
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
                      className={`pointer-events-auto transition-colors duration-200 rounded-lg flex items-center justify-center ${
                        isHovered
                          ? "bg-primary/30 border-2 border-primary shadow-lg z-10"
                          : "bg-primary/5 border-2 border-primary/20 hover:border-primary/40 hover:bg-primary/10"
                      }`}
                      style={{
                        gridColumn: `${regionCol * regionSize + 1} / span ${regionSize}`,
                        gridRow: `${regionRow * regionSize + 1} / span ${regionSize}`,
                      }}
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
                    >
                      <span className="text-xs font-bold text-white bg-black/50 px-2 py-1 rounded">
                        {regionRow},{regionCol}
                      </span>
                    </button>
                  );
                },
              )}
            </div>
          </div>
        )}
      </div>

      {/* Qubit Detail Modal */}
      {selectedQubitInfo && (
        <div
          className="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50 backdrop-blur-sm sm:p-4"
          onClick={() => setSelectedQubitInfo(null)}
        >
          <div
            className="bg-base-100 rounded-t-xl sm:rounded-xl w-full sm:max-w-6xl max-h-[85vh] sm:max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-base-300 flex items-center justify-between">
              <div className="min-w-0 flex-1">
                <h2 className="text-lg sm:text-2xl font-bold truncate">
                  {selectedQubitInfo.qid} - {title}
                </h2>
                <p className="text-sm sm:text-base text-base-content/70 mt-0.5 sm:mt-1">
                  {selectedQubitInfo.metric.value !== null
                    ? `${selectedQubitInfo.metric.value.toFixed(4)} ${unit}`
                    : "No data"}
                </p>
              </div>
              <button
                onClick={() => setSelectedQubitInfo(null)}
                className="btn btn-ghost btn-sm btn-circle flex-shrink-0 ml-2"
              >
                ✕
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-auto p-3 sm:p-6">
              <QubitMetricHistoryModal
                chipId={chipId}
                qid={selectedQubitInfo.qid}
                metricName={metricKey}
                metricUnit={unit}
              />
            </div>

            {/* Modal Footer */}
            <div className="px-4 sm:px-6 py-3 sm:py-4 border-t border-base-300 flex justify-end gap-2">
              <button
                onClick={() => setSelectedQubitInfo(null)}
                className="btn btn-ghost btn-sm sm:btn-md"
              >
                Close
              </button>
              <a
                href={`/chip/${chipId}/qubit/${selectedQubitInfo.qid}`}
                className="btn btn-primary btn-sm sm:btn-md"
              >
                Details
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
