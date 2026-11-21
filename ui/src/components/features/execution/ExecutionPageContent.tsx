"use client";

import { useState, useEffect, useMemo, useRef, useCallback } from "react";

import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  StopCircle,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";

import { isExecutionCancellable } from "@/lib/executionStatus";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { DEFAULT_TIMEZONE, formatDateTime } from "@/lib/utils/datetime";

import { AgentSessionGroupRow } from "./AgentSessionGroupRow";
import { pluralize } from "./agentSessionDisplay";
import {
  type ActivityWindow,
  DEFAULT_ACTIVITY_WINDOW,
  ExecutionActivityChart,
} from "./ExecutionActivityChart";
import { ExecutionAgentSessionNotice } from "./ExecutionAgentSessionNotice";
import {
  ExecutionListCard,
  formatActorLabel,
  getStatusBorderStyle,
  getStatusIcon,
} from "./ExecutionListCard";

import type { ExecutionResponseSummary } from "@/schemas";

import { useListChips } from "@/client/chip/chip";
import {
  useListExecutions,
  useListExecutionGroups,
  useGetExecution,
  useCancelExecution,
  getListExecutionsQueryKey,
  getListExecutionGroupsQueryKey,
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

  // Add date state for navigation
  const [selectedDate, setSelectedDate] = useState<string>("latest");

  const { projectId } = useProject();
  // Agent sessions are grouped on the server; the flat list stays available.
  const [groupSessions, setGroupSessions] = useState(true);
  const [expandedSessions, setExpandedSessions] = useState<ReadonlySet<string>>(new Set());
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

  const listParams = {
    chip_id: selectedChip || "",
    skip: (currentPage - 1) * itemsPerPage,
    limit: itemsPerPage,
    // A picked day is filtered on the server, so every run of that day is reachable,
    // not only those on the first page. The day follows the UI's display time zone.
    ...(selectedDate === "latest" ? {} : { date: selectedDate, timezone: DEFAULT_TIMEZONE }),
  };

  // Fetch execution summary list by chip_id
  const flatList = useListExecutions(listParams, {
    query: {
      // Refresh every 5 seconds
      refetchInterval: 5000,
      // Keep polling even when the window is in the background
      refetchIntervalInBackground: true,
      enabled: !!selectedChip && !groupSessions,
    },
  });
  // Rows with each agent session grouped; the key and header pin the project the page shows.
  const groupedList = useListExecutionGroups(listParams, {
    query: {
      queryKey: [...getListExecutionGroupsQueryKey(listParams), projectId],
      refetchInterval: 5000,
      refetchIntervalInBackground: true,
      enabled: !!selectedChip && groupSessions && projectId !== null,
    },
    request: projectId ? { headers: { "X-Project-Id": projectId } } : undefined,
  });
  const activeList = groupSessions ? groupedList : flatList;
  const { isError, isLoading } = activeList;
  const executionData = flatList.data;
  const groupData = groupedList.data?.data;

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

  // The executions on screen, in list order: the panel browses these.
  const cardData = useMemo<ExecutionResponseSummary[]>(() => {
    if (!groupSessions) return executionData?.data?.executions ?? [];
    return (groupData?.items ?? []).flatMap((item) => {
      if (item.kind === "execution") return item.execution ? [item.execution] : [];
      const sessionId = item.agent_session?.session_id;
      return sessionId && expandedSessions.has(sessionId)
        ? (item.children ?? []).map((child) => child.execution)
        : [];
    });
  }, [executionData, expandedSessions, groupData, groupSessions]);

  const selectedExecutionIndex = cardData.findIndex(
    (execution) => execution.execution_id === selectedExecutionId,
  );

  const handleCloseSidebar = useCallback(() => {
    if (selectedExecutionId) pendingFocusRestore.current = selectedExecutionId;
    if (sidebarRef.current) sidebarRef.current.scrollTop = 0;
    setIsSidebarOpen(false);
    setSelectedExecutionId(null);
    setExpandedTaskIndex(null);
  }, [selectedExecutionId]);

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

  useEffect(() => {
    if (sidebarRef.current) sidebarRef.current.scrollTop = 0;
  }, [selectedExecutionId]);

  useEffect(() => {
    if (!isSidebarOpen) return;

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
  }, [isSidebarOpen, showCancelConfirm, handleCloseSidebar]);

  // A project switch shows another project's records: drop what this one had open.
  const shownProject = useRef(projectId);
  useEffect(() => {
    if (shownProject.current === projectId) return;
    shownProject.current = projectId;
    pendingFocusRestore.current = null;
    setIsSidebarOpen(false);
    setSelectedExecutionId(null);
    setExpandedTaskIndex(null);
    setExpandedSessions(new Set());
    setCurrentPage(1);
  }, [projectId]);

  const toggleSession = (sessionId: string) => {
    setExpandedSessions((current) => {
      const next = new Set(current);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  };

  const handleGroupingChange = (grouped: boolean) => {
    handleCloseSidebar();
    setGroupSessions(grouped);
    setExpandedSessions(new Set());
    setCurrentPage(1);
  };

  // Chip selection change handler
  const handleChipChange = (chipId: string) => {
    handleCloseSidebar();
    setExpandedSessions(new Set());
    setSelectedChip(chipId || null);
    // A day picked for one chip means nothing for another.
    setSelectedDate("latest");
    setCurrentPage(1);
  };

  // Wrap date setter to reset page
  const handleDateChange = (date: string) => {
    handleCloseSidebar();
    setExpandedSessions(new Set());
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

  const registerCard = (executionId: string, element: HTMLDivElement | null) => {
    if (element) executionCards.current.set(executionId, element);
    else executionCards.current.delete(executionId);
  };

  const handleCardClick = (execution: ExecutionResponseSummary) => {
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
          queryClient.invalidateQueries({ queryKey: getListExecutionGroupsQueryKey() });
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

  const pageRows = groupSessions
    ? (groupData?.items.length ?? 0)
    : (executionData?.data?.executions.length ?? 0);
  const hasMorePages = pageRows >= itemsPerPage;

  const total = groupSessions ? groupData?.total : executionData?.data?.total;
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
        <PageFiltersBar.Group>
          <PageFiltersBar.Item>
            <label className="choice-field gap-2 text-sm">
              <input
                type="checkbox"
                className="toggle toggle-sm"
                checked={groupSessions}
                onChange={(event) => handleGroupingChange(event.target.checked)}
              />
              <span>Group agent sessions</span>
            </label>
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
            {groupSessions && groupData
              ? groupData.agent_sessions > 0
                ? `${pluralize(groupData.total_executions, "execution")}, ${groupData.grouped_executions} of them in ${pluralize(groupData.agent_sessions, "agent session")}; ${pluralize(groupData.total, "row")}`
                : pluralize(groupData.total_executions, "execution")
              : total != null
                ? `${total} execution${total === 1 ? "" : "s"}`
                : `${cardData.length} shown`}
          </p>
        </div>
        {pageRows === 0 && (
          <div className="rounded-box border border-dashed border-base-300 bg-base-100 px-6 py-12 text-center">
            <h3 className="font-medium">No executions found</h3>
            <p className="mt-1 text-sm text-base-content/60">
              Try another chip or date to view execution history.
            </p>
          </div>
        )}
        <div className="grid grid-cols-1 gap-2">
          {groupSessions
            ? (groupData?.items ?? []).map((item) =>
                item.kind === "agent_session" && item.agent_session ? (
                  <AgentSessionGroupRow
                    key={`session:${item.agent_session.session_id}`}
                    item={item}
                    projectId={projectId}
                    isExpanded={expandedSessions.has(item.agent_session.session_id)}
                    onToggle={toggleSession}
                    selectedExecutionId={selectedExecutionId}
                    isPanelOpen={isSidebarOpen}
                    onOpenExecution={handleCardClick}
                    registerCard={registerCard}
                    hasDayFilter={selectedDate !== "latest"}
                  />
                ) : item.execution ? (
                  <ExecutionListCard
                    key={getExecutionKey(item.execution)}
                    execution={item.execution}
                    isSelected={selectedExecutionId === item.execution.execution_id}
                    isPanelOpen={isSidebarOpen}
                    onOpen={handleCardClick}
                    registerCard={registerCard}
                  />
                ) : null,
              )
            : cardData.map((execution) => (
                <ExecutionListCard
                  key={getExecutionKey(execution)}
                  execution={execution}
                  isSelected={selectedExecutionId === execution.execution_id}
                  isPanelOpen={isSidebarOpen}
                  onOpen={handleCardClick}
                  registerCard={registerCard}
                />
              ))}
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
        inert={!isSidebarOpen}
        aria-label="Execution details"
        aria-hidden={!isSidebarOpen}
        className={`fixed right-0 top-0 z-50 h-full w-full overflow-y-auto border-l border-base-300 bg-base-100 p-4 shadow-xl transition-transform duration-300 sm:w-3/4 sm:p-6 lg:w-2/5 ${isSidebarOpen ? "translate-x-0" : "translate-x-full"}`}
      >
        <button
          ref={closeButtonRef}
          onClick={handleCloseSidebar}
          className="btn btn-ghost btn-sm btn-circle absolute top-3 right-3 z-10 sm:top-4 sm:right-4"
          aria-label="Close execution details"
        >
          <X className="h-4 w-4" />
        </button>
        {selectedExecutionId && (
          <div>
            <nav aria-label="Browse executions" className="mb-4 flex items-center gap-2 pr-10">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                aria-label="Previous execution"
                disabled={selectedExecutionIndex <= 0}
                onClick={() => handleCardClick(cardData[selectedExecutionIndex - 1])}
              >
                <ChevronLeft data-icon="inline-start" aria-hidden="true" />
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
                <ChevronRight data-icon="inline-end" aria-hidden="true" />
              </button>
            </nav>
            <div className="p-2 sm:p-4 bg-base-100 mb-4 sm:mb-6">
              <h2 className="text-sm font-medium pr-8">
                {cardData.find((exec) => getExecutionKey(exec) === selectedExecutionId)?.name ??
                  executionDetailData?.data?.name}
              </h2>
              <ExecutionAgentSessionNotice
                link={executionDetailData?.data?.agent_session}
                chipId={executionDetailData?.data?.chip_id || selectedChip || ""}
                className="mt-3"
              />
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
                  <ExternalLink data-icon="inline-start" />
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
                    !!detailFlowRunId &&
                    isExecutionCancellable(
                      selectedExec?.status ?? executionDetailData?.data?.status,
                    );
                  return (
                    isCancellable && (
                      <button
                        onClick={() => setShowCancelConfirm(true)}
                        disabled={cancelMutation.isPending}
                        className="btn btn-error btn-sm sm:btn-md"
                      >
                        <StopCircle data-icon="inline-start" />
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
      </aside>
      <CancelExecutionModal
        isOpen={showCancelConfirm}
        isPending={cancelMutation.isPending}
        onConfirm={handleCancel}
        onClose={() => setShowCancelConfirm(false)}
      />
    </PageContainer>
  );
}
