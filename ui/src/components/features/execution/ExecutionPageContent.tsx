"use client";

import { useState, useEffect, useRef, useMemo } from "react";

import { ExternalLink } from "lucide-react";

import { formatDateTime } from "@/utils/datetime";

import { ExecutionStats } from "./ExecutionStats";

import type { ExecutionResponseSummary } from "@/schemas";

import { useListChips } from "@/client/chip/chip";
import {
  useListExecutions,
  useGetExecution,
} from "@/client/execution/execution";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { DateSelector } from "@/components/selectors/DateSelector";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { ExecutionPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useDateNavigation } from "@/hooks/useDateNavigation";
import { useExecutionUrlState } from "@/hooks/useUrlState";

function PaginationControls({
  currentPage,
  setCurrentPage,
  hasMore,
}: {
  currentPage: number;
  setCurrentPage: React.Dispatch<React.SetStateAction<number>>;
  hasMore: boolean;
}) {
  return (
    <div className="flex justify-center items-center gap-2 sm:gap-4 my-3 sm:my-4 px-4">
      <button
        onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
        disabled={currentPage === 1}
        className="btn btn-xs sm:btn-sm btn-outline"
      >
        Prev
      </button>
      <span className="text-xs sm:text-sm">Page {currentPage}</span>
      <button
        onClick={() => setCurrentPage((prev) => prev + 1)}
        disabled={!hasMore}
        className="btn btn-xs sm:btn-sm btn-outline"
      >
        Next
      </button>
    </div>
  );
}

export function ExecutionPageContent() {
  // URL state management
  const { selectedChip, setSelectedChip, isInitialized } =
    useExecutionUrlState();

  // Add date state for navigation
  const [selectedDate, setSelectedDate] = useState<string>("latest");

  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(
    null,
  );
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [expandedTaskIndex, setExpandedTaskIndex] = useState<number | null>(
    null,
  );
  const [selectedTag, setSelectedTag] = useState<string | null>(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;

  // Track if we've already set the default chip to prevent race conditions
  const hasSetDefaultChip = useRef(false);

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
    if (
      isInitialized &&
      !selectedChip &&
      !hasSetDefaultChip.current &&
      sortedChips.length > 0
    ) {
      hasSetDefaultChip.current = true;
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
      const execDate = new Date(exec.start_at);
      const execDateStr = `${execDate.getFullYear()}${String(
        execDate.getMonth() + 1,
      ).padStart(2, "0")}${String(execDate.getDate()).padStart(2, "0")}`;
      return execDateStr === selectedDate;
    });
  }, [executionData, selectedDate]);

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
  if (isError) return <div>Error</div>;

  // Generate unique key for execution
  const getExecutionKey = (execution: ExecutionResponseSummary) =>
    `${execution.execution_id}`;

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

  // Toggle task expansion on click
  const handleTaskClick = (index: number) => {
    setExpandedTaskIndex(expandedTaskIndex === index ? null : index);
  };

  // Get border color based on status
  const getStatusBorderStyle = (status: string) => {
    switch (status) {
      case "running":
        return "border-l-4 border-info";
      case "completed":
        return "border-l-4 border-success";
      case "scheduled":
        return "border-l-4 border-warning";
      case "failed":
        return "border-l-4 border-error";
      default:
        return "border-l-4 border-base-300";
    }
  };

  const hasMorePages =
    !!executionData?.data?.executions &&
    executionData.data.executions.length >= itemsPerPage;

  return (
    <PageContainer>
      <PageHeader
        title="Execution History"
        description="Monitor workflow runs and task results"
      />
      <PageFiltersBar className="mb-4 sm:mb-6">
        <PageFiltersBar.Group>
          <PageFiltersBar.Item>
            <ChipSelector
              selectedChip={selectedChip || ""}
              onChipSelect={handleChipChange}
            />
          </PageFiltersBar.Item>
          <PageFiltersBar.Item>
            <DateSelector
              chipId={selectedChip || ""}
              selectedDate={selectedDate}
              onDateSelect={handleDateChange}
              disabled={!selectedChip}
            />
          </PageFiltersBar.Item>
        </PageFiltersBar.Group>
      </PageFiltersBar>
      {/* Statistics display */}
      <ExecutionStats
        executions={cardData}
        selectedTag={selectedTag}
        onTagSelect={setSelectedTag}
      />
      {/* Pagination controls - Top */}
      <PaginationControls
        currentPage={currentPage}
        setCurrentPage={setCurrentPage}
        hasMore={hasMorePages}
      />
      <div className="grid grid-cols-1 gap-1.5 sm:gap-2">
        {cardData.map((execution) => {
          const executionKey = getExecutionKey(execution);
          const isSelected = selectedExecutionId === execution.execution_id;
          const statusBorderStyle = getStatusBorderStyle(execution.status);

          return (
            <div
              key={executionKey}
              className={`p-2 sm:p-4 rounded-lg shadow-md flex cursor-pointer relative overflow-hidden transition-transform duration-200 bg-base-100 ${
                isSelected ? "transform scale-100" : "sm:transform sm:scale-95"
              } ${statusBorderStyle}`}
              onClick={() => handleCardClick(execution)}
            >
              {isSelected && (
                <div className="absolute inset-0 bg-primary opacity-10 pointer-events-none transition-opacity duration-500" />
              )}
              <div className="relative z-10 w-full">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-sm sm:text-xl font-semibold truncate">
                    {execution.name}
                  </h2>
                  <span
                    className={`text-xs sm:text-sm font-semibold flex-shrink-0 ${
                      execution.status === "running"
                        ? "text-info status-pulse"
                        : execution.status === "completed"
                          ? "text-success"
                          : execution.status === "scheduled"
                            ? "text-warning"
                            : "text-error"
                    }`}
                  >
                    {execution.status === "running"
                      ? "Running"
                      : execution.status === "completed"
                        ? "Completed"
                        : execution.status === "scheduled"
                          ? "Scheduled"
                          : "Failed"}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-x-2 sm:gap-x-3 gap-y-0.5 mt-0.5 sm:mt-1 text-xs sm:text-sm text-base-content/60">
                  <span>{formatDateTime(execution.start_at)}</span>
                  {execution.elapsed_time && (
                    <span className="hidden sm:inline">
                      Duration: {execution.elapsed_time}
                    </span>
                  )}
                  {execution.elapsed_time && (
                    <span className="sm:hidden">{execution.elapsed_time}</span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {/* Pagination controls - Bottom */}
      <PaginationControls
        currentPage={currentPage}
        setCurrentPage={setCurrentPage}
        hasMore={hasMorePages}
      />
      {/* Sidebar */}
      <div
        className={`fixed right-0 top-0 w-full sm:w-3/4 lg:w-2/5 h-full bg-base-100 shadow-xl border-l overflow-y-auto p-4 sm:p-6 transition-transform duration-300 z-50 ${
          isSidebarOpen
            ? "transform translate-x-0"
            : "transform translate-x-full"
        }`}
      >
        <button
          onClick={handleCloseSidebar}
          className="btn btn-ghost btn-sm btn-circle absolute top-3 right-3 sm:top-4 sm:right-4"
          aria-label="Close sidebar"
        >
          ✕
        </button>
        {selectedExecutionId && (
          <>
            <div className="p-2 sm:p-4 bg-base-100 mb-4 sm:mb-6">
              <h2 className="text-lg sm:text-2xl font-bold pr-8">
                {
                  cardData.find(
                    (exec) => getExecutionKey(exec) === selectedExecutionId,
                  )?.name
                }
              </h2>
              <div className="mt-3 sm:mt-4">
                <a
                  href={`/execution/${selectedChip || ""}/${selectedExecutionId}`}
                  className="btn btn-primary btn-sm sm:btn-md"
                >
                  <ExternalLink className="w-3 h-3 sm:w-4 sm:h-4" />
                  View Details
                </a>
              </div>
            </div>
            <div>
              <h3 className="text-base sm:text-xl font-bold mb-3 sm:mb-4">
                Execution Details
              </h3>
              {isDetailLoading && <div>Loading details...</div>}
              {isDetailError && <div>Error loading details.</div>}
              {executionDetailData &&
                executionDetailData.data.task &&
                executionDetailData.data.task.map((detailTask, idx) => {
                  const taskBorderStyle = getStatusBorderStyle(
                    detailTask.status ?? "unknown",
                  );

                  return (
                    <div
                      key={idx}
                      className={`mb-2 sm:mb-4 p-2 sm:p-4 rounded-lg shadow-md bg-base-100 cursor-pointer hover:shadow-lg transition-shadow ${taskBorderStyle}`}
                      onClick={() => handleTaskClick(idx)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <h4 className="text-sm sm:text-lg font-semibold text-left truncate flex-1">
                          {detailTask.qid
                            ? `${detailTask.qid}-${detailTask.name}`
                            : detailTask.name}
                        </h4>
                        <span
                          className={`text-xs sm:text-sm font-semibold flex-shrink-0 ${
                            detailTask.status === "running"
                              ? "text-info status-pulse"
                              : detailTask.status === "completed"
                                ? "text-success"
                                : detailTask.status === "scheduled"
                                  ? "text-warning"
                                  : "text-error"
                          }`}
                        >
                          {detailTask.status === "running"
                            ? "Running"
                            : detailTask.status === "completed"
                              ? "Completed"
                              : detailTask.status === "scheduled"
                                ? "Scheduled"
                                : "Failed"}
                        </span>
                      </div>
                      <div className="text-xs sm:text-sm text-base-content/60 mt-1">
                        <span>
                          {detailTask.start_at
                            ? formatDateTime(detailTask.start_at)
                            : "N/A"}
                        </span>
                        {detailTask.elapsed_time && (
                          <span className="ml-2 sm:ml-3">
                            {detailTask.elapsed_time}
                          </span>
                        )}
                      </div>
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
          </>
        )}
      </div>
    </PageContainer>
  );
}
