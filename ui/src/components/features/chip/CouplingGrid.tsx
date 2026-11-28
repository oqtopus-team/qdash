"use client";

import { ArrowRightLeft, Check } from "lucide-react";
import { useState, useMemo, useRef, useCallback, type CSSProperties } from "react";

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
import { CouplingTaskHistoryModal } from "@/components/features/chip/modals/CouplingTaskHistoryModal";
import { gridFullscreenPanelClass } from "@/components/ui/GridFullscreenButton";
import {
  GridRegionBackBar,
  PositionedRegionOverlay,
  GridViewModeSwitch,
  GridViewport,
} from "@/components/ui/GridViewControls";
import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { useCouplingTaskResults } from "@/hooks/useCouplingTaskResults";
import { useFullscreenPanel } from "@/hooks/useFullscreenPanel";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useGridViewState } from "@/hooks/useGridViewState";
import { usePanClickGuard } from "@/hooks/usePanClickGuard";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import { getQubitGridPosition, type TopologyLayoutParams } from "@/lib/utils/grid-position";
import {
  buildMuxCellMap,
  clipMuxBoxes,
  muxLabelPosition,
  type MuxGroupBox,
} from "@/lib/utils/mux-groups";
import { calculateGridDimension } from "@/lib/utils/grid-layout";

const NO_MUX_GROUPS: MuxGroupBox[] = [];

interface CouplingGridProps {
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
  couplingId: string;
  taskName: string;
}

interface ExtendedTask extends Task {
  couplingId: string;
}

interface CouplingStatusDotProps {
  label: string;
  className: string;
  style: CSSProperties;
  onClick: () => void;
}

// Status dot using the shared Tooltip primitive, whose portal keeps the tooltip from being
// clipped by the grid's overflow-hidden container and pan/zoom transform.
export function CouplingStatusDot({ label, className, style, onClick }: CouplingStatusDotProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          aria-label={label}
          style={style}
          className={className}
        />
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

/**
 * Chip grid of coupling task results with Lock (region selection) and Zoom (pan/zoom) view modes.
 */
export function CouplingGrid({
  chipId,
  topologyId,
  selectedTask,
  selectedDate,
  startAt,
  endAt,
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
    couplings: topologyCouplings,
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
  const isSquareGrid = gridRows === gridCols;

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

  const [isDirectionReversed, setIsDirectionReversed] = useState(false);
  const { isFullscreen, toggleFullscreen, exitFullscreen } = useFullscreenPanel();
  const panClickGuard = usePanClickGuard();

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

  // LOD: store zoom scale, compute visibility flags from effective cell size.
  const [currentScale, setCurrentScale] = useState<number | null>(null);
  const lodTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const numRegions = Math.floor(gridSize / regionSize);

  const {
    data: taskResponse,
    isLoading,
    isFetching,
    isError,
    error,
  } = useCouplingTaskResults({
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

  // Use grid layout hook for responsive sizing
  const displayCols = zoomMode === "region" ? regionSize : gridCols;
  const displayRows = zoomMode === "region" ? regionSize : gridRows;
  const { containerRef, cellSize, isMobile, viewportHeight, gap, padding } = useGridLayout({
    cols: displayCols,
    rows: displayRows,
    reservedHeight: isFullscreen ? { mobile: 160, desktop: 180 } : { mobile: 300, desktop: 350 },
    deps: [taskResponse?.data, isFullscreen],
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

  const baseCouplingPairs = useMemo(() => {
    if (topologyCouplings && topologyCouplings.length > 0) {
      return topologyCouplings;
    }

    const pairs = new Map<string, [number, number]>();
    Object.keys(taskResultMap).forEach((couplingId) => {
      const [a, b] = couplingId.split("-").map(Number);
      if (!Number.isFinite(a) || !Number.isFinite(b)) return;
      const pair: [number, number] = a < b ? [a, b] : [b, a];
      pairs.set(`${pair[0]}-${pair[1]}`, pair);
    });
    return [...pairs.values()];
  }, [taskResultMap, topologyCouplings]);

  const displayedCouplingTasks = useMemo(() => {
    return baseCouplingPairs
      .map(([qid1, qid2]) => {
        const couplingId = isDirectionReversed ? `${qid2}-${qid1}` : `${qid1}-${qid2}`;
        const task = taskResultMap[couplingId];
        if (!task) return null;
        return {
          ...task,
          couplingId,
          baseQid1: qid1,
          baseQid2: qid2,
        } as ExtendedTask & { baseQid1: number; baseQid2: number };
      })
      .filter((task): task is ExtendedTask & { baseQid1: number; baseQid2: number } =>
        Boolean(task),
      );
  }, [baseCouplingPairs, isDirectionReversed, taskResultMap]);

  const downloadableCouplingIds = useMemo(
    () => displayedCouplingTasks.filter(hasDownloadableArtifacts).map((task) => task.couplingId),
    [displayedCouplingTasks],
  );
  const download = useGridArtifactDownload({
    tasksById: taskResultMap,
    downloadableIds: downloadableCouplingIds,
    zipFilename: `${chipId}_${selectedTask}_${selectedDate}_coupling_artifacts.zip`,
  });

  const containerClass = isFullscreen
    ? gridFullscreenPanelClass
    : "flex flex-col h-full space-y-2 max-w-4xl mx-auto w-full mt-8";

  if (isLoading)
    return (
      <GridLoadingPanel
        className={containerClass}
        isFullscreen={isFullscreen}
        onExitFullscreen={exitFullscreen}
      />
    );

  const displayCellSize = zoomMode === "region" ? cellSize * 0.8 : cellSize;
  const displayGridSize = zoomMode === "region" ? regionSize : gridSize;
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

  // LOD flags: compute from effective pixel size (cellSize * zoom scale)
  const activeScale = currentScale ?? initialScale;
  const effectiveCellSize = displayCellSize * (viewMode === "pan-zoom" ? activeScale : 1);
  const showLabels = effectiveCellSize >= 20 || zoomMode === "region";
  const showFigures = effectiveCellSize >= 50 || zoomMode === "region";

  // Helper function to get qubit position from topology (explicit) or computed
  const getQubitPosition = (qid: number) => {
    if (topologyQubits && topologyQubits[qid]) {
      return topologyQubits[qid];
    }
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

  // Download selection helpers

  const setCouplingDirection = (reversed: boolean) => {
    setIsDirectionReversed(reversed);
    download.cancel();
  };

  // Grid content (extracted for reuse in both view modes)
  const gridContent = (
    <div
      className="relative flex-shrink-0"
      style={{
        width: calculateGridDimension(displayGridSize, displayCellSize, isMobile, viewportHeight),
        height: calculateGridDimension(displayGridSize, displayCellSize, isMobile, viewportHeight),
        maxWidth: viewMode === "pan-zoom" ? "none" : "100%",
      }}
    >
      {/* Qubit positions - either from topology or computed, with MUX styling */}
      {(() => {
        const qubitIds = topologyQubits
          ? Object.keys(topologyQubits).map(Number)
          : Array.from({ length: gridRows * gridCols }, (_, i) => i);

        return qubitIds
          .filter((qid) => isQubitInRegion(qid))
          .map((qid) => {
            const pos = getQubitPosition(qid);
            const row = pos.row;
            const col = pos.col;

            const displayRow = row - displayGridStart.row;
            const displayCol = col - displayGridStart.col;
            const x = displayCol * (displayCellSize + gap);
            const y = displayRow * (displayCellSize + gap);

            const muxBox = muxCellMap.get(`${row},${col}`);

            const muxBgClass =
              hasMux && showMuxBoundaries && muxBox
                ? muxBox.isEven
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
                {showLabels && (
                  <span className={zoomMode === "full" ? "hidden md:inline" : ""}>{qid}</span>
                )}
              </div>
            );
          });
      })()}

      {/* MUX labels - centered in each MUX group */}
      {hasMux && showMuxBoundaries && showLabels && (
        <>
          {clipMuxBoxes(muxGroups, {
            row: displayGridStart.row,
            col: displayGridStart.col,
            rows: displayGridSize,
            cols: displayGridSize,
          }).map((box) => {
            // Centered over several cells; a single cell gets its label at an edge.
            const position = muxLabelPosition(box, displayCellSize, gap);

            return (
              <div
                key={`mux-label-${box.muxId}`}
                className={`absolute z-10 pointer-events-none ${
                  zoomMode === "full" ? "hidden md:flex" : "flex"
                }`}
                style={{
                  top: position.top,
                  left: position.left,
                  transform: position.transform,
                }}
              >
                <div className="text-[0.45rem] md:text-[0.6rem] font-medium text-base-content/30 bg-base-100/60 px-1 py-px rounded border border-base-content/5">
                  MUX{box.muxId}
                </div>
              </div>
            );
          })}
        </>
      )}

      {/* Coupling overlays */}
      {displayedCouplingTasks
        .filter((task) => isCouplingInRegion(task.baseQid1, task.baseQid2))
        .map((task) => {
          const qid1 = task.baseQid1;
          const qid2 = task.baseQid2;
          const figurePath = Array.isArray(task.figure_path)
            ? task.figure_path[0]
            : task.figure_path || null;
          const pos1 = getQubitPosition(qid1);
          const pos2 = getQubitPosition(qid2);
          const row1 = pos1.row;
          const col1 = pos1.col;
          const row2 = pos2.row;
          const col2 = pos2.col;

          const displayRow1 = row1 - displayGridStart.row;
          const displayCol1 = col1 - displayGridStart.col;
          const displayRow2 = row2 - displayGridStart.row;
          const displayCol2 = col2 - displayGridStart.col;
          const centerX =
            ((displayCol1 + displayCol2) / 2) * (displayCellSize + gap) + displayCellSize / 2;
          const centerY =
            ((displayRow1 + displayRow2) / 2) * (displayCellSize + gap) + displayCellSize / 2;

          const isSelectedForDownload = download.selectedIds.has(task.couplingId);
          const canBeDownloaded = hasDownloadableArtifacts(taskResultMap[task.couplingId]);

          const statusColor =
            task.status === "completed"
              ? "bg-success"
              : task.status === "failed"
                ? "bg-error"
                : "bg-warning";

          // Zoomed-out: status-colored dot
          if (!showFigures) {
            return (
              <CouplingStatusDot
                key={task.couplingId}
                label={`${task.couplingId}: ${task.status}`}
                onClick={() => {
                  if (download.isSelecting) {
                    if (canBeDownloaded) download.toggle(task.couplingId);
                  } else {
                    setSelectedTaskInfo({
                      couplingId: task.couplingId,
                      taskName: selectedTask,
                    });
                  }
                }}
                style={{
                  position: "absolute",
                  top: centerY,
                  left: centerX,
                  width: displayCellSize * 0.45,
                  height: displayCellSize * 0.45,
                }}
                className={`rounded-md shadow-sm cursor-pointer -translate-x-1/2 -translate-y-1/2 ${statusColor} ${
                  download.isSelecting && isSelectedForDownload
                    ? "ring-2 ring-primary ring-offset-1"
                    : ""
                }`}
              />
            );
          }

          // Zoomed-in: full figure
          return (
            <button
              key={task.couplingId}
              onClick={() => {
                if (download.isSelecting) {
                  if (canBeDownloaded) {
                    download.toggle(task.couplingId);
                  }
                } else {
                  setSelectedTaskInfo({
                    couplingId: task.couplingId,
                    taskName: selectedTask,
                  });
                }
              }}
              style={{
                position: "absolute",
                top: centerY,
                left: centerX,
                width: displayCellSize * 0.6,
                height: displayCellSize * 0.6,
              }}
              className={`rounded-xl bg-white shadow-xs border border-base-300/60 overflow-hidden transition-colors duration-200 hover:border-primary/40 -translate-x-1/2 -translate-y-1/2 ${
                download.isSelecting && isSelectedForDownload
                  ? "ring-2 ring-primary ring-offset-2"
                  : ""
              } ${download.isSelecting && !canBeDownloaded ? "opacity-40 cursor-not-allowed" : ""}`}
            >
              {figurePath && (
                <div className="absolute inset-1">
                  <TaskFigure
                    path={figurePath}
                    qid={String(task.couplingId)}
                    className="w-full h-full object-contain"
                    hideExpandButton
                  />
                </div>
              )}
              {/* Download selection overlay */}
              {download.isSelecting && canBeDownloaded && (
                <div
                  className={`absolute inset-0 flex items-center justify-center transition-colors ${
                    isSelectedForDownload
                      ? "bg-primary/20"
                      : "bg-transparent hover:bg-base-content/10"
                  }`}
                >
                  {isSelectedForDownload && (
                    <div className="bg-primary text-primary-content rounded-full p-1">
                      <Check size={16} />
                    </div>
                  )}
                </div>
              )}
            </button>
          );
        })}

      {/* Region selection overlay - only for square grids */}
      {zoomMode === "full" && regionSelectionEnabled && isSquareGrid && viewMode === "region" && (
        <PositionedRegionOverlay
          numRegions={numRegions}
          regionSize={regionSize}
          hoveredRegion={hoveredRegion}
          onHoverChange={setHoveredRegion}
          onSelect={zoomToRegion}
          cellSize={displayCellSize}
          gap={gap}
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
        isRefreshing={isFetching && !isLoading}
        isError={isError}
        error={error}
      />
      {/* View mode toggle and Download controls */}
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

          <button
            type="button"
            onClick={() => setCouplingDirection(!isDirectionReversed)}
            className={`btn btn-sm ${isDirectionReversed ? "btn-secondary" : "btn-outline"}`}
            title={isDirectionReversed ? "Showing reverse direction" : "Showing forward direction"}
          >
            <ArrowRightLeft data-icon="inline-start" />
            <span className="text-xs">{isDirectionReversed ? "Reverse" : "Forward"}</span>
          </button>
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

      {/* Back button when in region mode */}
      {viewMode === "region" && zoomMode === "region" && selectedRegion && (
        <GridRegionBackBar region={selectedRegion} onBack={showFullGrid} />
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
      >
        {gridContent}
      </GridViewport>

      <CouplingTaskHistoryModal
        chipId={chipId}
        couplingId={selectedTaskInfo?.couplingId || ""}
        taskName={selectedTaskInfo?.taskName || ""}
        isOpen={!!selectedTaskInfo}
        onClose={() => setSelectedTaskInfo(null)}
        selectedDate={selectedDate}
      />
    </div>
  );
}
