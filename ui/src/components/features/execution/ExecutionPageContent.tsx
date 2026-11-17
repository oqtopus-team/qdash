"use client";

import { useState, useEffect, useLayoutEffect, useMemo, useRef, useCallback } from "react";

import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  AppWindow,
  ArrowUpRight,
  Ban,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CircleHelp,
  CirclePlay,
  CircleX,
  Clock,
  ExternalLink,
  GripHorizontal,
  Minus,
  MoveDiagonal2,
  PanelRight,
  StopCircle,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

import { isExecutionCancellable } from "@/lib/executionStatus";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { DEFAULT_TIMEZONE, formatDateTime } from "@/lib/utils/datetime";

import {
  type ActivityWindow,
  DEFAULT_ACTIVITY_WINDOW,
  ExecutionActivityChart,
} from "./ExecutionActivityChart";
import {
  type DetailPanelMode,
  FLOATING_PANEL_MEDIA_QUERY,
  animateWindowEntry,
  arrowKeyDelta,
  useFloatingWindowGeometry,
  useMediaQuery,
} from "./useFloatingDetailWindow";

import type { ExecutionResponseSummary } from "@/schemas";

import { useListChips } from "@/client/chip/chip";
import {
  useListExecutions,
  useGetExecution,
  useCancelExecution,
  getListExecutionsQueryKey,
  getGetExecutionQueryKey,
} from "@/client/execution/execution";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { InvestigateWithAiButton } from "@/components/features/chat/InvestigateWithAiButton";
import { CancelExecutionModal } from "@/components/features/execution/CancelExecutionModal";
import { ExecutionRunSummary } from "@/components/features/execution/ExecutionRunSummary";
import { ExecutionTaskProgress } from "@/components/features/execution/ExecutionTaskProgress";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { DateSelector } from "@/components/selectors/DateSelector";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { ExecutionPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { TaskMessagePanel } from "@/components/ui/TaskMessagePanel";
import { useToast } from "@/components/ui/Toast";
import { useProject } from "@/contexts/ProjectContext";
import { useDateNavigation } from "@/hooks/useDateNavigation";
import { useExecutionUrlState } from "@/hooks/useUrlState";

type ActorFields = {
  user_id?: string | null;
  username?: string;
};

function formatActorLabel(actor?: ActorFields | null) {
  if (actor?.username) return `@${actor.username}`;
  return actor?.user_id || "Unknown";
}

function getStatusLabel(status: string) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function getStatusBadgeClass(status: string) {
  switch (status) {
    case "running":
      return "badge-info";
    case "completed":
      return "badge-success";
    case "scheduled":
    case "pending":
      return "badge-warning";
    case "failed":
      return "badge-error";
    default:
      return "badge-ghost";
  }
}

// Static icons pair each status color with a shape, so running and cancelling stay
// recognizable without a continuous pulse and status never relies on color alone.
function getStatusIcon(status: string): LucideIcon {
  switch (status) {
    case "running":
      return CirclePlay;
    case "completed":
      return CircleCheck;
    case "scheduled":
    case "pending":
      return Clock;
    case "failed":
      return CircleX;
    case "cancelling":
      return StopCircle;
    case "cancelled":
      return Ban;
    default:
      return CircleHelp;
  }
}

// Task rows keep their established mapping: any status outside the known set reads as failed.
function getTaskStatusDisplay(status?: string | null) {
  switch (status) {
    case "running":
      return { label: "Running", textClass: "text-info", Icon: getStatusIcon("running") };
    case "completed":
      return { label: "Completed", textClass: "text-success", Icon: getStatusIcon("completed") };
    case "scheduled":
      return { label: "Scheduled", textClass: "text-warning", Icon: getStatusIcon("scheduled") };
    case "cancelled":
      return { label: "Cancelled", textClass: "text-neutral", Icon: getStatusIcon("cancelled") };
    default:
      return { label: "Failed", textClass: "text-error", Icon: getStatusIcon("failed") };
  }
}

function PaginationControls({
  currentPage,
  setCurrentPage,
  hasMore,
  totalPages,
}: {
  currentPage: number;
  setCurrentPage: React.Dispatch<React.SetStateAction<number>>;
  hasMore: boolean;
  totalPages?: number;
}) {
  const isNextDisabled = totalPages !== undefined ? currentPage >= totalPages : !hasMore;
  const pageLabel =
    totalPages !== undefined ? `Page ${currentPage} of ${totalPages}` : `Page ${currentPage}`;

  return (
    <div className="flex justify-center items-center gap-2 sm:gap-4 my-3 sm:my-4 px-4">
      <button
        onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
        disabled={currentPage === 1}
        className="btn btn-xs sm:btn-sm btn-outline"
      >
        Prev
      </button>
      <span className="text-sm">{pageLabel}</span>
      <button
        onClick={() => setCurrentPage((prev) => prev + 1)}
        disabled={isNextDisabled}
        className="btn btn-xs sm:btn-sm btn-outline"
      >
        Next
      </button>
    </div>
  );
}

/**
 * Execution history page listing workflow runs with task results and cancellation controls
 */
export function ExecutionPageContent() {
  const queryClient = useQueryClient();

  // URL state management
  const { selectedChip, setSelectedChip, isInitialized } = useExecutionUrlState();
  const { projectId } = useProject();

  // Add date state for navigation
  const [selectedDate, setSelectedDate] = useState<string>("latest");

  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [expandedTaskIndex, setExpandedTaskIndex] = useState<number | null>(null);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [activityDays, setActivityDays] = useState<ActivityWindow>(DEFAULT_ACTIVITY_WINDOW);
  const sidebarRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const executionCards = useRef(new Map<string, HTMLDivElement>());
  const pendingFocusRestore = useRef<string | null>(null);
  const executionListHeading = useRef<HTMLHeadingElement>(null);
  const scrollBodyRef = useRef<HTMLDivElement>(null);
  const floatButtonRef = useRef<HTMLButtonElement>(null);
  const dockButtonRef = useRef<HTMLButtonElement>(null);
  const minimizeButtonRef = useRef<HTMLButtonElement>(null);
  const restoreButtonRef = useRef<HTMLButtonElement>(null);
  const restoreControlRef = useRef<HTMLDivElement>(null);
  const pendingPanelFocus = useRef<"float" | "dock" | "minimize" | "restore" | null>(null);
  const pendingPanelMotion = useRef<{
    target: "panel" | "restore";
    from: DOMRect | null;
    origin?: string;
  } | null>(null);

  // The user's preferred placement survives closing the panel; minimizing does not.
  const [panelMode, setPanelMode] = useState<DetailPanelMode>("docked");
  const canFloat = useMediaQuery(FLOATING_PANEL_MEDIA_QUERY);
  // Narrow viewports always use the full-width drawer, so no window can sit offscreen.
  const effectiveMode: DetailPanelMode = canFloat ? panelMode : "docked";
  const isFloating = effectiveMode === "floating";
  const isMinimized = effectiveMode === "minimized";
  const isPanelVisible = isSidebarOpen && !isMinimized;
  const windowGeometry = useFloatingWindowGeometry(sidebarRef, isFloating);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;

  // Use custom hook for date navigation (unused but kept for potential future use)
  useDateNavigation(selectedChip || "", selectedDate, setSelectedDate);

  // Get list of chips to set default
  const { data: chipsData } = useListChips();

  // Memoize sorted chips to avoid recalculating on every render
  const sortedChips = useMemo(() => {
    if (!chipsData?.data?.chips) return [];
    return [...chipsData.data.chips].sort((a, b) => {
      const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
      const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
      return dateB - dateA;
    });
  }, [chipsData?.data?.chips]);

  // Set the latest chip as default when chips are loaded and no chip is selected from URL
  useEffect(() => {
    if (isInitialized && !selectedChip && sortedChips.length > 0) {
      setSelectedChip(sortedChips[0].chip_id);
    }
  }, [isInitialized, selectedChip, sortedChips, setSelectedChip]);

  // Fetch execution summary list by chip_id
  const {
    data: executionData,
    isError,
    isLoading,
  } = useListExecutions(
    {
      chip_id: selectedChip || "",
      skip: (currentPage - 1) * itemsPerPage,
      limit: itemsPerPage,
      // A picked day is filtered on the server, so every run of that day is reachable,
      // not only those on the first page. The day follows the UI's display time zone.
      ...(selectedDate === "latest" ? {} : { date: selectedDate, timezone: DEFAULT_TIMEZONE }),
    },
    {
      query: {
        // Refresh every 5 seconds
        refetchInterval: 5000,
        // Keep polling even when the window is in the background
        refetchIntervalInBackground: true,
        enabled: !!selectedChip,
      },
    },
  );

  const cancelMutation = useCancelExecution();
  const toast = useToast();

  // Fetch task list for the selected execution_id
  const {
    data: executionDetailData,
    isLoading: isDetailLoading,
    isError: isDetailError,
  } = useGetExecution(selectedExecutionId || "", {
    query: {
      // Refresh every 5 seconds
      refetchInterval: 5000,
      // Keep polling even when the window is in the background
      refetchIntervalInBackground: true,
      // Only enable polling when an execution is selected
      enabled: !!selectedExecutionId,
    },
  });

  // Compute card data from execution data (filter by date)
  const cardData = useMemo(() => executionData?.data?.executions ?? [], [executionData]);

  const selectedExecutionIndex = cardData.findIndex(
    (execution) => execution.execution_id === selectedExecutionId,
  );

  const selectedExecutionName = cardData.find(
    (execution) => execution.execution_id === selectedExecutionId,
  )?.name;

  const handleCloseSidebar = useCallback(() => {
    if (selectedExecutionId) pendingFocusRestore.current = selectedExecutionId;
    if (scrollBodyRef.current) scrollBodyRef.current.scrollTop = 0;
    setIsSidebarOpen(false);
    setSelectedExecutionId(null);
    setExpandedTaskIndex(null);
    setPanelMode((mode) => (mode === "minimized" ? "floating" : mode));
  }, [selectedExecutionId]);

  // Runs are scoped to a project and a chip. A change of either from any source (the selectors,
  // a project switch, URL history, or a deep link) closes the panel and any pending cancellation,
  // so neither shows or acts on another scope's execution. Projects can share chip IDs, so the
  // project is observed on its own; its first resolution is not a switch.
  const previousScope = useRef({ chip: selectedChip, project: projectId });
  useEffect(() => {
    const previous = previousScope.current;
    const chipChanged = previous.chip !== selectedChip;
    const projectSwitched =
      projectId !== null && previous.project !== null && previous.project !== projectId;
    previousScope.current = { chip: selectedChip, project: projectId ?? previous.project };
    if (!chipChanged && !projectSwitched) return;
    setShowCancelConfirm(false);
    if (projectSwitched) {
      // A day or page picked in one project means nothing in another.
      setSelectedDate("latest");
      setCurrentPage(1);
    }
    if (!selectedExecutionId) return;
    const active = document.activeElement;
    const panelHadFocus =
      !!active &&
      (!!sidebarRef.current?.contains(active) || !!restoreControlRef.current?.contains(active));
    handleCloseSidebar();
    // Focus returns to the list only from the closing panel, never from the control that
    // switched the scope.
    if (!panelHadFocus) pendingFocusRestore.current = null;
  }, [selectedChip, projectId, selectedExecutionId, handleCloseSidebar]);

  // Mode changes record where the panel was and what should receive focus; both apply once the
  // new layout is in the DOM, before paint.
  useLayoutEffect(() => {
    const motion = pendingPanelMotion.current;
    pendingPanelMotion.current = null;
    if (motion) {
      animateWindowEntry(
        motion.target === "panel" ? sidebarRef.current : restoreControlRef.current,
        motion.from,
        motion.origin,
      );
    }
    const focusTarget = pendingPanelFocus.current;
    pendingPanelFocus.current = null;
    if (focusTarget) {
      const refs = {
        float: floatButtonRef,
        dock: dockButtonRef,
        minimize: minimizeButtonRef,
        restore: restoreButtonRef,
      };
      refs[focusTarget].current?.focus({ preventScroll: true });
    }
  }, [effectiveMode, isSidebarOpen]);

  const captureRect = (element: HTMLElement | null) => element?.getBoundingClientRect() ?? null;

  const handleFloat = () => {
    pendingPanelMotion.current = { target: "panel", from: captureRect(sidebarRef.current) };
    pendingPanelFocus.current = "dock";
    setPanelMode("floating");
  };

  const handleDock = () => {
    pendingPanelMotion.current = { target: "panel", from: captureRect(sidebarRef.current) };
    pendingPanelFocus.current = "float";
    setPanelMode("docked");
  };

  const handleMinimize = () => {
    pendingPanelMotion.current = { target: "restore", from: null, origin: "bottom right" };
    pendingPanelFocus.current = "restore";
    setPanelMode("minimized");
  };

  const handleRestore = (focusTarget: "minimize" | null = "minimize") => {
    pendingPanelMotion.current = {
      target: "panel",
      from: captureRect(restoreControlRef.current),
    };
    pendingPanelFocus.current = focusTarget;
    setPanelMode("floating");
  };

  useEffect(() => {
    if (isSidebarOpen || isLoading || !pendingFocusRestore.current) return;
    const firstId = cardData[0]?.execution_id;
    const target =
      executionCards.current.get(pendingFocusRestore.current) ??
      (firstId ? executionCards.current.get(firstId) : null) ??
      executionListHeading.current;
    target?.focus({ preventScroll: true });
    pendingFocusRestore.current = null;
  }, [cardData, isLoading, isSidebarOpen]);

  useEffect(() => {
    if (isSidebarOpen) closeButtonRef.current?.focus({ preventScroll: true });
  }, [isSidebarOpen]);

  // Tracks the panel control that last had focus. Focus or a pointer press anywhere else
  // forgets it, so the breakpoint handling below never takes unrelated focus.
  const lastPanelFocus = useRef<Element | null>(null);
  useEffect(() => {
    const ownedByPanel = (node: EventTarget | null): node is Element =>
      node instanceof Element &&
      (!!sidebarRef.current?.contains(node) || !!restoreControlRef.current?.contains(node));
    const active = document.activeElement;
    lastPanelFocus.current = isSidebarOpen && ownedByPanel(active) ? active : null;
    if (!isSidebarOpen) return;
    const handleFocusIn = (event: FocusEvent) => {
      lastPanelFocus.current = ownedByPanel(event.target) ? event.target : null;
    };
    const handlePointerDown = (event: PointerEvent) => {
      if (!ownedByPanel(event.target)) lastPanelFocus.current = null;
    };
    document.addEventListener("focusin", handleFocusIn);
    document.addEventListener("pointerdown", handlePointerDown, true);
    return () => {
      document.removeEventListener("focusin", handleFocusIn);
      document.removeEventListener("pointerdown", handlePointerDown, true);
    };
  }, [isSidebarOpen]);

  // Crossing the desktop breakpoint removes the window controls (Move, Resize, Dock, Minimize,
  // Restore) or hides a minimized panel. When that takes the focused control away, focus moves
  // to the close button of the visible panel, or to Restore when the panel is minimized.
  const previousCanFloat = useRef(canFloat);
  useLayoutEffect(() => {
    if (previousCanFloat.current === canFloat) return;
    previousCanFloat.current = canFloat;
    const previous = lastPanelFocus.current;
    if (!isSidebarOpen || !previous) return;
    const hiddenInPanel = !isPanelVisible && !!sidebarRef.current?.contains(previous);
    if (previous.isConnected && !hiddenInPanel) return;
    const active = document.activeElement;
    if (active && active !== document.body && active !== previous) return;
    const target = isPanelVisible ? closeButtonRef.current : restoreButtonRef.current;
    target?.focus({ preventScroll: true });
  }, [canFloat, isSidebarOpen, isPanelVisible]);

  useEffect(() => {
    if (scrollBodyRef.current) scrollBodyRef.current.scrollTop = 0;
  }, [selectedExecutionId]);

  useEffect(() => {
    // The docked drawer closes on Escape from anywhere on the page, as before. A floating window
    // is a peer of the list, so it only takes Escape while focus is inside it.
    if (!isSidebarOpen || effectiveMode !== "docked") return;

    const handleEscape = (event: KeyboardEvent) => {
      if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        !event.isComposing &&
        !showCancelConfirm &&
        !document.querySelector('[role="dialog"], [role="alertdialog"]')
      ) {
        handleCloseSidebar();
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isSidebarOpen, effectiveMode, showCancelConfirm, handleCloseSidebar]);

  // Chip selection change handler
  const handleChipChange = (chipId: string) => {
    handleCloseSidebar();
    setSelectedChip(chipId || null);
    // A day picked for one chip means nothing for another.
    setSelectedDate("latest");
    setCurrentPage(1);
  };

  // Wrap date setter to reset page
  const handleDateChange = (date: string) => {
    handleCloseSidebar();
    setSelectedDate(date);
    setCurrentPage(1);
  };

  if (isLoading) return <ExecutionPageSkeleton />;
  if (isError) {
    return (
      <PageContainer>
        <PageHeader title="Execution" description="Workflow runs and their task results" />
        <div role="alert" className="alert alert-error">
          <AlertCircle className="h-5 w-5" />
          <span>Execution history could not be loaded. Please try again.</span>
        </div>
      </PageContainer>
    );
  }

  // Generate unique key for execution
  const getExecutionKey = (execution: ExecutionResponseSummary) => `${execution.execution_id}`;

  const handleCardClick = (execution: ExecutionResponseSummary) => {
    if (isMinimized) {
      // Picking another run brings the window back; focus stays on the list.
      handleRestore(null);
    } else if (!isSidebarOpen && isFloating) {
      pendingPanelMotion.current = { target: "panel", from: null };
    }
    setSelectedExecutionId(execution.execution_id);
    setIsSidebarOpen(true);
    setExpandedTaskIndex(null);
  };

  const handleCancel = () => {
    const flowRunId = executionDetailData?.data?.note?.flow_run_id as string | undefined;
    if (!flowRunId) return;
    cancelMutation.mutate(
      { flowRunId },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListExecutionsQueryKey() });
          if (selectedExecutionId) {
            queryClient.invalidateQueries({
              queryKey: getGetExecutionQueryKey(selectedExecutionId),
            });
          }
          toast.success("Cancellation requested successfully");
          setShowCancelConfirm(false);
        },
        onError: (error) => {
          toast.error(getApiErrorMessage(error, "Failed to cancel execution"));
          setShowCancelConfirm(false);
        },
      },
    );
  };

  // Toggle task expansion on click
  const handleTaskClick = (index: number) => {
    setExpandedTaskIndex(expandedTaskIndex === index ? null : index);
  };

  // Get border color based on status
  const getStatusBorderStyle = (status: string) => {
    switch (status) {
      case "running":
        return "border-l-4 border-l-info";
      case "completed":
        return "border-l-4 border-l-success";
      case "scheduled":
        return "border-l-4 border-l-warning";
      case "failed":
        return "border-l-4 border-l-error";
      case "cancelled":
      case "cancelling":
        return "border-l-4 border-l-neutral";
      default:
        return "border-l-4 border-l-base-300";
    }
  };

  const handlePanelKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (
      !isFloating ||
      event.key !== "Escape" ||
      event.defaultPrevented ||
      event.nativeEvent.isComposing ||
      showCancelConfirm ||
      // Escape inside a nested dialog (a figure preview) belongs to that dialog.
      (event.target as Element).closest?.('[role="dialog"], [role="alertdialog"]')
    ) {
      return;
    }
    event.preventDefault();
    handleCloseSidebar();
  };

  const handleMoveKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "Home") {
      event.preventDefault();
      windowGeometry.reset();
      return;
    }
    const delta = arrowKeyDelta(event);
    if (!delta) return;
    event.preventDefault();
    windowGeometry.moveBy(delta.dx, delta.dy);
  };

  const handleResizeKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    const delta = arrowKeyDelta(event);
    if (!delta) return;
    event.preventDefault();
    windowGeometry.resizeBy(delta.dx, delta.dy);
  };

  const moveHandlers = windowGeometry.pointerHandlers("move");
  const headerDragHandlers = isFloating
    ? {
        ...moveHandlers,
        onPointerDown: (event: React.PointerEvent<HTMLElement>) => {
          // The header drags the window, except from its other controls.
          const control = (event.target as Element).closest("button, a");
          if (control && !control.hasAttribute("data-window-move-handle")) return;
          moveHandlers.onPointerDown(event);
        },
      }
    : {};

  const floatingRect = isFloating || isMinimized ? windowGeometry.rect : null;
  const asideClassName =
    effectiveMode === "docked"
      ? `fixed right-0 top-0 z-50 flex h-full w-full flex-col border-l border-base-300 bg-base-100 shadow-xl transition-transform duration-300 sm:w-3/4 lg:w-2/5 ${isSidebarOpen ? "translate-x-0" : "translate-x-full"}`
      : // No CSS transition here: pointer moves must land immediately.
        `fixed z-50 flex flex-col overflow-hidden rounded-box border border-base-300 bg-base-100 shadow-xl ${isPanelVisible ? "" : "invisible"}`;

  const hasMorePages =
    !!executionData?.data?.executions && executionData.data.executions.length >= itemsPerPage;

  const total = executionData?.data?.total;
  const totalPages = total != null ? Math.max(1, Math.ceil(total / itemsPerPage)) : undefined;
  const shouldShowPagination = currentPage > 1 || hasMorePages || (totalPages ?? 1) > 1;

  return (
    <PageContainer>
      <PageHeader title="Execution" description="Workflow runs and their task results" />
      <PageFiltersBar className="mb-4 sm:mb-6">
        <PageFiltersBar.Group>
          <PageFiltersBar.Item className="sm:w-64">
            <ChipSelector selectedChip={selectedChip || ""} onChipSelect={handleChipChange} />
          </PageFiltersBar.Item>
          <PageFiltersBar.Item className="sm:w-44">
            <DateSelector
              chipId={selectedChip || ""}
              selectedDate={selectedDate}
              onDateSelect={handleDateChange}
              disabled={!selectedChip}
            />
          </PageFiltersBar.Item>
        </PageFiltersBar.Group>
      </PageFiltersBar>
      <ExecutionActivityChart
        chipId={selectedChip || ""}
        days={activityDays}
        onDaysChange={setActivityDays}
        selectedDate={selectedDate}
        onDateSelect={handleDateChange}
      />
      <section aria-labelledby="recent-executions-heading">
        <div className="mb-3">
          <h2
            ref={executionListHeading}
            tabIndex={-1}
            id="recent-executions-heading"
            className="text-sm font-medium"
          >
            Recent executions
          </h2>
          <p className="text-sm text-base-content/60">
            {total != null
              ? `${total} execution${total === 1 ? "" : "s"}`
              : `${cardData.length} shown`}
          </p>
        </div>
        {cardData.length === 0 && (
          <div className="rounded-box border border-dashed border-base-300 bg-base-100 px-6 py-12 text-center">
            <h3 className="font-medium">No executions found</h3>
            <p className="mt-1 text-sm text-base-content/60">
              Try another chip or date to view execution history.
            </p>
          </div>
        )}
        <div className="grid grid-cols-1 gap-2">
          {cardData.map((execution) => {
            const executionKey = getExecutionKey(execution);
            const isSelected = selectedExecutionId === execution.execution_id;
            const statusBorderStyle = getStatusBorderStyle(execution.status);
            const StatusIcon = getStatusIcon(execution.status);

            return (
              <div
                key={executionKey}
                ref={(element) => {
                  if (element) executionCards.current.set(execution.execution_id, element);
                  else executionCards.current.delete(execution.execution_id);
                }}
                role="button"
                aria-expanded={isSelected && isPanelVisible}
                aria-controls="execution-details-panel"
                tabIndex={0}
                aria-label={`View ${execution.name} execution details`}
                className={`relative flex cursor-pointer overflow-hidden rounded-box border border-base-200 bg-base-100 p-3 shadow-sm transition-colors hover:border-primary/40 hover:bg-base-200/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary sm:p-4 ${statusBorderStyle}`}
                onClick={() => handleCardClick(execution)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleCardClick(execution);
                  }
                }}
              >
                {isSelected && (
                  <div className="absolute inset-0 bg-primary opacity-10 pointer-events-none transition-opacity duration-500" />
                )}
                <div className="relative z-10 w-full">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="truncate text-sm font-medium">{execution.name}</h3>
                    <span
                      className={`badge badge-sm flex-shrink-0 gap-1 ${getStatusBadgeClass(execution.status)}`}
                    >
                      <StatusIcon className="h-4 w-4" aria-hidden="true" />
                      {getStatusLabel(execution.status)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-2 sm:gap-x-3 gap-y-0.5 mt-0.5 sm:mt-1 text-sm text-base-content/60">
                    <span>{formatDateTime(execution.start_at)}</span>
                    {execution.elapsed_time && (
                      <span className="hidden sm:inline">Duration: {execution.elapsed_time}</span>
                    )}
                    {execution.elapsed_time && (
                      <span className="sm:hidden">{execution.elapsed_time}</span>
                    )}
                    <span className="inline-flex items-center gap-1 min-w-0">
                      <UserRound className="h-3 w-3 flex-shrink-0" />
                      <span className="truncate">{formatActorLabel(execution)}</span>
                    </span>
                  </div>
                  {execution.status === "failed" && execution.message && (
                    <p className="mt-2 line-clamp-2 text-xs text-error">{execution.message}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {shouldShowPagination && (
          <PaginationControls
            currentPage={currentPage}
            setCurrentPage={(page) => {
              handleCloseSidebar();
              setCurrentPage(page);
            }}
            hasMore={hasMorePages}
            totalPages={totalPages}
          />
        )}
      </section>
      <aside
        id="execution-details-panel"
        ref={sidebarRef}
        inert={!isPanelVisible}
        aria-label="Execution details"
        aria-hidden={!isPanelVisible}
        data-mode={effectiveMode}
        className={asideClassName}
        style={
          floatingRect
            ? {
                left: floatingRect.x,
                top: floatingRect.y,
                width: floatingRect.width,
                height: floatingRect.height,
              }
            : undefined
        }
        onKeyDown={handlePanelKeyDown}
      >
        <div
          className={`flex shrink-0 items-center gap-1 border-b border-base-300 px-3 py-2 sm:px-4 ${
            isFloating
              ? `touch-none select-none ${
                  windowGeometry.interaction === "move" ? "cursor-grabbing" : "cursor-grab"
                }`
              : ""
          }`}
          {...headerDragHandlers}
        >
          {isFloating && (
            <button
              type="button"
              data-window-move-handle=""
              className="btn btn-ghost btn-xs btn-square cursor-grab"
              aria-label="Move execution details window"
              aria-describedby="execution-window-move-hint"
              onKeyDown={handleMoveKeyDown}
            >
              <GripHorizontal className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
          <p className="min-w-0 flex-1 truncate text-xs font-medium text-base-content/60">
            {isFloating && selectedExecutionName ? selectedExecutionName : "Execution details"}
          </p>
          {canFloat &&
            (isFloating ? (
              <>
                <button
                  ref={dockButtonRef}
                  type="button"
                  className="btn btn-ghost btn-sm"
                  aria-label="Dock execution details"
                  title="Dock to the right edge"
                  onClick={handleDock}
                >
                  <PanelRight className="h-4 w-4" aria-hidden="true" />
                  Dock
                </button>
                <button
                  ref={minimizeButtonRef}
                  type="button"
                  className="btn btn-ghost btn-sm btn-square"
                  aria-label="Minimize execution details"
                  title="Minimize"
                  onClick={handleMinimize}
                >
                  <Minus className="h-4 w-4" aria-hidden="true" />
                </button>
              </>
            ) : (
              <button
                ref={floatButtonRef}
                type="button"
                className="btn btn-ghost btn-sm"
                aria-label="Float execution details"
                title="Float as a movable window"
                onClick={handleFloat}
              >
                <AppWindow className="h-4 w-4" aria-hidden="true" />
                Float
              </button>
            ))}
          <button
            ref={closeButtonRef}
            type="button"
            onClick={handleCloseSidebar}
            className="btn btn-ghost btn-sm btn-square"
            aria-label="Close execution details"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div
          ref={scrollBodyRef}
          data-testid="execution-details-scroll"
          className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6"
        >
          {selectedExecutionId && (
            <div>
              <nav aria-label="Browse executions" className="mb-4 flex items-center gap-2">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  aria-label="Previous execution"
                  disabled={selectedExecutionIndex <= 0}
                  onClick={() => handleCardClick(cardData[selectedExecutionIndex - 1])}
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                  Previous
                </button>
                <span className="text-xs text-base-content/60" role="status">
                  {selectedExecutionIndex >= 0
                    ? `${selectedExecutionIndex + 1} of ${cardData.length} on this page`
                    : "Outside current results"}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  aria-label="Next execution"
                  disabled={
                    selectedExecutionIndex < 0 || selectedExecutionIndex >= cardData.length - 1
                  }
                  onClick={() => handleCardClick(cardData[selectedExecutionIndex + 1])}
                >
                  Next
                  <ChevronRight className="h-4 w-4" aria-hidden="true" />
                </button>
              </nav>
              <div className="p-2 sm:p-4 bg-base-100 mb-4 sm:mb-6">
                <h2 className="text-sm font-medium">{selectedExecutionName}</h2>
                {executionDetailData?.data && (
                  <ExecutionRunSummary
                    status={executionDetailData.data.status}
                    tasks={executionDetailData.data.task ?? []}
                    className="mt-3"
                  />
                )}
                <div className="mt-3 sm:mt-4 flex flex-wrap gap-2">
                  <Link
                    href={`/execution/${selectedChip || ""}/${selectedExecutionId}`}
                    className="btn btn-primary btn-sm sm:btn-md"
                  >
                    <ExternalLink className="w-3 h-3 sm:w-4 sm:h-4" />
                    View Details
                  </Link>
                  {(() => {
                    const selectedExec = cardData.find(
                      (exec) => getExecutionKey(exec) === selectedExecutionId,
                    );
                    const detailFlowRunId = executionDetailData?.data?.note?.flow_run_id as
                      | string
                      | undefined;
                    const isCancellable =
                      !!detailFlowRunId && isExecutionCancellable(selectedExec?.status);
                    return (
                      isCancellable && (
                        <button
                          onClick={() => setShowCancelConfirm(true)}
                          disabled={cancelMutation.isPending}
                          className="btn btn-error btn-sm sm:btn-md"
                        >
                          <StopCircle className="w-3 h-3 sm:w-4 sm:h-4" />
                          {cancelMutation.isPending ? "Cancelling..." : "Cancel"}
                        </button>
                      )
                    );
                  })()}
                </div>
              </div>
              <div>
                <h3 className="mb-3 text-xs font-medium text-base-content/60 sm:mb-4">
                  Execution Details
                </h3>
                {isDetailLoading && (
                  <div role="status" className="flex items-center gap-2 py-4 text-base-content/60">
                    <span className="loading loading-spinner loading-sm" aria-hidden="true" />
                    Loading details...
                  </div>
                )}
                {isDetailError && <div>Error loading details.</div>}
                {executionDetailData?.data.status === "failed" && selectedExecutionId && (
                  // This panel is already a right-hand drawer, so the investigation
                  // opens in the floating window instead of a second docked sidebar.
                  <TaskMessagePanel
                    status="failed"
                    message={executionDetailData.data.message}
                    showEmptyFallback
                    className="mb-4"
                    action={
                      <InvestigateWithAiButton
                        target={{
                          executionId: selectedExecutionId,
                          chipId: executionDetailData.data.chip_id || null,
                        }}
                        surface="mini"
                      />
                    }
                  />
                )}
                {executionDetailData &&
                  executionDetailData.data.task &&
                  executionDetailData.data.task.map((detailTask, idx) => {
                    const taskBorderStyle = getStatusBorderStyle(detailTask.status ?? "unknown");
                    const taskStatus = getTaskStatusDisplay(detailTask.status);
                    const isTaskExpanded = expandedTaskIndex === idx;

                    return (
                      <div
                        key={idx}
                        className={`mb-2 sm:mb-3 p-2 sm:p-3 rounded-box border cursor-pointer transition-colors ${
                          isTaskExpanded
                            ? "border-primary/40 bg-primary/5"
                            : "border-base-content/10 bg-base-100 hover:bg-base-200/50"
                        } ${taskBorderStyle}`}
                        onClick={() => handleTaskClick(idx)}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="text-sm font-medium text-left truncate flex-1">
                            {detailTask.task_id ? (
                              <Link
                                href={`/task-results/${detailTask.task_id}`}
                                className="hover:text-primary inline-flex items-center gap-1"
                                onClick={(e) => e.stopPropagation()}
                              >
                                {detailTask.qid
                                  ? `${detailTask.qid}-${detailTask.name}`
                                  : detailTask.name}
                                <ArrowUpRight className="w-3 h-3 sm:w-4 sm:h-4 flex-shrink-0 opacity-50" />
                              </Link>
                            ) : detailTask.qid ? (
                              `${detailTask.qid}-${detailTask.name}`
                            ) : (
                              detailTask.name
                            )}
                          </h4>
                          <span
                            className={`inline-flex items-center gap-1 text-sm font-medium flex-shrink-0 ${taskStatus.textClass}`}
                          >
                            <taskStatus.Icon className="h-4 w-4" aria-hidden="true" />
                            {taskStatus.label}
                          </span>
                        </div>
                        <div className="text-sm text-base-content/60 mt-1">
                          <span>
                            {detailTask.start_at ? formatDateTime(detailTask.start_at) : "N/A"}
                          </span>
                          {detailTask.elapsed_time && (
                            <span className="ml-2 sm:ml-3">{detailTask.elapsed_time}</span>
                          )}
                          <span className="ml-2 sm:ml-3 inline-flex items-center gap-1">
                            <UserRound className="h-3 w-3" />
                            {formatActorLabel(detailTask)}
                          </span>
                        </div>
                        <ExecutionTaskProgress status={detailTask.status} note={detailTask.note} />
                        {isTaskExpanded && (
                          <div className="mt-2 sm:mt-3 space-y-2 sm:space-y-3">
                            {Array.isArray(detailTask.figure_path) &&
                            detailTask.figure_path.length > 0 ? (
                              detailTask.figure_path.map((path, i) => (
                                <div key={i}>
                                  <h5 className="text-sm font-medium mb-1 text-left">
                                    Figure {i + 1}
                                  </h5>
                                  <TaskFigure
                                    path={path}
                                    qid={detailTask.qid || ""}
                                    className="w-full h-auto max-h-[50vh] sm:max-h-[60vh] object-contain rounded border"
                                  />
                                </div>
                              ))
                            ) : detailTask.figure_path ? (
                              <div>
                                <h5 className="text-sm font-medium mb-1 text-left">Figure</h5>
                                <TaskFigure
                                  path={detailTask.figure_path}
                                  qid={detailTask.qid || ""}
                                  className="w-full h-auto max-h-[50vh] sm:max-h-[60vh] object-contain rounded border"
                                />
                              </div>
                            ) : (
                              <p className="text-sm text-base-content/50 italic">
                                No figure available
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
        {isFloating && (
          <>
            <span id="execution-window-move-hint" className="sr-only">
              Arrow keys move the window, Shift moves farther, Home resets its position
            </span>
            <span id="execution-window-resize-hint" className="sr-only">
              Arrow keys resize the window, Shift resizes farther
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-square absolute bottom-0.5 right-0.5 cursor-nwse-resize touch-none bg-base-100/80"
              aria-label="Resize execution details window"
              aria-describedby="execution-window-resize-hint"
              {...windowGeometry.pointerHandlers("resize")}
              onKeyDown={handleResizeKeyDown}
            >
              <MoveDiagonal2 className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </>
        )}
      </aside>
      {isSidebarOpen && isMinimized && (
        <div
          ref={restoreControlRef}
          role="region"
          aria-label="Minimized execution details"
          className="fixed bottom-4 right-4 z-50 flex max-w-xs items-center gap-1 rounded-box border border-base-300 bg-base-100 p-1 shadow-lg"
        >
          <button
            ref={restoreButtonRef}
            type="button"
            className="btn btn-ghost btn-sm min-w-0 justify-start"
            aria-label={`Restore execution details for ${selectedExecutionName ?? "the selected execution"}`}
            onClick={() => handleRestore()}
          >
            <AppWindow className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="truncate">{selectedExecutionName ?? "Execution details"}</span>
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-square"
            aria-label="Close execution details"
            onClick={handleCloseSidebar}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      )}
      <CancelExecutionModal
        isOpen={showCancelConfirm}
        isPending={cancelMutation.isPending}
        onConfirm={handleCancel}
        onClose={() => setShowCancelConfirm(false)}
      />
    </PageContainer>
  );
}
