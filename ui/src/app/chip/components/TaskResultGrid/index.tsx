"use client";

import { useState, useEffect, useCallback } from "react";

import { keepPreviousData } from "@tanstack/react-query";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/app/components/TaskFigure";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import {
  useFetchLatestQubitTaskGroupedByChip,
  useFetchHistoricalQubitTaskGroupedByChip,
} from "@/client/chip/chip";
import { TaskDetailModal } from "@/shared/components/TaskDetailModal";

interface TaskResultGridProps {
  chipId: string;
  selectedTask: string;
  selectedDate: string;
  gridSize: number;
  onDateChange?: (date: string) => void;
}

interface SelectedTaskInfo {
  qid: string;
  task: Task;
}

const MUX_SIZE = 2;

export function TaskResultGrid({
  chipId,
  selectedTask,
  selectedDate,
  gridSize,
  onDateChange,
}: TaskResultGridProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);

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
    isLoading: isLoadingTask,
    isError: isTaskError,
  } = selectedDate === "latest"
    ? useFetchLatestQubitTaskGroupedByChip(chipId, selectedTask, {
        query: {
          placeholderData: keepPreviousData,
          staleTime: 30000, // 30 seconds
        },
      })
    : useFetchHistoricalQubitTaskGroupedByChip(
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

  // Track previous date to distinguish modal navigation from external navigation
  const [previousDate, setPreviousDate] = useState(selectedDate);

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
        const updatedTask = taskResponse.data.result?.[selectedTaskInfo.qid];
        if (updatedTask) {
          setSelectedTaskInfo((prev) => {
            // Only update if the modal is still open and for the same qid
            if (prev?.qid === selectedTaskInfo.qid) {
              return { ...prev, task: updatedTask };
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
  }, [taskResponse?.data?.result, selectedTaskInfo?.qid]);

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
      const qidNum = parseInt(qid);
      const muxIndex = Math.floor(qidNum / 4);
      const muxRow = Math.floor(muxIndex / (gridSize / MUX_SIZE));
      const muxCol = muxIndex % (gridSize / MUX_SIZE);
      const localIndex = qidNum % 4;
      const localRow = Math.floor(localIndex / 2);
      const localCol = localIndex % 2;
      gridPositions[qid] = {
        row: muxRow * MUX_SIZE + localRow,
        col: muxCol * MUX_SIZE + localCol,
      };
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

      {/* Grid Container */}
      <div className="relative">
        <div
          className={`grid gap-2 p-4 bg-base-200/50 rounded-xl relative`}
          style={{
            gridTemplateColumns: `repeat(${displayGridSize}, minmax(0, 1fr))`,
          }}
        >
          {/* MUX highlight overlay */}
          <div className="absolute inset-0 pointer-events-none p-4">
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
          <div className="absolute inset-0 pointer-events-none p-4 z-10">
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
          {Array.from({ length: displayGridSize * displayGridSize }).map(
            (_, index) => {
              const localRow = Math.floor(index / displayGridSize);
              const localCol = index % displayGridSize;
              const actualRow = displayGridStart.row + localRow;
              const actualCol = displayGridStart.col + localCol;

              const qid = Object.keys(gridPositions).find(
                (key) =>
                  gridPositions[key].row === actualRow &&
                  gridPositions[key].col === actualCol,
              );
              if (!qid)
                return (
                  <div
                    key={index}
                    className="aspect-square bg-base-300/50 rounded-lg"
                  />
                );

              const task = getTaskResult(qid);
              if (!task)
                return (
                  <div
                    key={index}
                    className="aspect-square bg-base-300 rounded-lg flex items-center justify-center"
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
                    if (figurePath) setSelectedTaskInfo({ qid, task });
                  }}
                  className={`aspect-square rounded-lg bg-base-100 shadow-sm overflow-hidden transition-all duration-200 hover:shadow-xl hover:scale-105 relative w-full ${
                    task.over_threshold
                      ? "border-2 border-primary animate-pulse-light"
                      : ""
                  }`}
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
                  <div className="absolute top-1 left-1 bg-base-100/80 px-1.5 py-0.5 rounded text-xs font-medium">
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
            },
          )}
        </div>

        {/* Region selection overlay - only when enabled and in full view mode */}
        {zoomMode === "full" && regionSelectionEnabled && (
          <div className="absolute inset-0 pointer-events-none">
            <div className="relative w-full h-full p-4">
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
                        title={`Zoom to region (${regionRow + 1}, ${regionCol + 1})`}
                      />
                    );
                  },
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      <TaskDetailModal
        isOpen={!!selectedTaskInfo}
        task={selectedTaskInfo?.task || null}
        qid={selectedTaskInfo?.qid || ""}
        onClose={() => setSelectedTaskInfo(null)}
        chipId={chipId}
        selectedDate={selectedDate}
        onNavigatePrevious={navigateToPreviousDay}
        onNavigateNext={navigateToNextDay}
        canNavigatePrevious={canNavigatePrevious}
        canNavigateNext={canNavigateNext}
        formatDate={formatDate}
        taskName={selectedTaskInfo?.task?.name}
        variant="detailed"
      />
    </div>
  );
}
