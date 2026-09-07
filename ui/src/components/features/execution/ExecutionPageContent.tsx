"use client";

import { useState, useEffect, useMemo } from "react";

import {
  AlertCircle,
  ArrowUpRight,
  BarChart3,
  ChevronDown,
  ExternalLink,
  StopCircle,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";

import { formatDate, formatDateTime } from "@/lib/utils/datetime";

import { ExecutionDurationBreakdown } from "./ExecutionDurationBreakdown";

import type { ExecutionResponseSummary } from "@/schemas";

import { useListChips } from "@/client/chip/chip";
import {
  useListExecutions,
  useGetExecution,
  useCancelExecution,
} from "@/client/execution/execution";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { CancelExecutionModal } from "@/components/features/execution/CancelExecutionModal";
import { ExecutionTaskProgress } from "@/components/features/execution/ExecutionTaskProgress";
import { getCancelErrorMessage } from "@/components/features/execution/getCancelErrorMessage";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { DateSelector } from "@/components/selectors/DateSelector";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { ExecutionPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useToast } from "@/components/ui/Toast";
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
      <span className="text-xs sm:text-sm">{pageLabel}</span>
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
  // URL state management
  const { selectedChip, setSelectedChip, isInitialized } = useExecutionUrlState();

  // Add date state for navigation
  const [selectedDate, setSelectedDate] = useState<string>("latest");

  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [expandedTaskIndex, setExpandedTaskIndex] = useState<number | null>(null);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [showDurationBreakdown, setShowDurationBreakdown] = useState(false);

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
  const cardData = useMemo(() => {
    if (!executionData?.data?.executions) return [];
    if (selectedDate === "latest") return executionData.data.executions;
    return executionData.data.executions.filter((exec) => {
      if (!exec.start_at) return false;
      const execDateStr = formatDate(exec.start_at).replace(/-/g, "");
      return execDateStr === selectedDate;
    });
  }, [executionData, selectedDate]);

  const statusSummary = useMemo(
    () => ({
      total: cardData.length,
      running: cardData.filter((execution) =>
        ["running", "scheduled", "pending"].includes(execution.status),
      ).length,
      failed: cardData.filter((execution) => execution.status === "failed").length,
      completed: cardData.filter((execution) => execution.status === "completed").length,
    }),
    [cardData],
  );

  useEffect(() => {
    if (!isSidebarOpen) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !showCancelConfirm) {
        setIsSidebarOpen(false);
        setSelectedExecutionId(null);
        setExpandedTaskIndex(null);
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isSidebarOpen, showCancelConfirm]);

  // Chip selection change handler
  const handleChipChange = (chipId: string) => {
    setSelectedChip(chipId || null);
    setSelectedExecutionId(null);
    setIsSidebarOpen(false);
    setCurrentPage(1);
  };

  // Wrap date setter to reset page
  const handleDateChange = (date: string) => {
    setSelectedDate(date);
    setCurrentPage(1);
  };

  if (isLoading) return <ExecutionPageSkeleton />;
  if (isError) {
    return (
      <PageContainer>
        <PageHeader
          title="Execution History"
          description="Monitor workflow runs and task results"
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

  const handleCardClick = (execution: ExecutionResponseSummary) => {
    setSelectedExecutionId(execution.execution_id);
    setIsSidebarOpen(true);
    setExpandedTaskIndex(null);
  };

  const handleCloseSidebar = () => {
    setIsSidebarOpen(false);
    setSelectedExecutionId(null);
    setExpandedTaskIndex(null);
  };

  const handleCancel = () => {
    const flowRunId = executionDetailData?.data?.note?.flow_run_id as string | undefined;
    if (!flowRunId) return;
    cancelMutation.mutate(
      { flowRunId },
      {
        onSuccess: () => {
          toast.success("Cancellation requested successfully");
          setShowCancelConfirm(false);
        },
        onError: (error) => {
          toast.error(getCancelErrorMessage(error));
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
        return "border-l-4 border-l-neutral";
      default:
        return "border-l-4 border-l-base-300";
    }
  };

  const hasMorePages =
    !!executionData?.data?.executions && executionData.data.executions.length >= itemsPerPage;

  const total = executionData?.data?.total;
  const totalPages = total != null ? Math.max(1, Math.ceil(total / itemsPerPage)) : undefined;
  const shouldShowPagination = currentPage > 1 || hasMorePages || (totalPages ?? 1) > 1;

  return (
    <PageContainer>
      <PageHeader title="Execution History" description="Monitor workflow runs and task results" />
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
      <section aria-label="Execution status summary" className="mb-4 sm:mb-6">
        <div className="stats stats-horizontal w-full overflow-x-auto border border-base-300 bg-base-100 shadow-sm">
          <div className="stat min-w-28 px-4 py-3 sm:min-w-0">
            <div className="stat-title text-xs">Total</div>
            <div className="stat-value text-2xl">{statusSummary.total}</div>
          </div>
          <div className="stat min-w-28 px-4 py-3 sm:min-w-0">
            <div className="stat-title text-xs">Running</div>
            <div className="stat-value text-2xl text-info">{statusSummary.running}</div>
          </div>
          <div className="stat min-w-28 px-4 py-3 sm:min-w-0">
            <div className="stat-title text-xs">Failed</div>
            <div className="stat-value text-2xl text-error">{statusSummary.failed}</div>
          </div>
          <div className="stat min-w-28 px-4 py-3 sm:min-w-0">
            <div className="stat-title text-xs">Completed</div>
            <div className="stat-value text-2xl text-success">{statusSummary.completed}</div>
          </div>
        </div>
      </section>
      <section className="mb-6" aria-labelledby="duration-breakdown-heading">
        <button
          type="button"
          className="flex w-full items-center gap-3 rounded-box border border-base-300 bg-base-100 px-4 py-3 text-left transition-colors hover:bg-base-200/50"
          aria-expanded={showDurationBreakdown}
          aria-controls="duration-breakdown-content"
          onClick={() => setShowDurationBreakdown((value) => !value)}
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <BarChart3 className="h-5 w-5" />
          </span>
          <span className="min-w-0 flex-1">
            <span id="duration-breakdown-heading" className="block font-semibold">
              Task duration breakdown
            </span>
            <span className="block text-sm text-base-content/60">
              Compare task timing across the current execution set
            </span>
          </span>
          <ChevronDown
            className={`h-5 w-5 shrink-0 transition-transform ${showDurationBreakdown ? "rotate-180" : ""}`}
          />
        </button>
        {showDurationBreakdown && (
          <div id="duration-breakdown-content" className="mt-3">
            <ExecutionDurationBreakdown
              executions={cardData}
              selectedTag={selectedTag}
              onTagSelect={setSelectedTag}
              allItemsHref={`/execution/durations${selectedChip ? `?chip=${encodeURIComponent(selectedChip)}` : ""}`}
            />
          </div>
        )}
      </section>
      <section aria-labelledby="recent-executions-heading">
        <div className="mb-3">
          <h2 id="recent-executions-heading" className="text-lg font-semibold">
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
            <h3 className="font-semibold">No executions found</h3>
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

            return (
              <div
                key={executionKey}
                role="button"
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
                    <h3 className="truncate text-sm font-semibold sm:text-base">
                      {execution.name}
                    </h3>
                    <span
                      className={`badge badge-sm flex-shrink-0 ${getStatusBadgeClass(execution.status)} ${execution.status === "running" ? "status-pulse" : ""}`}
                    >
                      {getStatusLabel(execution.status)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-2 sm:gap-x-3 gap-y-0.5 mt-0.5 sm:mt-1 text-xs sm:text-sm text-base-content/60">
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
            setCurrentPage={setCurrentPage}
            hasMore={hasMorePages}
            totalPages={totalPages}
          />
        )}
      </section>
      <aside
        aria-label="Execution details"
        aria-hidden={!isSidebarOpen}
        className={`fixed right-0 top-0 z-50 h-full w-full overflow-y-auto border-l border-base-300 bg-base-100 p-4 shadow-xl transition-transform duration-300 sm:w-3/4 sm:p-6 lg:w-2/5 ${isSidebarOpen ? "translate-x-0" : "translate-x-full"}`}
      >
        <button
          onClick={handleCloseSidebar}
          className="btn btn-ghost btn-sm btn-circle absolute top-3 right-3 z-10 sm:top-4 sm:right-4"
          aria-label="Close execution details"
        >
          <X className="h-4 w-4" />
        </button>
        {selectedExecutionId && (
          <div>
            <div className="p-2 sm:p-4 bg-base-100 mb-4 sm:mb-6">
              <h2 className="text-lg sm:text-2xl font-bold pr-8">
                {cardData.find((exec) => getExecutionKey(exec) === selectedExecutionId)?.name}
              </h2>
              <div className="mt-3 sm:mt-4 flex flex-wrap gap-2">
                <a
                  href={`/execution/${selectedChip || ""}/${selectedExecutionId}`}
                  className="btn btn-primary btn-sm sm:btn-md"
                >
                  <ExternalLink className="w-3 h-3 sm:w-4 sm:h-4" />
                  View Details
                </a>
                {(() => {
                  const selectedExec = cardData.find(
                    (exec) => getExecutionKey(exec) === selectedExecutionId,
                  );
                  const detailFlowRunId = executionDetailData?.data?.note?.flow_run_id as
                    | string
                    | undefined;
                  const isCancellable =
                    !!detailFlowRunId &&
                    (selectedExec?.status === "running" ||
                      selectedExec?.status === "scheduled" ||
                      selectedExec?.status === "pending");
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
              <h3 className="text-base sm:text-xl font-bold mb-3 sm:mb-4">Execution Details</h3>
              {isDetailLoading && <div>Loading details...</div>}
              {isDetailError && <div>Error loading details.</div>}
              {executionDetailData?.data.status === "failed" &&
                executionDetailData.data.message && (
                  <div className="alert alert-error mb-4 items-start text-sm">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span className="break-words whitespace-pre-wrap">
                      {executionDetailData.data.message}
                    </span>
                  </div>
                )}
              {executionDetailData &&
                executionDetailData.data.task &&
                executionDetailData.data.task.map((detailTask, idx) => {
                  const taskBorderStyle = getStatusBorderStyle(detailTask.status ?? "unknown");

                  return (
                    <div
                      key={idx}
                      className={`mb-2 sm:mb-4 p-2 sm:p-4 rounded-lg shadow-md bg-base-100 cursor-pointer hover:shadow-lg transition-shadow ${taskBorderStyle}`}
                      onClick={() => handleTaskClick(idx)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <h4 className="text-sm sm:text-lg font-semibold text-left truncate flex-1">
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
                          className={`text-xs sm:text-sm font-semibold flex-shrink-0 ${
                            detailTask.status === "running"
                              ? "text-info status-pulse"
                              : detailTask.status === "completed"
                                ? "text-success"
                                : detailTask.status === "scheduled"
                                  ? "text-warning"
                                  : detailTask.status === "cancelled"
                                    ? "text-neutral"
                                    : "text-error"
                          }`}
                        >
                          {detailTask.status === "running"
                            ? "Running"
                            : detailTask.status === "completed"
                              ? "Completed"
                              : detailTask.status === "scheduled"
                                ? "Scheduled"
                                : detailTask.status === "cancelled"
                                  ? "Cancelled"
                                  : "Failed"}
                        </span>
                      </div>
                      <div className="text-xs sm:text-sm text-base-content/60 mt-1">
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
                      {expandedTaskIndex === idx && (
                        <div className="mt-2 sm:mt-3 space-y-2 sm:space-y-3">
                          {Array.isArray(detailTask.figure_path) &&
                          detailTask.figure_path.length > 0 ? (
                            detailTask.figure_path.map((path, i) => (
                              <div key={i}>
                                <h5 className="text-xs sm:text-sm font-semibold mb-1 text-left">
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
                              <h5 className="text-xs sm:text-sm font-semibold mb-1 text-left">
                                Figure
                              </h5>
                              <TaskFigure
                                path={detailTask.figure_path}
                                qid={detailTask.qid || ""}
                                className="w-full h-auto max-h-[50vh] sm:max-h-[60vh] object-contain rounded border"
                              />
                            </div>
                          ) : (
                            <p className="text-xs sm:text-sm text-base-content/50 italic">
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
