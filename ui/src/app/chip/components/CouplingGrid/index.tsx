"use client";

import dynamic from "next/dynamic";
import { useState, useEffect, useCallback, useRef } from "react";

import { keepPreviousData } from "@tanstack/react-query";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/app/components/TaskFigure";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import {
  useFetchLatestCouplingTaskGroupedByChip,
  useFetchHistoricalCouplingTaskGroupedByChip,
} from "@/client/chip/chip";

const PlotlyRenderer = dynamic(
  () => import("@/app/components/PlotlyRenderer").then((mod) => mod.default),
  { ssr: false },
);

interface CouplingGridProps {
  chipId: string;
  selectedTask: string;
  selectedDate: string;
  gridSize: number;
  onDateChange?: (date: string) => void;
}

interface ParameterValue {
  value: unknown;
  unit?: string;
}

interface ExtendedTask extends Task {
  couplingId: string;
}

interface SelectedTaskInfo {
  path: string;
  couplingId: string;
  taskList: ExtendedTask[];
  index: number;
  subIndex?: number;
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
  onDateChange,
}: CouplingGridProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);
  const [viewMode, setViewMode] = useState<"static" | "interactive">("static");
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

  // Track previous date to distinguish modal navigation from external navigation
  const [previousDate, setPreviousDate] = useState(selectedDate);

  // Use custom hook for date navigation
  const {
    navigateToPreviousDay: originalNavigateToPreviousDay,
    navigateToNextDay: originalNavigateToNextDay,
    canNavigatePrevious,
    canNavigateNext,
    formatDate,
  } = useDateNavigation(chipId, selectedDate, onDateChange);

  // Wrap navigation functions to track modal navigation
  const navigateToPreviousDay = useCallback(() => {
    if (selectedTaskInfo) {
      // Modal navigation - don't close modal
      originalNavigateToPreviousDay();
    } else {
      originalNavigateToPreviousDay();
    }
  }, [originalNavigateToPreviousDay, selectedTaskInfo]);

  const navigateToNextDay = useCallback(() => {
    if (selectedTaskInfo) {
      // Modal navigation - don't close modal
      originalNavigateToNextDay();
    } else {
      originalNavigateToNextDay();
    }
  }, [originalNavigateToNextDay, selectedTaskInfo]);

  const {
    data: taskResponse,
    isLoading,
    isError,
  } = selectedDate === "latest"
    ? useFetchLatestCouplingTaskGroupedByChip(chipId, selectedTask, {
        query: {
          placeholderData: keepPreviousData,
          staleTime: 30000, // 30 seconds
        },
      })
    : useFetchHistoricalCouplingTaskGroupedByChip(
        chipId,
        selectedTask,
        selectedDate,
        {
          query: {
            placeholderData: keepPreviousData,
            staleTime: 30000, // 30 seconds
          },
        },
      );

  // Reset modal only when date changes externally (not from modal navigation)
  useEffect(() => {
    if (previousDate !== selectedDate && !selectedTaskInfo) {
      // External navigation - no modal open, safe to update
      setPreviousDate(selectedDate);
    } else if (previousDate !== selectedDate && selectedTaskInfo) {
      // Date changed while modal is open - update previous date but keep modal
      setPreviousDate(selectedDate);
    }
  }, [selectedDate, selectedTaskInfo, previousDate]);

  // Update modal data with debounce to prevent race conditions
  useEffect(() => {
    let timeoutId: NodeJS.Timeout;

    if (selectedTaskInfo && taskResponse?.data?.result) {
      timeoutId = setTimeout(() => {
        const normalizedResultMap: Record<string, ExtendedTask[]> = {};
        for (const [couplingId, task] of Object.entries(
          taskResponse.data.result,
        )) {
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

        const updatedTaskList =
          normalizedResultMap[selectedTaskInfo.couplingId];
        if (updatedTaskList) {
          setSelectedTaskInfo((prev) => {
            // Only update if the modal is still open and for the same couplingId
            if (prev?.couplingId === selectedTaskInfo.couplingId) {
              return { ...prev, taskList: updatedTaskList };
            }
            return prev;
          });
        }
      }, 100); // 100ms debounce
    }

    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [taskResponse?.data?.result, selectedTaskInfo?.couplingId]);

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
                  {qid}
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
                    if (figurePath) {
                      setSelectedTaskInfo({
                        path: figurePath,
                        couplingId: normKey,
                        taskList,
                        index: 0,
                        subIndex: 0,
                      });
                      setViewMode("static");
                    }
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
            <div className="absolute inset-0 pointer-events-none">
              <div
                className="grid gap-2 w-full h-full"
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
                          setSelectedRegion({ row: regionRow, col: regionCol });
                          setZoomMode("region");
                        }}
                        title={`Zoom to region (${regionRow + 1}, ${
                          regionCol + 1
                        })`}
                      />
                    );
                  },
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {selectedTaskInfo && (
        <dialog className="modal modal-open">
          <div className="modal-box max-w-6xl p-6 rounded-2xl shadow-xl bg-base-100">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">
                Coupling{" "}
                {selectedTaskInfo.taskList[selectedTaskInfo.index].couplingId}
              </h3>
              <div className="flex items-center gap-2">
                {onDateChange && (
                  <>
                    <button
                      onClick={navigateToPreviousDay}
                      disabled={!canNavigatePrevious}
                      className="btn btn-sm btn-ghost"
                      title="Previous Day"
                    >
                      ←
                    </button>
                    <span className="text-sm text-base-content/70 px-2">
                      {formatDate(selectedDate)}
                    </span>
                    <button
                      onClick={navigateToNextDay}
                      disabled={!canNavigateNext}
                      className="btn btn-sm btn-ghost"
                      title="Next Day"
                    >
                      →
                    </button>
                  </>
                )}
                <button
                  onClick={() => setSelectedTaskInfo(null)}
                  className="btn btn-sm btn-circle btn-ghost"
                >
                  ✕
                </button>
              </div>
            </div>

            {viewMode === "static" ? (
              <div className="grid grid-cols-2 gap-8">
                <div className="aspect-square bg-base-200/50 rounded-xl p-4">
                  {(() => {
                    const selectedTask =
                      selectedTaskInfo.taskList[selectedTaskInfo.index];
                    const figures = Array.isArray(selectedTask.figure_path)
                      ? selectedTask.figure_path
                      : selectedTask.figure_path
                        ? [selectedTask.figure_path]
                        : [];
                    const currentSubIndex = selectedTaskInfo.subIndex ?? 0;
                    const currentFigure = figures[currentSubIndex];
                    return (
                      <>
                        <TaskFigure
                          path={currentFigure}
                          qid={String(selectedTask.couplingId)}
                          className="w-full h-full object-contain"
                        />
                        {figures.length > 1 && (
                          <div className="flex justify-center mt-2 gap-2">
                            <button
                              className="btn btn-xs"
                              onClick={() =>
                                setSelectedTaskInfo((prev) =>
                                  prev
                                    ? {
                                        ...prev,
                                        subIndex:
                                          ((prev.subIndex ?? 0) -
                                            1 +
                                            figures.length) %
                                          figures.length,
                                      }
                                    : null,
                                )
                              }
                            >
                              ◀
                            </button>
                            <span className="text-sm">
                              {currentSubIndex + 1} / {figures.length}
                            </span>
                            <button
                              className="btn btn-xs"
                              onClick={() =>
                                setSelectedTaskInfo((prev) =>
                                  prev
                                    ? {
                                        ...prev,
                                        subIndex:
                                          ((prev.subIndex ?? 0) + 1) %
                                          figures.length,
                                      }
                                    : null,
                                )
                              }
                            >
                              ▶
                            </button>
                          </div>
                        )}
                        {selectedTask.json_figure_path && (
                          <button
                            className="btn btn-sm mt-4"
                            onClick={() => setViewMode("interactive")}
                          >
                            Interactive View
                          </button>
                        )}
                      </>
                    );
                  })()}
                </div>
                <div className="space-y-6">
                  {selectedTaskInfo.taskList.length > 1 && (
                    <button
                      className="btn btn-sm"
                      onClick={() =>
                        setSelectedTaskInfo((prev) =>
                          prev
                            ? {
                                ...prev,
                                index: (prev.index + 1) % prev.taskList.length,
                                subIndex: 0,
                              }
                            : null,
                        )
                      }
                    >
                      Toggle Direction
                    </button>
                  )}
                  <div className="card bg-base-200 p-4 rounded-xl">
                    <h4 className="font-medium mb-2">Status</h4>
                    <div
                      className={`badge ${
                        selectedTaskInfo.taskList[selectedTaskInfo.index]
                          .status === "completed"
                          ? "badge-success"
                          : selectedTaskInfo.taskList[selectedTaskInfo.index]
                                .status === "failed"
                            ? "badge-error"
                            : "badge-warning"
                      }`}
                    >
                      {selectedTaskInfo.taskList[selectedTaskInfo.index].status}
                    </div>
                  </div>
                  {(() => {
                    const endAt =
                      selectedTaskInfo.taskList[selectedTaskInfo.index].end_at;
                    if (!endAt) return null;
                    return (
                      <div className="card bg-base-200 p-4 rounded-xl">
                        <h4 className="font-medium mb-2">Calibrated At</h4>
                        <p className="text-sm">
                          {new Date(endAt).toLocaleString()}
                        </p>
                      </div>
                    );
                  })()}
                  {(() => {
                    const outputParams =
                      selectedTaskInfo.taskList[selectedTaskInfo.index]
                        .output_parameters;
                    if (!outputParams) return null;

                    return (
                      <div className="card bg-base-200 p-4 rounded-xl">
                        <h4 className="font-medium mb-2">Parameters</h4>
                        <div className="space-y-2">
                          {Object.entries(outputParams).map(([key, value]) => {
                            const paramValue: ParameterValue =
                              typeof value === "object" &&
                              value !== null &&
                              "value" in value
                                ? (value as ParameterValue)
                                : { value };
                            return (
                              <div key={key} className="flex justify-between">
                                <span className="font-medium">{key}:</span>
                                <span>
                                  {typeof paramValue.value === "number"
                                    ? paramValue.value.toFixed(4)
                                    : String(paramValue.value)}
                                  {paramValue.unit ? ` ${paramValue.unit}` : ""}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })()}
                  {selectedTaskInfo.taskList[selectedTaskInfo.index]
                    .message && (
                    <div className="card bg-base-200 p-4 rounded-xl">
                      <h4 className="font-medium mb-2">Message</h4>
                      <p className="text-sm">
                        {
                          selectedTaskInfo.taskList[selectedTaskInfo.index]
                            .message
                        }
                      </p>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="w-full h-[70vh] flex justify-center items-center">
                <div className="w-[70vw] h-full bg-base-200 rounded-xl p-4 shadow flex justify-center items-center">
                  <div className="w-full h-full flex justify-center items-center">
                    <div className="w-fit h-fit m-auto">
                      <PlotlyRenderer
                        className="w-full h-full"
                        fullPath={`${
                          process.env.NEXT_PUBLIC_API_URL
                        }/api/executions/figure?path=${encodeURIComponent(
                          selectedTaskInfo.taskList[selectedTaskInfo.index]
                            .json_figure_path?.[0] || "",
                        )}`}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="mt-6 flex justify-end gap-2">
              {viewMode === "interactive" &&
                (() => {
                  const selectedTask =
                    selectedTaskInfo.taskList[selectedTaskInfo.index];
                  const path = selectedTask.json_figure_path;
                  const figures = Array.isArray(path)
                    ? path
                    : path
                      ? [path]
                      : [];
                  const currentSubIndex = selectedTaskInfo.subIndex ?? 0;
                  const currentFigure = figures[currentSubIndex];

                  return (
                    <div className="w-full h-[70vh] flex flex-col justify-center items-center space-y-4">
                      <div className="w-[70vw] h-full bg-base-200 rounded-xl p-4 shadow flex justify-center items-center">
                        <div className="w-full h-full flex justify-center items-center">
                          <div className="w-fit h-fit m-auto">
                            <PlotlyRenderer
                              className="w-full h-full"
                              fullPath={`${
                                process.env.NEXT_PUBLIC_API_URL
                              }/api/executions/figure?path=${encodeURIComponent(
                                currentFigure || "",
                              )}`}
                            />
                          </div>
                        </div>
                      </div>

                      {figures.length > 1 && (
                        <div className="flex justify-center gap-2">
                          <button
                            className="btn btn-xs"
                            onClick={() =>
                              setSelectedTaskInfo((prev) =>
                                prev
                                  ? {
                                      ...prev,
                                      subIndex:
                                        ((prev.subIndex ?? 0) -
                                          1 +
                                          figures.length) %
                                        figures.length,
                                    }
                                  : null,
                              )
                            }
                          >
                            ◀
                          </button>
                          <span className="text-sm">
                            {currentSubIndex + 1} / {figures.length}
                          </span>
                          <button
                            className="btn btn-xs"
                            onClick={() =>
                              setSelectedTaskInfo((prev) =>
                                prev
                                  ? {
                                      ...prev,
                                      subIndex:
                                        ((prev.subIndex ?? 0) + 1) %
                                        figures.length,
                                    }
                                  : null,
                              )
                            }
                          >
                            ▶
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })()}
            </div>
          </div>
          <form method="dialog" className="modal-backdrop">
            <button onClick={() => setSelectedTaskInfo(null)}>close</button>
          </form>
        </dialog>
      )}
    </div>
  );
}
