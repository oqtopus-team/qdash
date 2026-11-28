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
import {
  type ExecutionListContext,
  type SessionReturnContext,
  executionDetailHref,
} from "@/lib/executionArea";
import { DEFAULT_TIMEZONE, formatDateTime } from "@/lib/utils/datetime";

import { AgentSessionGroupRow } from "./AgentSessionGroupRow";
import {
  CalibrationSessionGroupRow,
  calibrationRowExecutions,
  calibrationRowKey,
} from "./CalibrationSessionGroupRow";
import { pluralize } from "./agentSessionDisplay";
import {
  type ActivityWindow,
  DEFAULT_ACTIVITY_WINDOW,
  ExecutionActivityChart,
} from "./ExecutionActivityChart";
import { ExecutionAgentSessionNotice } from "./ExecutionAgentSessionNotice";
import { ExecutionViewSwitch } from "./ExecutionAreaNav";
import { ExecutionCalibrationNotice } from "./ExecutionCalibrationContext";
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
import { TransformStepOutcome } from "@/components/features/execution/TransformStepOutcome";
import { isTransformExecution } from "@/lib/transformStep";
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
  onPageChange,
  hasMore,
  totalPages,
}: {
  currentPage: number;
  onPageChange: (page: number) => void;
  hasMore: boolean;
  totalPages?: number;
}) {
  const isNextDisabled = totalPages !== undefined ? currentPage >= totalPages : !hasMore;
  const pageLabel =
    totalPages !== undefined ? `Page ${currentPage} of ${totalPages}` : `Page ${currentPage}`;

  return (
    <div className="flex justify-center items-center gap-2 sm:gap-4 my-3 sm:my-4 px-4">
      <button
        onClick={() => onPageChange(Math.max(1, currentPage - 1))}
        disabled={currentPage === 1}
        className="btn btn-xs sm:btn-sm btn-outline"
      >
        Prev
      </button>
      <span className="text-sm">{pageLabel}</span>
      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={isNextDisabled}
        className="btn btn-xs sm:btn-sm btn-outline"
      >
        Next
      </button>
    </div>
  );
}

/** "2 calibration sessions and 1 agent session", naming only the kinds present. */
function groupedLabel(calibrationSessions: number, agentSessions: number): string {
  const parts = [
    calibrationSessions > 0 ? pluralize(calibrationSessions, "calibration session") : "",
    agentSessions > 0 ? pluralize(agentSessions, "agent session") : "",
  ].filter(Boolean);
  return parts.join(" and ") || "sessions";
}

/**
 * Execution history page listing workflow runs with task results and cancellation controls
 */
export function ExecutionPageContent() {
  const queryClient = useQueryClient();

  // The chip, day, grouping and page live in the URL, so Back and links back restore them.
  // Calibration and agent sessions are grouped on the server; the flat list stays available.
  const {
    selectedChip,
    setSelectedChip,
    selectedDate,
    groupSessions,
    page: currentPage,
    changeChip,
    changeDate,
    changeGrouping,
    setPage,
    resetForProject,
    isInitialized,
  } = useExecutionUrlState();

  const { projectId } = useProject();
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

  const itemsPerPage = 20;

  // Use custom hook for date navigation (unused but kept for potential future use)
  useDateNavigation(selectedChip || "", selectedDate, changeDate);

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

  // Set when a project switch cleared the chip: the old chip's day and page go with it.
  const projectSwitched = useRef(false);

  // Set the latest chip as default when chips are loaded and no chip is selected from URL
  useEffect(() => {
    if (isInitialized && !selectedChip && sortedChips.length > 0) {
      const chipId = sortedChips[0].chip_id;
      // One URL update for the chip and the reset, so neither overwrites the other.
      if (projectSwitched.current) resetForProject(chipId);
      else setSelectedChip(chipId);
      projectSwitched.current = false;
    }
  }, [isInitialized, selectedChip, sortedChips, setSelectedChip, resetForProject]);

  const listParams = {
    chip_id: selectedChip || "",
    skip: (currentPage - 1) * itemsPerPage,
    limit: itemsPerPage,
    // A picked day is filtered on the server, so every run of that day is reachable,
    // not only those on the first page. The day follows the UI's display time zone.
    ...(selectedDate === "latest" ? {} : { date: selectedDate, timezone: DEFAULT_TIMEZONE }),
  };

  // The list is read only for a chip of the open project. Around a project switch, or on Back
  // to another project's entry, the chip and the project briefly disagree; asking then would
  // show one project's chip under another, so the list waits for the project's chips.
  const chipsLoaded = !!chipsData?.data?.chips;
  const chipInProject = !!selectedChip && sortedChips.some((chip) => chip.chip_id === selectedChip);

  // Fetch execution summary list by chip_id; like the grouped list, the key and header pin the
  // project the page shows, so a refetch during a project switch stays in its own project.
  const flatList = useListExecutions(listParams, {
    query: {
      queryKey: [...getListExecutionsQueryKey(listParams), projectId],
      // Refresh every 5 seconds
      refetchInterval: 5000,
      // Keep polling even when the window is in the background
      refetchIntervalInBackground: true,
      enabled: chipInProject && !groupSessions && projectId !== null,
    },
    request: projectId ? { headers: { "X-Project-Id": projectId } } : undefined,
  });
  // Rows with each agent session grouped; the key and header pin the project the page shows.
  const groupedList = useListExecutionGroups(listParams, {
    query: {
      queryKey: [...getListExecutionGroupsQueryKey(listParams), projectId],
      refetchInterval: 5000,
      refetchIntervalInBackground: true,
      enabled: chipInProject && groupSessions && projectId !== null,
    },
    request: projectId ? { headers: { "X-Project-Id": projectId } } : undefined,
  });
  const activeList = groupSessions ? groupedList : flatList;
  const { isError } = activeList;
  const isLoading = activeList.isLoading || (!!selectedChip && !chipsLoaded);
  // Rows of another project's chip are never shown, even when an earlier answer is cached.
  const executionData = chipInProject ? flatList.data : undefined;
  const groupData = chipInProject ? groupedList.data?.data : undefined;
  const listTotal = groupSessions ? groupData?.total : executionData?.data?.total;

  // A page past the end, as from an old link or a list that shrank, moves to the last page
  // without a history entry.
  // The total is read only from the answer for this page's own request.
  useEffect(() => {
    if (listTotal == null) return;
    const lastPage = Math.max(1, Math.ceil(listTotal / itemsPerPage));
    if (currentPage > lastPage) setPage(lastPage, { replace: true });
  }, [currentPage, listTotal, setPage]);

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
      if (item.kind === "calibration_session") {
        const id = item.calibration_session?.calibration_session_id;
        return id && expandedSessions.has(calibrationRowKey(id))
          ? calibrationRowExecutions(item, expandedSessions)
          : [];
      }
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
    const previous = shownProject.current;
    shownProject.current = projectId;
    pendingFocusRestore.current = null;
    setIsSidebarOpen(false);
    setSelectedExecutionId(null);
    setExpandedTaskIndex(null);
    setExpandedSessions(new Set());
    // Switching project clears the chip from the URL; the old chip's day and page go with it
    // when the new project's default chip is picked. The first project to load, and Back to an
    // entry of another project (which names its own chip), keep the view the URL holds.
    projectSwitched.current =
      previous !== null && !new URLSearchParams(window.location.search).get("chip");
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
    setExpandedSessions(new Set());
    changeGrouping(grouped);
  };

  // Chip selection change handler. A day picked for one chip means nothing for another, so
  // the day and page reset with it.
  const handleChipChange = (chipId: string) => {
    handleCloseSidebar();
    setExpandedSessions(new Set());
    changeChip(chipId || null);
  };

  // A new day starts on its first page.
  const handleDateChange = (date: string) => {
    handleCloseSidebar();
    setExpandedSessions(new Set());
    changeDate(date);
  };

  const handlePageChange = (page: number) => {
    handleCloseSidebar();
    setPage(page);
  };

  if (isLoading) return <ExecutionPageSkeleton />;
  if (isError) {
    return (
      <PageContainer>
        <PageHeader title="Execution" description="Workflow runs and their task results" />
        <ExecutionViewSwitch
          current="executions"
          chipId={selectedChip}
          projectId={projectId}
          className="mb-4"
        />
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

  // A session or execution page opened from this list links back to this same view.
  const listContext: ExecutionListContext = {
    chip: selectedChip,
    date: selectedDate === "latest" ? null : selectedDate,
    flat: !groupSessions,
    page: currentPage,
  };
  const sessionReturn: SessionReturnContext = { from: "executions", list: listContext };

  const pageRows = groupSessions
    ? (groupData?.items.length ?? 0)
    : (executionData?.data?.executions.length ?? 0);
  const hasMorePages = pageRows >= itemsPerPage;

  const total = listTotal;
  const totalPages = total != null ? Math.max(1, Math.ceil(total / itemsPerPage)) : undefined;
  const shouldShowPagination = currentPage > 1 || hasMorePages || (totalPages ?? 1) > 1;

  return (
    <PageContainer>
      <PageHeader title="Execution" description="Workflow runs and their task results" />
      <ExecutionViewSwitch
        current="executions"
        chipId={selectedChip}
        projectId={projectId}
        className="mb-4"
      />
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
              <span>Group sessions</span>
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
              ? groupData.grouped_executions > 0 ||
                groupData.agent_sessions > 0 ||
                (groupData.calibration_sessions ?? 0) > 0
                ? `${pluralize(groupData.total_executions, "execution")}, ${groupData.grouped_executions} of them in ${groupedLabel(groupData.calibration_sessions ?? 0, groupData.agent_sessions)}; ${pluralize(groupData.total, "row")}`
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
                item.kind === "calibration_session" && item.calibration_session ? (
                  <CalibrationSessionGroupRow
                    key={`calibration:${item.calibration_session.calibration_session_id}`}
                    item={item}
                    projectId={projectId}
                    expanded={expandedSessions}
                    onToggle={toggleSession}
                    selectedExecutionId={selectedExecutionId}
                    isPanelOpen={isSidebarOpen}
                    onOpenExecution={handleCardClick}
                    registerCard={registerCard}
                    hasDayFilter={selectedDate !== "latest"}
                    sessionReturn={sessionReturn}
                  />
                ) : item.kind === "agent_session" && item.agent_session ? (
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
                    sessionReturn={sessionReturn}
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
            onPageChange={handlePageChange}
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
              <ExecutionCalibrationNotice
                link={executionDetailData?.data?.calibration_session}
                origin={executionDetailData?.data?.reported_origin}
                projectId={projectId}
                sessionReturn={sessionReturn}
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
                  href={executionDetailHref(
                    selectedChip || "",
                    selectedExecutionId,
                    projectId,
                    listContext,
                  )}
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
              {executionDetailData && isTransformExecution(executionDetailData.data.note) && (
                <TransformStepOutcome
                  note={executionDetailData.data.note}
                  status={executionDetailData.data.status}
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
