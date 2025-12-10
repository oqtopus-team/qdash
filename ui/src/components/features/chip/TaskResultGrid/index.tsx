"use client";

import { useState, useRef } from "react";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/components/charts/TaskFigure";
import { TaskHistoryModal } from "@/components/features/chip/modals/TaskHistoryModal";
import { useQubitTaskResults } from "@/hooks/useQubitTaskResults";

interface TaskResultGridProps {
  chipId: string;
  selectedTask: string;
  selectedDate: string;
  gridSize: number;
  onDateChange?: (date: string) => void;
}

interface SelectedTaskInfo {
  qid: string;
  taskName: string;
}

const MUX_SIZE = 2;

export function TaskResultGrid({
  chipId,
  selectedTask,
  selectedDate,
  gridSize,
}: TaskResultGridProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);

  // Long press preview state
  const [previewQubit, setPreviewQubit] = useState<{
    qid: string;
    task: Task;
  } | null>(null);
  const longPressTimerRef = useRef<NodeJS.Timeout | null>(null);

  const handleLongPressStart = (qid: string, task: Task) => {
    longPressTimerRef.current = setTimeout(() => {
      setPreviewQubit({ qid, task });
    }, 300); // 300ms for long press
  };

  const handleLongPressEnd = () => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  };

  const handleClosePreview = () => {
    setPreviewQubit(null);
  };

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

      {/* Long press preview overlay */}
      {previewQubit && (
        <div
          className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center pt-16 px-4"
          onClick={handleClosePreview}
          onTouchEnd={handleClosePreview}
        >
          <div className="bg-base-100 rounded-xl shadow-2xl max-w-sm w-full overflow-hidden">
            {/* Preview image */}
            <div className="aspect-square bg-base-200">
              {previewQubit.task.figure_path && (
                <TaskFigure
                  path={
                    Array.isArray(previewQubit.task.figure_path)
                      ? previewQubit.task.figure_path[0]
                      : previewQubit.task.figure_path
                  }
                  qid={previewQubit.qid}
                  className="w-full h-full object-contain"
                />
              )}
            </div>
            {/* Info */}
            <div className="p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-lg">
                  QID: {previewQubit.qid}
                </span>
                <span
                  className={`badge ${
                    previewQubit.task.status === "completed"
                      ? "badge-success"
                      : previewQubit.task.status === "failed"
                        ? "badge-error"
                        : "badge-warning"
                  }`}
                >
                  {previewQubit.task.status}
                </span>
              </div>
              {previewQubit.task.end_at && (
                <div className="text-sm text-base-content/70">
                  {new Date(previewQubit.task.end_at).toLocaleString("ja-JP", {
                    timeZone: "Asia/Tokyo",
                  })}
                </div>
              )}
              <div className="text-xs text-base-content/50">
                Tap anywhere to close • Tap cell to view history
              </div>
            </div>
          </div>
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
          {/* MUX labels overlay - hidden on mobile in full view */}
          <div
            className={`absolute inset-0 pointer-events-none p-4 z-10 ${
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
                    handleLongPressEnd();
                    setSelectedTaskInfo({ qid, taskName: selectedTask });
                  }}
                  onTouchStart={() => handleLongPressStart(qid, task)}
                  onTouchEnd={handleLongPressEnd}
                  onTouchCancel={handleLongPressEnd}
                  onMouseDown={() => handleLongPressStart(qid, task)}
                  onMouseUp={handleLongPressEnd}
                  onMouseLeave={handleLongPressEnd}
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
            },
          )}
        </div>

        {/* Region selection overlay - only when enabled and in full view mode */}
        {zoomMode === "full" && regionSelectionEnabled && (
          <div className="absolute inset-0 pointer-events-none p-4 z-20">
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
