"use client";

import { useState, useEffect, useCallback, useRef } from "react";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/components/charts/TaskFigure";
import { CouplingTaskHistoryModal } from "@/components/features/chip/modals/CouplingTaskHistoryModal";
import { useCouplingTaskResults } from "@/hooks/useCouplingTaskResults";

interface CouplingGridProps {
  chipId: string;
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

const MUX_SIZE = 2;

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

export function CouplingGrid({
  chipId,
  selectedTask,
  selectedDate,
  gridSize,
}: CouplingGridProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);
  const [cellSize, setCellSize] = useState(60);
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

  const regionSize = 4; // 4×4 qubits per region
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
    // Use actual container width instead of viewport width
    const containerWidth =
      containerRef.current?.offsetWidth || window.innerWidth;
    // Subtract padding: px-4 on both sides (32px total) + some margin for safety
    const availableWidth = containerWidth - 64; // 64px = padding + margin
    const effectiveGridSize = zoomMode === "region" ? regionSize : gridSize;
    const gap = 8; // gap between cells
    const totalGap = gap * (effectiveGridSize - 1);
    const calculatedSize = Math.floor(
      (availableWidth - totalGap) / effectiveGridSize,
    );
    setCellSize(Math.max(calculatedSize, 30));
  }, [gridSize, zoomMode, regionSize]);

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

  return (
    <div ref={containerRef} className="space-y-4 px-4">
      {/* Zoom mode toggle - only show in full view mode */}
      {zoomMode === "full" && (
        <div className="flex items-center gap-2 px-4">
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
          {/* MUX labels overlay - hidden on mobile in full view */}
          <div
            className={`absolute inset-0 pointer-events-none z-10 ${
              zoomMode === "full" ? "hidden md:block" : ""
            }`}
          >
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
          {Array.from({ length: gridSize === 8 ? 64 : 144 })
            .filter((_, qid) => isQubitInRegion(qid))
            .map((_, idx) => {
              // Find actual qid from filtered index
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

              // Adjust position for region mode
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
                  {/* QID - hidden on mobile in full view */}
                  <span
                    className={zoomMode === "full" ? "hidden md:inline" : ""}
                  >
                    {qid}
                  </span>
                </div>
              );
            })}

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
              const { row1, col1, row2, col2 } = getCouplingPosition(
                qid1,
                qid2,
                gridSize,
              );

              // Adjust position for region mode
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

          {/* Region selection overlay - only when enabled and in full view mode */}
          {zoomMode === "full" && regionSelectionEnabled && (
            <div className="absolute inset-0 pointer-events-none z-20">
              <div
                className="grid gap-2 w-full h-full"
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
              </div>
            </div>
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
