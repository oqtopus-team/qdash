"use client";

import React, { useMemo, useState, useRef, useLayoutEffect } from "react";
import Link from "next/link";

import { GitBranch } from "lucide-react";

import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import {
  getQubitGridPosition,
  type TopologyLayoutParams,
} from "@/utils/gridPosition";
import { calculateGridContainerWidth } from "@/utils/gridLayout";

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
  topologyId: string;
  selectedDate: string;
}

interface SelectedQubitInfo {
  qid: string;
  metric: MetricValue;
}

export function QubitMetricsGrid({
  metricData,
  title,
  metricKey,
  unit,
  colorScale,
  gridSize = 8,
  chipId,
  topologyId,
  selectedDate: _selectedDate,
}: QubitMetricsGridProps) {
  // Get topology configuration
  const {
    muxSize = 2,
    regionSize = 4,
    hasMux = false,
    layoutType = "grid",
    showMuxBoundaries = false,
    qubits: topologyQubits,
    gridSize: topologyGridSize,
  } = useTopologyConfig(topologyId) ?? {};

  // Calculate actual grid dimensions from topology qubit positions
  const { gridRows, gridCols } = useMemo(() => {
    if (topologyQubits) {
      let maxRow = 0;
      let maxCol = 0;
      Object.values(topologyQubits).forEach((pos) => {
        if (pos.row > maxRow) maxRow = pos.row;
        if (pos.col > maxCol) maxCol = pos.col;
      });
      return { gridRows: maxRow + 1, gridCols: maxCol + 1 };
    }
    // Fallback to square grid
    const size = topologyGridSize ?? gridSize;
    return { gridRows: size, gridCols: size };
  }, [topologyQubits, topologyGridSize, gridSize]);

  // Use the larger dimension for calculations
  const effectiveGridSize = Math.max(gridRows, gridCols);

  // Layout params for grid position calculations
  const layoutParams: TopologyLayoutParams = useMemo(
    () => ({
      muxEnabled: hasMux,
      muxSize,
      gridSize: effectiveGridSize,
      layoutType,
    }),
    [hasMux, muxSize, effectiveGridSize, layoutType],
  );

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
  const modalRef = useRef<HTMLDialogElement>(null);

  // Use grid layout hook for responsive sizing
  const displayCols = zoomMode === "region" ? regionSize : gridCols;
  const displayRows = zoomMode === "region" ? regionSize : gridRows;
  const { containerRef, cellSize, isMobile } = useGridLayout({
    cols: displayCols,
    rows: displayRows,
    reservedHeight: { mobile: 300, desktop: 350 },
    deps: [metricData],
  });

  // Control modal with native dialog API (useLayoutEffect for instant response)
  const isModalOpen = selectedQubitInfo !== null;
  useLayoutEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;

    if (isModalOpen && !modal.open) {
      modal.showModal();
    } else if (!isModalOpen && modal.open) {
      modal.close();
    }
  }, [isModalOpen]);

  const numRegions = Math.floor(effectiveGridSize / regionSize);
  const isSquareGrid = gridRows === gridCols;

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

  // Use empty object if no data, so grid structure is still shown
  const displayData = metricData ?? {};

  // Calculate display cell size (smaller in region zoom mode)
  const displayCellSize = zoomMode === "region" ? cellSize * 0.9 : cellSize;
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Zoom mode toggle - only show in full view mode for square grids */}
      {zoomMode === "full" && isSquareGrid && (
        <RegionZoomToggle
          enabled={regionSelectionEnabled}
          onToggle={setRegionSelectionEnabled}
        />
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
      <div
        className="flex-1 p-1 md:p-4 relative overflow-x-auto flex justify-center"
        ref={containerRef}
      >
        <div
          className="grid gap-1 md:gap-2 p-2 md:p-4 bg-base-200/50 rounded-xl relative"
          style={{
            gridTemplateColumns: `repeat(${displayCols}, minmax(${displayCellSize}px, 1fr))`,
            gridTemplateRows: `repeat(${displayRows}, minmax(${displayCellSize}px, 1fr))`,
            width: calculateGridContainerWidth(
              displayCols,
              displayCellSize,
              isMobile,
            ),
          }}
        >
          {Array.from({ length: displayRows * displayCols }).map((_, index) => {
            const localRow = Math.floor(index / displayCols);
            const localCol = index % displayCols;
            const actualRow = displayGridStart.row + localRow;
            const actualCol = displayGridStart.col + localCol;

            // Calculate MUX position for this cell
            const muxRow = Math.floor(actualRow / muxSize);
            const muxCol = Math.floor(actualCol / muxSize);
            const isEvenMux = (muxRow + muxCol) % 2 === 0;

            // Find which qubit should be at this grid position
            // Use topology positions if available
            let qid: string | undefined;
            if (topologyQubits) {
              // Find qubit ID from topology by position
              const foundEntry = Object.entries(topologyQubits).find(
                ([, pos]) => pos.row === actualRow && pos.col === actualCol,
              );
              if (foundEntry) {
                qid = foundEntry[0];
              }
            } else {
              // Fallback: try to find from metricData or compute
              qid = Object.keys(displayData).find((key) => {
                const pos = getQubitGridPosition(key, layoutParams);
                return pos.row === actualRow && pos.col === actualCol;
              });
              // If no metric data, compute expected qid for this position
              if (!qid) {
                const expectedQid = actualRow * gridSize + actualCol;
                if (expectedQid < gridSize * gridSize) {
                  qid = String(expectedQid);
                }
              }
            }

            const metric = qid ? displayData[qid] : null;
            const value = metric?.value ?? null;

            // MUX background class
            const muxBgClass =
              hasMux && showMuxBoundaries
                ? isEvenMux
                  ? "ring-2 ring-inset ring-primary/20"
                  : "ring-2 ring-inset ring-secondary/20"
                : "";

            // Empty cell if no qubit at this position (outside topology)
            if (!qid) {
              return (
                <div
                  key={index}
                  className={`aspect-square bg-base-300/50 rounded-lg ${muxBgClass}`}
                />
              );
            }

            const bgColor = stats
              ? getColor(value, stats.min, stats.max)
              : null;

            return (
              <button
                key={qid}
                onClick={() => metric && setSelectedQubitInfo({ qid, metric })}
                className={`aspect-square rounded-lg shadow-md flex flex-col items-center justify-center transition-all hover:shadow-xl hover:scale-105 relative group cursor-pointer ${
                  !bgColor ? "bg-base-300/50" : ""
                } ${muxBgClass}`}
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
          })}

          {/* MUX labels overlay - centered in each MUX group */}
          {hasMux && showMuxBoundaries && (
            <div
              className={`absolute inset-0 pointer-events-none p-2 md:p-4 z-10 ${
                zoomMode === "full" ? "hidden md:block" : ""
              }`}
            >
              <div
                className="grid gap-1 md:gap-2 w-full h-full"
                style={{
                  gridTemplateColumns: `repeat(${displayCols}, minmax(${displayCellSize}px, 1fr))`,
                  gridTemplateRows: `repeat(${displayRows}, minmax(${displayCellSize}px, 1fr))`,
                }}
              >
                {Array.from({
                  length: Math.pow(Math.ceil(displayCols / muxSize), 2),
                }).map((_, idx) => {
                  const numMuxCols = Math.ceil(displayCols / muxSize);
                  const muxLocalRow = Math.floor(idx / numMuxCols);
                  const muxLocalCol = idx % numMuxCols;

                  // Calculate actual MUX position considering zoom offset
                  const muxActualRow =
                    Math.floor(displayGridStart.row / muxSize) + muxLocalRow;
                  const muxActualCol =
                    Math.floor(displayGridStart.col / muxSize) + muxLocalCol;
                  const muxIndex =
                    muxActualRow * Math.floor(effectiveGridSize / muxSize) +
                    muxActualCol;

                  // Calculate grid position for this MUX label (centered)
                  const startCol = muxLocalCol * muxSize + 1;
                  const startRow = muxLocalRow * muxSize + 1;
                  const spanCols = Math.min(
                    muxSize,
                    displayCols - muxLocalCol * muxSize,
                  );
                  const spanRows = Math.min(
                    muxSize,
                    displayRows - muxLocalRow * muxSize,
                  );

                  if (spanCols <= 0 || spanRows <= 0) return null;

                  return (
                    <div
                      key={idx}
                      className="flex items-center justify-center"
                      style={{
                        gridColumn: `${startCol} / span ${spanCols}`,
                        gridRow: `${startRow} / span ${spanRows}`,
                      }}
                    >
                      <div className="text-[0.5rem] md:text-xs font-bold text-base-content/60 bg-base-100/90 backdrop-blur-sm px-1.5 py-0.5 rounded shadow-sm border border-base-content/10">
                        MUX{muxIndex}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Region selection overlay - only when enabled and in full view mode for square grids */}
          {zoomMode === "full" && regionSelectionEnabled && isSquareGrid && (
            <div className="absolute inset-0 pointer-events-none p-2 md:p-4 z-20">
              <div
                className="grid gap-1 md:gap-2 w-full h-full"
                style={{
                  gridTemplateColumns: `repeat(${displayCols}, minmax(${displayCellSize}px, 1fr))`,
                  gridTemplateRows: `repeat(${displayRows}, minmax(${displayCellSize}px, 1fr))`,
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
      </div>

      {/* Qubit Detail Modal */}
      <dialog
        ref={modalRef}
        className="modal modal-bottom sm:modal-middle"
        onClose={() => setSelectedQubitInfo(null)}
      >
        <div className="modal-box w-full sm:w-11/12 max-w-5xl bg-base-100 p-0 h-[85vh] sm:h-[90vh] overflow-hidden flex flex-col">
          {selectedQubitInfo && (
            <>
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
              <div className="px-4 sm:px-6 py-3 sm:py-4 border-t border-base-300 flex justify-between items-center">
                <Link
                  href={`/provenance?parameter=${encodeURIComponent(metricKey)}&qid=${encodeURIComponent(selectedQubitInfo.qid)}&tab=lineage`}
                  className="btn btn-ghost btn-sm sm:btn-md gap-1"
                >
                  <GitBranch className="h-4 w-4" />
                  <span className="hidden sm:inline">Lineage</span>
                </Link>
                <div className="flex gap-2">
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
            </>
          )}
        </div>
        <form method="dialog" className="modal-backdrop">
          <button>close</button>
        </form>
      </dialog>
    </div>
  );
}
