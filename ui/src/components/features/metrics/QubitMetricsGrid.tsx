"use client";

import React, {
  useMemo,
  useState,
  useRef,
  useLayoutEffect,
  useCallback,
  memo,
} from "react";
import Link from "next/link";
import {
  TransformWrapper,
  TransformComponent,
  useControls,
} from "react-zoom-pan-pinch";

import { GitBranch, ZoomIn, ZoomOut, Maximize2, Move } from "lucide-react";

import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import {
  getQubitGridPosition,
  type TopologyLayoutParams,
} from "@/utils/gridPosition";
import { calculateGridContainerWidth } from "@/utils/gridLayout";

import { QubitMetricHistoryModal } from "./QubitMetricHistoryModal";

interface MetricValue {
  value: number | null;
  task_id?: string | null;
  execution_id?: string | null;
}

interface QubitMetricsGridProps {
  metricData: { [key: string]: MetricValue } | null;
  title: string;
  metricKey: string;
  unit: string;
  colorScale: {
    min: number;
    max: number;
    colors: string[];
  };
  gridSize?: number;
  chipId: string;
  topologyId: string;
  selectedDate: string;
}

interface SelectedQubitInfo {
  qid: string;
  metric: MetricValue;
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

// Memoized grid cell component for performance
interface GridCellProps {
  qid: string;
  value: number | null;
  bgColor: string | null;
  unit: string;
  muxBgClass: string;
  showLabels: boolean;
  showValues: boolean;
  showUnits: boolean;
  onClick: () => void;
}

const GridCell = memo(function GridCell({
  qid,
  value,
  bgColor,
  unit,
  muxBgClass,
  showLabels,
  showValues,
  showUnits,
  onClick,
}: GridCellProps) {
  return (
    <button
      onClick={onClick}
      className={`aspect-square rounded-lg shadow-md flex flex-col items-center justify-center relative group cursor-pointer ${
        !bgColor ? "bg-base-300/50" : ""
      } ${muxBgClass}`}
      style={{
        backgroundColor: bgColor || undefined,
      }}
    >
      {/* QID Label */}
      {showLabels && (
        <div
          className={`absolute top-0.5 left-0.5 md:top-1 md:left-1 backdrop-blur-sm px-1 py-0.5 md:px-2 rounded text-[0.6rem] md:text-xs font-bold shadow-sm ${
            value !== null && value !== undefined
              ? "bg-black/30 text-white"
              : "bg-base-content/20 text-base-content"
          }`}
        >
          {qid}
        </div>
      )}

      {/* Value Display */}
      {value !== null && value !== undefined && showValues && (
        <div className="flex flex-col items-center justify-center h-full">
          <div className="text-[0.6rem] sm:text-sm md:text-base lg:text-lg font-bold text-white drop-shadow-md">
            {value.toFixed(2)}
          </div>
          {showUnits && (
            <div className="text-[0.5rem] md:text-xs text-white/90 font-medium drop-shadow hidden md:block">
              {unit}
            </div>
          )}
        </div>
      )}

      {/* No data indicator */}
      {(value === null || value === undefined) && showValues && (
        <div className="flex flex-col items-center justify-center h-full pt-3 md:pt-4">
          <div className="text-xs text-base-content/40 font-medium">N/A</div>
        </div>
      )}

      {/* Hover tooltip - only render when needed */}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-base-100 text-base-content text-sm rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
        {value !== null && value !== undefined
          ? `${qid}: ${value.toFixed(4)} ${unit}`
          : `${qid}: No data`}
      </div>
    </button>
  );
});

// Empty cell component
const EmptyCell = memo(function EmptyCell({
  muxBgClass,
}: {
  muxBgClass: string;
}) {
  return (
    <div className={`aspect-square bg-base-300/50 rounded-lg ${muxBgClass}`} />
  );
});

export function QubitMetricsGrid({
  metricData,
  title,
  metricKey,
  unit,
  colorScale,
  gridSize = 8,
  chipId,
  topologyId,
  selectedDate: _selectedDate,
}: QubitMetricsGridProps) {
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
    const size = topologyGridSize ?? gridSize;
    return { gridRows: size, gridCols: size };
  }, [topologyQubits, topologyGridSize, gridSize]);

  const effectiveGridSize = Math.max(gridRows, gridCols);

  const layoutParams: TopologyLayoutParams = useMemo(
    () => ({
      muxEnabled: hasMux,
      muxSize,
      gridSize: effectiveGridSize,
      layoutType,
    }),
    [hasMux, muxSize, effectiveGridSize, layoutType],
  );

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

  // Modal state
  const [selectedQubitInfo, setSelectedQubitInfo] =
    useState<SelectedQubitInfo | null>(null);
  const modalRef = useRef<HTMLDialogElement>(null);

  // Grid layout
  const displayCols = zoomMode === "region" ? regionSize : gridCols;
  const displayRows = zoomMode === "region" ? regionSize : gridRows;
  const { containerRef, cellSize, isMobile } = useGridLayout({
    cols: displayCols,
    rows: displayRows,
    reservedHeight: { mobile: 300, desktop: 350 },
    deps: [metricData],
  });

  // Modal control
  const isModalOpen = selectedQubitInfo !== null;
  useLayoutEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;
    if (isModalOpen && !modal.open) {
      modal.showModal();
    } else if (!isModalOpen && modal.open) {
      modal.close();
    }
  }, [isModalOpen]);

  const numRegions = Math.floor(effectiveGridSize / regionSize);
  const isSquareGrid = gridRows === gridCols;

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

  // Color interpolation
  const interpolateColor = useCallback(
    (color1: string, color2: string, factor: number): string => {
      const c1 = parseInt(color1.slice(1), 16);
      const c2 = parseInt(color2.slice(1), 16);
      const r1 = (c1 >> 16) & 0xff,
        g1 = (c1 >> 8) & 0xff,
        b1 = c1 & 0xff;
      const r2 = (c2 >> 16) & 0xff,
        g2 = (c2 >> 8) & 0xff,
        b2 = c2 & 0xff;
      const r = Math.round(r1 + (r2 - r1) * factor);
      const g = Math.round(g1 + (g2 - g1) * factor);
      const b = Math.round(b1 + (b2 - b1) * factor);
      return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
    },
    [],
  );

  // Get color for value
  const getColor = useCallback(
    (value: number | null, autoMin: number, autoMax: number): string | null => {
      if (value === null || value === undefined) return null;
      const { colors } = colorScale;
      if (colors.length === 0) return null;

      const effectiveMin =
        colorScale.min === 0 && colorScale.max === 0 ? autoMin : colorScale.min;
      const effectiveMax =
        colorScale.min === 0 && colorScale.max === 0 ? autoMax : colorScale.max;

      if (effectiveMin === effectiveMax) return colors[colors.length - 1];

      const normalized = Math.max(
        0,
        Math.min(1, (value - effectiveMin) / (effectiveMax - effectiveMin)),
      );
      const position = normalized * (colors.length - 1);
      const lowerIndex = Math.floor(position);
      const upperIndex = Math.min(lowerIndex + 1, colors.length - 1);
      const factor = position - lowerIndex;

      if (factor === 0 || lowerIndex === upperIndex) return colors[lowerIndex];
      return interpolateColor(colors[lowerIndex], colors[upperIndex], factor);
    },
    [colorScale, interpolateColor],
  );

  // Calculate statistics
  const stats = useMemo(() => {
    if (!metricData) return null;
    const values = Object.values(metricData)
      .map((m) => m.value)
      .filter((v): v is number => v !== null && v !== undefined);
    if (values.length === 0) return null;

    const sum = values.reduce((a, b) => a + b, 0);
    const sortedValues = [...values].sort((a, b) => a - b);
    return {
      count: values.length,
      avg: sum / values.length,
      min: sortedValues[0],
      max: sortedValues[sortedValues.length - 1],
      median: sortedValues[Math.floor(sortedValues.length / 2)],
    };
  }, [metricData]);

  const displayData = useMemo(() => metricData ?? {}, [metricData]);
  const displayCellSize = zoomMode === "region" ? cellSize * 0.9 : cellSize;
  const displayGridStart = useMemo(
    () =>
      selectedRegion
        ? {
            row: selectedRegion.row * regionSize,
            col: selectedRegion.col * regionSize,
          }
        : { row: 0, col: 0 },
    [selectedRegion, regionSize],
  );

  // LOD flags
  const showLabels = lodLevel !== "low" || zoomMode === "region";
  const showValues = lodLevel !== "low" || zoomMode === "region";
  const showUnits = lodLevel === "high" || zoomMode === "region";

  // Pre-compute grid cells data for memoization
  const gridCellsData = useMemo(() => {
    const cells: Array<{
      index: number;
      qid: string | undefined;
      value: number | null;
      bgColor: string | null;
      muxBgClass: string;
      metric: MetricValue | null;
    }> = [];

    for (let index = 0; index < displayRows * displayCols; index++) {
      const localRow = Math.floor(index / displayCols);
      const localCol = index % displayCols;
      const actualRow = displayGridStart.row + localRow;
      const actualCol = displayGridStart.col + localCol;

      const muxRow = Math.floor(actualRow / muxSize);
      const muxCol = Math.floor(actualCol / muxSize);
      const isEvenMux = (muxRow + muxCol) % 2 === 0;

      let qid: string | undefined;
      if (topologyQubits) {
        const foundEntry = Object.entries(topologyQubits).find(
          ([, pos]) => pos.row === actualRow && pos.col === actualCol,
        );
        if (foundEntry) qid = foundEntry[0];
      } else {
        qid = Object.keys(displayData).find((key) => {
          const pos = getQubitGridPosition(key, layoutParams);
          return pos.row === actualRow && pos.col === actualCol;
        });
        if (!qid) {
          const expectedQid = actualRow * gridSize + actualCol;
          if (expectedQid < gridSize * gridSize) qid = String(expectedQid);
        }
      }

      const metric = qid ? displayData[qid] : null;
      const value = metric?.value ?? null;
      const muxBgClass =
        hasMux && showMuxBoundaries
          ? isEvenMux
            ? "ring-2 ring-inset ring-primary/20"
            : "ring-2 ring-inset ring-secondary/20"
          : "";
      const bgColor = stats ? getColor(value, stats.min, stats.max) : null;

      cells.push({ index, qid, value, bgColor, muxBgClass, metric });
    }
    return cells;
  }, [
    displayRows,
    displayCols,
    displayGridStart,
    muxSize,
    topologyQubits,
    displayData,
    layoutParams,
    gridSize,
    hasMux,
    showMuxBoundaries,
    stats,
    getColor,
  ]);

  // Stable click handler
  const handleCellClick = useCallback((qid: string, metric: MetricValue) => {
    setSelectedQubitInfo({ qid, metric });
  }, []);

  // Grid content
  const gridContent = useMemo(
    () => (
      <div
        className="grid gap-1 md:gap-2 p-2 md:p-4 bg-base-200/50 rounded-xl relative"
        style={{
          gridTemplateColumns: `repeat(${displayCols}, minmax(${displayCellSize}px, 1fr))`,
          gridTemplateRows: `repeat(${displayRows}, minmax(${displayCellSize}px, 1fr))`,
          width: calculateGridContainerWidth(
            displayCols,
            displayCellSize,
            isMobile,
          ),
          willChange: "transform",
        }}
      >
        {gridCellsData.map((cell) => {
          if (!cell.qid) {
            return <EmptyCell key={cell.index} muxBgClass={cell.muxBgClass} />;
          }
          return (
            <GridCell
              key={cell.qid}
              qid={cell.qid}
              value={cell.value}
              bgColor={cell.bgColor}
              unit={unit}
              muxBgClass={cell.muxBgClass}
              showLabels={showLabels}
              showValues={showValues}
              showUnits={showUnits}
              onClick={() =>
                cell.metric && handleCellClick(cell.qid!, cell.metric)
              }
            />
          );
        })}

        {/* MUX labels overlay */}
        {hasMux && showMuxBoundaries && showLabels && (
          <div className="absolute inset-0 pointer-events-none p-2 md:p-4 z-10 hidden md:block">
            <div
              className="grid gap-1 md:gap-2 w-full h-full"
              style={{
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
                  muxActualRow * Math.floor(effectiveGridSize / muxSize) +
                  muxActualCol;
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
                    <div className="text-[0.5rem] md:text-xs font-bold text-base-content/60 bg-base-100/90 backdrop-blur-sm px-1.5 py-0.5 rounded shadow-sm border border-base-content/10">
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
            <div className="absolute inset-0 pointer-events-none p-2 md:p-4 z-20">
              <div
                className="grid gap-1 md:gap-2 w-full h-full"
                style={{
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
    ),
    [
      displayCols,
      displayRows,
      displayCellSize,
      isMobile,
      gridCellsData,
      unit,
      showLabels,
      showValues,
      showUnits,
      handleCellClick,
      hasMux,
      showMuxBoundaries,
      muxSize,
      displayGridStart,
      effectiveGridSize,
      zoomMode,
      regionSelectionEnabled,
      isSquareGrid,
      viewMode,
      numRegions,
      regionSize,
      hoveredRegion,
    ],
  );

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* View Mode Toggle */}
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

        {viewMode === "region" && zoomMode === "full" && isSquareGrid && (
          <RegionZoomToggle
            enabled={regionSelectionEnabled}
            onToggle={setRegionSelectionEnabled}
          />
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
        className={`flex-1 p-1 md:p-4 relative overflow-hidden flex justify-center ${
          viewMode === "pan-zoom"
            ? "bg-base-200/30 border-2 border-dashed border-base-300 rounded-lg m-1 md:m-2"
            : ""
        }`}
        ref={containerRef}
      >
        {viewMode === "pan-zoom" ? (
          <TransformWrapper
            initialScale={1}
            minScale={0.3}
            maxScale={4}
            wheel={{ step: 0.08, smoothStep: 0.004 }}
            pinch={{ step: 5 }}
            doubleClick={{ mode: "reset" }}
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

      {/* Qubit Detail Modal */}
      <dialog
        ref={modalRef}
        className="modal modal-bottom sm:modal-middle"
        onClose={() => setSelectedQubitInfo(null)}
      >
        <div className="modal-box w-full sm:w-[95vw] max-w-[1800px] bg-base-100 p-0 h-[90vh] sm:h-[95vh] overflow-hidden flex flex-col">
          {selectedQubitInfo && (
            <>
              <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-base-300 flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg sm:text-2xl font-bold truncate">
                    {selectedQubitInfo.qid} - {title}
                  </h2>
                  <p className="text-sm sm:text-base text-base-content/70 mt-0.5 sm:mt-1">
                    {selectedQubitInfo.metric.value !== null
                      ? `${selectedQubitInfo.metric.value.toFixed(4)} ${unit}`
                      : "No data"}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedQubitInfo(null)}
                  className="btn btn-ghost btn-sm btn-circle flex-shrink-0 ml-2"
                >
                  ✕
                </button>
              </div>
              <div className="flex-1 overflow-auto p-3 sm:p-6">
                <QubitMetricHistoryModal
                  chipId={chipId}
                  qid={selectedQubitInfo.qid}
                  metricName={metricKey}
                  metricUnit={unit}
                />
              </div>
              <div className="px-4 sm:px-6 py-3 sm:py-4 border-t border-base-300 flex justify-between items-center">
                <Link
                  href={`/provenance?parameter=${encodeURIComponent(metricKey)}&qid=${encodeURIComponent(selectedQubitInfo.qid)}&tab=lineage`}
                  className="btn btn-ghost btn-sm sm:btn-md gap-1"
                >
                  <GitBranch className="h-4 w-4" />
                  <span className="hidden sm:inline">Lineage</span>
                </Link>
                <div className="flex gap-2">
                  <button
                    onClick={() => setSelectedQubitInfo(null)}
                    className="btn btn-ghost btn-sm sm:btn-md"
                  >
                    Close
                  </button>
                  <a
                    href={`/chip/${chipId}/qubit/${selectedQubitInfo.qid}`}
                    className="btn btn-primary btn-sm sm:btn-md"
                  >
                    Details
                  </a>
                </div>
              </div>
            </>
          )}
        </div>
        <form method="dialog" className="modal-backdrop">
          <button>close</button>
        </form>
      </dialog>
    </div>
  );
}
