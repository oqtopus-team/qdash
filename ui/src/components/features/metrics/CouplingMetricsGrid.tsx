"use client";

import React, { useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { GitBranch } from "lucide-react";

import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import {
  getQubitGridPosition,
  type TopologyLayoutParams,
} from "@/utils/gridPosition";
import { calculateGridDimension } from "@/utils/gridLayout";

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
  topologyId: string;
  selectedDate: string;
}

interface SelectedCouplingInfo {
  couplingId: string;
  metric: MetricValue;
}

export function CouplingMetricsGrid({
  metricData,
  title,
  metricKey,
  unit,
  colorScale,
  gridSize = 8,
  chipId,
  topologyId,
  selectedDate: _selectedDate,
}: CouplingMetricsGridProps) {
  // Get topology configuration
  const {
    muxSize = 2,
    regionSize = 4,
    hasMux = false,
    layoutType = "grid",
    showMuxBoundaries = false,
    qubits: topologyQubits,
    couplings: topologyCouplings,
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
  const isSquareGrid = gridRows === gridCols;

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
  const [selectedCouplingInfo, setSelectedCouplingInfo] =
    useState<SelectedCouplingInfo | null>(null);
  const modalRef = useRef<HTMLDialogElement>(null);

  // Control modal with native dialog API (useLayoutEffect for instant response)
  const isModalOpen = selectedCouplingInfo !== null;
  useLayoutEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;

    if (isModalOpen && !modal.open) {
      modal.showModal();
    } else if (!isModalOpen && modal.open) {
      modal.close();
    }
  }, [isModalOpen]);

  // Use grid layout hook for responsive sizing
  const displayCols = zoomMode === "region" ? regionSize : gridCols;
  const displayRows = zoomMode === "region" ? regionSize : gridRows;
  const { containerRef, cellSize, isMobile, gap } = useGridLayout({
    cols: displayCols,
    rows: displayRows,
    reservedHeight: { mobile: 300, desktop: 350 },
    deps: [metricData],
  });

  const numRegions = Math.floor(effectiveGridSize / regionSize);

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

  // Helper function to get qubit position from topology (explicit) or computed
  const getQubitPosition = (qid: number) => {
    // Try explicit position from topology first
    if (topologyQubits && topologyQubits[qid]) {
      return topologyQubits[qid];
    }
    // Fallback to computed position
    return getQubitGridPosition(qid, layoutParams);
  };

  // Helper function to check if a qubit is in the displayed region
  const isQubitInRegion = (qid: number): boolean => {
    if (zoomMode === "full") return true;

    const pos = getQubitPosition(qid);

    const displayGridStart = selectedRegion
      ? {
          row: selectedRegion.row * regionSize,
          col: selectedRegion.col * regionSize,
        }
      : { row: 0, col: 0 };

    return (
      pos.row >= displayGridStart.row &&
      pos.row < displayGridStart.row + regionSize &&
      pos.col >= displayGridStart.col &&
      pos.col < displayGridStart.col + regionSize
    );
  };

  // Helper function to check if a coupling is in the displayed region
  const isCouplingInRegion = (qid1: number, qid2: number): boolean => {
    return isQubitInRegion(qid1) && isQubitInRegion(qid2);
  };

  // Use empty object if no data, so grid structure is still shown
  const displayData = metricData ?? {};

  const displayGridSize =
    zoomMode === "region" ? regionSize : effectiveGridSize;
  const displayCellSize = zoomMode === "region" ? cellSize * 0.8 : cellSize;
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

  return (
    <div className="flex flex-col h-full space-y-4" ref={containerRef}>
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
            Region {selectedRegion.row + 1},{selectedRegion.col + 1}
          </span>
        </div>
      )}

      {/* Grid Container */}
      <div className="relative w-full flex justify-center overflow-x-auto p-1 md:p-4">
        <div
          className="relative flex-shrink-0"
          style={{
            width: calculateGridDimension(
              displayGridSize,
              displayCellSize,
              isMobile,
            ),
            height: calculateGridDimension(
              displayGridSize,
              displayCellSize,
              isMobile,
            ),
            maxWidth: "100%",
          }}
        >
          {/* Qubit cells (background) with MUX styling */}
          {(() => {
            // Use topology qubits if available, otherwise fall back to computed positions
            const qubitList = topologyQubits
              ? Object.keys(topologyQubits).map(Number)
              : Array.from(
                  { length: effectiveGridSize * effectiveGridSize },
                  (_, i) => i,
                );

            return qubitList
              .filter((qid) => isQubitInRegion(qid))
              .map((qid) => {
                const pos = getQubitPosition(qid);

                const displayRow = pos.row - displayGridStart.row;
                const displayCol = pos.col - displayGridStart.col;
                const x = displayCol * (displayCellSize + gap);
                const y = displayRow * (displayCellSize + gap);

                // Calculate MUX index for this cell (using actual position, not display position)
                const muxRow = Math.floor(pos.row / muxSize);
                const muxCol = Math.floor(pos.col / muxSize);
                const isEvenMux = (muxRow + muxCol) % 2 === 0;

                // MUX styling class
                const muxBgClass =
                  hasMux && showMuxBoundaries
                    ? isEvenMux
                      ? "ring-2 ring-inset ring-primary/20"
                      : "ring-2 ring-inset ring-secondary/20"
                    : "";

                return (
                  <div
                    key={qid}
                    className={`absolute bg-base-300/30 rounded-lg flex items-center justify-center text-sm text-base-content/30 ${muxBgClass}`}
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
              });
          })()}

          {/* MUX labels - centered in each MUX group */}
          {hasMux && showMuxBoundaries && (
            <>
              {Array.from({
                length: Math.pow(Math.ceil(displayGridSize / muxSize), 2),
              }).map((_, idx) => {
                const numMuxCols = Math.ceil(displayGridSize / muxSize);
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

                // Calculate center position of MUX group
                const muxCenterX =
                  (muxLocalCol * muxSize + muxSize / 2) *
                    (displayCellSize + gap) -
                  gap / 2;
                const muxCenterY =
                  (muxLocalRow * muxSize + muxSize / 2) *
                    (displayCellSize + gap) -
                  gap / 2;

                return (
                  <div
                    key={`mux-label-${idx}`}
                    className={`absolute z-10 pointer-events-none ${
                      zoomMode === "full" ? "hidden md:flex" : "flex"
                    }`}
                    style={{
                      top: muxCenterY,
                      left: muxCenterX,
                      transform: "translate(-50%, -50%)",
                    }}
                  >
                    <div className="text-[0.5rem] md:text-xs font-bold text-base-content/60 bg-base-100/90 backdrop-blur-sm px-1.5 py-0.5 rounded shadow-sm border border-base-content/10">
                      MUX{muxIndex}
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Coupling cells (overlay) - render all topology couplings */}
          {(() => {
            // Use topology couplings if available, otherwise use data keys
            const couplingList: [number, number][] = topologyCouplings
              ? topologyCouplings
              : Object.keys(displayData).map((key) => {
                  const [a, b] = key.split("-").map(Number);
                  return [a, b] as [number, number];
                });

            return couplingList
              .filter(([qid1, qid2]) => isCouplingInRegion(qid1, qid2))
              .map(([qid1, qid2]) => {
                const couplingId = `${qid1}-${qid2}`;
                const metric =
                  displayData[couplingId] || displayData[`${qid2}-${qid1}`];

                // Use explicit positions from topology
                const pos1 = getQubitPosition(qid1);
                const pos2 = getQubitPosition(qid2);
                const row1 = pos1.row;
                const col1 = pos1.col;
                const row2 = pos2.row;
                const col2 = pos2.col;

                const displayRow1 = row1 - displayGridStart.row;
                const displayCol1 = col1 - displayGridStart.col;
                const displayRow2 = row2 - displayGridStart.row;
                const displayCol2 = col2 - displayGridStart.col;
                const centerX =
                  ((displayCol1 + displayCol2) / 2) * (displayCellSize + gap) +
                  displayCellSize / 2;
                const centerY =
                  ((displayRow1 + displayRow2) / 2) * (displayCellSize + gap) +
                  displayCellSize / 2;

                const value = metric?.value ?? null;
                const bgColor = stats
                  ? getColor(value, stats.min, stats.max)
                  : null;

                return (
                  <button
                    key={couplingId}
                    onClick={() =>
                      metric && setSelectedCouplingInfo({ couplingId, metric })
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
                    {/* Coupling ID Label - hidden on mobile in full view */}
                    <div
                      className={`absolute top-0.5 left-0.5 md:top-1 md:left-1 backdrop-blur-sm px-1 py-0.5 md:px-2 rounded text-[0.5rem] md:text-xs font-bold shadow-sm ${
                        zoomMode === "full" ? "hidden md:block" : ""
                      } ${
                        value !== null && value !== undefined
                          ? "bg-black/30 text-white"
                          : "bg-base-content/20 text-base-content"
                      }`}
                    >
                      {couplingId}
                    </div>

                    {/* Value Display */}
                    {value !== null && value !== undefined && (
                      <div className="flex flex-col items-center justify-center h-full">
                        <div className="text-[0.5rem] sm:text-xs md:text-sm lg:text-base font-bold text-white drop-shadow-md">
                          {value.toFixed(2)}
                        </div>
                        {/* Unit - hidden on mobile in full view */}
                        <div
                          className={`text-[0.4rem] md:text-xs text-white/90 font-medium drop-shadow ${
                            zoomMode === "full" ? "hidden md:block" : ""
                          }`}
                        >
                          {unit}
                        </div>
                      </div>
                    )}

                    {/* No data indicator */}
                    {(value === null || value === undefined) && (
                      <div className="flex flex-col items-center justify-center h-full">
                        <div className="text-[0.5rem] sm:text-xs text-base-content/40 font-medium">
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
              });
          })()}

          {/* Region selection overlay - only for square grids */}
          {zoomMode === "full" && regionSelectionEnabled && isSquareGrid && (
            <>
              {Array.from({ length: numRegions * numRegions }).map(
                (_, index) => {
                  const regionRow = Math.floor(index / numRegions);
                  const regionCol = index % numRegions;
                  const isHovered =
                    hoveredRegion?.row === regionRow &&
                    hoveredRegion?.col === regionCol;

                  const regionX =
                    regionCol * regionSize * (displayCellSize + gap);
                  const regionY =
                    regionRow * regionSize * (displayCellSize + gap);
                  const regionWidth =
                    regionSize * (displayCellSize + gap) - gap;
                  const regionHeight =
                    regionSize * (displayCellSize + gap) - gap;

                  return (
                    <button
                      key={index}
                      className={`absolute transition-colors duration-200 rounded-lg flex items-center justify-center z-20 ${
                        isHovered
                          ? "bg-primary/30 border-2 border-primary shadow-lg"
                          : "bg-primary/5 border-2 border-primary/20 hover:border-primary/40 hover:bg-primary/10"
                      }`}
                      style={{
                        top: regionY,
                        left: regionX,
                        width: regionWidth,
                        height: regionHeight,
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
                },
              )}
            </>
          )}
        </div>
      </div>

      {/* Coupling Detail Modal with History */}
      <dialog
        ref={modalRef}
        className="modal modal-bottom sm:modal-middle"
        onClose={() => setSelectedCouplingInfo(null)}
      >
        <div className="modal-box w-full sm:w-11/12 max-w-5xl bg-base-100 p-0 max-h-[85vh] sm:max-h-[90vh] overflow-hidden flex flex-col">
          {selectedCouplingInfo && (
            <>
              {/* Modal Header */}
              <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-base-300 flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg sm:text-2xl font-bold truncate">
                    {selectedCouplingInfo.couplingId} - {title}
                  </h2>
                  <p className="text-sm sm:text-base text-base-content/70 mt-0.5 sm:mt-1">
                    {selectedCouplingInfo.metric.value !== null
                      ? `${selectedCouplingInfo.metric.value.toFixed(4)} ${unit}`
                      : "No data"}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedCouplingInfo(null)}
                  className="btn btn-ghost btn-sm btn-circle flex-shrink-0 ml-2"
                >
                  ✕
                </button>
              </div>

              {/* Modal Content - History */}
              <div className="flex-1 overflow-auto p-3 sm:p-6">
                <CouplingMetricHistoryModal
                  chipId={chipId}
                  couplingId={selectedCouplingInfo.couplingId}
                  metricName={metricKey}
                  metricUnit={unit}
                />
              </div>

              {/* Modal Footer */}
              <div className="px-4 sm:px-6 py-3 sm:py-4 border-t border-base-300 flex justify-between items-center">
                <Link
                  href={`/provenance?parameter=${encodeURIComponent(metricKey)}&qid=${encodeURIComponent(selectedCouplingInfo.couplingId)}&tab=lineage`}
                  className="btn btn-ghost btn-sm sm:btn-md gap-1"
                >
                  <GitBranch className="h-4 w-4" />
                  <span className="hidden sm:inline">Lineage</span>
                </Link>
                <div className="flex gap-2">
                  <button
                    onClick={() => setSelectedCouplingInfo(null)}
                    className="btn btn-ghost btn-sm sm:btn-md"
                  >
                    Close
                  </button>
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
