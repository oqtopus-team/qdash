"use client";

import React, { useEffect, Suspense } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { BsArrowLeft, BsGraphUp, BsTable, BsEye } from "react-icons/bs";

import { 
  useFetchLatestQubitTaskGroupedByChip,
  useFetchHistoricalQubitTaskGroupedByChip,
  useFetchChip
} from "@/client/chip/chip";
import { useFetchAllTasks } from "@/client/task/task";

import { ChipSelector } from "@/app/components/ChipSelector";
import { DateSelector } from "@/app/components/DateSelector";
import { TaskSelector } from "@/app/components/TaskSelector";
import { TaskFigure } from "@/app/components/TaskFigure";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import { useChipUrlState } from "@/app/hooks/useUrlState";
import { QubitTimeSeriesView } from "./components/QubitTimeSeriesView";
import { QubitRadarChart } from "./components/QubitRadarChart";

import type { Task, TaskResponse } from "@/schemas";


function QubitDetailPageContent() {
  const params = useParams();
  const chipId = params.chipId as string;
  const qubitId = params.qubitsId as string;

  // URL state management  
  const {
    selectedChip,
    selectedDate,
    selectedTask,
    qubitViewMode,
    setSelectedChip,
    setSelectedDate,
    setSelectedTask,
    setQubitViewMode,
    isInitialized,
  } = useChipUrlState();

  const viewMode = qubitViewMode as "dashboard" | "timeseries" | "radar" | "comparison";
  const setViewMode = setQubitViewMode;
  
  const { data: chipData } = useFetchChip(chipId);
  const { data: tasks } = useFetchAllTasks();

  // Update selected chip if different from URL
  useEffect(() => {
    if (isInitialized && chipId && chipId !== selectedChip) {
      setSelectedChip(chipId);
    }
  }, [isInitialized, chipId, selectedChip, setSelectedChip]);

  const {
    navigateToPreviousDay,
    navigateToNextDay,
    canNavigatePrevious,
    canNavigateNext,
    formatDate,
  } = useDateNavigation(chipId, selectedDate, setSelectedDate);



  // Get filtered tasks for qubit type
  const filteredTasks = tasks?.data?.tasks?.filter((task: TaskResponse) => 
    task.task_type === "qubit"
  ) || [];

  // Get data for common qubit tasks for dashboard
  const { data: rabiData } = selectedDate === "latest" 
    ? useFetchLatestQubitTaskGroupedByChip(chipId, "CheckRabi", {
        query: {
          staleTime: 30000,
        },
      })
    : useFetchHistoricalQubitTaskGroupedByChip(
        chipId,
        "CheckRabi",
        selectedDate === "latest" ? new Date().toISOString().split('T')[0] : selectedDate,
        {
          query: {
            staleTime: 30000,
            enabled: selectedDate !== "latest",
          },
        }
      );

  const { data: ramseysData } = selectedDate === "latest"
    ? useFetchLatestQubitTaskGroupedByChip(chipId, "CheckRamseys", {
        query: {
          staleTime: 30000,
        },
      })
    : useFetchHistoricalQubitTaskGroupedByChip(
        chipId,
        "CheckRamseys", 
        selectedDate === "latest" ? new Date().toISOString().split('T')[0] : selectedDate,
        {
          query: {
            staleTime: 30000,
            enabled: selectedDate !== "latest",
          },
        }
      );

  const { data: t1Data } = selectedDate === "latest"
    ? useFetchLatestQubitTaskGroupedByChip(chipId, "CheckT1", {
        query: {
          staleTime: 30000,
        },
      })
    : useFetchHistoricalQubitTaskGroupedByChip(
        chipId,
        "CheckT1",
        selectedDate === "latest" ? new Date().toISOString().split('T')[0] : selectedDate,
        {
          query: {
            staleTime: 30000,
            enabled: selectedDate !== "latest",
          },
        }
      );

  // Additional data for radar chart
  const { data: t2EchoData } = selectedDate === "latest"
    ? useFetchLatestQubitTaskGroupedByChip(chipId, "CheckT2Echo", {
        query: {
          staleTime: 30000,
        },
      })
    : useFetchHistoricalQubitTaskGroupedByChip(
        chipId,
        "CheckT2Echo",
        selectedDate === "latest" ? new Date().toISOString().split('T')[0] : selectedDate,
        {
          query: {
            staleTime: 30000,
            enabled: selectedDate !== "latest",
          },
        }
      );

  const { data: gateFidelityData } = selectedDate === "latest"
    ? useFetchLatestQubitTaskGroupedByChip(chipId, "RandomizedBenchmarking", {
        query: {
          staleTime: 30000,
        },
      })
    : useFetchHistoricalQubitTaskGroupedByChip(
        chipId,
        "RandomizedBenchmarking",
        selectedDate === "latest" ? new Date().toISOString().split('T')[0] : selectedDate,
        {
          query: {
            staleTime: 30000,
            enabled: selectedDate !== "latest",
          },
        }
      );

  const { data: readoutFidelityData } = selectedDate === "latest"
    ? useFetchLatestQubitTaskGroupedByChip(chipId, "ReadoutClassification", {
        query: {
          staleTime: 30000,
        },
      })
    : useFetchHistoricalQubitTaskGroupedByChip(
        chipId,
        "ReadoutClassification",
        selectedDate === "latest" ? new Date().toISOString().split('T')[0] : selectedDate,
        {
          query: {
            staleTime: 30000,
            enabled: selectedDate !== "latest",
          },
        }
      );

  // Collect all task data
  const allTasksData: Record<string, Task | null> = {
    "CheckRabi": rabiData?.data?.result?.[qubitId] || null,
    "CheckRamseys": ramseysData?.data?.result?.[qubitId] || null,
    "CheckT1": t1Data?.data?.result?.[qubitId] || null,
    "CheckT2Echo": t2EchoData?.data?.result?.[qubitId] || null,
    "RandomizedBenchmarking": gateFidelityData?.data?.result?.[qubitId] || null,
    "ReadoutClassification": readoutFidelityData?.data?.result?.[qubitId] || null,
  };

  // Set default task if none selected
  useEffect(() => {
    if (isInitialized && !selectedTask && filteredTasks.length > 0) {
      setSelectedTask("CheckRabi");
    }
  }, [isInitialized, selectedTask, filteredTasks, setSelectedTask]);


  const isLoading = false;

  return (
    <div className="w-full px-6 py-6" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="space-y-6">
        {/* Header Section */}
        <div className="flex flex-col gap-6">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-4">
              <Link href="/chip" className="btn btn-ghost btn-sm">
                <BsArrowLeft className="text-lg" />
                Back to Chip View
              </Link>
              <h1 className="text-2xl font-bold">
                Qubit {qubitId} Analysis - {chipData?.data?.chip_id || chipId}
              </h1>
            </div>
            <div className="join rounded-lg overflow-hidden">
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "dashboard" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("dashboard")}
              >
                <BsEye className="text-lg" />
                <span className="ml-2">Dashboard</span>
              </button>
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "timeseries" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("timeseries")}
              >
                <BsGraphUp className="text-lg" />
                <span className="ml-2">Time Series</span>
              </button>
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "radar" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("radar")}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="text-lg w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"></polygon>
                  <circle cx="12" cy="12" r="2"></circle>
                </svg>
                <span className="ml-2">Radar</span>
              </button>
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "comparison" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("comparison")}
              >
                <BsTable className="text-lg" />
                <span className="ml-2">Comparison</span>
              </button>
            </div>
          </div>

          {/* Controls */}
          <div className="flex gap-4">
            <div className="flex flex-col gap-1">
              <div className="flex justify-center gap-1 opacity-0">
                <button className="btn btn-xs btn-ghost invisible">←</button>
                <button className="btn btn-xs btn-ghost invisible">→</button>
              </div>
              <ChipSelector
                selectedChip={chipId}
                onChipSelect={(newChipId) => {
                  // Navigate to the new chip's qubit detail page
                  window.location.href = `/chip/${newChipId}/qubit/${qubitId}`;
                }}
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
                chipId={chipId}
                selectedDate={selectedDate}
                onDateSelect={setSelectedDate}
                disabled={!chipId}
              />
            </div>

            <div className="flex flex-col gap-1">
              <div className="flex justify-center gap-1 opacity-0">
                <button className="btn btn-xs btn-ghost invisible">←</button>
                <button className="btn btn-xs btn-ghost invisible">→</button>
              </div>
              <TaskSelector
                tasks={filteredTasks}
                selectedTask={selectedTask}
                onTaskSelect={setSelectedTask}
                disabled={false}
              />
            </div>

          </div>
        </div>

        {/* Content Section */}
        <div className="pt-4">
          {isLoading ? (
            <div className="w-full flex justify-center py-12">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          ) : viewMode === "dashboard" ? (
            <div className="space-y-6">
              {/* Qubit Information Header */}
              <div className="stats shadow w-full">
                <div className="stat">
                  <div className="stat-title">Qubit ID</div>
                  <div className="stat-value text-primary">{qubitId}</div>
                </div>
                <div className="stat">
                  <div className="stat-title">Chip</div>
                  <div className="stat-value text-sm">{chipData?.data?.chip_id}</div>
                </div>
                <div className="stat">
                  <div className="stat-title">Date</div>
                  <div className="stat-value text-sm">
                    {selectedDate === "latest" ? "Latest" : formatDate(selectedDate)}
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-title">Experiments</div>
                  <div className="stat-value text-sm">
                    {Object.values(allTasksData).filter(Boolean).length} / {Object.keys(allTasksData).length}
                  </div>
                </div>
              </div>

              {/* Experiments Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {Object.entries(allTasksData).map(([taskName, taskData]) => (
                  <div key={taskName} className="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow">
                    <div className="card-body p-4">
                      <h3 className="card-title text-lg flex items-center justify-between">
                        {taskName.replace("Check", "")}
                        <div
                          className={`badge ${
                            taskData?.status === "completed"
                              ? "badge-success"
                              : taskData?.status === "failed"
                              ? "badge-error"
                              : "badge-ghost"
                          }`}
                        >
                          {taskData?.status || "No Data"}
                        </div>
                      </h3>
                      
                      {taskData ? (
                        <div className="space-y-3">
                          {taskData.figure_path && (
                            <div className="relative h-32 bg-base-200 rounded-lg overflow-hidden">
                              <TaskFigure
                                path={Array.isArray(taskData.figure_path) 
                                  ? taskData.figure_path[0] 
                                  : taskData.figure_path}
                                qid={qubitId}
                                className="w-full h-full object-contain"
                              />
                            </div>
                          )}
                          
                          {taskData.output_parameters && (
                            <div className="bg-base-200 p-2 rounded">
                              {Object.entries(taskData.output_parameters).slice(0, 3).map(([key, value]) => {
                                const paramValue = (
                                  typeof value === "object" &&
                                  value !== null &&
                                  "value" in value
                                    ? value
                                    : { value }
                                ) as { value: number | string; unit?: string };
                                return (
                                  <div key={key} className="text-xs flex justify-between">
                                    <span className="font-medium">{key}:</span>
                                    <span>
                                      {typeof paramValue.value === "number"
                                        ? paramValue.value.toFixed(4)
                                        : String(paramValue.value)}
                                      {paramValue.unit ? ` ${paramValue.unit}` : ""}
                                    </span>
                                  </div>
                                );
                              })}
                              {Object.keys(taskData.output_parameters).length > 3 && (
                                <div className="text-xs text-center text-base-content/60 mt-1">
                                  +{Object.keys(taskData.output_parameters).length - 3} more...
                                </div>
                              )}
                            </div>
                          )}
                          
                          <div className="card-actions justify-end">
                            <button 
                              className="btn btn-sm btn-primary"
                              onClick={() => setSelectedTask(taskName)}
                            >
                              View Details
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="text-center text-base-content/60 py-8">
                          <div className="text-4xl mb-2">🚫</div>
                          <div className="text-sm">No data available</div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : viewMode === "timeseries" ? (
            <QubitTimeSeriesView chipId={chipId} qubitId={qubitId} />
          ) : viewMode === "radar" ? (
            <QubitRadarChart 
              qubitId={qubitId} 
              taskData={allTasksData} 
              isLoading={isLoading}
            />
          ) : (
            <div className="space-y-6">
              {/* Comparison View */}
              <div className="card bg-base-100 shadow-xl">
                <div className="card-body">
                  <h2 className="card-title mb-6">Experiment Comparison for Qubit {qubitId}</h2>
                  
                  {/* Comparison Table */}
                  <div className="overflow-x-auto">
                    <table className="table table-zebra">
                      <thead>
                        <tr>
                          <th>Experiment</th>
                          <th>Status</th>
                          <th>Key Parameters</th>
                          <th>Last Updated</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(allTasksData).map(([taskName, taskData]) => (
                          <tr key={taskName}>
                            <td>
                              <div className="font-bold">{taskName.replace("Check", "")}</div>
                              <div className="text-sm text-base-content/70">{taskName}</div>
                            </td>
                            <td>
                              <div
                                className={`badge ${
                                  taskData?.status === "completed"
                                    ? "badge-success"
                                    : taskData?.status === "failed"
                                    ? "badge-error"
                                    : "badge-ghost"
                                }`}
                              >
                                {taskData?.status || "No Data"}
                              </div>
                            </td>
                            <td>
                              {taskData?.output_parameters ? (
                                <div className="space-y-1">
                                  {Object.entries(taskData.output_parameters).slice(0, 2).map(([key, value]) => {
                                    const paramValue = (
                                      typeof value === "object" &&
                                      value !== null &&
                                      "value" in value
                                        ? value
                                        : { value }
                                    ) as { value: number | string; unit?: string };
                                    return (
                                      <div key={key} className="text-xs">
                                        <span className="font-medium">{key}:</span>{" "}
                                        <span>
                                          {typeof paramValue.value === "number"
                                            ? paramValue.value.toFixed(4)
                                            : String(paramValue.value)}
                                          {paramValue.unit ? ` ${paramValue.unit}` : ""}
                                        </span>
                                      </div>
                                    );
                                  })}
                                  {Object.keys(taskData.output_parameters).length > 2 && (
                                    <div className="text-xs text-base-content/60">
                                      +{Object.keys(taskData.output_parameters).length - 2} more...
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <span className="text-base-content/60">No parameters</span>
                              )}
                            </td>
                            <td>
                              {taskData?.end_at ? (
                                <div className="text-sm">
                                  {new Date(taskData.end_at).toLocaleDateString()}
                                  <div className="text-xs text-base-content/70">
                                    {new Date(taskData.end_at).toLocaleTimeString()}
                                  </div>
                                </div>
                              ) : (
                                <span className="text-base-content/60">-</span>
                              )}
                            </td>
                            <td>
                              <div className="flex gap-2">
                                <button
                                  className="btn btn-xs btn-primary"
                                  onClick={() => setSelectedTask(taskName)}
                                  disabled={!taskData}
                                >
                                  View
                                </button>
                                {taskData?.figure_path && (
                                  <button
                                    className="btn btn-xs btn-secondary"
                                    onClick={() => {
                                      setSelectedTask(taskName);
                                      setViewMode("dashboard");
                                    }}
                                  >
                                    Figure
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Summary Statistics */}
                  <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="stat bg-base-200 rounded-lg">
                      <div className="stat-title">Completed Experiments</div>
                      <div className="stat-value text-success">
                        {Object.values(allTasksData).filter(task => task?.status === "completed").length}
                      </div>
                    </div>
                    <div className="stat bg-base-200 rounded-lg">
                      <div className="stat-title">Failed Experiments</div>
                      <div className="stat-value text-error">
                        {Object.values(allTasksData).filter(task => task?.status === "failed").length}
                      </div>
                    </div>
                    <div className="stat bg-base-200 rounded-lg">
                      <div className="stat-title">Success Rate</div>
                      <div className="stat-value text-primary">
                        {Object.values(allTasksData).filter(Boolean).length > 0
                          ? Math.round(
                              (Object.values(allTasksData).filter(task => task?.status === "completed").length /
                                Object.values(allTasksData).filter(Boolean).length) * 100
                            )
                          : 0}%
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function QubitDetailPage() {
  return (
    <Suspense
      fallback={
        <div className="w-full flex justify-center py-12">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      }
    >
      <QubitDetailPageContent />
    </Suspense>
  );
}