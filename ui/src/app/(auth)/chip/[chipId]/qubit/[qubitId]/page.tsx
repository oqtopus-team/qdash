"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import React, { useEffect, Suspense } from "react";

import { ArrowLeft, Clock, Eye, TrendingUp } from "lucide-react";

import type { TaskInfo } from "@/schemas";

import { QubitDetailPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

import { useGetChip } from "@/client/chip/chip";
import {
  useListTaskInfo,
  useGetTaskFileSettings,
} from "@/client/task-file/task-file";
import { QubitTaskCard } from "@/components/features/qubit/QubitTaskCard";
import { QubitTimeSeriesView } from "@/components/features/qubit/QubitTimeSeriesView";
import { TaskHistoryViewer } from "@/components/features/qubit/TaskHistoryViewer";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { DateSelector } from "@/components/selectors/DateSelector";
import { TaskSelector } from "@/components/selectors/TaskSelector";
import { useDateNavigation } from "@/hooks/useDateNavigation";
import { useChipUrlState } from "@/hooks/useUrlState";

function QubitDetailPageContent() {
  const params = useParams();
  const chipId = params.chipId as string;
  const qubitId = params.qubitId as string;

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

  const viewMode = qubitViewMode as "dashboard" | "timeseries" | "history";
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

  // Set default task if none selected
  useEffect(() => {
    if (isInitialized && !selectedTask && filteredTasks.length > 0) {
      setSelectedTask(filteredTasks[0].name);
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
          <div className="flex flex-col sm:flex-row sm:justify-between items-start gap-4">
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
            </div>
          </div>

          {/* Controls */}
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="w-full sm:w-auto">
              <ChipSelector
                selectedChip={chipId}
                onChipSelect={(newChipId) => {
                  // Navigate to the new chip's qubit detail page
                  window.location.href = `/chip/${newChipId}/qubit/${qubitId}`;
                }}
              />
            </div>

            {viewMode !== "history" && (
              <div className="w-full sm:w-auto">
                <DateSelector
                  chipId={chipId}
                  selectedDate={selectedDate}
                  onDateSelect={setSelectedDate}
                  disabled={!chipId}
                />
              </div>
            )}

            <div className="w-full sm:w-auto">
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
                    {filteredTasks.length}
                  </div>
                </div>
              </div>

              {/* Experiments Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {filteredTasks.map((task: TaskInfo) => (
                  <QubitTaskCard
                    key={task.name}
                    task={task}
                    chipId={chipId}
                    qubitId={qubitId}
                    selectedDate={selectedDate}
                    onViewDetails={(taskName) => {
                      setSelectedTask(taskName);
                      setViewMode("history");
                    }}
                  />
                ))}
              </div>
            </div>
          ) : viewMode === "timeseries" ? (
            <QubitTimeSeriesView chipId={chipId} qubitId={qubitId} />
          ) : (
            <TaskHistoryViewer
              chipId={chipId}
              qubitId={qubitId}
              taskName={selectedTask || filteredTasks[0]?.name || ""}
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
