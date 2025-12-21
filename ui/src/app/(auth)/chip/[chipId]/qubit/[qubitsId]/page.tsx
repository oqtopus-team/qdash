"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import React, { useEffect, Suspense } from "react";

import { ArrowLeft, Clock, Eye, TrendingUp } from "lucide-react";

import type { Task, TaskInfo } from "@/schemas";

import { FluentEmoji } from "@/components/ui/FluentEmoji";
import { QubitDetailPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

import { useGetChip } from "@/client/chip/chip";
import {
  useListTaskInfo,
  useGetTaskFileSettings,
} from "@/client/task-file/task-file";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { QubitRadarChart } from "@/components/features/qubit/QubitRadarChart";
import { QubitTimeSeriesView } from "@/components/features/qubit/QubitTimeSeriesView";
import { TaskHistoryViewer } from "@/components/features/qubit/TaskHistoryViewer";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { DateSelector } from "@/components/selectors/DateSelector";
import { TaskSelector } from "@/components/selectors/TaskSelector";
import { useDateNavigation } from "@/hooks/useDateNavigation";
import { useQubitTaskResults } from "@/hooks/useQubitTaskResults";
import { useChipUrlState } from "@/hooks/useUrlState";

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

  const { data: chipData, isLoading: isChipLoading } = useGetChip(chipId);

  // Get task file settings to determine default backend
  const { data: taskFileSettings, isLoading: isSettingsLoading } =
    useGetTaskFileSettings();
  const defaultBackend = taskFileSettings?.data?.default_backend || "qubex";

  // Get task list from task-files API
  const { data: taskInfoData, isLoading: isTaskInfoLoading } = useListTaskInfo({
    backend: defaultBackend,
  });

  // Update selected chip if different from URL
  useEffect(() => {
    if (isInitialized && chipId && chipId !== selectedChip) {
      setSelectedChip(chipId);
    }
  }, [isInitialized, chipId, selectedChip, setSelectedChip]);

  const { formatDate } = useDateNavigation(
    chipId,
    selectedDate,
    setSelectedDate,
  );

  // Get filtered tasks for qubit type
  const filteredTasks = (taskInfoData?.data?.tasks || []).filter(
    (task: TaskInfo) => task.task_type === "qubit",
  );

  // Get data for common qubit tasks for dashboard
  const { data: rabiData } = useQubitTaskResults({
    chipId,
    task: "CheckRabi",
    selectedDate,
  });

  const { data: ramseyData } = useQubitTaskResults({
    chipId,
    task: "CheckRamsey",
    selectedDate,
  });

  const { data: t1Data } = useQubitTaskResults({
    chipId,
    task: "CheckT1",
    selectedDate,
  });

  // Additional data for radar chart
  const { data: t2EchoData } = useQubitTaskResults({
    chipId,
    task: "CheckT2Echo",
    selectedDate,
  });

  const { data: gateFidelityData } = useQubitTaskResults({
    chipId,
    task: "RandomizedBenchmarking",
    selectedDate,
  });

  const { data: readoutFidelityData } = useQubitTaskResults({
    chipId,
    task: "ReadoutClassification",
    selectedDate,
  });

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

  // Show skeleton during initial loading
  if (
    !isInitialized ||
    isChipLoading ||
    isSettingsLoading ||
    isTaskInfoLoading
  ) {
    return <QubitDetailPageSkeleton />;
  }

  return (
    <div className="w-full px-6 py-6">
      <div className="space-y-6">
        {/* Back navigation */}
        <Link href="/chip" className="btn btn-ghost btn-sm gap-2 w-fit">
          <ArrowLeft size={16} />
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
                <Eye size={18} />
                <span className="ml-2">Dashboard</span>
              </button>
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "history" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("history")}
              >
                <Clock size={18} />
                <span className="ml-2">History</span>
              </button>
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "timeseries" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("timeseries")}
              >
                <TrendingUp size={18} />
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
            <ChipSelector
              selectedChip={chipId}
              onChipSelect={(newChipId) => {
                // Navigate to the new chip's qubit detail page
                window.location.href = `/chip/${newChipId}/qubit/${qubitId}`;
              }}
            />

            {viewMode !== "history" && (
              <DateSelector
                chipId={chipId}
                selectedDate={selectedDate}
                onDateSelect={setSelectedDate}
                disabled={!chipId}
              />
            )}

            <TaskSelector
              tasks={filteredTasks}
              selectedTask={selectedTask}
              onTaskSelect={setSelectedTask}
              disabled={false}
            />
          </div>
        </div>

        {/* Content Section */}
        <div className="pt-4">
          {viewMode === "dashboard" ? (
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
                          <FluentEmoji
                            name="prohibited"
                            size={48}
                            className="mb-2"
                          />
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
              isLoading={false}
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
    <Suspense fallback={<QubitDetailPageSkeleton />}>
      <QubitDetailPageContent />
    </Suspense>
  );
}
