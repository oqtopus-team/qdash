"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/components/charts/TaskFigure";
import { CouplingTaskHistoryModal } from "@/components/features/chip/modals/CouplingTaskHistoryModal";
import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import { useCouplingTaskResults } from "@/hooks/useCouplingTaskResults";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import {
  getQubitGridPosition,
  type TopologyLayoutParams,
} from "@/utils/gridPosition";

interface CouplingGridProps {
  chipId: string;
  topologyId: string;
  selectedTask: string;
  selectedDate: string;
  gridSize: number;
  onDateChange?: (date: string) => void;
}

interface SelectedTaskInfo {
  couplingId: string;
  taskName: string;
}

interface ExtendedTask extends Task {
  couplingId: string;
}

export function CouplingGrid({
  chipId,
  topologyId,
  selectedTask,
  selectedDate,
  gridSize: defaultGridSize,
}: CouplingGridProps) {
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
    const size = topologyGridSize ?? defaultGridSize;
    return { gridRows: size, gridCols: size };
  }, [topologyQubits, topologyGridSize, defaultGridSize]);

  // Use the larger dimension for square grids, or actual dimensions for non-square
  const gridSize = Math.max(gridRows, gridCols);

  // Layout params for grid position calculations
  const layoutParams: TopologyLayoutParams = useMemo(
    () => ({
      muxEnabled: hasMux,
      muxSize,
      gridSize,
      layoutType,
    }),
    [hasMux, muxSize, gridSize, layoutType],
  );

  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);
  const [cellSize, setCellSize] = useState(60);
  const [isMobile, setIsMobile] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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

  const numRegions = Math.floor(gridSize / regionSize);

  const {
    data: taskResponse,
    isLoading,
    isError,
  } = useCouplingTaskResults({
    chipId,
    task: selectedTask,
    selectedDate,
  });

  // Calculate cell size based on container width
  const updateSize = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const displayCols = zoomMode === "region" ? regionSize : gridCols;
    const displayRows = zoomMode === "region" ? regionSize : gridRows;

    // Get available space - use viewport width for mobile
    const viewportWidth = window.innerWidth;
    const mobile = viewportWidth < 768;
    setIsMobile(mobile);
    const padding = mobile ? 16 : 32;
    const containerWidth =
      Math.min(container.offsetWidth, viewportWidth) - padding * 2;
    const viewportHeight = window.innerHeight;
    // Reserve space for header, controls (~300px)
    const availableHeight = viewportHeight - (mobile ? 250 : 300);

    const gap = mobile ? 4 : 8;
    const totalGapX = gap * (displayCols - 1);
    const totalGapY = gap * (displayRows - 1);

    // Calculate max cell size that fits both dimensions
    const maxCellByWidth = Math.floor(
      (containerWidth - totalGapX) / displayCols,
    );
    const maxCellByHeight = Math.floor(
      (availableHeight - totalGapY) / displayRows,
    );

    // Use smaller dimension, with min size (smaller on mobile)
    const minSize = mobile ? 28 : 40;
    const calculatedSize = Math.min(maxCellByWidth, maxCellByHeight);
    setCellSize(Math.max(minSize, calculatedSize));
  }, [gridCols, gridRows, zoomMode, regionSize]);

  useEffect(() => {
    // Initial calculation with a small delay to ensure container is rendered
    const timeoutId = setTimeout(updateSize, 0);

    window.addEventListener("resize", updateSize);
    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener("resize", updateSize);
    };
  }, [updateSize]);

  // Recalculate when data loads
  useEffect(() => {
    if (taskResponse?.data) {
      updateSize();
    }
  }, [taskResponse?.data, updateSize]);

  const normalizedResultMap: Record<string, ExtendedTask[]> = {};
  if (taskResponse?.data?.result) {
    for (const [couplingId, task] of Object.entries(taskResponse.data.result)) {
      const [a, b] = couplingId.split("-").map(Number);
      const normKey = a < b ? `${a}-${b}` : `${b}-${a}`;
      if (!normalizedResultMap[normKey]) normalizedResultMap[normKey] = [];
      normalizedResultMap[normKey].push({
        ...task,
        couplingId,
      } as ExtendedTask);
      normalizedResultMap[normKey].sort(
        (a, b) => (b.default_view ? 1 : 0) - (a.default_view ? 1 : 0),
      );
    }
  }

  if (isLoading)
    return (
      <div className="w-full flex justify-center py-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  if (isError)
    return <div className="alert alert-error">Failed to load data</div>;

  // Calculate displayed area based on zoom mode
  const displayCellSize = zoomMode === "region" ? cellSize * 0.8 : cellSize;
  const displayGridSize = zoomMode === "region" ? regionSize : gridSize;
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

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

  return (
    <div ref={containerRef} className="space-y-4 px-4">
      {/* Zoom mode toggle - only show in full view mode for square grids */}
      {zoomMode === "full" && gridRows === gridCols && (
        <div className="px-4">
          <RegionZoomToggle
            enabled={regionSelectionEnabled}
            onToggle={setRegionSelectionEnabled}
          />
        </div>
      )}

      {/* Back button when in region mode */}
      {zoomMode === "region" && selectedRegion && (
        <div className="flex items-center gap-4 px-4">
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

      {/* Grid Container - scrollable for non-square or large grids */}
      <div className="relative overflow-x-auto p-1 md:p-4">
        <div
          className="relative flex-shrink-0 mx-auto"
          style={{
            width:
              zoomMode === "region"
                ? displayGridSize * (displayCellSize + (isMobile ? 4 : 8))
                : gridCols * (displayCellSize + (isMobile ? 4 : 8)),
            height:
              zoomMode === "region"
                ? displayGridSize * (displayCellSize + (isMobile ? 4 : 8))
                : gridRows * (displayCellSize + (isMobile ? 4 : 8)),
            maxWidth: "100%",
          }}
        >
          {/* Qubit positions - either from topology or computed, with MUX styling */}
          {(() => {
            // Get all qubit IDs to render
            const qubitIds = topologyQubits
              ? Object.keys(topologyQubits).map(Number)
              : Array.from({ length: gridRows * gridCols }, (_, i) => i);

            const gap = isMobile ? 4 : 8;

            return qubitIds
              .filter((qid) => isQubitInRegion(qid))
              .map((qid) => {
                const pos = getQubitPosition(qid);
                const row = pos.row;
                const col = pos.col;

                // Adjust position for region mode
                const displayRow = row - displayGridStart.row;
                const displayCol = col - displayGridStart.col;
                const x = displayCol * (displayCellSize + gap);
                const y = displayRow * (displayCellSize + gap);

                // Calculate MUX index for this cell (using actual position, not display position)
                const muxRow = Math.floor(row / muxSize);
                const muxCol = Math.floor(col / muxSize);
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
                    {/* QID - hidden on mobile in full view */}
                    <span
                      className={zoomMode === "full" ? "hidden md:inline" : ""}
                    >
                      {qid}
                    </span>
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
                  muxActualRow * Math.floor(gridSize / muxSize) + muxActualCol;

                const gap = isMobile ? 4 : 8;
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

          {Object.entries(normalizedResultMap)
            .filter(([normKey]) => {
              const [qid1, qid2] = normKey.split("-").map(Number);
              return isCouplingInRegion(qid1, qid2);
            })
            .map(([normKey, taskList]) => {
              const [qid1, qid2] = normKey.split("-").map(Number);
              const task = taskList[0];
              const figurePath = Array.isArray(task.figure_path)
                ? task.figure_path[0]
                : task.figure_path || null;
              // Use explicit positions from topology
              const pos1 = getQubitPosition(qid1);
              const pos2 = getQubitPosition(qid2);
              const row1 = pos1.row;
              const col1 = pos1.col;
              const row2 = pos2.row;
              const col2 = pos2.col;

              // Adjust position for region mode
              const gap = isMobile ? 4 : 8;
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
              return (
                <button
                  key={normKey}
                  onClick={() => {
                    setSelectedTaskInfo({
                      couplingId: task.couplingId,
                      taskName: selectedTask,
                    });
                  }}
                  style={{
                    position: "absolute",
                    top: centerY,
                    left: centerX,
                    width: displayCellSize * 0.6,
                    height: displayCellSize * 0.6,
                  }}
                  className={`rounded-lg bg-base-100 shadow-sm overflow-hidden transition-all duration-200 hover:shadow-xl hover:scale-105 -translate-x-1/2 -translate-y-1/2 ${
                    task.over_threshold
                      ? "border-2 border-primary animate-pulse-light"
                      : ""
                  }`}
                >
                  {figurePath && (
                    <TaskFigure
                      path={figurePath}
                      qid={String(task.couplingId)}
                      className="w-full h-full object-contain"
                    />
                  )}
                </button>
              );
            })}

          {/* Region selection overlay - only when enabled and in full view mode (square grids only) */}
          {zoomMode === "full" &&
            regionSelectionEnabled &&
            gridRows === gridCols && (
              <>
                {Array.from({ length: numRegions * numRegions }).map(
                  (_, index) => {
                    const regionRow = Math.floor(index / numRegions);
                    const regionCol = index % numRegions;
                    const isHovered =
                      hoveredRegion?.row === regionRow &&
                      hoveredRegion?.col === regionCol;

                    const gap = isMobile ? 4 : 8;
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
              </>
            )}
        </div>
      </div>

      <CouplingTaskHistoryModal
        chipId={chipId}
        couplingId={selectedTaskInfo?.couplingId || ""}
        taskName={selectedTaskInfo?.taskName || ""}
        isOpen={!!selectedTaskInfo}
        onClose={() => setSelectedTaskInfo(null)}
      />
    </div>
  );
}
