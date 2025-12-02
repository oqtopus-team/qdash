"use client";

import { useState, useEffect, useRef, useMemo } from "react";

import { FaExternalLinkAlt } from "react-icons/fa";
import JsonView from "react18-json-view";

import { ExecutionStats } from "./ExecutionStats";

import type { ExecutionResponseSummary } from "@/schemas";

import { ChipSelector } from "@/app/components/ChipSelector";
import { DateSelector } from "@/app/components/DateSelector";
import { TaskFigure } from "@/app/components/TaskFigure";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import { useExecutionUrlState } from "@/app/hooks/useUrlState";
import { useListChips } from "@/client/chip/chip";
import {
  useListExecutions,
  useFetchExecution,
} from "@/client/execution/execution";

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
  const [cardData, setCardData] = useState<ExecutionResponseSummary[]>([]);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;

  // Track if we've already set the default chip to prevent race conditions
  const hasSetDefaultChip = useRef(false);

  // Use custom hook for date navigation
  const {
    navigateToPreviousDay,
    navigateToNextDay,
    canNavigatePrevious,
    canNavigateNext,
  } = useDateNavigation(selectedChip || "", selectedDate, setSelectedDate);

  // Get list of chips to set default
  const { data: chipsData } = useListChips();

  // Memoize sorted chips to avoid recalculating on every render
  const sortedChips = useMemo(() => {
    if (!chipsData?.data) return [];
    return [...chipsData.data].sort((a, b) => {
      const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
      const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
      return dateB - dateA;
    });
  }, [chipsData?.data]);

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
  } = useFetchExecution(selectedExecutionId || "", {
    query: {
      // Refresh every 5 seconds
      refetchInterval: 5000,
      // Keep polling even when the window is in the background
      refetchIntervalInBackground: true,
      // Only enable polling when an execution is selected
      enabled: !!selectedExecutionId,
    },
  });

  // Set card data when execution data is fetched (filter by date)
  useEffect(() => {
    if (executionData) {
      let filteredData = executionData.data;

      // Filter by date if not "latest"
      if (selectedDate !== "latest") {
        filteredData = executionData.data.filter((exec) => {
          const execDate = new Date(exec.start_at);
          const execDateStr = `${execDate.getFullYear()}${String(
            execDate.getMonth() + 1,
          ).padStart(2, "0")}${String(execDate.getDate()).padStart(2, "0")}`;
          return execDateStr === selectedDate;
        });
      }

      setCardData(filteredData);
    }
  }, [executionData, selectedDate]);

  // Chip selection change handler
  const handleChipChange = (chipId: string) => {
    setSelectedChip(chipId || null);
    setSelectedExecutionId(null);
    setIsSidebarOpen(false);
    setCardData([]);
    setCurrentPage(1); // Reset to first page when changing chips
  };

  // Reset page when date changes
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedDate]);

  if (isLoading) return <div>Loading...</div>;
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

  // Pagination controls component
  const PaginationControls = () => (
    <div className="flex justify-center items-center gap-4 my-4">
      <button
        onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
        disabled={currentPage === 1}
        className="btn btn-sm btn-outline"
      >
        Previous
      </button>
      <span className="text-sm">Page {currentPage}</span>
      <button
        onClick={() => setCurrentPage((prev) => prev + 1)}
        disabled={
          !executionData?.data || executionData.data.length < itemsPerPage
        }
        className="btn btn-sm btn-outline"
      >
        Next
      </button>
    </div>
  );

  return (
    <div className="w-full px-4 relative">
      <div className="px-10 pb-3">
        <h1 className="text-left text-3xl font-bold">Execution History</h1>
      </div>
      <div className="px-10 pb-6 flex gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex justify-center gap-1 opacity-0">
            <button className="btn btn-xs btn-ghost invisible">←</button>
            <button className="btn btn-xs btn-ghost invisible">→</button>
          </div>
          <ChipSelector
            selectedChip={selectedChip || ""}
            onChipSelect={handleChipChange}
          />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-center gap-1">
            <button
              onClick={navigateToPreviousDay}
              disabled={!canNavigatePrevious}
              className="btn btn-xs btn-ghost"
              title="Previous Day"
            >
              ←
            </button>
            <button
              onClick={navigateToNextDay}
              disabled={!canNavigateNext}
              className="btn btn-xs btn-ghost"
              title="Next Day"
            >
              →
            </button>
          </div>
          <DateSelector
            chipId={selectedChip || ""}
            selectedDate={selectedDate}
            onDateSelect={setSelectedDate}
            disabled={!selectedChip}
          />
        </div>
      </div>
      {/* Statistics display */}
      <ExecutionStats
        executions={cardData}
        selectedTag={selectedTag}
        onTagSelect={setSelectedTag}
      />
      {/* Pagination controls - Top */}
      <PaginationControls />
      <div className="grid grid-cols-1 gap-2 mx-5">
        {cardData.map((execution) => {
          const executionKey = getExecutionKey(execution);
          const isSelected = selectedExecutionId === execution.execution_id;
          const statusBorderStyle = getStatusBorderStyle(execution.status);

          return (
            <div
              key={executionKey}
              className={`p-4 rounded-lg shadow-md flex cursor-pointer relative overflow-hidden transition-transform duration-200 bg-base-100 ${
                isSelected ? "transform scale-100" : "transform scale-95"
              } ${statusBorderStyle}`}
              onClick={() => handleCardClick(execution)}
            >
              {isSelected && (
                <div className="absolute inset-0 bg-primary opacity-10 pointer-events-none transition-opacity duration-500" />
              )}
              <div className="relative z-10">
                <h2 className="text-xl font-semibold mb-1">{execution.name}</h2>
                <div className="flex items-center mb-1">
                  <p className="text-sm text-base-content/60 mr-4">
                    {new Date(execution.start_at).toLocaleString()}
                  </p>
                  {execution.elapsed_time && (
                    <p className="text-sm text-base-content/60 mr-4">
                      Duration: {execution.elapsed_time}
                    </p>
                  )}
                  <span
                    className={`text-sm font-semibold ${
                      execution.status === "running"
                        ? "text-info"
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
              </div>
            </div>
          );
        })}
      </div>
      {/* Pagination controls - Bottom */}
      <PaginationControls />
      {/* Sidebar */}
      <div
        className={`fixed right-0 top-0 w-1/2 h-full bg-base-100 shadow-xl border-l overflow-y-auto p-6 transition-transform duration-300 ${
          isSidebarOpen
            ? "transform translate-x-0"
            : "transform translate-x-full"
        }`}
        style={{ maxWidth: "40%" }}
      >
        <button
          onClick={handleCloseSidebar}
          className="text-base-content/60 text-2xl font-bold absolute top-4 right-4 hover:text-base-content"
        >
          ×
        </button>
        {selectedExecutionId && (
          <>
            <div className="p-4 bg-base-100 mb-6">
              <h2 className="text-2xl font-bold">
                {
                  cardData.find(
                    (exec) => getExecutionKey(exec) === selectedExecutionId,
                  )?.name
                }
              </h2>
              <div className="flex space-x-4 mt-4">
                <a
                  href={`/execution/${selectedChip || ""}/${selectedExecutionId}`}
                  className="bg-neutral text-neutral-content px-4 py-2 rounded flex items-center hover:opacity-80 transition-colors"
                >
                  <FaExternalLinkAlt className="mr-2" />
                  Go to Detail
                </a>
                <a
                  href={String(
                    cardData.find(
                      (exec) => getExecutionKey(exec) === selectedExecutionId,
                    )?.note?.ui_url || "#",
                  )}
                  className="bg-accent text-accent-content px-4 py-2 rounded flex items-center hover:opacity-80 transition-colors"
                >
                  <FaExternalLinkAlt className="mr-2" />
                  Go to Flow
                </a>
              </div>
            </div>
            <div className="bg-base-100"></div>
            <div>
              <h3 className="text-xl font-bold mb-4">Execution Details</h3>
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
                      className={`mb-4 p-4 rounded-lg shadow-md bg-base-100 cursor-pointer hover:shadow-lg transition-shadow ${taskBorderStyle}`}
                      onClick={() => handleTaskClick(idx)}
                    >
                      <h4 className="text-lg font-semibold text-left">
                        {detailTask.qid
                          ? `${detailTask.qid}-${detailTask.name}`
                          : detailTask.name}
                      </h4>
                      <p className="text-left">
                        Start at:{" "}
                        {detailTask.start_at
                          ? new Date(detailTask.start_at).toLocaleString()
                          : "N/A"}
                      </p>
                      <p className="text-left">
                        Elapsed time: {detailTask.elapsed_time}
                      </p>
                      <p
                        className={`text-left text-sm font-semibold ${
                          detailTask.status === "running"
                            ? "text-info"
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
                      </p>
                      {expandedTaskIndex === idx && (
                        <div className="mt-2">
                          {Array.isArray(detailTask.figure_path) ? (
                            detailTask.figure_path.map((path, i) => (
                              <div key={i} className="mt-2">
                                <h5 className="text-md font-semibold mb-1 text-left">
                                  Figure {i + 1}
                                </h5>
                                <TaskFigure
                                  path={path}
                                  qid={detailTask.qid || ""}
                                  className="w-full h-auto max-h-[60vh] object-contain rounded border"
                                />
                              </div>
                            ))
                          ) : detailTask.figure_path ? (
                            <div className="mt-2">
                              <h5 className="text-md font-semibold mb-1 text-left">
                                Figure
                              </h5>
                              <TaskFigure
                                path={detailTask.figure_path}
                                qid={detailTask.qid || ""}
                                className="w-full h-auto max-h-[60vh] object-contain rounded border"
                              />
                            </div>
                          ) : null}
                        </div>
                      )}
                      {expandedTaskIndex === idx && (
                        <div className="mt-2">
                          <h5 className="text-md font-semibold mb-1 text-left">
                            Input Parameters
                          </h5>
                          <div className="bg-base-200 p-2 rounded">
                            <JsonView
                              src={detailTask.input_parameters}
                              theme="vscode"
                              collapsed={1}
                            />
                          </div>
                        </div>
                      )}
                      {expandedTaskIndex === idx && (
                        <div className="mt-2">
                          <h5 className="text-md font-semibold mb-1 text-left">
                            Output Parameters
                          </h5>
                          <div className="bg-base-200 p-2 rounded">
                            <JsonView
                              src={detailTask.output_parameters}
                              theme="vscode"
                              collapsed={2}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
