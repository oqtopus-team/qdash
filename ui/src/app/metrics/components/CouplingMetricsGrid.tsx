"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { CouplingMetricHistoryModal } from "./CouplingMetricHistoryModal";

interface MetricValue {
  value: number | null;
  task_id?: string | null;
  execution_id?: string | null;
}

interface CouplingMetricsGridProps {
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

interface SelectedCouplingInfo {
  couplingId: string;
  metric: MetricValue;
}

const MUX_SIZE = 2; // 2x2 qubits per MUX

// Calculate grid position for a coupling based on MUX layout
const getCouplingPosition = (qid1: number, qid2: number, gridSize: number) => {
  const muxIndex1 = Math.floor(qid1 / 4);
  const muxIndex2 = Math.floor(qid2 / 4);
  const muxRow1 = Math.floor(muxIndex1 / (gridSize / MUX_SIZE));
  const muxCol1 = muxIndex1 % (gridSize / MUX_SIZE);
  const muxRow2 = Math.floor(muxIndex2 / (gridSize / MUX_SIZE));
  const muxCol2 = muxIndex2 % (gridSize / MUX_SIZE);
  const localIndex1 = qid1 % 4;
  const localIndex2 = qid2 % 4;
  const localRow1 = Math.floor(localIndex1 / 2);
  const localCol1 = localIndex1 % 2;
  const localRow2 = Math.floor(localIndex2 / 2);
  const localCol2 = localIndex2 % 2;

  return {
    row1: muxRow1 * MUX_SIZE + localRow1,
    col1: muxCol1 * MUX_SIZE + localCol1,
    row2: muxRow2 * MUX_SIZE + localRow2,
    col2: muxCol2 * MUX_SIZE + localCol2,
  };
};

export function CouplingMetricsGrid({
  metricData,
  title,
  metricKey,
  unit,
  colorScale,
  gridSize = 8,
  chipId,
  selectedDate: _selectedDate,
}: CouplingMetricsGridProps) {
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
  const [selectedCouplingInfo, setSelectedCouplingInfo] =
    useState<SelectedCouplingInfo | null>(null);

  const [cellSize, setCellSize] = useState(60);
  const containerRef = useRef<HTMLDivElement>(null);

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

  // Calculate color for a value
  const getColor = (
    value: number | null,
    autoMin: number,
    autoMax: number,
  ): string | null => {
    if (value === null || value === undefined) {
      return null;
    }

    const { colors } = colorScale;
    if (colors.length === 0) return null;

    const effectiveMin =
      colorScale.min === 0 && colorScale.max === 0 ? autoMin : colorScale.min;
    const effectiveMax =
      colorScale.min === 0 && colorScale.max === 0 ? autoMax : colorScale.max;

    if (effectiveMin === effectiveMax) {
      return colors[colors.length - 1];
    }

    const normalized = Math.max(
      0,
      Math.min(1, (value - effectiveMin) / (effectiveMax - effectiveMin)),
    );

    const position = normalized * (colors.length - 1);
    const lowerIndex = Math.floor(position);
    const upperIndex = Math.min(lowerIndex + 1, colors.length - 1);
    const factor = position - lowerIndex;

    if (factor === 0 || lowerIndex === upperIndex) {
      return colors[lowerIndex];
    }

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

  // Calculate cell size based on container width
  const updateSize = useCallback(() => {
    const containerWidth =
      containerRef.current?.offsetWidth || window.innerWidth;
    const availableWidth = containerWidth - 64;
    const effectiveGridSize = zoomMode === "region" ? regionSize : gridSize;
    const gap = 8;
    const totalGap = gap * (effectiveGridSize - 1);
    const calculatedSize = Math.floor(
      (availableWidth - totalGap) / effectiveGridSize,
    );
    setCellSize(Math.max(calculatedSize, 30));
  }, [gridSize, zoomMode, regionSize]);

  useEffect(() => {
    const timeoutId = setTimeout(updateSize, 0);
    window.addEventListener("resize", updateSize);
    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener("resize", updateSize);
    };
  }, [updateSize]);

  // Recalculate when data loads
  useEffect(() => {
    if (metricData) {
      updateSize();
    }
  }, [metricData, updateSize]);

  // Helper function to check if a qubit is in the displayed region
  const isQubitInRegion = (qid: number): boolean => {
    if (zoomMode === "full") return true;

    const muxIndex = Math.floor(qid / 4);
    const localIndex = qid % 4;
    const muxRow = Math.floor(muxIndex / (gridSize / MUX_SIZE));
    const muxCol = muxIndex % (gridSize / MUX_SIZE);
    const localRow = Math.floor(localIndex / 2);
    const localCol = localIndex % 2;
    const row = muxRow * MUX_SIZE + localRow;
    const col = muxCol * MUX_SIZE + localCol;

    const displayGridStart = selectedRegion
      ? {
          row: selectedRegion.row * regionSize,
          col: selectedRegion.col * regionSize,
        }
      : { row: 0, col: 0 };

    return (
      row >= displayGridStart.row &&
      row < displayGridStart.row + regionSize &&
      col >= displayGridStart.col &&
      col < displayGridStart.col + regionSize
    );
  };

  // Helper function to check if a coupling is in the displayed region
  const isCouplingInRegion = (qid1: number, qid2: number): boolean => {
    return isQubitInRegion(qid1) && isQubitInRegion(qid2);
  };

  if (!metricData || !stats) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-base-content/60">No data available</div>
      </div>
    );
  }

  const displayGridSize = zoomMode === "region" ? regionSize : gridSize;
  const displayCellSize = zoomMode === "region" ? cellSize * 0.8 : cellSize;
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

  return (
    <div className="flex flex-col h-full space-y-4" ref={containerRef}>
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
            Region {selectedRegion.row + 1},{selectedRegion.col + 1}
          </span>
        </div>
      )}

      {/* Grid Container */}
      <div className="relative w-full flex justify-center">
        <div
          className="relative"
          style={{
            width: displayGridSize * (displayCellSize + 8),
            height: displayGridSize * (displayCellSize + 8),
          }}
        >
          {/* MUX highlight overlay */}
          <div className="absolute inset-0 pointer-events-none">
            <div
              className="grid gap-2 w-full h-full"
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
                  >
                    {/* MUX number label - positioned absolutely relative to grid container */}
                  </div>
                );
              })}
            </div>
          </div>
          {/* MUX labels overlay - separate layer on top */}
          <div className="absolute inset-0 pointer-events-none z-10">
            <div
              className="grid gap-2 w-full h-full"
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
          {/* Qubit cells (background) */}
          {Array.from({ length: gridSize === 8 ? 64 : 144 })
            .filter((_, qid) => isQubitInRegion(qid))
            .map((_, idx) => {
              const allQids = Array.from({
                length: gridSize === 8 ? 64 : 144,
              }).map((_, i) => i);
              const filteredQids = allQids.filter((qid) =>
                isQubitInRegion(qid),
              );
              const qid = filteredQids[idx];
              const muxIndex = Math.floor(qid / 4);
              const localIndex = qid % 4;
              const muxRow = Math.floor(muxIndex / (gridSize / MUX_SIZE));
              const muxCol = muxIndex % (gridSize / MUX_SIZE);
              const localRow = Math.floor(localIndex / 2);
              const localCol = localIndex % 2;
              const row = muxRow * MUX_SIZE + localRow;
              const col = muxCol * MUX_SIZE + localCol;

              const displayRow = row - displayGridStart.row;
              const displayCol = col - displayGridStart.col;
              const x = displayCol * (displayCellSize + 8);
              const y = displayRow * (displayCellSize + 8);

              return (
                <div
                  key={qid}
                  className="absolute bg-base-300/30 rounded-lg flex items-center justify-center text-sm text-base-content/30"
                  style={{
                    top: y,
                    left: x,
                    width: displayCellSize,
                    height: displayCellSize,
                  }}
                >
                  {qid}
                </div>
              );
            })}

          {/* Coupling cells (overlay) */}
          {Object.entries(metricData)
            .filter(([couplingId]) => {
              const [qid1, qid2] = couplingId.split("-").map(Number);
              return isCouplingInRegion(qid1, qid2);
            })
            .map(([couplingId, metric]) => {
              const [qid1, qid2] = couplingId.split("-").map(Number);
              const { row1, col1, row2, col2 } = getCouplingPosition(
                qid1,
                qid2,
                gridSize,
              );

              const displayRow1 = row1 - displayGridStart.row;
              const displayCol1 = col1 - displayGridStart.col;
              const displayRow2 = row2 - displayGridStart.row;
              const displayCol2 = col2 - displayGridStart.col;
              const centerX =
                ((displayCol1 + displayCol2) / 2) * (displayCellSize + 8) +
                displayCellSize / 2;
              const centerY =
                ((displayRow1 + displayRow2) / 2) * (displayCellSize + 8) +
                displayCellSize / 2;

              const value = metric.value;
              const bgColor = getColor(value, stats.min, stats.max);

              return (
                <button
                  key={couplingId}
                  onClick={() =>
                    setSelectedCouplingInfo({ couplingId, metric })
                  }
                  style={{
                    position: "absolute",
                    top: centerY,
                    left: centerX,
                    width: displayCellSize * 0.6,
                    height: displayCellSize * 0.6,
                    backgroundColor: bgColor || undefined,
                  }}
                  className={`rounded-lg shadow-md flex flex-col items-center justify-center transition-all hover:shadow-xl hover:scale-105 -translate-x-1/2 -translate-y-1/2 relative group cursor-pointer ${
                    !bgColor ? "bg-base-300/50" : ""
                  }`}
                >
                  {/* Coupling ID Label */}
                  <div
                    className={`absolute top-0.5 left-0.5 md:top-1 md:left-1 backdrop-blur-sm px-1 py-0.5 md:px-2 rounded text-[0.5rem] md:text-xs font-bold shadow-sm ${
                      value !== null && value !== undefined
                        ? "bg-black/30 text-white"
                        : "bg-base-content/20 text-base-content"
                    }`}
                  >
                    {couplingId}
                  </div>

                  {/* Value Display */}
                  {value !== null && value !== undefined && (
                    <div className="flex flex-col items-center justify-center h-full pt-3 md:pt-4">
                      <div className="text-xs md:text-sm lg:text-base font-bold text-white drop-shadow-md">
                        {value.toFixed(2)}
                      </div>
                      <div className="text-[0.5rem] md:text-xs text-white/90 font-medium drop-shadow">
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
                      ? `${couplingId}: ${value.toFixed(4)} ${unit}`
                      : `${couplingId}: No data`}
                  </div>
                </button>
              );
            })}

          {/* Region selection overlay */}
          {zoomMode === "full" && regionSelectionEnabled && (
            <div className="absolute inset-0 pointer-events-none z-20">
              <div
                className="grid gap-2 w-full h-full"
                style={{
                  gridTemplateColumns: `repeat(${gridSize}, minmax(0, 1fr))`,
                  gridTemplateRows: `repeat(${gridSize}, minmax(0, 1fr))`,
                }}
              >
                {Array.from({ length: numRegions * numRegions }).map((_, index) => {
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
                        setSelectedRegion({ row: regionRow, col: regionCol });
                        setZoomMode("region");
                      }}
                      title={`Zoom to region (${regionRow + 1}, ${regionCol + 1})`}
                    >
                      <span className="text-xs font-bold text-white bg-black/50 px-2 py-1 rounded">
                        {regionRow},{regionCol}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Coupling Detail Modal with History */}
      {selectedCouplingInfo && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
          onClick={() => setSelectedCouplingInfo(null)}
        >
          <div
            className="bg-base-100 rounded-xl w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold">
                  Coupling {selectedCouplingInfo.couplingId} - {title} History
                </h2>
                <p className="text-base-content/70 mt-1">
                  Current Value:{" "}
                  {selectedCouplingInfo.metric.value !== null
                    ? `${selectedCouplingInfo.metric.value.toFixed(4)} ${unit}`
                    : "No data"}
                </p>
              </div>
              <button
                onClick={() => setSelectedCouplingInfo(null)}
                className="btn btn-ghost btn-sm btn-circle"
              >
                ✕
              </button>
            </div>

            {/* Modal Content - History */}
            <div className="flex-1 overflow-auto p-6">
              <CouplingMetricHistoryModal
                chipId={chipId}
                couplingId={selectedCouplingInfo.couplingId}
                metricName={metricKey}
                metricUnit={unit}
              />
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-base-300 flex justify-end gap-2">
              <button
                onClick={() => setSelectedCouplingInfo(null)}
                className="btn btn-ghost"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
