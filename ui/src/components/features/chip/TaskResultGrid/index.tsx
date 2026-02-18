"use client";

import {
  Check,
  Download,
  X,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Move,
} from "lucide-react";
import { useMemo, useState, useRef, useCallback, memo } from "react";
import {
  TransformWrapper,
  TransformComponent,
  useControls,
} from "react-zoom-pan-pinch";

import type { Task } from "@/schemas";

import { downloadFiguresAsZip } from "@/client/task-result/task-result";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { TaskHistoryModal } from "@/components/features/chip/modals/TaskHistoryModal";
import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useQubitTaskResults } from "@/hooks/useQubitTaskResults";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import {
  getQubitGridPosition,
  type TopologyLayoutParams,
} from "@/utils/gridPosition";
import { calculateGridContainerWidth } from "@/utils/gridLayout";

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

// Zoom control buttons component
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

// Memoized empty cell component
const EmptyCell = memo(function EmptyCell({
  muxBgClass,
}: {
  muxBgClass: string;
}) {
  return (
    <div className={`aspect-square bg-base-300/50 rounded-lg ${muxBgClass}`} />
  );
});

// Memoized grid cell component for performance
interface GridCellProps {
  qid: string;
  task: Task | null;
  figurePath: string | null;
  muxBgClass: string;
  showLabels: boolean;
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
        {showLabels && (
          <div className="text-sm font-medium text-base-content/50">{qid}</div>
        )}
      </div>
    );
  }

  return (
    <button
      onClick={onClick}
      className={`aspect-square rounded-xl bg-white shadow-md border border-base-300/60 overflow-hidden transition-all duration-200 hover:shadow-xl hover:scale-105 hover:border-primary/40 relative w-full ${muxBgClass} ${
        isDownloadMode && isSelectedForDownload
          ? "ring-2 ring-primary ring-offset-2"
          : ""
      } ${
        isDownloadMode && !canBeDownloaded
          ? "opacity-40 cursor-not-allowed"
          : ""
      }`}
    >
      {task.figure_path && figurePath && (
        <div className="absolute inset-1">
          <TaskFigure
            path={figurePath}
            qid={qid}
            className="w-full h-full object-contain"
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
      <div
        className={`absolute bottom-1 right-1 w-2 h-2 rounded-full ${
          task.status === "completed"
            ? "bg-success"
            : task.status === "failed"
              ? "bg-error"
              : "bg-warning"
        }`}
      />
      {/* Download selection overlay */}
      {isDownloadMode && canBeDownloaded && (
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
});

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

  // Download selection mode state
  const [downloadSelectionEnabled, setDownloadSelectionEnabled] =
    useState(false);
  const [selectedForDownload, setSelectedForDownload] = useState<Set<string>>(
    new Set(),
  );
  const [isDownloading, setIsDownloading] = useState(false);

  // Fetch task results
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

  // View mode state: 'pan-zoom' for DOM with pan/zoom, 'region' for region zoom
  const [viewMode, setViewMode] = useState<"pan-zoom" | "region">("pan-zoom");
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

  // LOD state with ref to avoid excessive re-renders
  const [lodLevel, setLodLevel] = useState<"high" | "medium" | "low">("high");
  const lodTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const numRegions = Math.floor(gridSize / regionSize);
  const isSquareGrid = gridRows === gridCols;

  // Calculate displayed grid size based on zoom mode
  const displayCols = zoomMode === "region" ? regionSize : gridCols;
  const displayRows = zoomMode === "region" ? regionSize : gridRows;

  // Use grid layout hook for responsive sizing
  const { containerRef, cellSize, isMobile, viewportHeight, gap, padding } =
    useGridLayout({
      cols: displayCols,
      rows: displayRows,
      reservedHeight: { mobile: 300, desktop: 350 },
      deps: [taskResponse, topologyQubits, zoomMode, selectedRegion],
    });

  // Debounced LOD update to avoid excessive re-renders during zoom
  const handleTransform = useCallback(
    (_: unknown, state: { scale: number }) => {
      if (lodTimeoutRef.current) {
        clearTimeout(lodTimeoutRef.current);
      }
      lodTimeoutRef.current = setTimeout(() => {
        const scale = state.scale;
        const newLod = scale >= 0.9 ? "high" : scale >= 0.6 ? "medium" : "low";
        setLodLevel((prev) => (prev !== newLod ? newLod : prev));
      }, 100);
    },
    [],
  );

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
      const numericId = parseInt(qid.replace(/\D/g, ""), 10);
      if (topologyQubits && topologyQubits[numericId]) {
        gridPositions[qid] = topologyQubits[numericId];
      } else {
        const pos = getQubitGridPosition(qid, layoutParams);
        gridPositions[qid] = pos;
      }
    });
  }

  const getTaskResult = (qid: string): Task | null =>
    taskResponse?.data?.result?.[qid] || null;

  // Download selection helpers
  const toggleDownloadSelection = (qid: string) => {
    setSelectedForDownload((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(qid)) {
        newSet.delete(qid);
      } else {
        newSet.add(qid);
      }
      return newSet;
    });
  };

  const selectAllForDownload = () => {
    const allQids = Object.entries(taskResponse?.data?.result || {})
      .filter(([, task]) => task.json_figure_path)
      .map(([qid]) => qid);
    setSelectedForDownload(new Set(allQids));
  };

  const clearDownloadSelection = () => {
    setSelectedForDownload(new Set());
  };

  const handleDownload = async () => {
    if (selectedForDownload.size === 0) return;

    const paths: string[] = [];
    selectedForDownload.forEach((qid) => {
      const task = taskResponse?.data?.result?.[qid];
      if (task?.json_figure_path) {
        const jsonPaths = Array.isArray(task.json_figure_path)
          ? task.json_figure_path
          : [task.json_figure_path];
        paths.push(...jsonPaths);
      }
    });

    if (paths.length === 0) return;

    setIsDownloading(true);
    try {
      const filename = `${chipId}_${selectedTask}_${selectedDate}_json_figures.zip`;
      const response = await downloadFiguresAsZip(
        { paths, filename },
        { responseType: "blob" },
      );

      const blob = new Blob([response.data as BlobPart], {
        type: "application/zip",
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setDownloadSelectionEnabled(false);
      setSelectedForDownload(new Set());
    } catch (error) {
      console.error("Download error:", error);
      alert("Download failed. Please try again.");
    } finally {
      setIsDownloading(false);
    }
  };

  const hasJsonFigures = (qid: string): boolean => {
    const task = taskResponse?.data?.result?.[qid];
    return !!task?.json_figure_path;
  };

  const availableForDownloadCount = Object.entries(
    taskResponse?.data?.result || {},
  ).filter(([, task]) => task.json_figure_path).length;

  // Calculate displayed grid size based on zoom mode
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

  const displayCellSize = zoomMode === "region" ? cellSize * 0.9 : cellSize;

  // LOD flags
  const showLabels = lodLevel !== "low" || zoomMode === "region";

  // Grid content (extracted for reuse in both view modes)
  const gridContent = (
    <div
      className="grid bg-base-200/50 rounded-xl relative"
      style={{
        gap: `${gap}px`,
        padding: `${padding / 2}px`,
        gridTemplateColumns: `repeat(${displayCols}, minmax(${displayCellSize}px, 1fr))`,
        gridTemplateRows: `repeat(${displayRows}, minmax(${displayCellSize}px, 1fr))`,
        width: calculateGridContainerWidth(
          displayCols,
          displayCellSize,
          isMobile,
          viewportHeight,
        ),
        willChange: "transform",
      }}
    >
      {Array.from({
        length: displayRows * displayCols,
      }).map((_, index) => {
        const localRow = Math.floor(index / displayCols);
        const localCol = index % displayCols;
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

        if (!qid) {
          return <EmptyCell key={index} muxBgClass={muxBgClass} />;
        }

        const task = getTaskResult(qid);
        const figurePath = task
          ? Array.isArray(task.figure_path)
            ? task.figure_path[0]
            : task.figure_path || null
          : null;
        const isSelectedForDownload = selectedForDownload.has(qid);
        const canBeDownloaded = hasJsonFigures(qid);

        return (
          <GridCell
            key={qid}
            qid={qid}
            task={task}
            figurePath={figurePath}
            muxBgClass={muxBgClass}
            showLabels={showLabels}
            zoomMode={zoomMode}
            isDownloadMode={downloadSelectionEnabled}
            isSelectedForDownload={isSelectedForDownload}
            canBeDownloaded={canBeDownloaded}
            onClick={() => {
              if (downloadSelectionEnabled) {
                if (canBeDownloaded) {
                  toggleDownloadSelection(qid);
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
            {Array.from({
              length: Math.pow(Math.ceil(displayCols / muxSize), 2),
            }).map((_, idx) => {
              const numMuxCols = Math.ceil(displayCols / muxSize);
              const muxLocalRow = Math.floor(idx / numMuxCols);
              const muxLocalCol = idx % numMuxCols;
              const muxActualRow =
                Math.floor(displayGridStart.row / muxSize) + muxLocalRow;
              const muxActualCol =
                Math.floor(displayGridStart.col / muxSize) + muxLocalCol;
              const muxIndex =
                muxActualRow * Math.floor(gridSize / muxSize) + muxActualCol;
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
                  <div className="text-[0.45rem] md:text-[0.6rem] font-semibold text-base-content/30 bg-base-100/60 px-1 py-px rounded border border-base-content/5">
                    MUX{muxIndex}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Region selection overlay */}
      {zoomMode === "full" &&
        regionSelectionEnabled &&
        isSquareGrid &&
        viewMode === "region" && (
          <div
            className="absolute inset-0 pointer-events-none z-20"
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
  );

  return (
    <div className="flex flex-col h-full space-y-2">
      {/* View Mode Toggle and Download Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="tabs tabs-boxed bg-base-200 w-fit">
            <button
              className={`tab gap-2 ${viewMode === "pan-zoom" ? "tab-active" : ""}`}
              onClick={() => {
                setViewMode("pan-zoom");
                setZoomMode("full");
                setSelectedRegion(null);
                setRegionSelectionEnabled(false);
              }}
            >
              <Move className="h-4 w-4" />
              <span className="hidden sm:inline">DOM</span>
            </button>
            {isSquareGrid && (
              <button
                className={`tab gap-2 ${viewMode === "region" ? "tab-active" : ""}`}
                onClick={() => setViewMode("region")}
              >
                <Maximize2 className="h-4 w-4" />
                <span className="hidden sm:inline">Region</span>
              </button>
            )}
          </div>

          {viewMode === "region" &&
            zoomMode === "full" &&
            isSquareGrid &&
            !downloadSelectionEnabled && (
              <RegionZoomToggle
                enabled={regionSelectionEnabled}
                onToggle={setRegionSelectionEnabled}
              />
            )}
        </div>

        {/* Download selection controls */}
        {zoomMode === "full" && (
          <>
            {downloadSelectionEnabled ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-base-content/70">
                  {selectedForDownload.size} / {availableForDownloadCount}{" "}
                  selected
                </span>
                <button
                  className="btn btn-xs btn-ghost"
                  onClick={selectAllForDownload}
                  title="Select all"
                >
                  All
                </button>
                <button
                  className="btn btn-xs btn-ghost"
                  onClick={clearDownloadSelection}
                  title="Clear selection"
                >
                  Clear
                </button>
                <button
                  className="btn btn-sm btn-primary gap-1"
                  onClick={handleDownload}
                  disabled={selectedForDownload.size === 0 || isDownloading}
                >
                  {isDownloading ? (
                    <span className="loading loading-spinner loading-xs" />
                  ) : (
                    <Download size={16} />
                  )}
                  Download
                </button>
                <button
                  className="btn btn-sm btn-ghost btn-circle"
                  onClick={() => {
                    setDownloadSelectionEnabled(false);
                    setSelectedForDownload(new Set());
                  }}
                  title="Cancel"
                >
                  <X size={16} />
                </button>
              </div>
            ) : (
              <button
                className="btn btn-sm btn-outline gap-2"
                onClick={() => {
                  setDownloadSelectionEnabled(true);
                  setRegionSelectionEnabled(false);
                  selectAllForDownload();
                }}
                title="Select figures to download"
                disabled={availableForDownloadCount === 0}
              >
                <Download size={16} />
                Download
              </button>
            )}
          </>
        )}
      </div>

      {/* Back button */}
      {zoomMode === "region" && selectedRegion && (
        <div className="flex items-center gap-4">
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

      {/* Grid display */}
      <div
        className={`flex-1 relative overflow-hidden flex justify-center ${
          viewMode === "pan-zoom"
            ? "bg-base-200/30 border-2 border-dashed border-base-300 rounded-lg"
            : ""
        }`}
        style={{ padding: `${Math.max(4, padding / 4)}px` }}
        ref={containerRef}
      >
        {viewMode === "pan-zoom" ? (
          <TransformWrapper
            initialScale={1}
            minScale={0.3}
            maxScale={4}
            wheel={{ step: 0.08, smoothStep: 0.004 }}
            pinch={{ step: 5 }}
            doubleClick={{ mode: "zoomIn", step: 0.7 }}
            panning={{ velocityDisabled: false }}
            smooth={true}
            onTransformed={handleTransform}
          >
            <ZoomControls />
            <TransformComponent
              wrapperStyle={{ width: "100%", height: "100%" }}
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
          gridContent
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
