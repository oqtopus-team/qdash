"use client";

import { useMemo, useState, memo } from "react";
import { TransformWrapper, TransformComponent, useControls } from "react-zoom-pan-pinch";
import { ZoomIn, ZoomOut, Maximize2 } from "lucide-react";

import type { Task } from "@/schemas";

import { useGetChip } from "@/client/chip/chip";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { TaskDetailModal } from "@/components/features/chip/modals/TaskDetailModal";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import { getQubitGridPosition, type TopologyLayoutParams } from "@/lib/utils/grid-position";
import { calculateGridContainerWidth } from "@/lib/utils/grid-layout";

interface ExecutionTopologyViewProps {
  chipId: string;
  tasks: Task[];
  filterTaskName: string;
}

// Zoom control buttons
function ZoomControls() {
  const { zoomIn, zoomOut, resetTransform } = useControls();
  return (
    <div className="absolute top-2 right-2 z-30 flex flex-col gap-1">
      <button
        onClick={() => zoomIn()}
        className="btn btn-sm btn-square btn-ghost bg-base-100/90 shadow-md hover:bg-base-200"
        title="Zoom in"
      >
        <ZoomIn className="h-4 w-4" />
      </button>
      <button
        onClick={() => zoomOut()}
        className="btn btn-sm btn-square btn-ghost bg-base-100/90 shadow-md hover:bg-base-200"
        title="Zoom out"
      >
        <ZoomOut className="h-4 w-4" />
      </button>
      <button
        onClick={() => resetTransform()}
        className="btn btn-sm btn-square btn-ghost bg-base-100/90 shadow-md hover:bg-base-200"
        title="Reset view"
      >
        <Maximize2 className="h-4 w-4" />
      </button>
    </div>
  );
}

function getStatusColor(status: string | undefined): string {
  switch (status) {
    case "completed":
      return "bg-success";
    case "failed":
      return "bg-error";
    default:
      return "bg-warning";
  }
}

// Aggregate status: worst status wins
function aggregateStatus(tasks: Task[]): string {
  if (tasks.some((t) => t.status === "failed")) return "failed";
  if (tasks.some((t) => t.status === "running")) return "running";
  if (tasks.every((t) => t.status === "completed")) return "completed";
  return "pending";
}

const EmptyCell = memo(function EmptyCell({ muxBgClass }: { muxBgClass: string }) {
  return <div className={`aspect-square bg-base-300/50 rounded-lg ${muxBgClass}`} />;
});

interface TopologyCellProps {
  qid: string;
  tasks: Task[];
  figurePath: string | null;
  jsonFigurePath: string | null;
  muxBgClass: string;
  showLabels: boolean;
  showFigures: boolean;
  onClick: () => void;
}

const TopologyCell = memo(function TopologyCell({
  qid,
  tasks,
  figurePath,
  jsonFigurePath,
  muxBgClass,
  showLabels,
  showFigures,
  onClick,
}: TopologyCellProps) {
  if (tasks.length === 0) {
    return (
      <div
        className={`aspect-square bg-base-300 rounded-lg flex items-center justify-center relative ${muxBgClass}`}
      >
        {showLabels && <div className="text-sm font-medium text-base-content/50">{qid}</div>}
      </div>
    );
  }

  const status = tasks.length === 1 ? tasks[0].status : aggregateStatus(tasks);

  // Zoomed-out: status-colored tile
  if (!showFigures) {
    return (
      <button
        onClick={onClick}
        className={`aspect-square rounded-lg shadow-sm relative group cursor-pointer ${getStatusColor(status)} ${muxBgClass}`}
      >
        {showLabels && (
          <div className="absolute top-0.5 left-0.5 bg-black/30 text-white px-0.5 py-px rounded text-[0.5rem] font-bold">
            {qid}
          </div>
        )}
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-base-100 text-base-content text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
          {qid}: {status}
          {tasks.length > 1 && ` (${tasks.length} tasks)`}
        </div>
      </button>
    );
  }

  // Zoomed-in: show figure
  return (
    <button
      onClick={onClick}
      className={`aspect-square rounded-xl bg-white shadow-md border border-base-300/60 overflow-hidden transition-all duration-200 hover:shadow-xl hover:scale-105 hover:border-primary/40 relative w-full ${muxBgClass}`}
    >
      {figurePath && (
        <div className="absolute inset-1">
          <TaskFigure
            path={figurePath}
            jsonFigurePath={jsonFigurePath || undefined}
            qid={qid}
            className="w-full h-full object-contain"
          />
        </div>
      )}
      {showLabels && (
        <div className="absolute top-1 left-1 bg-base-100/80 px-1.5 py-0.5 rounded text-xs font-medium">
          {qid}
        </div>
      )}
      <div className={`absolute bottom-1 right-1 w-2 h-2 rounded-full ${getStatusColor(status)}`} />
      {tasks.length > 1 && (
        <div className="absolute top-1 right-1 bg-base-100/80 px-1 py-px rounded text-[0.6rem] font-bold">
          {tasks.length}
        </div>
      )}
    </button>
  );
});

export function ExecutionTopologyView({
  chipId,
  tasks,
  filterTaskName,
}: ExecutionTopologyViewProps) {
  const [selectedQid, setSelectedQid] = useState<string | null>(null);

  // Get chip data to derive topology_id
  const { data: chipData } = useGetChip(chipId, {
    query: { staleTime: Infinity, gcTime: Infinity, enabled: !!chipId },
  });

  const chipSize = chipData?.data?.size ?? 64;
  const topologyId = chipData?.data?.topology_id ?? `square-lattice-mux-${chipSize}`;

  // Get topology config
  const {
    muxSize = 2,
    hasMux = false,
    layoutType = "grid",
    showMuxBoundaries = false,
    qubits: topologyQubits,
    gridSize: topologyGridSize,
  } = useTopologyConfig(topologyId) ?? {};

  const defaultGridSize = Math.ceil(Math.sqrt(chipSize));

  // Calculate grid dimensions
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
    const size = topologyGridSize ?? defaultGridSize;
    return { gridRows: size, gridCols: size };
  }, [topologyQubits, topologyGridSize, defaultGridSize]);

  const gridSize = Math.max(gridRows, gridCols);

  const layoutParams: TopologyLayoutParams = useMemo(
    () => ({
      muxEnabled: hasMux,
      muxSize,
      gridSize,
      layoutType,
    }),
    [hasMux, muxSize, gridSize, layoutType],
  );

  // Group tasks by qid. If filterTaskName is set, only include matching tasks.
  const tasksByQid = useMemo(() => {
    const map: Record<string, Task[]> = {};
    for (const task of tasks) {
      if (!task.qid) continue;
      // Only include qubit-level tasks (skip coupling tasks like "10-11")
      if (task.qid.includes("-")) continue;
      if (filterTaskName !== "all" && task.name !== filterTaskName) continue;
      if (!map[task.qid]) map[task.qid] = [];
      map[task.qid].push(task);
    }
    return map;
  }, [tasks, filterTaskName]);

  // Build grid positions for all qids
  const gridPositions = useMemo(() => {
    const positions: Record<string, { row: number; col: number }> = {};
    for (const qid of Object.keys(tasksByQid)) {
      const numericId = parseInt(qid.replace(/\D/g, ""), 10);
      if (topologyQubits && topologyQubits[numericId]) {
        positions[qid] = topologyQubits[numericId];
      } else {
        positions[qid] = getQubitGridPosition(qid, layoutParams);
      }
    }
    return positions;
  }, [tasksByQid, topologyQubits, layoutParams]);

  // Responsive grid sizing
  const { containerRef, cellSize, isMobile, viewportHeight, gap, padding } = useGridLayout({
    cols: gridCols,
    rows: gridRows,
    reservedHeight: { mobile: 300, desktop: 350 },
    deps: [tasksByQid, topologyQubits],
  });

  const MIN_FIGURE_CELL_SIZE = 60;
  const baseCellSize = Math.max(cellSize, MIN_FIGURE_CELL_SIZE);

  // Fixed LOD thresholds (pan-zoom handles the rest)
  const showLabels = baseCellSize >= 20;
  const showFigures = baseCellSize >= 50;

  // Selected task for modal
  const selectedTask = useMemo(() => {
    if (!selectedQid || !tasksByQid[selectedQid]) return null;
    const qidTasks = tasksByQid[selectedQid];
    // Show the first (or only) task
    return qidTasks[0] ?? null;
  }, [selectedQid, tasksByQid]);

  if (Object.keys(tasksByQid).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-base-content/50">
        <p className="text-sm">No qubit tasks to display in topology view</p>
        <p className="text-xs mt-1">Coupling tasks are not shown in this view</p>
      </div>
    );
  }

  const gridContent = (
    <div
      className="grid bg-base-200/50 rounded-xl relative"
      style={{
        gap: `${gap}px`,
        padding: `${padding / 2}px`,
        gridTemplateColumns: `repeat(${gridCols}, minmax(${baseCellSize}px, 1fr))`,
        gridTemplateRows: `repeat(${gridRows}, minmax(${baseCellSize}px, 1fr))`,
        width: calculateGridContainerWidth(gridCols, baseCellSize, isMobile, viewportHeight),
        willChange: "transform",
      }}
    >
      {Array.from({ length: gridRows * gridCols }).map((_, index) => {
        const row = Math.floor(index / gridCols);
        const col = index % gridCols;

        const muxRow = Math.floor(row / muxSize);
        const muxCol = Math.floor(col / muxSize);
        const isEvenMux = (muxRow + muxCol) % 2 === 0;
        const muxBgClass =
          hasMux && showMuxBoundaries
            ? isEvenMux
              ? "ring-2 ring-inset ring-primary/20"
              : "ring-2 ring-inset ring-secondary/20"
            : "";

        const qid = Object.keys(gridPositions).find(
          (key) => gridPositions[key].row === row && gridPositions[key].col === col,
        );

        if (!qid) {
          return <EmptyCell key={`empty-${index}`} muxBgClass={muxBgClass} />;
        }

        const qidTasks = tasksByQid[qid] || [];
        // Pick the representative task (first one) for figure display
        const repTask = qidTasks[0];
        const figurePath = repTask
          ? Array.isArray(repTask.figure_path)
            ? repTask.figure_path[0]
            : repTask.figure_path || null
          : null;
        const jsonFigurePath = repTask
          ? Array.isArray(repTask.json_figure_path)
            ? repTask.json_figure_path[0]
            : repTask.json_figure_path || null
          : null;

        return (
          <TopologyCell
            key={qid}
            qid={qid}
            tasks={qidTasks}
            figurePath={figurePath}
            jsonFigurePath={jsonFigurePath}
            muxBgClass={muxBgClass}
            showLabels={showLabels}
            showFigures={showFigures}
            onClick={() => setSelectedQid(qid)}
          />
        );
      })}

      {/* MUX labels overlay */}
      {hasMux && showMuxBoundaries && showLabels && (
        <div
          className="absolute inset-0 pointer-events-none z-10 hidden md:block"
          style={{ padding: `${padding / 2}px` }}
        >
          <div
            className="grid w-full h-full"
            style={{
              gap: `${gap}px`,
              gridTemplateColumns: `repeat(${gridCols}, minmax(${baseCellSize}px, 1fr))`,
              gridTemplateRows: `repeat(${gridRows}, minmax(${baseCellSize}px, 1fr))`,
            }}
          >
            {Array.from({
              length: Math.pow(Math.ceil(gridCols / muxSize), 2),
            }).map((_, idx) => {
              const numMuxCols = Math.ceil(gridCols / muxSize);
              const muxLocalRow = Math.floor(idx / numMuxCols);
              const muxLocalCol = idx % numMuxCols;
              const muxActualRow = muxLocalRow;
              const muxActualCol = muxLocalCol;
              const muxIndex = muxActualRow * Math.floor(gridSize / muxSize) + muxActualCol;
              const startCol = muxLocalCol * muxSize + 1;
              const startRow = muxLocalRow * muxSize + 1;
              const spanCols = Math.min(muxSize, gridCols - muxLocalCol * muxSize);
              const spanRows = Math.min(muxSize, gridRows - muxLocalRow * muxSize);
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
                  <div className="text-[0.45rem] md:text-[0.6rem] font-semibold text-base-content/30 bg-base-100/60 px-1 py-px rounded border border-base-content/5">
                    MUX{muxIndex}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div ref={containerRef} className="w-full relative">
      <TransformWrapper
        initialScale={1}
        minScale={0.3}
        maxScale={5}
        wheel={{ step: 0.1 }}
        doubleClick={{ mode: "zoomIn", step: 0.7 }}
        centerOnInit
      >
        <ZoomControls />
        <TransformComponent
          wrapperStyle={{ width: "100%", overflow: "hidden" }}
          contentStyle={{
            display: "flex",
            justifyContent: "center",
          }}
        >
          {gridContent}
        </TransformComponent>
      </TransformWrapper>

      {/* Task detail modal */}
      {selectedQid && selectedTask && (
        <TaskDetailModal
          isOpen={!!selectedQid}
          task={selectedTask}
          qid={selectedQid}
          chipId={chipId}
          onClose={() => setSelectedQid(null)}
          taskId={selectedTask.task_id || undefined}
          taskName={selectedTask.name || undefined}
          variant="detailed"
        />
      )}
    </div>
  );
}
