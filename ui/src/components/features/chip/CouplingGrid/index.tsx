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
import { useState, useMemo, useRef, useCallback } from "react";
import {
  TransformWrapper,
  TransformComponent,
  useControls,
} from "react-zoom-pan-pinch";

import type { Task } from "@/schemas";

import { downloadFiguresAsZip } from "@/client/task-result/task-result";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { CouplingTaskHistoryModal } from "@/components/features/chip/modals/CouplingTaskHistoryModal";
import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import { useCouplingTaskResults } from "@/hooks/useCouplingTaskResults";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import {
  getQubitGridPosition,
  type TopologyLayoutParams,
} from "@/utils/gridPosition";
import { calculateGridDimension } from "@/utils/gridLayout";

interface CouplingGridProps {
  chipId: string;
  topologyId: string;
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

export function CouplingGrid({
  chipId,
  topologyId,
  selectedTask,
  selectedDate,
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

  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);

  // Download selection mode state
  const [downloadSelectionEnabled, setDownloadSelectionEnabled] =
    useState(false);
  const [selectedForDownload, setSelectedForDownload] = useState<Set<string>>(
    new Set(),
  );
  const [isDownloading, setIsDownloading] = useState(false);

  // View mode state: 'pan-zoom' for DOM with pan/zoom, 'region' for region zoom
  const [viewMode, setViewMode] = useState<"pan-zoom" | "region">("pan-zoom");

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

  // LOD (Level of Detail) state for pan-zoom mode
  const [lodLevel, setLodLevel] = useState<"high" | "medium" | "low">("high");
  const lodTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Use grid layout hook for responsive sizing
  const displayCols = zoomMode === "region" ? regionSize : gridCols;
  const displayRows = zoomMode === "region" ? regionSize : gridRows;
  const { containerRef, cellSize, isMobile, viewportHeight, gap, padding } =
    useGridLayout({
      cols: displayCols,
      rows: displayRows,
      reservedHeight: { mobile: 300, desktop: 350 },
      deps: [taskResponse?.data],
    });

  // Handle transform changes for LOD (debounced)
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

  // LOD-based visibility flags
  const showLabels = lodLevel !== "low" || zoomMode === "region";

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
  const effectiveGridSize = gridSize;
  const displayCellSize = zoomMode === "region" ? cellSize * 0.8 : cellSize;
  const displayGridSize = zoomMode === "region" ? regionSize : gridSize;
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

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
  const toggleDownloadSelection = (couplingId: string) => {
    setSelectedForDownload((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(couplingId)) {
        newSet.delete(couplingId);
      } else {
        newSet.add(couplingId);
      }
      return newSet;
    });
  };

  const selectAllForDownload = () => {
    const allCouplingIds = Object.entries(taskResponse?.data?.result || {})
      .filter(([, task]) => task.json_figure_path)
      .map(([couplingId]) => couplingId);
    setSelectedForDownload(new Set(allCouplingIds));
  };

  const clearDownloadSelection = () => {
    setSelectedForDownload(new Set());
  };

  const handleDownload = async () => {
    if (selectedForDownload.size === 0) return;

    const paths: string[] = [];
    selectedForDownload.forEach((couplingId) => {
      const task = taskResponse?.data?.result?.[couplingId];
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
      const filename = `${chipId}_${selectedTask}_${selectedDate}_coupling_json_figures.zip`;
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

  const hasJsonFigures = (couplingId: string): boolean => {
    const task = taskResponse?.data?.result?.[couplingId];
    return !!task?.json_figure_path;
  };

  const availableForDownloadCount = Object.entries(
    taskResponse?.data?.result || {},
  ).filter(([, task]) => task.json_figure_path).length;

  // Grid content (extracted for reuse in both view modes)
  const gridContent = (
    <div
      className="relative flex-shrink-0"
      style={{
        width: calculateGridDimension(
          displayGridSize,
          displayCellSize,
          isMobile,
          viewportHeight,
        ),
        height: calculateGridDimension(
          displayGridSize,
          displayCellSize,
          isMobile,
          viewportHeight,
        ),
        maxWidth: viewMode === "pan-zoom" ? "none" : "100%",
        willChange: viewMode === "pan-zoom" ? "transform" : "auto",
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

            const muxRow = Math.floor(row / muxSize);
            const muxCol = Math.floor(col / muxSize);
            const isEvenMux = (muxRow + muxCol) % 2 === 0;

            const muxBgClass =
              hasMux && showMuxBoundaries
                ? isEvenMux
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
                  <span
                    className={zoomMode === "full" ? "hidden md:inline" : ""}
                  >
                    {qid}
                  </span>
                )}
              </div>
            );
          });
      })()}

      {/* MUX labels - centered in each MUX group */}
      {hasMux && showMuxBoundaries && showLabels && (
        <>
          {Array.from({
            length: Math.pow(Math.ceil(displayGridSize / muxSize), 2),
          }).map((_, idx) => {
            const numMuxCols = Math.ceil(displayGridSize / muxSize);
            const muxLocalRow = Math.floor(idx / numMuxCols);
            const muxLocalCol = idx % numMuxCols;

            const muxActualRow =
              Math.floor(displayGridStart.row / muxSize) + muxLocalRow;
            const muxActualCol =
              Math.floor(displayGridStart.col / muxSize) + muxLocalCol;
            const muxIndex =
              muxActualRow * Math.floor(effectiveGridSize / muxSize) +
              muxActualCol;

            const muxCenterX =
              (muxLocalCol * muxSize + muxSize / 2) * (displayCellSize + gap) -
              gap / 2;
            const muxCenterY =
              (muxLocalRow * muxSize + muxSize / 2) * (displayCellSize + gap) -
              gap / 2;

            return (
              <div
                key={`mux-label-${idx}`}
                className={`absolute z-10 pointer-events-none ${
                  zoomMode === "full" ? "hidden md:flex" : "flex"
                }`}
                style={{
                  top: muxCenterY,
                  left: muxCenterX,
                  transform: "translate(-50%, -50%)",
                }}
              >
                <div className="text-[0.45rem] md:text-[0.6rem] font-semibold text-base-content/30 bg-base-100/60 px-1 py-px rounded border border-base-content/5">
                  MUX{muxIndex}
                </div>
              </div>
            );
          })}
        </>
      )}

      {/* Coupling overlays */}
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
            ((displayCol1 + displayCol2) / 2) * (displayCellSize + gap) +
            displayCellSize / 2;
          const centerY =
            ((displayRow1 + displayRow2) / 2) * (displayCellSize + gap) +
            displayCellSize / 2;

          const isSelectedForDownload = selectedForDownload.has(
            task.couplingId,
          );
          const canBeDownloaded = hasJsonFigures(task.couplingId);

          return (
            <button
              key={normKey}
              onClick={() => {
                if (downloadSelectionEnabled) {
                  if (canBeDownloaded) {
                    toggleDownloadSelection(task.couplingId);
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
              className={`rounded-xl bg-white shadow-md border border-base-300/60 overflow-hidden transition-all duration-200 hover:shadow-xl hover:scale-105 hover:border-primary/40 -translate-x-1/2 -translate-y-1/2 ${
                downloadSelectionEnabled && isSelectedForDownload
                  ? "ring-2 ring-primary ring-offset-2"
                  : ""
              } ${
                downloadSelectionEnabled && !canBeDownloaded
                  ? "opacity-40 cursor-not-allowed"
                  : ""
              }`}
            >
              {figurePath && (
                <div className="absolute inset-1">
                  <TaskFigure
                    path={figurePath}
                    qid={String(task.couplingId)}
                    className="w-full h-full object-contain"
                  />
                </div>
              )}
              {/* Download selection overlay */}
              {downloadSelectionEnabled && canBeDownloaded && (
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
      {zoomMode === "full" &&
        regionSelectionEnabled &&
        isSquareGrid &&
        viewMode === "region" && (
          <>
            {Array.from({ length: numRegions * numRegions }).map((_, index) => {
              const regionRow = Math.floor(index / numRegions);
              const regionCol = index % numRegions;
              const isHovered =
                hoveredRegion?.row === regionRow &&
                hoveredRegion?.col === regionCol;

              const regionX = regionCol * regionSize * (displayCellSize + gap);
              const regionY = regionRow * regionSize * (displayCellSize + gap);
              const regionWidth = regionSize * (displayCellSize + gap) - gap;
              const regionHeight = regionSize * (displayCellSize + gap) - gap;

              return (
                <button
                  key={index}
                  className={`absolute transition-colors duration-200 rounded-lg flex items-center justify-center z-20 ${
                    isHovered
                      ? "bg-primary/30 border-2 border-primary shadow-lg"
                      : "bg-primary/5 border-2 border-primary/20 hover:border-primary/40 hover:bg-primary/10"
                  }`}
                  style={{
                    top: regionY,
                    left: regionX,
                    width: regionWidth,
                    height: regionHeight,
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
            })}
          </>
        )}
    </div>
  );

  return (
    <div className="flex flex-col h-full space-y-2">
      {/* View mode toggle and Download controls */}
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

      {/* Back button when in region mode */}
      {viewMode === "region" && zoomMode === "region" && selectedRegion && (
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
            Region {selectedRegion.row + 1},{selectedRegion.col + 1}
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
