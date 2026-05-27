"use client";

import { Bot, Check, Download, LoaderCircle, X, Maximize2, Move } from "lucide-react";
import { useState, useMemo, useRef, useCallback, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";

import type { Task } from "@/schemas";

import { getGetChipNotesSummaryQueryKey } from "@/client/note/note";
import { useGetCopilotConfig } from "@/client/copilot/copilot";
import { downloadFiguresAsZip, requestBulkAiReview } from "@/client/task-result/task-result";
import { AiReviewConfirmModal } from "@/components/features/chip/AiReviewConfirmModal";
import type { AiReviewBadgeState } from "@/components/features/chip/aiReviewBadge";
import {
  DownloadConfirmModal,
  type DownloadItemCounts,
  type DownloadOptions,
} from "@/components/features/chip/DownloadConfirmModal";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { CouplingTaskHistoryModal } from "@/components/features/chip/modals/CouplingTaskHistoryModal";
import { GridZoomControls } from "@/components/ui/GridZoomControls";
import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";
import { useCouplingTaskResults } from "@/hooks/useCouplingTaskResults";
import { useGridLayout } from "@/hooks/useGridLayout";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import {
  buildAnalysisModelOptions,
  getStoredAnalysisModelKey,
  resolveAnalysisModelOption,
  setStoredAnalysisModelKey,
} from "@/lib/copilotModels";
import { getQubitGridPosition, type TopologyLayoutParams } from "@/lib/utils/grid-position";
import { calculateGridDimension } from "@/lib/utils/grid-layout";

interface CouplingGridProps {
  chipId: string;
  topologyId: string;
  selectedTask: string;
  selectedDate: string;
  gridSize: number;
  onDateChange?: (date: string) => void;
  aiReviewBadgesByTaskId?: Map<string, AiReviewBadgeState>;
}

interface SelectedTaskInfo {
  couplingId: string;
  taskName: string;
}

interface ExtendedTask extends Task {
  couplingId: string;
}

type TaskWithAiReview = Task & {
  ai_review?: {
    status?: string;
  } | null;
};

const DEFAULT_DOWNLOAD_OPTIONS: DownloadOptions = {
  figureImages: false,
  jsonFigures: true,
  rawData: false,
  aiReviewNotes: false,
  aiReviewReplayBundles: false,
};

function toPathList(paths: string[] | string | null | undefined): string[] {
  if (!paths) return [];
  return Array.isArray(paths) ? paths : [paths];
}

function isAiReviewRequestPending(task: TaskWithAiReview | null | undefined): boolean {
  const status = task?.ai_review?.status;
  return status === "requested" || status === "running";
}

function getPendingAiReviewTaskIds(
  tasks: Record<string, TaskWithAiReview> | undefined,
): Set<string> {
  const taskIds = new Set<string>();
  for (const task of Object.values(tasks ?? {})) {
    if (task.task_id && isAiReviewRequestPending(task)) {
      taskIds.add(task.task_id);
    }
  }
  return taskIds;
}

export function CouplingGrid({
  chipId,
  topologyId,
  selectedTask,
  selectedDate,
  gridSize: defaultGridSize,
  aiReviewBadgesByTaskId,
}: CouplingGridProps) {
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

  // Download selection mode state
  const [downloadSelectionEnabled, setDownloadSelectionEnabled] = useState(false);
  const [selectedForDownload, setSelectedForDownload] = useState<Set<string>>(new Set());
  const [isDownloading, setIsDownloading] = useState(false);
  const [isDownloadConfirmOpen, setIsDownloadConfirmOpen] = useState(false);
  const [downloadOptions, setDownloadOptions] = useState<DownloadOptions>(DEFAULT_DOWNLOAD_OPTIONS);
  const [aiReviewSelectionEnabled, setAiReviewSelectionEnabled] = useState(false);
  const [selectedForAiReview, setSelectedForAiReview] = useState<Set<string>>(new Set());
  const [pendingAiReviewTaskIds, setPendingAiReviewTaskIds] = useState<Set<string>>(new Set());
  const [isRequestingAiReview, setIsRequestingAiReview] = useState(false);
  const [isAiReviewConfirmOpen, setIsAiReviewConfirmOpen] = useState(false);
  const [aiReviewStatus, setAiReviewStatus] = useState<string | null>(null);
  const [selectedModelKey, setSelectedModelKey] = useState(getStoredAnalysisModelKey);
  const { data: copilotConfigResponse } = useGetCopilotConfig();
  const modelOptions = useMemo(
    () => buildAnalysisModelOptions(copilotConfigResponse?.data ?? null),
    [copilotConfigResponse?.data],
  );
  const selectedModel = resolveAnalysisModelOption(modelOptions, selectedModelKey);

  // View mode state: 'pan-zoom' for DOM with pan/zoom, 'region' for region zoom
  const [viewMode, setViewMode] = useState<"pan-zoom" | "region">("region");

  // Region tab is only available for square grids; fall back to pan-zoom otherwise.
  useEffect(() => {
    if (!isSquareGrid && viewMode === "region") {
      setViewMode("pan-zoom");
    }
  }, [isSquareGrid, viewMode]);

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

  // LOD: store zoom scale, compute visibility flags from effective cell size.
  const [currentScale, setCurrentScale] = useState<number | null>(null);
  const lodTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const numRegions = Math.floor(gridSize / regionSize);

  const {
    data: taskResponse,
    isLoading,
    isError,
    refetch: refetchTaskResults,
  } = useCouplingTaskResults({
    chipId,
    task: selectedTask,
    selectedDate,
  });
  const persistedPendingAiReviewTaskIds = useMemo(
    () => getPendingAiReviewTaskIds(taskResponse?.data?.result),
    [taskResponse?.data?.result],
  );
  const visiblePendingAiReviewCount = useMemo(() => {
    const taskIds = new Set(pendingAiReviewTaskIds);
    for (const taskId of persistedPendingAiReviewTaskIds) {
      taskIds.add(taskId);
    }
    return taskIds.size;
  }, [pendingAiReviewTaskIds, persistedPendingAiReviewTaskIds]);
  const downloadCounts = useMemo(() => {
    const counts: DownloadItemCounts = {
      figureImages: 0,
      jsonFigures: 0,
      rawData: 0,
      aiReviewNotes: 0,
      aiReviewReplayBundles: 0,
    };
    selectedForDownload.forEach((couplingId) => {
      const task = taskResponse?.data?.result?.[couplingId];
      counts.figureImages += toPathList(task?.figure_path).length;
      counts.jsonFigures += toPathList(task?.json_figure_path).length;
      counts.rawData += toPathList(task?.raw_data_path).length;
      if (task?.task_id && aiReviewBadgesByTaskId?.has(task.task_id)) {
        counts.aiReviewNotes += 1;
      }
      if (task?.task_id) {
        counts.aiReviewReplayBundles += 1;
      }
    });
    return counts;
  }, [aiReviewBadgesByTaskId, selectedForDownload, taskResponse?.data?.result]);

  useEffect(() => {
    if (!aiReviewBadgesByTaskId || pendingAiReviewTaskIds.size === 0) return;
    setPendingAiReviewTaskIds((prev) => {
      const next = new Set(prev);
      for (const taskId of aiReviewBadgesByTaskId.keys()) {
        next.delete(taskId);
      }
      return next.size === prev.size ? prev : next;
    });
  }, [aiReviewBadgesByTaskId, pendingAiReviewTaskIds.size]);

  useEffect(() => {
    if (visiblePendingAiReviewCount === 0) return;
    void refetchTaskResults();
    void queryClient.invalidateQueries({
      queryKey: getGetChipNotesSummaryQueryKey(chipId),
    });
    const intervalId = window.setInterval(() => {
      void refetchTaskResults();
      void queryClient.invalidateQueries({
        queryKey: getGetChipNotesSummaryQueryKey(chipId),
      });
    }, 5_000);
    return () => window.clearInterval(intervalId);
  }, [chipId, queryClient, refetchTaskResults, visiblePendingAiReviewCount]);

  // Use grid layout hook for responsive sizing
  const displayCols = zoomMode === "region" ? regionSize : gridCols;
  const displayRows = zoomMode === "region" ? regionSize : gridRows;
  const { containerRef, cellSize, isMobile, viewportHeight, gap, padding } = useGridLayout({
    cols: displayCols,
    rows: displayRows,
    reservedHeight: { mobile: 300, desktop: 350 },
    deps: [taskResponse?.data],
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

  const effectiveGridSize = gridSize;
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
      .filter(([, task]) => hasDownloadableArtifacts(task))
      .map(([couplingId]) => couplingId);
    setSelectedForDownload(new Set(allCouplingIds));
  };

  const clearDownloadSelection = () => {
    setSelectedForDownload(new Set());
  };

  const handleDownload = async () => {
    if (selectedForDownload.size === 0) return;

    const paths: string[] = [];
    const aiReviewTaskIds: string[] = [];
    const aiReviewBundleTaskIds: string[] = [];
    selectedForDownload.forEach((couplingId) => {
      const task = taskResponse?.data?.result?.[couplingId];
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
      if (downloadOptions.aiReviewNotes && task.task_id) {
        aiReviewTaskIds.push(task.task_id);
      }
      if (downloadOptions.aiReviewReplayBundles && task.task_id) {
        aiReviewBundleTaskIds.push(task.task_id);
      }
    });

    if (paths.length === 0 && aiReviewTaskIds.length === 0 && aiReviewBundleTaskIds.length === 0)
      return;

    setIsDownloading(true);
    try {
      const filename = `${chipId}_${selectedTask}_${selectedDate}_coupling_artifacts.zip`;
      const response = await downloadFiguresAsZip(
        {
          paths,
          filename,
          ai_review_task_ids: aiReviewTaskIds,
          ai_review_bundle_task_ids: aiReviewBundleTaskIds,
        },
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

  const hasJsonFigures = (couplingId: string): boolean => {
    const task = taskResponse?.data?.result?.[couplingId];
    return hasDownloadableArtifacts(task);
  };

  const availableForDownloadCount = Object.entries(taskResponse?.data?.result || {}).filter(
    ([, task]) => hasDownloadableArtifacts(task),
  ).length;
  const availableForAiReviewCount = Object.values(taskResponse?.data?.result || {}).filter(
    (task) => task.task_id,
  ).length;
  const copilotConfig = copilotConfigResponse?.data as
    | {
        enabled?: boolean;
        analysis?: { enabled?: boolean; ai_review_tasks?: string[] };
      }
    | undefined;
  const isAiReviewTaskConfigured = Boolean(
    copilotConfig?.enabled &&
    copilotConfig.analysis?.enabled &&
    copilotConfig.analysis.ai_review_tasks?.includes(selectedTask),
  );
  const handleModelChange = (key: string) => {
    setSelectedModelKey(key);
    setStoredAnalysisModelKey(key);
  };

  const canAiReviewCoupling = (couplingId: string): boolean =>
    Boolean(isAiReviewTaskConfigured && taskResponse?.data?.result?.[couplingId]?.task_id);

  const toggleAiReviewSelection = (couplingId: string) => {
    setSelectedForAiReview((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(couplingId)) {
        newSet.delete(couplingId);
      } else {
        newSet.add(couplingId);
      }
      return newSet;
    });
  };

  const selectAllForAiReview = () => {
    const allCouplingIds = Object.keys(taskResponse?.data?.result || {}).filter(
      canAiReviewCoupling,
    );
    setSelectedForAiReview(new Set(allCouplingIds));
  };

  const clearAiReviewSelection = () => {
    setSelectedForAiReview(new Set());
  };

  const handleBulkAiReview = async () => {
    if (selectedForAiReview.size === 0 || !isAiReviewTaskConfigured) return;

    const taskIds = Array.from(selectedForAiReview)
      .map((couplingId) => taskResponse?.data?.result?.[couplingId]?.task_id)
      .filter((taskId): taskId is string => Boolean(taskId));
    if (taskIds.length === 0) return;

    setIsRequestingAiReview(true);
    try {
      const response = await requestBulkAiReview({
        chip_id: chipId,
        task: selectedTask,
        entity_type: "coupling",
        date: selectedDate === "latest" ? null : selectedDate,
        task_ids: taskIds,
        model_override: selectedModel.model,
      });
      setAiReviewStatus(`AI review requested for ${response.data.requested_count} task results.`);
      setPendingAiReviewTaskIds((prev) => {
        const next = new Set(prev);
        for (const taskId of response.data.task_ids) {
          next.add(taskId);
        }
        return next;
      });
      void refetchTaskResults();
      void queryClient.invalidateQueries({
        queryKey: getGetChipNotesSummaryQueryKey(chipId),
      });
      setIsAiReviewConfirmOpen(false);
      setAiReviewSelectionEnabled(false);
      setSelectedForAiReview(new Set());
    } catch (error) {
      console.error("AI review request error:", error);
      setAiReviewStatus("AI review request failed. Please try again.");
    } finally {
      setIsRequestingAiReview(false);
    }
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
                  <span className={zoomMode === "full" ? "hidden md:inline" : ""}>{qid}</span>
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

            const muxActualRow = Math.floor(displayGridStart.row / muxSize) + muxLocalRow;
            const muxActualCol = Math.floor(displayGridStart.col / muxSize) + muxLocalCol;
            const muxIndex = muxActualRow * Math.floor(effectiveGridSize / muxSize) + muxActualCol;

            const muxCenterX =
              (muxLocalCol * muxSize + muxSize / 2) * (displayCellSize + gap) - gap / 2;
            const muxCenterY =
              (muxLocalRow * muxSize + muxSize / 2) * (displayCellSize + gap) - gap / 2;

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
            ((displayCol1 + displayCol2) / 2) * (displayCellSize + gap) + displayCellSize / 2;
          const centerY =
            ((displayRow1 + displayRow2) / 2) * (displayCellSize + gap) + displayCellSize / 2;

          const isSelectedForDownload = selectedForDownload.has(task.couplingId);
          const canBeDownloaded = hasJsonFigures(task.couplingId);
          const isSelectedForAiReview = selectedForAiReview.has(task.couplingId);
          const canBeAiReviewed = canAiReviewCoupling(task.couplingId);
          const isAiReviewPending = Boolean(
            task.task_id &&
            (pendingAiReviewTaskIds.has(task.task_id) || isAiReviewRequestPending(task)),
          );
          const aiReviewBadge = task.task_id
            ? (aiReviewBadgesByTaskId?.get(task.task_id) ?? null)
            : null;

          const statusColor =
            task.status === "completed"
              ? "bg-success"
              : task.status === "failed"
                ? "bg-error"
                : "bg-warning";

          // Zoomed-out: status-colored dot
          if (!showFigures) {
            return (
              <button
                key={normKey}
                onClick={() => {
                  if (downloadSelectionEnabled) {
                    if (canBeDownloaded) toggleDownloadSelection(task.couplingId);
                  } else if (aiReviewSelectionEnabled) {
                    if (canBeAiReviewed) {
                      toggleAiReviewSelection(task.couplingId);
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
                  width: displayCellSize * 0.45,
                  height: displayCellSize * 0.45,
                }}
                className={`rounded-md shadow-sm group cursor-pointer -translate-x-1/2 -translate-y-1/2 ${statusColor} ${
                  downloadSelectionEnabled && isSelectedForDownload
                    ? "ring-2 ring-primary ring-offset-1"
                    : ""
                } ${
                  aiReviewSelectionEnabled && isSelectedForAiReview
                    ? "ring-2 ring-primary ring-offset-1"
                    : ""
                }`}
              >
                {isAiReviewPending && (
                  <div
                    className="absolute top-0 right-0 rounded bg-info text-info-content p-0.5 shadow-sm"
                    title="AI review requested"
                  >
                    <LoaderCircle size={10} className="animate-spin" />
                  </div>
                )}
                {!isAiReviewPending && aiReviewBadge && (
                  <div
                    className={`absolute top-0 right-0 rounded ${aiReviewBadge.iconClass} p-0.5 shadow-sm`}
                    title={aiReviewBadge.title}
                  >
                    <Bot size={10} />
                  </div>
                )}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-base-100 text-base-content text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
                  {task.couplingId}: {task.status}
                  {isAiReviewPending ? " · AI review requested" : ""}
                  {aiReviewBadge ? ` · ${aiReviewBadge.tooltip}` : ""}
                </div>
              </button>
            );
          }

          // Zoomed-in: full figure
          return (
            <button
              key={normKey}
              onClick={() => {
                if (downloadSelectionEnabled) {
                  if (canBeDownloaded) {
                    toggleDownloadSelection(task.couplingId);
                  }
                } else if (aiReviewSelectionEnabled) {
                  if (canBeAiReviewed) {
                    toggleAiReviewSelection(task.couplingId);
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
                aiReviewSelectionEnabled && isSelectedForAiReview
                  ? "ring-2 ring-primary ring-offset-2"
                  : ""
              } ${
                downloadSelectionEnabled && !canBeDownloaded ? "opacity-40 cursor-not-allowed" : ""
              } ${
                aiReviewSelectionEnabled && !canBeAiReviewed ? "opacity-40 cursor-not-allowed" : ""
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
              {isAiReviewPending && (
                <div
                  className="absolute top-1 right-1 rounded bg-info text-info-content p-1 shadow-sm"
                  title="AI review requested"
                >
                  <LoaderCircle size={14} className="animate-spin" />
                </div>
              )}
              {!isAiReviewPending && aiReviewBadge && (
                <div
                  className={`absolute top-1 right-1 rounded ${aiReviewBadge.iconClass} p-1 shadow-sm`}
                  title={aiReviewBadge.title}
                >
                  <Bot size={14} />
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
              {aiReviewSelectionEnabled && canBeAiReviewed && (
                <div
                  className={`absolute inset-0 flex items-center justify-center transition-colors ${
                    isSelectedForAiReview
                      ? "bg-primary/20"
                      : "bg-transparent hover:bg-base-content/10"
                  }`}
                >
                  {isSelectedForAiReview && (
                    <div className="bg-primary text-primary-content rounded-full p-1">
                      <Bot size={16} />
                    </div>
                  )}
                </div>
              )}
            </button>
          );
        })}

      {/* Region selection overlay - only for square grids */}
      {zoomMode === "full" && regionSelectionEnabled && isSquareGrid && viewMode === "region" && (
        <>
          {Array.from({ length: numRegions * numRegions }).map((_, index) => {
            const regionRow = Math.floor(index / numRegions);
            const regionCol = index % numRegions;
            const isHovered = hoveredRegion?.row === regionRow && hoveredRegion?.col === regionCol;

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
        </>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-full space-y-2 max-w-4xl mx-auto w-full mt-8">
      {isError && (
        <div className="alert alert-error">
          Failed to load {selectedTask} data for {selectedDate}
        </div>
      )}
      {/* View mode toggle and Download controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg py-2">
        <div className="flex items-center gap-4">
          <div className="tabs tabs-boxed bg-base-300 w-fit">
            {isSquareGrid && (
              <button
                className={`tab gap-2 ${viewMode === "region" ? "tab-active" : ""}`}
                onClick={() => setViewMode("region")}
              >
                <Maximize2 className="h-4 w-4" />
                <span className="hidden sm:inline">Region</span>
              </button>
            )}
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
          </div>

          <div
            className={
              viewMode !== "region" ||
              zoomMode !== "full" ||
              !isSquareGrid ||
              downloadSelectionEnabled
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
            ) : aiReviewSelectionEnabled ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-base-content/70">
                  {selectedForAiReview.size} / {availableForAiReviewCount} selected
                </span>
                <button
                  className="btn btn-xs btn-ghost"
                  onClick={selectAllForAiReview}
                  title="Select all"
                >
                  All
                </button>
                <button
                  className="btn btn-xs btn-ghost"
                  onClick={clearAiReviewSelection}
                  title="Clear selection"
                >
                  Clear
                </button>
                <button
                  className="btn btn-sm btn-primary gap-1"
                  onClick={() => setIsAiReviewConfirmOpen(true)}
                  disabled={selectedForAiReview.size === 0 || isRequestingAiReview}
                >
                  {isRequestingAiReview ? (
                    <span className="loading loading-spinner loading-xs" />
                  ) : (
                    <Bot size={16} />
                  )}
                  AI Review
                </button>
                <button
                  className="btn btn-sm btn-ghost btn-circle"
                  onClick={() => {
                    setAiReviewSelectionEnabled(false);
                    setSelectedForAiReview(new Set());
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
                    setAiReviewSelectionEnabled(true);
                    setDownloadSelectionEnabled(false);
                    setRegionSelectionEnabled(false);
                    selectAllForAiReview();
                  }}
                  title="Request AI review for the displayed task results"
                  disabled={availableForAiReviewCount === 0 || !isAiReviewTaskConfigured}
                >
                  <Bot size={16} />
                  AI Review
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
      {(aiReviewStatus || visiblePendingAiReviewCount > 0) && (
        <div className="text-xs text-base-content/70 text-right flex justify-end items-center gap-2">
          {visiblePendingAiReviewCount > 0 && (
            <LoaderCircle className="h-3 w-3 animate-spin text-info" />
          )}
          <span>
            {visiblePendingAiReviewCount > 0
              ? `${aiReviewStatus ?? "AI review is in progress."} Waiting for ${visiblePendingAiReviewCount} note update(s).`
              : aiReviewStatus}
          </span>
        </div>
      )}

      <AiReviewConfirmModal
        isOpen={isAiReviewConfirmOpen}
        selectedCount={selectedForAiReview.size}
        taskName={selectedTask}
        modelOptions={modelOptions}
        selectedModelKey={selectedModel.key}
        isSubmitting={isRequestingAiReview}
        onModelChange={handleModelChange}
        onConfirm={handleBulkAiReview}
        onClose={() => setIsAiReviewConfirmOpen(false)}
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
        className={`flex-1 relative flex justify-center ${
          viewMode === "pan-zoom"
            ? "bg-base-200/30 border-2 border-dashed border-base-300 rounded-lg"
            : "bg-base-200/60 rounded-lg"
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
            smooth={false}
            centerOnInit={true}
            onTransform={handleTransform}
          >
            <GridZoomControls />
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
        selectedDate={selectedDate}
      />
    </div>
  );
}
