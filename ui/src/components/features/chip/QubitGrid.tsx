"use client";

import {
  Check,
  Download,
  Bot,
  LoaderCircle,
  X,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Move,
} from "lucide-react";
import { useMemo, useState, useRef, useCallback, memo, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { TransformWrapper, TransformComponent, useControls } from "react-zoom-pan-pinch";

import type { Task } from "@/schemas";

import { getGetChipNotesSummaryQueryKey } from "@/client/note/note";
import { useGetCopilotConfig } from "@/client/copilot/copilot";
import { downloadFiguresAsZip, requestBulkAiTriageReview } from "@/client/task-result/task-result";
import { AiTriageConfirmModal } from "@/components/features/chip/AiTriageConfirmModal";
import type { AiTriageBadgeState } from "@/components/features/chip/aiTriageBadge";
import {
  DownloadConfirmModal,
  type DownloadItemCounts,
  type DownloadOptions,
} from "@/components/features/chip/DownloadConfirmModal";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { TaskHistoryModal } from "@/components/features/chip/modals/TaskHistoryModal";
import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useQubitTaskResults } from "@/hooks/useQubitTaskResults";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import {
  buildAnalysisModelOptions,
  getStoredAnalysisModelKey,
  resolveAnalysisModelOption,
  setStoredAnalysisModelKey,
} from "@/lib/copilotModels";
import { getQubitGridPosition, type TopologyLayoutParams } from "@/lib/utils/grid-position";
import { calculateGridContainerWidth } from "@/lib/utils/grid-layout";

interface TaskResultGridProps {
  chipId: string;
  topologyId: string;
  selectedTask: string;
  selectedDate: string;
  gridSize: number;
  onDateChange?: (date: string) => void;
  aiTriageBadgesByTaskId?: Map<string, AiTriageBadgeState>;
}

interface SelectedTaskInfo {
  qid: string;
  taskName: string;
}

type TaskWithAiTriage = Task & {
  ai_triage?: {
    status?: string;
  } | null;
};

const DEFAULT_DOWNLOAD_OPTIONS: DownloadOptions = {
  figureImages: false,
  jsonFigures: true,
  rawData: false,
  aiTriageNotes: false,
};

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
const EmptyCell = memo(function EmptyCell({ muxBgClass }: { muxBgClass: string }) {
  return <div className={`aspect-square bg-base-300/50 rounded-lg ${muxBgClass}`} />;
});

// Status color helper
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

function isAiTriageReviewPending(task: TaskWithAiTriage | null | undefined): boolean {
  const status = task?.ai_triage?.status;
  return status === "requested" || status === "running";
}

function getPendingAiTriageTaskIds(
  tasks: Record<string, TaskWithAiTriage> | undefined,
): Set<string> {
  const taskIds = new Set<string>();
  for (const task of Object.values(tasks ?? {})) {
    if (task.task_id && isAiTriageReviewPending(task)) {
      taskIds.add(task.task_id);
    }
  }
  return taskIds;
}

function toPathList(paths: string[] | string | null | undefined): string[] {
  if (!paths) return [];
  return Array.isArray(paths) ? paths : [paths];
}

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
  isAiTriageMode: boolean;
  isSelectedForAiTriage: boolean;
  canBeAiTriaged: boolean;
  aiTriageBadge: AiTriageBadgeState | null;
  isAiTriagePending: boolean;
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
  isAiTriageMode,
  isSelectedForAiTriage,
  canBeAiTriaged,
  aiTriageBadge,
  isAiTriagePending,
  onClick,
}: GridCellProps) {
  const isSelectionMode = isDownloadMode || isAiTriageMode;
  const isSelected = isDownloadMode ? isSelectedForDownload : isSelectedForAiTriage;
  const canBeSelected = isDownloadMode ? canBeDownloaded : canBeAiTriaged;

  if (!task) {
    return (
      <div
        className={`aspect-square bg-base-300 rounded-lg flex items-center justify-center relative ${muxBgClass}`}
      >
        {showLabels && <div className="text-sm font-medium text-base-content/50">{qid}</div>}
      </div>
    );
  }

  // Zoomed-out: show status-colored tile (heatmap style)
  if (!showFigures) {
    return (
      <button
        onClick={onClick}
        className={`aspect-square rounded-lg shadow-sm relative group cursor-pointer ${getStatusColor(task.status)} ${muxBgClass} ${
          isSelectionMode && isSelected ? "ring-2 ring-primary ring-offset-1" : ""
        } ${isSelectionMode && !canBeSelected ? "opacity-40 cursor-not-allowed" : ""}`}
      >
        {showLabels && (
          <div className="absolute top-0.5 left-0.5 bg-black/30 text-white px-0.5 py-px rounded text-[0.5rem] font-bold">
            {qid}
          </div>
        )}
        {isAiTriagePending ? (
          <div
            className="absolute top-0.5 right-0.5 rounded bg-info text-info-content p-0.5 shadow-sm"
            title="AI triage review requested"
          >
            <LoaderCircle size={10} className="animate-spin" />
          </div>
        ) : aiTriageBadge ? (
          <div
            className={`absolute top-0.5 right-0.5 rounded ${aiTriageBadge.iconClass} p-0.5 shadow-sm`}
            title={aiTriageBadge.title}
          >
            <Bot size={10} />
          </div>
        ) : null}
        {/* Hover tooltip */}
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-base-100 text-base-content text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
          {qid}: {task.status}
          {isAiTriagePending ? " · AI triage review requested" : ""}
          {aiTriageBadge ? ` · ${aiTriageBadge.tooltip}` : ""}
        </div>
        {isSelectionMode && canBeSelected && isSelected && (
          <div className="absolute inset-0 flex items-center justify-center bg-primary/20">
            <div className="bg-primary text-primary-content rounded-full p-0.5">
              {isAiTriageMode ? <Bot size={10} /> : <Check size={10} />}
            </div>
          </div>
        )}
      </button>
    );
  }

  // Zoomed-in: show full figure
  return (
    <button
      onClick={onClick}
      className={`aspect-square rounded-xl bg-white shadow-md border border-base-300/60 overflow-hidden transition-all duration-200 hover:shadow-xl hover:scale-105 hover:border-primary/40 relative w-full ${muxBgClass} ${
        isSelectionMode && isSelected ? "ring-2 ring-primary ring-offset-2" : ""
      } ${isSelectionMode && !canBeSelected ? "opacity-40 cursor-not-allowed" : ""}`}
    >
      {task.figure_path && figurePath && (
        <div className="absolute inset-1 [&_button]:hidden">
          <TaskFigure path={figurePath} qid={qid} className="w-full h-full object-contain" />
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
      {isAiTriagePending ? (
        <div
          className="absolute top-1 right-1 rounded bg-info text-info-content p-1 shadow-sm"
          title="AI triage review requested"
        >
          <LoaderCircle size={14} className="animate-spin" />
        </div>
      ) : aiTriageBadge ? (
        <div
          className={`absolute top-1 right-1 rounded ${aiTriageBadge.iconClass} p-1 shadow-sm`}
          title={aiTriageBadge.title}
        >
          <Bot size={14} />
        </div>
      ) : null}
      <div
        className={`absolute bottom-1 right-1 w-2 h-2 rounded-full ${getStatusColor(task.status)}`}
      />
      {/* Download selection overlay */}
      {isSelectionMode && canBeSelected && (
        <div
          className={`absolute inset-0 flex items-center justify-center transition-colors ${
            isSelected ? "bg-primary/20" : "bg-transparent hover:bg-base-content/10"
          }`}
        >
          {isSelected && (
            <div className="bg-primary text-primary-content rounded-full p-1">
              {isAiTriageMode ? <Bot size={16} /> : <Check size={16} />}
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
  aiTriageBadgesByTaskId,
}: TaskResultGridProps) {
  const queryClient = useQueryClient();
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

  const [selectedTaskInfo, setSelectedTaskInfo] = useState<SelectedTaskInfo | null>(null);

  // Download selection mode state
  const [downloadSelectionEnabled, setDownloadSelectionEnabled] = useState(false);
  const [selectedForDownload, setSelectedForDownload] = useState<Set<string>>(new Set());
  const [isDownloading, setIsDownloading] = useState(false);
  const [isDownloadConfirmOpen, setIsDownloadConfirmOpen] = useState(false);
  const [downloadOptions, setDownloadOptions] = useState<DownloadOptions>(DEFAULT_DOWNLOAD_OPTIONS);
  const [aiTriageSelectionEnabled, setAiTriageSelectionEnabled] = useState(false);
  const [selectedForAiTriage, setSelectedForAiTriage] = useState<Set<string>>(new Set());
  const [pendingAiTriageTaskIds, setPendingAiTriageTaskIds] = useState<Set<string>>(new Set());
  const [isRequestingAiTriage, setIsRequestingAiTriage] = useState(false);
  const [isAiTriageConfirmOpen, setIsAiTriageConfirmOpen] = useState(false);
  const [aiTriageStatus, setAiTriageStatus] = useState<string | null>(null);
  const [selectedModelKey, setSelectedModelKey] = useState(getStoredAnalysisModelKey);
  const { data: copilotConfigResponse } = useGetCopilotConfig();
  const modelOptions = useMemo(
    () => buildAnalysisModelOptions(copilotConfigResponse?.data ?? null),
    [copilotConfigResponse?.data],
  );
  const selectedModel = resolveAnalysisModelOption(modelOptions, selectedModelKey);

  // Fetch task results
  const {
    data: taskResponse,
    isLoading: isLoadingTask,
    isError: isTaskError,
    refetch: refetchTaskResults,
  } = useQubitTaskResults({
    chipId,
    task: selectedTask,
    selectedDate,
    keepPrevious: true,
  });
  const persistedPendingAiTriageTaskIds = useMemo(
    () => getPendingAiTriageTaskIds(taskResponse?.data?.result),
    [taskResponse?.data?.result],
  );
  const visiblePendingAiTriageCount = useMemo(() => {
    const taskIds = new Set(pendingAiTriageTaskIds);
    for (const taskId of persistedPendingAiTriageTaskIds) {
      taskIds.add(taskId);
    }
    return taskIds.size;
  }, [pendingAiTriageTaskIds, persistedPendingAiTriageTaskIds]);
  const downloadCounts = useMemo(() => {
    const counts: DownloadItemCounts = {
      figureImages: 0,
      jsonFigures: 0,
      rawData: 0,
      aiTriageNotes: 0,
    };
    selectedForDownload.forEach((qid) => {
      const task = taskResponse?.data?.result?.[qid];
      counts.figureImages += toPathList(task?.figure_path).length;
      counts.jsonFigures += toPathList(task?.json_figure_path).length;
      counts.rawData += toPathList(task?.raw_data_path).length;
      if (task?.task_id && aiTriageBadgesByTaskId?.has(task.task_id)) {
        counts.aiTriageNotes += 1;
      }
    });
    return counts;
  }, [aiTriageBadgesByTaskId, selectedForDownload, taskResponse?.data?.result]);

  useEffect(() => {
    if (!aiTriageBadgesByTaskId || pendingAiTriageTaskIds.size === 0) return;
    setPendingAiTriageTaskIds((prev) => {
      const next = new Set(prev);
      for (const taskId of aiTriageBadgesByTaskId.keys()) {
        next.delete(taskId);
      }
      return next.size === prev.size ? prev : next;
    });
  }, [aiTriageBadgesByTaskId, pendingAiTriageTaskIds.size]);

  useEffect(() => {
    if (visiblePendingAiTriageCount === 0) return;
    const intervalId = window.setInterval(() => {
      void refetchTaskResults();
      void queryClient.invalidateQueries({
        queryKey: getGetChipNotesSummaryQueryKey(chipId),
      });
    }, 5_000);
    return () => window.clearInterval(intervalId);
  }, [chipId, queryClient, refetchTaskResults, visiblePendingAiTriageCount]);

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

  // LOD: store zoom scale, compute visibility flags from effective cell size.
  // Initialize to a conservative value; will be updated on first transform.
  const [currentScale, setCurrentScale] = useState<number | null>(null);
  const lodTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const numRegions = Math.floor(gridSize / regionSize);
  const isSquareGrid = gridRows === gridCols;

  // Calculate displayed grid size based on zoom mode
  const displayCols = zoomMode === "region" ? regionSize : gridCols;
  const displayRows = zoomMode === "region" ? regionSize : gridRows;

  // Use grid layout hook for responsive sizing
  const { containerRef, cellSize, isMobile, viewportHeight, gap, padding } = useGridLayout({
    cols: displayCols,
    rows: displayRows,
    reservedHeight: { mobile: 300, desktop: 350 },
    deps: [taskResponse, topologyQubits, zoomMode, selectedRegion],
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

  // Calculate initial scale for TransformWrapper (must be before early returns)
  const MIN_FIGURE_CELL_SIZE = 60;
  const initialScale = useMemo(() => {
    if (viewMode !== "pan-zoom" || cellSize >= MIN_FIGURE_CELL_SIZE) return 1;
    return Math.max(0.3, cellSize / MIN_FIGURE_CELL_SIZE);
  }, [viewMode, cellSize]);

  if (isLoadingTask)
    return (
      <div className="w-full flex justify-center py-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
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
      .filter(([, task]) => hasDownloadableArtifacts(task))
      .map(([qid]) => qid);
    setSelectedForDownload(new Set(allQids));
  };

  const clearDownloadSelection = () => {
    setSelectedForDownload(new Set());
  };

  const handleDownload = async () => {
    if (selectedForDownload.size === 0) return;

    const paths: string[] = [];
    const aiTriageTaskIds: string[] = [];
    selectedForDownload.forEach((qid) => {
      const task = taskResponse?.data?.result?.[qid];
      if (!task) return;
      if (downloadOptions.figureImages) {
        paths.push(...toPathList(task.figure_path));
      }
      if (downloadOptions.jsonFigures) {
        paths.push(...toPathList(task.json_figure_path));
      }
      if (downloadOptions.rawData) {
        paths.push(...toPathList(task.raw_data_path));
      }
      if (downloadOptions.aiTriageNotes && task.task_id) {
        aiTriageTaskIds.push(task.task_id);
      }
    });

    if (paths.length === 0 && aiTriageTaskIds.length === 0) return;

    setIsDownloading(true);
    try {
      const filename = `${chipId}_${selectedTask}_${selectedDate}_artifacts.zip`;
      const response = await downloadFiguresAsZip(
        { paths, filename, ai_triage_task_ids: aiTriageTaskIds },
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

      setIsDownloadConfirmOpen(false);
      setDownloadSelectionEnabled(false);
      setSelectedForDownload(new Set());
    } catch (error) {
      console.error("Download error:", error);
      alert("Download failed. Please try again.");
    } finally {
      setIsDownloading(false);
    }
  };

  const hasDownloadableArtifacts = (task: Task | null | undefined): boolean =>
    Boolean(
      toPathList(task?.figure_path).length ||
      toPathList(task?.json_figure_path).length ||
      toPathList(task?.raw_data_path).length ||
      task?.task_id,
    );

  const hasJsonFigures = (qid: string): boolean => {
    const task = taskResponse?.data?.result?.[qid];
    return hasDownloadableArtifacts(task);
  };

  const availableForDownloadCount = Object.entries(taskResponse?.data?.result || {}).filter(
    ([, task]) => hasDownloadableArtifacts(task),
  ).length;
  const availableForAiTriageCount = Object.values(taskResponse?.data?.result || {}).filter(
    (task) => task.task_id,
  ).length;
  const copilotConfig = copilotConfigResponse?.data as
    | {
        enabled?: boolean;
        analysis?: { enabled?: boolean; ai_triage_tasks?: string[] };
      }
    | undefined;
  const isAiTriageTaskConfigured = Boolean(
    copilotConfig?.enabled &&
    copilotConfig.analysis?.enabled &&
    copilotConfig.analysis.ai_triage_tasks?.includes(selectedTask),
  );
  const handleModelChange = (key: string) => {
    setSelectedModelKey(key);
    setStoredAnalysisModelKey(key);
  };

  const canAiTriageQid = (qid: string): boolean =>
    Boolean(isAiTriageTaskConfigured && taskResponse?.data?.result?.[qid]?.task_id);

  const toggleAiTriageSelection = (qid: string) => {
    setSelectedForAiTriage((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(qid)) {
        newSet.delete(qid);
      } else {
        newSet.add(qid);
      }
      return newSet;
    });
  };

  const selectAllForAiTriage = () => {
    const allQids = Object.keys(taskResponse?.data?.result || {}).filter(canAiTriageQid);
    setSelectedForAiTriage(new Set(allQids));
  };

  const clearAiTriageSelection = () => {
    setSelectedForAiTriage(new Set());
  };

  const handleBulkAiTriage = async () => {
    if (selectedForAiTriage.size === 0 || !isAiTriageTaskConfigured) return;

    const taskIds = Array.from(selectedForAiTriage)
      .map((qid) => taskResponse?.data?.result?.[qid]?.task_id)
      .filter((taskId): taskId is string => Boolean(taskId));
    if (taskIds.length === 0) return;

    setIsRequestingAiTriage(true);
    try {
      const response = await requestBulkAiTriageReview({
        chip_id: chipId,
        task: selectedTask,
        entity_type: "qubit",
        date: selectedDate === "latest" ? null : selectedDate,
        task_ids: taskIds,
        model_override: selectedModel.model,
      });
      setAiTriageStatus(
        `AI triage review requested for ${response.data.requested_count} task results.`,
      );
      setPendingAiTriageTaskIds((prev) => {
        const next = new Set(prev);
        for (const taskId of response.data.task_ids) {
          next.add(taskId);
        }
        return next;
      });
      setIsAiTriageConfirmOpen(false);
      setAiTriageSelectionEnabled(false);
      setSelectedForAiTriage(new Set());
    } catch (error) {
      console.error("AI triage request error:", error);
      setAiTriageStatus("AI triage request failed. Please try again.");
    } finally {
      setIsRequestingAiTriage(false);
    }
  };

  // Calculate displayed grid size based on zoom mode
  const displayGridStart = selectedRegion
    ? {
        row: selectedRegion.row * regionSize,
        col: selectedRegion.col * regionSize,
      }
    : { row: 0, col: 0 };

  // In pan-zoom mode, ensure cells are large enough for figures to be readable.
  // For large grids (e.g., 144Q) the calculated cellSize may be very small,
  // but TransformWrapper handles panning/zooming the oversized grid.
  const baseCellSize =
    viewMode === "pan-zoom" ? Math.max(cellSize, MIN_FIGURE_CELL_SIZE) : cellSize;
  const displayCellSize = zoomMode === "region" ? baseCellSize * 0.9 : baseCellSize;

  // LOD flags: compute from effective pixel size (cellSize * zoom scale)
  const activeScale = currentScale ?? initialScale;
  const effectiveCellSize = displayCellSize * (viewMode === "pan-zoom" ? activeScale : 1);
  const showLabels = effectiveCellSize >= 20 || zoomMode === "region";
  const showFigures = effectiveCellSize >= 50 || zoomMode === "region";

  // Grid content (extracted for reuse in both view modes)
  const gridContent = (
    <div
      className="grid bg-base-200/50 rounded-xl relative"
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
        const isSelectedForDownload = selectedForDownload.has(qid);
        const canBeDownloaded = hasJsonFigures(qid);
        const aiTriageBadge = task?.task_id
          ? (aiTriageBadgesByTaskId?.get(task.task_id) ?? null)
          : null;
        const isAiTriagePending = Boolean(
          task?.task_id &&
          (pendingAiTriageTaskIds.has(task.task_id) || isAiTriageReviewPending(task)),
        );

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
            isDownloadMode={downloadSelectionEnabled}
            isSelectedForDownload={isSelectedForDownload}
            canBeDownloaded={canBeDownloaded}
            isAiTriageMode={aiTriageSelectionEnabled}
            isSelectedForAiTriage={selectedForAiTriage.has(qid)}
            canBeAiTriaged={canAiTriageQid(qid)}
            aiTriageBadge={aiTriageBadge}
            isAiTriagePending={isAiTriagePending}
            onClick={() => {
              if (downloadSelectionEnabled) {
                if (canBeDownloaded) {
                  toggleDownloadSelection(qid);
                }
              } else if (aiTriageSelectionEnabled) {
                if (canAiTriageQid(qid)) {
                  toggleAiTriageSelection(qid);
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
              const muxActualRow = Math.floor(displayGridStart.row / muxSize) + muxLocalRow;
              const muxActualCol = Math.floor(displayGridStart.col / muxSize) + muxLocalCol;
              const muxIndex = muxActualRow * Math.floor(gridSize / muxSize) + muxActualCol;
              const startCol = muxLocalCol * muxSize + 1;
              const startRow = muxLocalRow * muxSize + 1;
              const spanCols = Math.min(muxSize, displayCols - muxLocalCol * muxSize);
              const spanRows = Math.min(muxSize, displayRows - muxLocalRow * muxSize);
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
      {zoomMode === "full" && regionSelectionEnabled && isSquareGrid && viewMode === "region" && (
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
            {Array.from({ length: numRegions * numRegions }).map((_, index) => {
              const regionRow = Math.floor(index / numRegions);
              const regionCol = index % numRegions;
              const isHovered =
                hoveredRegion?.row === regionRow && hoveredRegion?.col === regionCol;

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
                  onMouseEnter={() => setHoveredRegion({ row: regionRow, col: regionCol })}
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
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-full space-y-2">
      {isTaskError && <div className="alert alert-error">Failed to load data</div>}
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
                  {selectedForDownload.size} / {availableForDownloadCount} selected
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
                  onClick={() => setIsDownloadConfirmOpen(true)}
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
            ) : aiTriageSelectionEnabled ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-base-content/70">
                  {selectedForAiTriage.size} / {availableForAiTriageCount} selected
                </span>
                <button
                  className="btn btn-xs btn-ghost"
                  onClick={selectAllForAiTriage}
                  title="Select all"
                >
                  All
                </button>
                <button
                  className="btn btn-xs btn-ghost"
                  onClick={clearAiTriageSelection}
                  title="Clear selection"
                >
                  Clear
                </button>
                <button
                  className="btn btn-sm btn-primary gap-1"
                  onClick={() => setIsAiTriageConfirmOpen(true)}
                  disabled={selectedForAiTriage.size === 0 || isRequestingAiTriage}
                >
                  {isRequestingAiTriage ? (
                    <span className="loading loading-spinner loading-xs" />
                  ) : (
                    <Bot size={16} />
                  )}
                  AI Triage
                </button>
                <button
                  className="btn btn-sm btn-ghost btn-circle"
                  onClick={() => {
                    setAiTriageSelectionEnabled(false);
                    setSelectedForAiTriage(new Set());
                  }}
                  title="Cancel"
                >
                  <X size={16} />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  className="btn btn-sm btn-outline gap-2"
                  onClick={() => {
                    setAiTriageSelectionEnabled(true);
                    setDownloadSelectionEnabled(false);
                    setRegionSelectionEnabled(false);
                    selectAllForAiTriage();
                  }}
                  title="Request AI triage review for the displayed task results"
                  disabled={availableForAiTriageCount === 0 || !isAiTriageTaskConfigured}
                >
                  <Bot size={16} />
                  AI Triage
                </button>
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
              </div>
            )}
          </>
        )}
      </div>
      {(aiTriageStatus || visiblePendingAiTriageCount > 0) && (
        <div className="text-xs text-base-content/70 text-right flex justify-end items-center gap-2">
          {visiblePendingAiTriageCount > 0 && (
            <LoaderCircle className="h-3 w-3 animate-spin text-info" />
          )}
          <span>
            {visiblePendingAiTriageCount > 0
              ? `${aiTriageStatus ?? "AI triage review is in progress."} Waiting for ${visiblePendingAiTriageCount} note update(s).`
              : aiTriageStatus}
          </span>
        </div>
      )}

      <AiTriageConfirmModal
        isOpen={isAiTriageConfirmOpen}
        selectedCount={selectedForAiTriage.size}
        taskName={selectedTask}
        modelOptions={modelOptions}
        selectedModelKey={selectedModel.key}
        isSubmitting={isRequestingAiTriage}
        onModelChange={handleModelChange}
        onConfirm={handleBulkAiTriage}
        onClose={() => setIsAiTriageConfirmOpen(false)}
      />
      <DownloadConfirmModal
        isOpen={isDownloadConfirmOpen}
        selectedCount={selectedForDownload.size}
        options={downloadOptions}
        counts={downloadCounts}
        isSubmitting={isDownloading}
        onOptionsChange={setDownloadOptions}
        onConfirm={handleDownload}
        onClose={() => setIsDownloadConfirmOpen(false)}
      />

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
            initialScale={initialScale}
            minScale={Math.min(0.3, initialScale)}
            maxScale={4}
            wheel={{ step: 0.08 }}
            pinch={{ step: 5 }}
            doubleClick={{ mode: "zoomIn", step: 0.7 }}
            panning={{ velocityDisabled: false }}
            smooth={true}
            centerOnInit={true}
            onTransform={handleTransform}
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
