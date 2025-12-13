"use client";

import { useMemo, useState, useRef, useEffect, useCallback } from "react";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/components/charts/TaskFigure";
import { TaskHistoryModal } from "@/components/features/chip/modals/TaskHistoryModal";
import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import { useQubitTaskResults } from "@/hooks/useQubitTaskResults";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import {
  getQubitGridPosition,
  type TopologyLayoutParams,
} from "@/utils/gridPosition";

interface TaskResultGridProps {
  chipId: string;
  topologyId: string;
  selectedTask: string;
  selectedDate: string;
  gridSize: number;
  onDateChange?: (date: string) => void;
}

interface SelectedTaskInfo {
  qid: string;
  taskName: string;
}

export function TaskResultGrid({
  chipId,
  topologyId,
  selectedTask,
  selectedDate,
  gridSize: defaultGridSize,
}: TaskResultGridProps) {
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

  // Cell size calculation for responsive grid
  const [cellSize, setCellSize] = useState(60);
  const [isMobile, setIsMobile] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Calculate cell size based on container and viewport
  const updateSize = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const displayCols = gridCols;
    const displayRows = gridRows;

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
    const minSize = mobile ? 32 : 50;
    const calculatedSize = Math.min(maxCellByWidth, maxCellByHeight);
    setCellSize(Math.max(minSize, calculatedSize));
  }, [gridCols, gridRows]);

  useEffect(() => {
    const timeoutId = setTimeout(updateSize, 0);
    window.addEventListener("resize", updateSize);
    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener("resize", updateSize);
    };
  }, [updateSize]);

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
    isLoading: isLoadingTask,
    isError: isTaskError,
  } = useQubitTaskResults({
    chipId,
    task: selectedTask,
    selectedDate,
    keepPrevious: true,
  });

  if (isLoadingTask)
    return (
      <div className="w-full flex justify-center py-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  if (isTaskError)
    return <div className="alert alert-error">Failed to load data</div>;

  const gridPositions: { [key: string]: { row: number; col: number } } = {};
  if (taskResponse?.data?.result) {
    Object.keys(taskResponse.data.result).forEach((qid) => {
      // Parse numeric ID from qid (handles both "Q00" format and plain numbers)
      const numericId = parseInt(qid.replace(/\D/g, ""), 10);
      // Use explicit position from topology if available
      if (topologyQubits && topologyQubits[numericId]) {
        gridPositions[qid] = topologyQubits[numericId];
      } else {
        // Fallback to computed position
        const pos = getQubitGridPosition(qid, layoutParams);
        gridPositions[qid] = pos;
      }
    });
  }

  const getTaskResult = (qid: string): Task | null =>
    taskResponse?.data?.result?.[qid] || null;

  // Calculate displayed grid size based on zoom mode
  const displayGridSize = zoomMode === "region" ? regionSize : gridSize;
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

  return (
    <div className="space-y-4">
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

      {/* Grid Container - scrollable for non-square or large grids */}
      <div className="relative overflow-x-auto p-1 md:p-4" ref={containerRef}>
        <div
          className="grid gap-1 md:gap-2 p-2 md:p-4 bg-base-200/50 rounded-xl relative"
          style={{
            gridTemplateColumns: `repeat(${zoomMode === "region" ? displayGridSize : gridCols}, minmax(${cellSize}px, 1fr))`,
            gridTemplateRows: `repeat(${zoomMode === "region" ? displayGridSize : gridRows}, minmax(${cellSize}px, 1fr))`,
            width: `${(() => {
              const cols = zoomMode === "region" ? displayGridSize : gridCols;
              return (
                cols * cellSize +
                (cols - 1) * (isMobile ? 4 : 8) +
                (isMobile ? 16 : 32)
              );
            })()}px`,
          }}
        >
          {Array.from({
            length:
              zoomMode === "region"
                ? displayGridSize * displayGridSize
                : gridRows * gridCols,
          }).map((_, index) => {
            const cols = zoomMode === "region" ? displayGridSize : gridCols;
            const localRow = Math.floor(index / cols);
            const localCol = index % cols;
            const actualRow = displayGridStart.row + localRow;
            const actualCol = displayGridStart.col + localCol;

            // Calculate MUX index for this cell
            const muxRow = Math.floor(actualRow / muxSize);
            const muxCol = Math.floor(actualCol / muxSize);
            const isEvenMux = (muxRow + muxCol) % 2 === 0;

            // MUX background class
            const muxBgClass =
              hasMux && showMuxBoundaries
                ? isEvenMux
                  ? "ring-2 ring-inset ring-primary/20"
                  : "ring-2 ring-inset ring-secondary/20"
                : "";

            const qid = Object.keys(gridPositions).find(
              (key) =>
                gridPositions[key].row === actualRow &&
                gridPositions[key].col === actualCol,
            );
            if (!qid)
              return (
                <div
                  key={index}
                  className={`aspect-square bg-base-300/50 rounded-lg ${muxBgClass}`}
                />
              );

            const task = getTaskResult(qid);
            if (!task)
              return (
                <div
                  key={index}
                  className={`aspect-square bg-base-300 rounded-lg flex items-center justify-center relative ${muxBgClass}`}
                >
                  <div className="text-sm font-medium text-base-content/50">
                    {qid}
                  </div>
                </div>
              );

            const figurePath = Array.isArray(task.figure_path)
              ? task.figure_path[0]
              : task.figure_path || null;
            return (
              <button
                key={index}
                onClick={() => {
                  setSelectedTaskInfo({ qid, taskName: selectedTask });
                }}
                className={`aspect-square rounded-lg bg-base-100 shadow-sm overflow-hidden transition-all duration-200 hover:shadow-xl hover:scale-105 relative w-full ${
                  task.over_threshold
                    ? "border-2 border-primary animate-pulse-light"
                    : ""
                } ${muxBgClass}`}
              >
                {task.figure_path && figurePath && (
                  <div className="absolute inset-0">
                    <TaskFigure
                      path={figurePath}
                      qid={qid}
                      className="w-full h-full object-contain"
                    />
                  </div>
                )}
                <div
                  className={`absolute top-1 left-1 bg-base-100/80 px-1.5 py-0.5 rounded text-xs font-medium ${
                    zoomMode === "full" ? "hidden md:block" : ""
                  }`}
                >
                  {qid}
                </div>
                <div
                  className={`absolute bottom-1 right-1 w-2 h-2 rounded-full ${
                    task.status === "completed"
                      ? "bg-success"
                      : task.status === "failed"
                        ? "bg-error"
                        : "bg-warning"
                  }`}
                />
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
                  gridTemplateColumns: `repeat(${zoomMode === "region" ? displayGridSize : gridCols}, minmax(${cellSize}px, 1fr))`,
                  gridTemplateRows: `repeat(${zoomMode === "region" ? displayGridSize : gridRows}, minmax(${cellSize}px, 1fr))`,
                }}
              >
                {Array.from({
                  length: Math.pow(
                    Math.ceil(
                      (zoomMode === "region" ? displayGridSize : gridCols) /
                        muxSize,
                    ),
                    2,
                  ),
                }).map((_, idx) => {
                  const displayCols =
                    zoomMode === "region" ? displayGridSize : gridCols;
                  const displayRows =
                    zoomMode === "region" ? displayGridSize : gridRows;
                  const numMuxCols = Math.ceil(displayCols / muxSize);
                  const muxLocalRow = Math.floor(idx / numMuxCols);
                  const muxLocalCol = idx % numMuxCols;

                  // Calculate actual MUX position considering zoom offset
                  const muxActualRow =
                    Math.floor(displayGridStart.row / muxSize) + muxLocalRow;
                  const muxActualCol =
                    Math.floor(displayGridStart.col / muxSize) + muxLocalCol;
                  const muxIndex =
                    muxActualRow * Math.floor(gridSize / muxSize) +
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

          {/* Region selection overlay - only when enabled and in full view mode (square grids only) */}
          {zoomMode === "full" &&
            regionSelectionEnabled &&
            gridRows === gridCols && (
              <div className="absolute inset-0 pointer-events-none p-2 md:p-4 z-20">
                <div
                  className="grid gap-1 md:gap-2 w-full h-full"
                  style={{
                    gridTemplateColumns: `repeat(${gridCols}, minmax(${cellSize}px, 1fr))`,
                    gridTemplateRows: `repeat(${gridRows}, minmax(${cellSize}px, 1fr))`,
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

      <TaskHistoryModal
        chipId={chipId}
        qid={selectedTaskInfo?.qid || ""}
        taskName={selectedTaskInfo?.taskName || ""}
        isOpen={!!selectedTaskInfo}
        onClose={() => setSelectedTaskInfo(null)}
      />
    </div>
  );
}
