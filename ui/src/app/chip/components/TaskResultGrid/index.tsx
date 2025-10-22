"use client";

import { useRouter } from "next/navigation";
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
  const router = useRouter();
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);

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

  return (
    <div className="space-y-6">
      <div
        className={`grid gap-2 p-4 bg-base-200/50 rounded-xl`}
        style={{ gridTemplateColumns: `repeat(${gridSize}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: gridSize * gridSize }).map((_, index) => {
          const row = Math.floor(index / gridSize);
          const col = index % gridSize;
          const qid = Object.keys(gridPositions).find(
            (key) =>
              gridPositions[key].row === row && gridPositions[key].col === col,
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
            <div key={index} className="relative group">
              <button
                onClick={() => {
                  if (figurePath) setSelectedTaskInfo({ qid, task });
                }}
                className={`aspect-square rounded-lg bg-base-100 shadow-sm overflow-hidden hover:shadow-md transition-shadow relative w-full ${
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

              {/* Detail Analysis Button */}
              <button
                onClick={() => router.push(`/chip/${chipId}/qubit/${qid}`)}
                className="absolute top-1 right-1 btn btn-xs btn-primary opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                title="Detailed Analysis"
              >
                Detail
              </button>
            </div>
          );
        })}
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
      />
    </div>
  );
}
