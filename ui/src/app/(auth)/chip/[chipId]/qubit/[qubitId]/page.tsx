"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, Suspense, useState } from "react";

import { ArrowLeft, CalendarDays, Clock, Eye, FlaskConical, TrendingUp } from "lucide-react";

import type { TaskInfo } from "@/schemas";

import { QubitDetailPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

import { useGetChip } from "@/client/chip/chip";
import { useListTaskInfo, useGetTaskFileSettings } from "@/client/task-file/task-file";
import { QubitTaskCard } from "@/components/features/qubit/QubitTaskCard";
import { QubitTimeSeriesView } from "@/components/features/qubit/QubitTimeSeriesView";
import { TaskHistoryViewer } from "@/components/features/qubit/TaskHistoryViewer";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { CooldownSelector } from "@/components/selectors/CooldownSelector";
import { TaskSelector } from "@/components/selectors/TaskSelector";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { TimeRangeSelector } from "@/components/ui/TimeRangeSelector";
import { useChipUrlState, useRangeModeUrlState } from "@/hooks/useUrlState";
import { dateToDateTimeLocal, toIsoSeconds } from "@/lib/utils/datetime";

function QubitDetailPageContent() {
  const params = useParams();
  const chipId = params.chipId as string;
  const qubitId = params.qubitId as string;

  // URL state management
  const {
    selectedChip,
    selectedTask,
    qubitViewMode,
    setSelectedChip,
    setSelectedTask,
    setQubitViewMode,
    isInitialized,
  } = useChipUrlState();

  const viewMode = qubitViewMode as "dashboard" | "timeseries" | "history";
  const setViewMode = setQubitViewMode;

  const { startDate, endDate, setStartDate, setEndDate, setQuickRange } = useRangeModeUrlState();
  const [selectedCooldownId, setSelectedCooldownId] = useState<string | null>(null);
  const startAt = toIsoSeconds(startDate);
  const endAt = toIsoSeconds(endDate);

  const { data: chipData, isLoading: isChipLoading } = useGetChip(chipId);

  // Get task file settings to determine default backend
  const { data: taskFileSettings, isLoading: isSettingsLoading } = useGetTaskFileSettings();
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
  if (!isInitialized || isChipLoading || isSettingsLoading || isTaskInfoLoading) {
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
                className={`join-item btn btn-sm ${viewMode === "dashboard" ? "btn-primary" : ""}`}
                onClick={() => setViewMode("dashboard")}
              >
                <Eye size={18} />
                <span className="ml-2">Dashboard</span>
              </button>
              <button
                className={`join-item btn btn-sm ${viewMode === "history" ? "btn-primary" : ""}`}
                onClick={() => setViewMode("history")}
              >
                <Clock size={18} />
                <span className="ml-2">History</span>
              </button>
              <button
                className={`join-item btn btn-sm ${viewMode === "timeseries" ? "btn-primary" : ""}`}
                onClick={() => setViewMode("timeseries")}
              >
                <TrendingUp size={18} />
                <span className="ml-2">Time Series</span>
              </button>
            </div>
          </div>

          {/* Controls */}
          <PageFiltersBar>
            <PageFiltersBar.Group>
              <PageFiltersBar.Item>
                <ChipSelector
                  selectedChip={chipId}
                  onChipSelect={(newChipId) => {
                    window.location.href = `/chip/${newChipId}/qubit/${qubitId}`;
                  }}
                />
              </PageFiltersBar.Item>
              <PageFiltersBar.Item>
                <CooldownSelector
                  chipId={chipId}
                  selectedCooldownId={selectedCooldownId}
                  onPick={(cooldown) => {
                    setSelectedCooldownId(cooldown.cooldown_id);
                    setStartDate(dateToDateTimeLocal(new Date(cooldown.started_at)));
                    setEndDate(
                      dateToDateTimeLocal(
                        cooldown.ended_at ? new Date(cooldown.ended_at) : new Date(),
                      ),
                    );
                  }}
                />
              </PageFiltersBar.Item>
              {viewMode === "history" && (
                <PageFiltersBar.Item>
                  <TaskSelector
                    tasks={filteredTasks}
                    selectedTask={selectedTask}
                    onTaskSelect={setSelectedTask}
                    disabled={false}
                  />
                </PageFiltersBar.Item>
              )}
            </PageFiltersBar.Group>
          </PageFiltersBar>

          {viewMode !== "timeseries" && (
            <TimeRangeSelector
              startDate={startDate}
              endDate={endDate}
              onStartDateChange={(value) => {
                setSelectedCooldownId(null);
                setStartDate(value);
              }}
              onEndDateChange={(value) => {
                setSelectedCooldownId(null);
                setEndDate(value);
              }}
              onQuickRange={(range) => {
                setSelectedCooldownId(null);
                setQuickRange(range);
              }}
            />
          )}
        </div>

        {/* Content Section */}
        <div className="pt-4">
          {viewMode === "dashboard" ? (
            <div className="space-y-4">
              <div className="rounded-lg border border-base-300 bg-base-100 px-4 py-3">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-md bg-primary px-2 py-1 text-sm font-semibold text-primary-content">
                        Q{qubitId}
                      </span>
                      <span className="truncate text-sm font-medium text-base-content">
                        {chipData?.data?.chip_id || chipId}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-base-content/55">
                      Latest available result for each qubit experiment in the selected range.
                    </p>
                  </div>

                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="inline-flex items-center gap-1 rounded-md border border-base-300 px-2.5 py-1.5">
                      <CalendarDays className="h-3.5 w-3.5 text-base-content/45" />
                      {startDate} - {endDate}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-md border border-base-300 px-2.5 py-1.5">
                      <FlaskConical className="h-3.5 w-3.5 text-base-content/45" />
                      {filteredTasks.length} experiments
                    </span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                {filteredTasks.map((task: TaskInfo) => (
                  <QubitTaskCard
                    key={task.name}
                    task={task}
                    chipId={chipId}
                    qubitId={qubitId}
                    startAt={startAt}
                    endAt={endAt}
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
              startAt={startAt}
              endAt={endAt}
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
