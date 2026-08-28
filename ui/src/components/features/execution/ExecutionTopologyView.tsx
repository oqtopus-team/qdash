"use client";

import { useCallback, useEffect, useMemo, useRef, useState, memo, type KeyboardEvent } from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";

import type { Task } from "@/schemas";

import { useGetChip } from "@/client/chip/chip";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ExecutionTaskDetailModal } from "@/components/features/execution/ExecutionTaskDetailModal";
import {
  filterTaskGroupsByName,
  groupTasksByEntity,
  resolveInitialTaskIndex,
  selectTaskNeighborhood,
} from "@/components/features/execution/executionTopologyTasks";
import { GridFullscreenButton } from "@/components/ui/GridFullscreenButton";
import { GridZoomControls } from "@/components/ui/GridZoomControls";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import { getQubitGridPosition, type TopologyLayoutParams } from "@/lib/utils/grid-position";
import { calculateGridContainerWidth } from "@/lib/utils/grid-layout";

interface ExecutionTopologyViewProps {
  chipId: string;
  executionId: string;
  executionName?: string;
  tasks: Task[];
  topologyMode: "1q" | "2q";
  filterTaskName: string;
  isFullscreen?: boolean;
  onToggleFullscreen: () => void;
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

function handleActivationKey(event: KeyboardEvent<HTMLDivElement>, onClick: () => void) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  onClick();
}

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
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(event) => handleActivationKey(event, onClick)}
      className={`aspect-square rounded-xl bg-white shadow-md border border-base-300/60 overflow-hidden transition-all duration-200 hover:shadow-xl hover:scale-105 hover:border-primary/40 relative w-full ${muxBgClass}`}
    >
      {figurePath && (
        <div className="absolute inset-1">
          <TaskFigure
            path={figurePath}
            jsonFigurePath={jsonFigurePath || undefined}
            qid={qid}
            className="w-full h-full object-contain"
            hideExpandButton
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
    </div>
  );
});

interface CouplingMarkerProps {
  couplingId: string;
  tasks: Task[];
  figurePath: string | null;
  jsonFigurePath: string | null;
  showFigures: boolean;
  cellSize: number;
  left: number;
  top: number;
  onClick: () => void;
}

const CouplingMarker = memo(function CouplingMarker({
  couplingId,
  tasks,
  figurePath,
  jsonFigurePath,
  showFigures,
  cellSize,
  left,
  top,
  onClick,
}: CouplingMarkerProps) {
  const status = tasks.length === 1 ? tasks[0].status : aggregateStatus(tasks);

  if (!showFigures) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`absolute z-20 rounded-md shadow-sm group cursor-pointer border border-base-100/70 -translate-x-1/2 -translate-y-1/2 ${getStatusColor(status)}`}
        style={{
          left,
          top,
          width: Math.max(24, cellSize * 0.44),
          height: Math.max(24, cellSize * 0.44),
        }}
      >
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-base-100 text-base-content text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-30">
          {couplingId}: {status}
          {tasks.length > 1 && ` (${tasks.length} tasks)`}
        </div>
      </button>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(event) => handleActivationKey(event, onClick)}
      className="absolute z-20 rounded-xl bg-white shadow-md border border-base-300/60 overflow-hidden transition-all duration-200 hover:shadow-xl hover:scale-105 hover:border-primary/40 -translate-x-1/2 -translate-y-1/2"
      style={{
        left,
        top,
        width: Math.max(48, cellSize * 0.7),
        height: Math.max(48, cellSize * 0.7),
      }}
    >
      {figurePath && (
        <div className="absolute inset-1">
          <TaskFigure
            path={figurePath}
            jsonFigurePath={jsonFigurePath || undefined}
            qid={couplingId}
            className="w-full h-full object-contain"
            hideExpandButton
          />
        </div>
      )}
      <div className="absolute top-1 left-1 bg-base-100/80 px-1.5 py-0.5 rounded text-[0.65rem] font-medium">
        {couplingId}
      </div>
      <div className={`absolute bottom-1 right-1 w-2 h-2 rounded-full ${getStatusColor(status)}`} />
      {tasks.length > 1 && (
        <div className="absolute top-1 right-1 bg-base-100/80 px-1 py-px rounded text-[0.6rem] font-bold">
          {tasks.length}
        </div>
      )}
    </div>
  );
});

export function ExecutionTopologyView({
  chipId,
  executionId,
  executionName,
  tasks,
  topologyMode,
  filterTaskName,
  isFullscreen,
  onToggleFullscreen,
}: ExecutionTopologyViewProps) {
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [currentScale, setCurrentScale] = useState(1);
  const lodTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const allTasksByEntity = useMemo(() => groupTasksByEntity(tasks), [tasks]);

  const oneQTasksByQid = useMemo(
    () => filterTaskGroupsByName(allTasksByEntity.oneQubit, filterTaskName),
    [allTasksByEntity, filterTaskName],
  );

  const couplingTasksByQid = useMemo(
    () => filterTaskGroupsByName(allTasksByEntity.coupling, filterTaskName),
    [allTasksByEntity, filterTaskName],
  );

  // Build grid positions for all qids
  const gridPositions = useMemo(() => {
    const positions: Record<string, { row: number; col: number }> = {};
    if (topologyQubits) {
      Object.entries(topologyQubits).forEach(([qid, position]) => {
        positions[qid] = position;
      });
      return positions;
    }
    for (let index = 0; index < chipSize; index += 1) {
      const qid = String(index);
      positions[qid] = getQubitGridPosition(qid, layoutParams);
    }
    return positions;
  }, [chipSize, topologyQubits, layoutParams]);

  const qidByPosition = useMemo(() => {
    const map: Record<string, string> = {};
    Object.entries(gridPositions).forEach(([qid, position]) => {
      map[`${position.row}:${position.col}`] = qid;
    });
    return map;
  }, [gridPositions]);

  // Responsive grid sizing
  const { containerRef, cellSize, isMobile, viewportHeight, gap, padding } = useGridLayout({
    cols: gridCols,
    rows: gridRows,
    reservedHeight: isFullscreen ? { mobile: 200, desktop: 220 } : { mobile: 300, desktop: 350 },
    deps: [oneQTasksByQid, couplingTasksByQid, topologyMode, topologyQubits, isFullscreen],
  });

  const MIN_FIGURE_CELL_SIZE = 60;
  const baseCellSize = Math.max(cellSize, MIN_FIGURE_CELL_SIZE);

  const handleTransform = useCallback((_: unknown, state: { scale: number }) => {
    if (lodTimeoutRef.current) {
      clearTimeout(lodTimeoutRef.current);
    }
    lodTimeoutRef.current = setTimeout(() => {
      setCurrentScale((prev) => (Math.abs(prev - state.scale) > 0.05 ? state.scale : prev));
    }, 100);
  }, []);

  useEffect(() => {
    return () => {
      if (lodTimeoutRef.current) clearTimeout(lodTimeoutRef.current);
    };
  }, []);

  const effectiveCellSize = baseCellSize * currentScale;
  const showLabels = effectiveCellSize >= 20;
  const showFigures = effectiveCellSize >= 50;

  const selectedTasks = useMemo(() => {
    if (!selectedEntityId) return null;
    const entityTasks =
      topologyMode === "2q"
        ? allTasksByEntity.coupling[selectedEntityId]
        : allTasksByEntity.oneQubit[selectedEntityId];
    if (!entityTasks) return [];
    return selectTaskNeighborhood(entityTasks, filterTaskName);
  }, [allTasksByEntity, selectedEntityId, topologyMode, filterTaskName]);

  const initialTaskIndex = useMemo(
    () => (selectedTasks ? resolveInitialTaskIndex(selectedTasks, filterTaskName) : 0),
    [selectedTasks, filterTaskName],
  );

  const visibleTaskGroups = topologyMode === "2q" ? couplingTasksByQid : oneQTasksByQid;
  const hasVisibleTasks = Object.keys(visibleTaskGroups).length > 0;

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

        const qid = qidByPosition[`${row}:${col}`];

        if (!qid) {
          return <EmptyCell key={`empty-${index}`} muxBgClass={muxBgClass} />;
        }

        const qidTasks = topologyMode === "1q" ? oneQTasksByQid[qid] || [] : [];
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
            onClick={() => setSelectedEntityId(qid)}
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

      {topologyMode === "2q" &&
        Object.entries(couplingTasksByQid).map(([couplingId, couplingTasks]) => {
          const [first, second] = couplingId.split("-");
          const firstPosition = first ? gridPositions[first] : undefined;
          const secondPosition = second ? gridPositions[second] : undefined;
          if (!firstPosition || !secondPosition) return null;

          const centerCol = (firstPosition.col + secondPosition.col) / 2;
          const centerRow = (firstPosition.row + secondPosition.row) / 2;
          const left = padding / 2 + centerCol * (baseCellSize + gap) + baseCellSize / 2;
          const top = padding / 2 + centerRow * (baseCellSize + gap) + baseCellSize / 2;
          const repTask = couplingTasks[0];
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
            <CouplingMarker
              key={couplingId}
              couplingId={couplingId}
              tasks={couplingTasks}
              figurePath={figurePath}
              jsonFigurePath={jsonFigurePath}
              showFigures={showFigures}
              cellSize={baseCellSize}
              left={left}
              top={top}
              onClick={() => setSelectedEntityId(couplingId)}
            />
          );
        })}
    </div>
  );

  return (
    <div
      className={`flex flex-col h-full space-y-2 w-full ${
        isFullscreen ? "flex-1 min-h-0" : "max-w-4xl mx-auto"
      }`}
    >
      <div
        ref={containerRef}
        className="flex-1 relative overflow-hidden flex justify-center bg-base-200/30 border-2 border-dashed border-base-300 rounded-lg"
        style={{ padding: `${Math.max(4, padding / 4)}px` }}
      >
        <GridFullscreenButton isFullscreen={isFullscreen} onToggle={onToggleFullscreen} />
        {hasVisibleTasks ? (
          <TransformWrapper
            initialScale={1}
            minScale={0.3}
            maxScale={4}
            wheel={{ step: 0.08 }}
            pinch={{ step: 5 }}
            doubleClick={{ mode: "zoomIn", step: 0.7 }}
            panning={{ velocityDisabled: true }}
            smooth={false}
            limitToBounds={false}
            centerOnInit
            onTransform={handleTransform}
          >
            <GridZoomControls isFullscreen={isFullscreen} className="top-12" />
            <TransformComponent
              wrapperStyle={{
                width: "100%",
                height: isFullscreen ? "100%" : undefined,
                minHeight: isFullscreen ? undefined : "520px",
                overflow: "hidden",
              }}
              contentStyle={{
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
              }}
            >
              {gridContent}
            </TransformComponent>
          </TransformWrapper>
        ) : (
          <div className="flex flex-col items-center justify-center py-12 text-base-content/50">
            <p className="text-sm">
              No {topologyMode === "2q" ? "coupling" : "one-qubit"} tasks to display in topology
              view
            </p>
          </div>
        )}
      </div>

      {selectedEntityId && selectedTasks && (
        <ExecutionTaskDetailModal
          key={selectedEntityId}
          isOpen={!!selectedEntityId}
          tasks={selectedTasks}
          initialTaskIndex={initialTaskIndex}
          qid={selectedEntityId}
          chipId={chipId}
          executionId={executionId}
          executionName={executionName}
          onClose={() => setSelectedEntityId(null)}
        />
      )}
    </div>
  );
}
