"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  ArrowLeft,
  Calendar,
  CheckCircle,
  Clock,
  Download,
  ExternalLink,
  StopCircle,
  XCircle,
} from "lucide-react";
import Select, { type SingleValue, type StylesConfig } from "react-select";

import { formatDateTime as formatDateTimeUtil } from "@/lib/utils/datetime";

import { ExecutionDAG } from "./ExecutionDAG";

import type { ExecutionResponseDetail } from "@/schemas";

import { useGetExecution, useCancelExecution } from "@/client/execution/execution";
import { ExecutionTopologyView } from "@/components/features/execution/ExecutionTopologyView";
import { ExecutionDetailPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";

type FilterOption = {
  value: string;
  label: string;
};

type TopologyMode = "1q" | "2q";

interface ExecutionDetailClientProps {
  chipId: string;
  executionId: string;
}

export function ExecutionDetailClient({ chipId, executionId }: ExecutionDetailClientProps) {
  const [topologyMode, setTopologyMode] = useState<TopologyMode>("1q");
  const [filterTaskName, setFilterTaskName] = useState<string>("");
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);

  const calculateDetailedDuration = (
    start: string | null | undefined,
    end: string | null | undefined,
  ) => {
    if (!start || !end) return "-";
    const startDate = new Date(start);
    const endDate = new Date(end);
    const diff = endDate.getTime() - startDate.getTime();

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);

    const parts = [];
    if (days > 0) parts.push(`${days} days`);
    if (hours > 0) parts.push(`${hours} hours`);
    if (minutes > 0) parts.push(`${minutes} minutes`);
    if (seconds > 0) parts.push(`${seconds} seconds`);

    return parts.join(", ");
  };

  const {
    data: executionDetailData,
    isLoading: isDetailLoading,
    isError: isDetailError,
  } = useGetExecution(executionId, {
    query: {
      // Refresh every 5 seconds
      refetchInterval: 5000,
      // Keep polling even when the window is in the background
      refetchIntervalInBackground: true,
    },
  });

  const cancelMutation = useCancelExecution();

  const execution = executionDetailData?.data as
    | (ExecutionResponseDetail & {
        tags?: string[];
        chip_id?: string;
        flow_name?: string;
      })
    | undefined;

  const flowRunId = execution?.note?.flow_run_id as string | undefined;

  const isCancellable =
    !!flowRunId &&
    (execution?.status === "running" ||
      execution?.status === "scheduled" ||
      execution?.status === "pending");

  const handleCancel = () => {
    if (!flowRunId) return;
    cancelMutation.mutate(
      { flowRunId },
      {
        onSuccess: () => {
          setShowCancelConfirm(false);
        },
        onError: () => {
          setShowCancelConfirm(false);
        },
      },
    );
  };

  const uniqueTaskNames = useMemo(() => {
    if (!execution?.task) return [];
    const names = new Set<string>();
    execution.task.forEach((task) => {
      const isCouplingTask = task.qid?.includes("-") ?? false;
      const matchesTopologyMode =
        topologyMode === "2q" ? isCouplingTask : task.qid ? !isCouplingTask : false;
      if (task.name && matchesTopologyMode) {
        names.add(task.name);
      }
    });
    return Array.from(names);
  }, [execution?.task, topologyMode]);

  const taskFilterOptions: FilterOption[] = useMemo(
    () => uniqueTaskNames.map((name) => ({ value: name, label: name })),
    [uniqueTaskNames],
  );

  useEffect(() => {
    const firstTaskName = uniqueTaskNames[0] ?? "";
    if (!filterTaskName || !uniqueTaskNames.includes(filterTaskName)) {
      setFilterTaskName(firstTaskName);
    }
  }, [filterTaskName, uniqueTaskNames]);

  const filterSelectStyles = useMemo<StylesConfig<FilterOption, false>>(
    () => ({
      control: (provided) => ({
        ...provided,
        minHeight: 34,
        height: 34,
      }),
      valueContainer: (provided) => ({
        ...provided,
        padding: "2px 8px",
      }),
      indicatorsContainer: (provided) => ({
        ...provided,
        height: 34,
      }),
      menu: (provided) => ({
        ...provided,
        zIndex: 20,
      }),
    }),
    [],
  );

  // Filter tasks based on selected filters
  const filteredTasks = useMemo(() => {
    if (!execution?.task) return [];
    return execution.task.filter((task) => {
      const isCouplingTask = task.qid?.includes("-") ?? false;
      const matchesTopologyMode =
        topologyMode === "2q" ? isCouplingTask : task.qid ? !isCouplingTask : false;
      const matchesTaskName = !!filterTaskName && task.name === filterTaskName;
      return matchesTopologyMode && matchesTaskName;
    });
  }, [execution?.task, filterTaskName, topologyMode]);

  // Filter out tasks without task_id and ensure all required fields are present
  const validTasks = useMemo(() => {
    if (!execution?.task) return [];
    return execution.task
      .filter((task) => task.task_id)
      .map((task) => {
        const taskName = task.name || "Unnamed Task";
        const displayName = task.qid ? `${task.qid}-${taskName}` : taskName;
        return {
          task_id: task.task_id as string,
          name: displayName,
          status: task.status || "unknown",
          upstream_id: task.upstream_id || undefined,
          start_at: task.start_at || undefined,
          end_at: task.end_at || undefined,
          elapsed_time: task.elapsed_time || undefined,
          figure_path: task.figure_path || undefined,
          input_parameters: task.input_parameters || undefined,
          output_parameters: task.output_parameters || undefined,
        };
      });
  }, [execution?.task]);

  if (isDetailLoading) {
    return <ExecutionDetailPageSkeleton />;
  }
  if (isDetailError) return <div>Error loading execution details.</div>;
  if (!executionDetailData || !execution) return <div>No data found.</div>;

  return (
    <div className="w-full px-4 py-6">
      <div className="space-y-6">
        {/* Back navigation */}
        <Link href="/execution" className="btn btn-ghost btn-sm gap-2 w-fit">
          <ArrowLeft size={16} />
          Back to Executions
        </Link>

        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
            <h1 className="text-2xl sm:text-3xl font-bold break-all">{execution.name}</h1>
            <div className="flex flex-col sm:flex-row gap-2 sm:gap-4">
              {isCancellable && (
                <button
                  onClick={() => setShowCancelConfirm(true)}
                  disabled={cancelMutation.isPending}
                  className="bg-error text-error-content px-4 py-2 rounded flex items-center justify-center hover:opacity-80 transition-colors text-sm sm:text-base disabled:opacity-50"
                >
                  <StopCircle className="mr-2" size={16} />
                  {cancelMutation.isPending ? "Cancelling..." : "Cancel Execution"}
                </button>
              )}
              <a
                href={`/execution/${executionId}/experiment`}
                className="bg-neutral text-neutral-content px-4 py-2 rounded flex items-center justify-center hover:opacity-80 transition-colors text-sm sm:text-base"
              >
                <ExternalLink className="mr-2" size={16} />
                Go to Experiment
              </a>
              <a
                href={((execution.note as { [key: string]: unknown })?.ui_url as string) || "#"}
                className="bg-accent text-accent-content px-4 py-2 rounded flex items-center justify-center hover:opacity-80 transition-colors text-sm sm:text-base"
              >
                <ExternalLink className="mr-2" size={16} />
                Go to Flow
              </a>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-6 text-sm bg-base-100/50 px-4 py-3 rounded-lg">
            <div className="flex items-center text-base-content/70">
              <Calendar className="mr-2 text-info/70 flex-shrink-0" size={14} />
              <span className="font-medium mr-1">Start:</span>
              <time className="truncate">{formatDateTimeUtil(execution.start_at)}</time>
            </div>
            <div className="flex items-center text-base-content/70">
              <Calendar className="mr-2 text-info/70 flex-shrink-0" size={14} />
              <span className="font-medium mr-1">End:</span>
              <time className="truncate">{formatDateTimeUtil(execution.end_at)}</time>
            </div>
            <div
              className="flex items-center text-base-content/70 tooltip tooltip-bottom"
              data-tip={calculateDetailedDuration(execution.start_at, execution.end_at)}
            >
              <Clock className="mr-2 text-info/70 flex-shrink-0" size={14} />
              <span className="font-medium mr-1">Duration:</span>
              <span>{execution.elapsed_time}</span>
            </div>
          </div>
        </div>

        <div className="bg-base-100 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-bold mb-4">Execution Flow</h2>
          <ExecutionDAG tasks={validTasks} />
        </div>

        {/* Execution Note (if available) */}
        {execution.note &&
          typeof execution.note === "object" &&
          Object.keys(execution.note).length > 0 && (
            <div className="bg-base-100 rounded-lg shadow-md p-6">
              <div className="collapse collapse-arrow border border-base-300">
                <input type="checkbox" />
                <div className="collapse-title text-lg font-semibold">Execution Note</div>
                <div className="collapse-content">
                  <div className="pt-4 space-y-4">
                    <div className="flex justify-end">
                      <button
                        onClick={() => {
                          const jsonStr = JSON.stringify(execution.note, null, 2);
                          const blob = new Blob([jsonStr], {
                            type: "application/json",
                          });
                          const url = URL.createObjectURL(blob);
                          const link = document.createElement("a");
                          link.href = url;
                          link.download = `execution_note_${chipId}_${executionId}.json`;
                          document.body.appendChild(link);
                          link.click();
                          document.body.removeChild(link);
                          URL.revokeObjectURL(url);
                        }}
                        className="btn btn-sm btn-primary gap-2"
                      >
                        <Download size={14} />
                        Download JSON
                      </button>
                    </div>
                    <pre className="bg-base-200 p-4 rounded-lg overflow-x-auto text-xs max-h-96">
                      <code>{JSON.stringify(execution.note, null, 2)}</code>
                    </pre>
                  </div>
                </div>
              </div>
            </div>
          )}

        <div className="bg-base-100 rounded-lg shadow-md p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 mb-4">
            <div>
              <h2 className="text-lg sm:text-xl font-bold">Task Topology</h2>
              <p className="mt-1 text-xs text-base-content/60">
                {filteredTasks.length} {topologyMode === "2q" ? "coupling" : "one-qubit"} tasks
                shown on the chip layout
              </p>
            </div>
            <div className="tabs tabs-boxed bg-base-200 w-fit">
              <button
                type="button"
                className={`tab ${topologyMode === "1q" ? "tab-active" : ""}`}
                onClick={() => {
                  setTopologyMode("1q");
                  setFilterTaskName("");
                }}
              >
                Qubit
              </button>
              <button
                type="button"
                className={`tab ${topologyMode === "2q" ? "tab-active" : ""}`}
                onClick={() => {
                  setTopologyMode("2q");
                  setFilterTaskName("");
                }}
              >
                Coupling
              </button>
            </div>
          </div>

          {/* Filter Controls */}
          <div className="flex flex-col sm:flex-row gap-2 sm:gap-4 mb-4">
            <div className="form-control flex-1 min-w-0">
              <label className="label py-1">
                <span className="label-text text-xs font-semibold">Task Name</span>
              </label>
              <Select<FilterOption, false>
                className="text-sm"
                classNamePrefix="react-select"
                options={taskFilterOptions}
                value={taskFilterOptions.find((option) => option.value === filterTaskName) ?? null}
                onChange={(option: SingleValue<FilterOption>) => {
                  setFilterTaskName(option?.value ?? "");
                }}
                placeholder="Select task"
                isSearchable
                styles={filterSelectStyles}
              />
            </div>
          </div>

          <ExecutionTopologyView
            chipId={chipId}
            tasks={execution.task || []}
            topologyMode={topologyMode}
            filterTaskName={filterTaskName}
          />
        </div>
      </div>

      {/* Cancel Confirmation Modal */}
      {showCancelConfirm && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Cancel Execution</h3>
            <p className="py-4">
              Are you sure you want to cancel this execution? This action cannot be undone.
            </p>
            {cancelMutation.isError && (
              <div className="alert alert-error mb-4">
                <XCircle size={16} />
                <span>
                  {(
                    cancelMutation.error as {
                      response?: { data?: { detail?: string } };
                    }
                  )?.response?.data?.detail || "Failed to cancel execution"}
                </span>
              </div>
            )}
            <div className="modal-action">
              <button
                className="btn btn-ghost"
                onClick={() => setShowCancelConfirm(false)}
                disabled={cancelMutation.isPending}
              >
                Close
              </button>
              <button
                className="btn btn-error"
                onClick={handleCancel}
                disabled={cancelMutation.isPending}
              >
                {cancelMutation.isPending ? (
                  <span className="loading loading-spinner loading-sm" />
                ) : (
                  "Cancel Execution"
                )}
              </button>
            </div>
          </div>
          <div
            className="modal-backdrop"
            onClick={() => !cancelMutation.isPending && setShowCancelConfirm(false)}
          />
        </div>
      )}

      {/* Cancel success alert */}
      {cancelMutation.isSuccess && (
        <div className="toast toast-end">
          <div className="alert alert-success">
            <CheckCircle size={16} />
            <span>Cancellation requested successfully</span>
          </div>
        </div>
      )}
    </div>
  );
}
