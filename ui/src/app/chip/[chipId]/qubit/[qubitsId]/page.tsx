"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import React, { useEffect, Suspense } from "react";

import { BsGraphUp, BsEye, BsClock } from "react-icons/bs";
import { FaArrowLeft } from "react-icons/fa";

import { QubitRadarChart } from "./components/QubitRadarChart";
import { QubitTimeSeriesView } from "./components/QubitTimeSeriesView";
import { TaskHistoryViewer } from "./components/TaskHistoryViewer";

import type { Task, TaskResponse } from "@/schemas";

import { ChipSelector } from "@/app/components/ChipSelector";
import { DateSelector } from "@/app/components/DateSelector";
import { TaskFigure } from "@/app/components/TaskFigure";
import { TaskSelector } from "@/app/components/TaskSelector";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import { useChipUrlState } from "@/app/hooks/useUrlState";
import { useGetChip } from "@/client/chip/chip";
import {
  useGetLatestQubitTaskResults,
  useGetHistoricalQubitTaskResults,
} from "@/client/task-result/task-result";
import { useListTasks } from "@/client/task/task";

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

  const viewMode = qubitViewMode as
    | "dashboard"
    | "timeseries"
    | "radar"
    | "history";
  const setViewMode = setQubitViewMode;

  const { data: chipData } = useGetChip(chipId);
  const { data: tasks } = useListTasks();

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
  const filteredTasks =
    tasks?.data?.tasks?.filter(
      (task: TaskResponse) => task.task_type === "qubit",
    ) || [];

  // Get data for common qubit tasks for dashboard
  const { data: rabiData } =
    selectedDate === "latest"
      ? useGetLatestQubitTaskResults(
          { chip_id: chipId, task: "CheckRabi" },
          {
            query: {
              staleTime: 30000,
            },
          },
        )
      : useGetHistoricalQubitTaskResults(
          {
            chip_id: chipId,
            task: "CheckRabi",
            date:
              selectedDate === "latest"
                ? new Date().toISOString().split("T")[0]
                : selectedDate,
          },
          {
            query: {
              staleTime: 30000,
              enabled: selectedDate !== "latest",
            },
          },
        );

  const { data: ramseyData } =
    selectedDate === "latest"
      ? useGetLatestQubitTaskResults(
          { chip_id: chipId, task: "CheckRamsey" },
          {
            query: {
              staleTime: 30000,
            },
          },
        )
      : useGetHistoricalQubitTaskResults(
          {
            chip_id: chipId,
            task: "CheckRamsey",
            date:
              selectedDate === "latest"
                ? new Date().toISOString().split("T")[0]
                : selectedDate,
          },
          {
            query: {
              staleTime: 30000,
              enabled: selectedDate !== "latest",
            },
          },
        );

  const { data: t1Data } =
    selectedDate === "latest"
      ? useGetLatestQubitTaskResults(
          { chip_id: chipId, task: "CheckT1" },
          {
            query: {
              staleTime: 30000,
            },
          },
        )
      : useGetHistoricalQubitTaskResults(
          {
            chip_id: chipId,
            task: "CheckT1",
            date:
              selectedDate === "latest"
                ? new Date().toISOString().split("T")[0]
                : selectedDate,
          },
          {
            query: {
              staleTime: 30000,
              enabled: selectedDate !== "latest",
            },
          },
        );

  // Additional data for radar chart
  const { data: t2EchoData } =
    selectedDate === "latest"
      ? useGetLatestQubitTaskResults(
          { chip_id: chipId, task: "CheckT2Echo" },
          {
            query: {
              staleTime: 30000,
            },
          },
        )
      : useGetHistoricalQubitTaskResults(
          {
            chip_id: chipId,
            task: "CheckT2Echo",
            date:
              selectedDate === "latest"
                ? new Date().toISOString().split("T")[0]
                : selectedDate,
          },
          {
            query: {
              staleTime: 30000,
              enabled: selectedDate !== "latest",
            },
          },
        );

  const { data: gateFidelityData } =
    selectedDate === "latest"
      ? useGetLatestQubitTaskResults(
          { chip_id: chipId, task: "RandomizedBenchmarking" },
          {
            query: {
              staleTime: 30000,
            },
          },
        )
      : useGetHistoricalQubitTaskResults(
          {
            chip_id: chipId,
            task: "RandomizedBenchmarking",
            date:
              selectedDate === "latest"
                ? new Date().toISOString().split("T")[0]
                : selectedDate,
          },
          {
            query: {
              staleTime: 30000,
              enabled: selectedDate !== "latest",
            },
          },
        );

  const { data: readoutFidelityData } =
    selectedDate === "latest"
      ? useGetLatestQubitTaskResults(
          { chip_id: chipId, task: "ReadoutClassification" },
          {
            query: {
              staleTime: 30000,
            },
          },
        )
      : useGetHistoricalQubitTaskResults(
          {
            chip_id: chipId,
            task: "ReadoutClassification",
            date:
              selectedDate === "latest"
                ? new Date().toISOString().split("T")[0]
                : selectedDate,
          },
          {
            query: {
              staleTime: 30000,
              enabled: selectedDate !== "latest",
            },
          },
        );

  // Collect all task data
  const allTasksData: Record<string, Task | null> = {
    CheckRabi: rabiData?.data?.result?.[qubitId] || null,
    CheckRamsey: ramseyData?.data?.result?.[qubitId] || null,
    CheckT1: t1Data?.data?.result?.[qubitId] || null,
    CheckT2Echo: t2EchoData?.data?.result?.[qubitId] || null,
    RandomizedBenchmarking: gateFidelityData?.data?.result?.[qubitId] || null,
    ReadoutClassification: readoutFidelityData?.data?.result?.[qubitId] || null,
  };

  // Set default task if none selected
  useEffect(() => {
    if (isInitialized && !selectedTask && filteredTasks.length > 0) {
      setSelectedTask("CheckRabi");
    }
  }, [isInitialized, selectedTask, filteredTasks, setSelectedTask]);

  const isLoading = false;

  return (
    <div className="w-full px-6 py-6">
      <div className="space-y-6">
        {/* Back navigation */}
        <Link href="/chip" className="btn btn-ghost btn-sm gap-2 w-fit">
          <FaArrowLeft />
          Back to Chip View
        </Link>

        {/* Header Section */}
        <div className="flex flex-col gap-6">
          <div className="flex justify-between items-center">
            <h1 className="text-2xl font-bold">
              Qubit {qubitId} Analysis - {chipData?.data?.chip_id || chipId}
            </h1>
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
                  viewMode === "history" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("history")}
              >
                <BsClock className="text-lg" />
                <span className="ml-2">History</span>
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

            {viewMode !== "history" && (
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
            )}

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
                  <div className="stat-value text-sm">
                    {chipData?.data?.chip_id}
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-title">Date</div>
                  <div className="stat-value text-sm">
                    {selectedDate === "latest"
                      ? "Latest"
                      : formatDate(selectedDate)}
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-title">Experiments</div>
                  <div className="stat-value text-sm">
                    {Object.values(allTasksData).filter(Boolean).length} /{" "}
                    {Object.keys(allTasksData).length}
                  </div>
                </div>
              </div>

              {/* Experiments Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {Object.entries(allTasksData).map(([taskName, taskData]) => (
                  <div
                    key={taskName}
                    className="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow"
                  >
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
                                path={
                                  Array.isArray(taskData.figure_path)
                                    ? taskData.figure_path[0]
                                    : taskData.figure_path
                                }
                                qid={qubitId}
                                className="w-full h-full object-contain"
                              />
                            </div>
                          )}

                          {taskData.output_parameters && (
                            <div className="bg-base-200 p-2 rounded">
                              {Object.entries(taskData.output_parameters)
                                .slice(0, 3)
                                .map(([key, value]) => {
                                  const paramValue = (
                                    typeof value === "object" &&
                                    value !== null &&
                                    "value" in value
                                      ? value
                                      : { value }
                                  ) as {
                                    value: number | string;
                                    unit?: string;
                                  };
                                  return (
                                    <div
                                      key={key}
                                      className="text-xs flex justify-between"
                                    >
                                      <span className="font-medium">
                                        {key}:
                                      </span>
                                      <span>
                                        {typeof paramValue.value === "number"
                                          ? paramValue.value.toFixed(4)
                                          : String(paramValue.value)}
                                        {paramValue.unit
                                          ? ` ${paramValue.unit}`
                                          : ""}
                                      </span>
                                    </div>
                                  );
                                })}
                              {Object.keys(taskData.output_parameters).length >
                                3 && (
                                <div className="text-xs text-center text-base-content/60 mt-1">
                                  +
                                  {Object.keys(taskData.output_parameters)
                                    .length - 3}{" "}
                                  more...
                                </div>
                              )}
                            </div>
                          )}

                          <div className="card-actions justify-end">
                            <button
                              className="btn btn-sm btn-primary"
                              onClick={() => {
                                setSelectedTask(taskName);
                                setViewMode("history");
                              }}
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
            <TaskHistoryViewer
              chipId={chipId}
              qubitId={qubitId}
              taskName={selectedTask || "CheckRabi"}
            />
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
