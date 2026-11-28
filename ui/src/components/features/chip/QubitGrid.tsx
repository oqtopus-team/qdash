"use client";

import { Check } from "lucide-react";
import { useMemo, useState, useRef, useCallback, memo, useEffect, type KeyboardEvent } from "react";

import type { Task } from "@/schemas";

import {
  GridDownloadConfirmModal,
  GridDownloadControls,
} from "@/components/features/chip/GridDownloadControls";
import { GridLoadingPanel, GridTaskRequestAlerts } from "@/components/features/chip/GridTaskStatus";
import {
  hasDownloadableArtifacts,
  useGridArtifactDownload,
} from "@/components/features/chip/useGridArtifactDownload";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { TaskHistoryModal } from "@/components/features/chip/modals/TaskHistoryModal";
import { gridFullscreenPanelClass } from "@/components/ui/GridFullscreenButton";
import {
  GridRegionBackBar,
  GridTemplateRegionOverlay,
  GridViewModeSwitch,
  GridViewport,
} from "@/components/ui/GridViewControls";
import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import {
  TaskTileStatusMark,
  taskTileLabel,
  taskTileStatusFill,
} from "@/components/ui/TaskTileStatus";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { useFullscreenPanel } from "@/hooks/useFullscreenPanel";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useGridViewState } from "@/hooks/useGridViewState";
import { usePanClickGuard } from "@/hooks/usePanClickGuard";
import { useQubitTaskResults } from "@/hooks/useQubitTaskResults";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import { getQubitGridPosition, type TopologyLayoutParams } from "@/lib/utils/grid-position";
import { calculateGridContainerWidth } from "@/lib/utils/grid-layout";
import {
  buildMuxCellMap,
  clipMuxBoxes,
  muxLabelAreaClass,
  type MuxGroupBox,
} from "@/lib/utils/mux-groups";

const NO_MUX_GROUPS: MuxGroupBox[] = [];

interface QubitGridProps {
  chipId: string;
  topologyId: string;
  selectedTask: string;
  selectedDate: string;
  startAt?: string | null;
  endAt?: string | null;
  gridSize: number;
  onDateChange?: (date: string) => void;
}

interface SelectedTaskInfo {
  qid: string;
  taskName: string;
}

// Memoized empty cell component
const EmptyCell = memo(function EmptyCell({ muxBgClass }: { muxBgClass: string }) {
  return <div className={`aspect-square bg-base-300/50 rounded-lg ${muxBgClass}`} />;
});

// Memoized grid cell component for performance
interface GridCellProps {
  qid: string;
  task: Task | null;
  figurePath: string | null;
  muxBgClass: string;
  showLabels: boolean;
  showFigures: boolean;
  zoomMode: "full" | "region";
  isDownloadMode: boolean;
  isSelectedForDownload: boolean;
  canBeDownloaded: boolean;
  onClick: () => void;
}

const GridCell = memo(function GridCell({
  qid,
  task,
  figurePath,
  muxBgClass,
  showLabels,
  showFigures,
  zoomMode,
  isDownloadMode,
  isSelectedForDownload,
  canBeDownloaded,
  onClick,
}: GridCellProps) {
  if (!task) {
    return (
      <div
        className={`aspect-square bg-base-300 rounded-lg flex items-center justify-center relative ${muxBgClass}`}
      >
        {showLabels && <div className="text-sm font-medium text-base-content/50">{qid}</div>}
      </div>
    );
  }

  const label = taskTileLabel("Qubit", qid, task.status);
  const downloadState = !isDownloadMode
    ? ""
    : !canBeDownloaded
      ? ", no figures to download"
      : isSelectedForDownload
        ? ", selected for download"
        : "";
  const accessibleName = `${label}${downloadState}`;
  const isUnavailable = isDownloadMode && !canBeDownloaded;

  // Zoomed-out: show status-colored tile (heatmap style)
  if (!showFigures) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onClick}
            aria-label={accessibleName}
            aria-disabled={isUnavailable || undefined}
            className={`aspect-square rounded-lg shadow-sm relative cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-base-content ${taskTileStatusFill(task.status)} ${muxBgClass} ${
              isDownloadMode && isSelectedForDownload ? "ring-2 ring-primary ring-offset-1" : ""
            } ${isUnavailable ? "opacity-40 cursor-not-allowed" : ""}`}
          >
            {showLabels && (
              <div className="absolute top-0.5 left-0.5 bg-black/30 text-white px-0.5 py-px rounded text-[0.5rem] font-medium">
                {qid}
              </div>
            )}
            {showLabels && (
              <TaskTileStatusMark
                status={task.status}
                variant="tile"
                className="absolute bottom-0.5 right-0.5"
              />
            )}
            {isDownloadMode && canBeDownloaded && isSelectedForDownload && (
              <div className="absolute inset-0 flex items-center justify-center bg-primary/20">
                <div className="bg-primary text-primary-content rounded-full p-0.5">
                  <Check size={10} />
                </div>
              </div>
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent>{accessibleName}</TooltipContent>
      </Tooltip>
    );
  }

  // Zoomed-in: show full figure
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onClick();
    }
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          role="button"
          tabIndex={0}
          onClick={onClick}
          onKeyDown={handleKeyDown}
          aria-label={accessibleName}
          aria-disabled={isUnavailable || undefined}
          className={`aspect-square rounded-xl bg-white shadow-xs border border-base-300/60 overflow-hidden transition-colors duration-200 hover:border-primary/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary relative w-full ${muxBgClass} ${
            isDownloadMode && isSelectedForDownload ? "ring-2 ring-primary ring-offset-2" : ""
          } ${isUnavailable ? "opacity-40 cursor-not-allowed" : ""}`}
        >
          {task.figure_path && figurePath && (
            <div className="absolute inset-1">
              <TaskFigure
                path={figurePath}
                qid={qid}
                className="w-full h-full object-contain"
                hideExpandButton
              />
            </div>
          )}
          {showLabels && (
            <div
              className={`absolute top-1 left-1 bg-base-100/80 px-1.5 py-0.5 rounded text-xs font-medium ${
                zoomMode === "full" ? "hidden md:block" : ""
              }`}
            >
              {qid}
            </div>
          )}
          <TaskTileStatusMark
            status={task.status}
            variant="figure"
            className="absolute bottom-1 right-1"
          />
          {/* Download selection overlay */}
          {isDownloadMode && canBeDownloaded && (
            <div
              className={`absolute inset-0 flex items-center justify-center transition-colors ${
                isSelectedForDownload ? "bg-primary/20" : "bg-transparent hover:bg-base-content/10"
              }`}
            >
              {isSelectedForDownload && (
                <div className="bg-primary text-primary-content rounded-full p-1">
                  <Check size={16} />
                </div>
              )}
            </div>
          )}
        </div>
      </TooltipTrigger>
      <TooltipContent>{accessibleName}</TooltipContent>
    </Tooltip>
  );
});

/**
 * Chip grid of per-qubit task results with Lock (region selection) and Zoom (pan/zoom) view modes.
 */
export function QubitGrid({
  chipId,
  topologyId,
  selectedTask,
  selectedDate,
  startAt,
  endAt,
  gridSize: defaultGridSize,
}: QubitGridProps) {
  // Get topology configuration
  const {
    muxSize = 2,
    regionSize = 4,
    hasMux = false,
    layoutType = "grid",
    showMuxBoundaries = false,
    qubits: topologyQubits,
    gridSize: topologyGridSize,
    muxGroups = NO_MUX_GROUPS,
  } = useTopologyConfig(topologyId) ?? {};

  // Cell -> MUX box, so boundaries follow the topology's actual MUX groups
  const muxCellMap = useMemo(
    () => buildMuxCellMap(muxGroups, topologyQubits),
    [muxGroups, topologyQubits],
  );

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

  const [selectedTaskInfo, setSelectedTaskInfo] = useState<SelectedTaskInfo | null>(null);

  // Fetch task results
  const {
    data: taskResponse,
    isLoading: isLoadingTask,
    isFetching: isFetchingTask,
    isError: isTaskError,
    error: taskError,
  } = useQubitTaskResults({
    chipId,
    task: selectedTask,
    selectedDate,
    startAt,
    endAt,
  });
  const taskResultMap = useMemo(
    () => taskResponse?.data?.result ?? {},
    [taskResponse?.data?.result],
  );
  const downloadableQids = useMemo(
    () =>
      Object.entries(taskResultMap)
        .filter(([, task]) => hasDownloadableArtifacts(task))
        .map(([qid]) => qid),
    [taskResultMap],
  );
  const download = useGridArtifactDownload({
    tasksById: taskResultMap,
    downloadableIds: downloadableQids,
    zipFilename: `${chipId}_${selectedTask}_${selectedDate}_artifacts.zip`,
  });

  const { isFullscreen, toggleFullscreen, exitFullscreen } = useFullscreenPanel();
  const panClickGuard = usePanClickGuard();

  // LOD: store zoom scale, compute visibility flags from effective cell size.
  // Initialize to a conservative value; will be updated on first transform.
  const [currentScale, setCurrentScale] = useState<number | null>(null);
  const lodTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (lodTimeoutRef.current !== null) {
        clearTimeout(lodTimeoutRef.current);
      }
    };
  }, []);

  const numRegions = Math.floor(gridSize / regionSize);
  const isSquareGrid = gridRows === gridCols;

  // View mode state: 'pan-zoom' for DOM with pan/zoom, 'region' for region zoom
  const {
    viewMode,
    changeViewMode,
    zoomMode,
    selectedRegion,
    zoomToRegion,
    showFullGrid,
    hoveredRegion,
    setHoveredRegion,
    regionSelectionEnabled,
    setRegionSelectionEnabled,
  } = useGridViewState(isSquareGrid);

  // Calculate displayed grid size based on zoom mode
  const displayCols = zoomMode === "region" ? regionSize : gridCols;
  const displayRows = zoomMode === "region" ? regionSize : gridRows;

  // Use grid layout hook for responsive sizing
  const { containerRef, cellSize, isMobile, viewportHeight, gap, padding } = useGridLayout({
    cols: displayCols,
    rows: displayRows,
    reservedHeight: isFullscreen ? { mobile: 160, desktop: 180 } : { mobile: 300, desktop: 350 },
    deps: [taskResponse, topologyQubits, zoomMode, selectedRegion, isFullscreen],
  });

  // Debounced scale update to avoid excessive re-renders during zoom
  const handleTransform = useCallback((_: unknown, state: { scale: number }) => {
    if (lodTimeoutRef.current) {
      clearTimeout(lodTimeoutRef.current);
    }
    lodTimeoutRef.current = setTimeout(() => {
      setCurrentScale((prev) => {
        if (prev === null) return state.scale;
        return Math.abs(prev - state.scale) > 0.05 ? state.scale : prev;
      });
    }, 100);
  }, []);

  const initialScale = 1;

  const containerClass = isFullscreen
    ? gridFullscreenPanelClass
    : "flex flex-col h-full space-y-2 max-w-4xl mx-auto w-full mt-8";

  if (isLoadingTask)
    return (
      <GridLoadingPanel
        className={containerClass}
        isFullscreen={isFullscreen}
        onExitFullscreen={exitFullscreen}
      />
    );

  const gridPositions: { [key: string]: { row: number; col: number } } = {};
  if (taskResponse?.data?.result) {
    Object.keys(taskResponse.data.result).forEach((qid) => {
      const numericId = parseInt(qid.replace(/\D/g, ""), 10);
      if (topologyQubits && topologyQubits[numericId]) {
        gridPositions[qid] = topologyQubits[numericId];
      } else {
        const pos = getQubitGridPosition(qid, layoutParams);
        gridPositions[qid] = pos;
      }
    });
  }

  const getTaskResult = (qid: string): Task | null => taskResponse?.data?.result?.[qid] || null;

  // Calculate displayed grid size based on zoom mode
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

  const displayCellSize = zoomMode === "region" ? cellSize * 0.9 : cellSize;

  // LOD flags: compute from effective pixel size (cellSize * zoom scale)
  const activeScale = currentScale ?? initialScale;
  const effectiveCellSize = displayCellSize * (viewMode === "pan-zoom" ? activeScale : 1);
  const showLabels = effectiveCellSize >= 20 || zoomMode === "region";
  const showFigures = effectiveCellSize >= 50 || zoomMode === "region";

  // Grid content (extracted for reuse in both view modes)
  const gridContent = (
    <div
      className="grid bg-base-200/50 rounded-[var(--radius-box)] relative"
      style={{
        gap: `${gap}px`,
        padding: `${padding / 2}px`,
        gridTemplateColumns: `repeat(${displayCols}, minmax(${displayCellSize}px, 1fr))`,
        gridTemplateRows: `repeat(${displayRows}, minmax(${displayCellSize}px, 1fr))`,
        width: calculateGridContainerWidth(displayCols, displayCellSize, isMobile, viewportHeight),
      }}
    >
      {Array.from({
        length: displayRows * displayCols,
      }).map((_, index) => {
        const localRow = Math.floor(index / displayCols);
        const localCol = index % displayCols;
        const actualRow = displayGridStart.row + localRow;
        const actualCol = displayGridStart.col + localCol;

        // MUX background class from the MUX group covering this cell, if any
        const muxBox = muxCellMap.get(`${actualRow},${actualCol}`);
        const muxBgClass =
          hasMux && showMuxBoundaries && muxBox
            ? muxBox.isEven
              ? "ring-2 ring-inset ring-primary/20"
              : "ring-2 ring-inset ring-secondary/20"
            : "";

        const qid = Object.keys(gridPositions).find(
          (key) => gridPositions[key].row === actualRow && gridPositions[key].col === actualCol,
        );

        if (!qid) {
          return <EmptyCell key={`empty-${index}`} muxBgClass={muxBgClass} />;
        }

        const task = getTaskResult(qid);
        const figurePath = task
          ? Array.isArray(task.figure_path)
            ? task.figure_path[0]
            : task.figure_path || null
          : null;
        const isSelectedForDownload = download.selectedIds.has(qid);
        const canBeDownloaded = hasDownloadableArtifacts(task);

        return (
          <GridCell
            key={qid}
            qid={qid}
            task={task}
            figurePath={figurePath}
            muxBgClass={muxBgClass}
            showLabels={showLabels}
            showFigures={showFigures}
            zoomMode={zoomMode}
            isDownloadMode={download.isSelecting}
            isSelectedForDownload={isSelectedForDownload}
            canBeDownloaded={canBeDownloaded}
            onClick={() => {
              if (download.isSelecting) {
                if (canBeDownloaded) {
                  download.toggle(qid);
                }
              } else {
                setSelectedTaskInfo({ qid, taskName: selectedTask });
              }
            }}
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
              gridTemplateColumns: `repeat(${displayCols}, minmax(${displayCellSize}px, 1fr))`,
              gridTemplateRows: `repeat(${displayRows}, minmax(${displayCellSize}px, 1fr))`,
            }}
          >
            {clipMuxBoxes(muxGroups, {
              row: displayGridStart.row,
              col: displayGridStart.col,
              rows: displayRows,
              cols: displayCols,
            }).map((box) => (
              <div
                key={box.muxId}
                className={muxLabelAreaClass(box)}
                style={{
                  gridColumn: `${box.col + 1} / span ${box.cols}`,
                  gridRow: `${box.row + 1} / span ${box.rows}`,
                }}
              >
                <div className="text-[0.45rem] md:text-[0.6rem] font-medium text-base-content/30 bg-base-100/60 px-1 py-px rounded border border-base-content/5">
                  MUX{box.muxId}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Region selection overlay */}
      {zoomMode === "full" && regionSelectionEnabled && isSquareGrid && viewMode === "region" && (
        <GridTemplateRegionOverlay
          numRegions={numRegions}
          regionSize={regionSize}
          hoveredRegion={hoveredRegion}
          onHoverChange={setHoveredRegion}
          onSelect={zoomToRegion}
          padding={padding}
          gap={gap}
          cols={displayCols}
          rows={displayRows}
          cellSize={displayCellSize}
        />
      )}
    </div>
  );

  return (
    <div className={containerClass}>
      <GridTaskRequestAlerts
        selectedTask={selectedTask}
        selectedDate={selectedDate}
        startAt={startAt}
        endAt={endAt}
        isRefreshing={isFetchingTask && !isLoadingTask}
        isError={isTaskError}
        error={taskError}
      />
      {/* View Mode Toggle and Download Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg py-2">
        <div className="flex items-center gap-4">
          <GridViewModeSwitch value={viewMode} onValueChange={changeViewMode} />

          <div
            className={
              viewMode !== "region" || zoomMode !== "full" || !isSquareGrid || download.isSelecting
                ? "invisible pointer-events-none"
                : ""
            }
          >
            <RegionZoomToggle
              enabled={regionSelectionEnabled}
              onToggle={setRegionSelectionEnabled}
            />
          </div>
        </div>

        {/* Download selection controls */}
        {zoomMode === "full" && (
          <GridDownloadControls
            download={download}
            onStart={() => setRegionSelectionEnabled(false)}
          />
        )}
      </div>

      <GridDownloadConfirmModal download={download} />

      {/* Back button */}
      {zoomMode === "region" && selectedRegion && (
        <GridRegionBackBar
          region={selectedRegion}
          onBack={showFullGrid}
          detail={
            <>
              {" "}
              (Qubits {displayGridStart.row * gridSize + displayGridStart.col} -{" "}
              {(displayGridStart.row + regionSize - 1) * gridSize +
                displayGridStart.col +
                regionSize -
                1}
              )
            </>
          }
        />
      )}

      {/* Grid display */}
      <GridViewport
        viewMode={viewMode}
        padding={padding}
        isFullscreen={isFullscreen}
        onToggleFullscreen={toggleFullscreen}
        onTransform={handleTransform}
        panClickGuard={panClickGuard}
        viewportRef={containerRef}
        panZoomClassName="overflow-hidden"
      >
        {gridContent}
      </GridViewport>

      <TaskHistoryModal
        chipId={chipId}
        qid={selectedTaskInfo?.qid || ""}
        taskName={selectedTaskInfo?.taskName || ""}
        isOpen={!!selectedTaskInfo}
        onClose={() => setSelectedTaskInfo(null)}
        selectedDate={selectedDate}
      />
    </div>
  );
}
