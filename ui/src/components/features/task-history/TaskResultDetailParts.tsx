"use client";

import type { ReactNode } from "react";
import { ChevronRight, FileText, ListTodo } from "lucide-react";

import type { Task } from "@/schemas";

import {
  ParametersTable,
  type ParameterOverride,
} from "@/components/features/metrics/ParametersTable";
import { formatDateTimeCompact } from "@/lib/utils/datetime";

function hasEntries(parameters: object | null | undefined): boolean {
  return parameters != null && Object.keys(parameters).length > 0;
}

interface TaskParametersTablesProps {
  task: {
    input_parameters?: object | null;
    output_parameters?: object | null;
    run_parameters?: object | null;
  };
  /** Manual overrides shown against the output parameters. */
  outputOverrides?: Record<string, ParameterOverride>;
  className: string;
}

/** Input, output, and run parameter tables of a task result, omitting empty groups. */
export function TaskParametersTables({
  task,
  outputOverrides,
  className,
}: TaskParametersTablesProps) {
  return (
    <div className={className}>
      {hasEntries(task.input_parameters) && (
        <ParametersTable
          title="Input Parameters"
          parameters={task.input_parameters as Record<string, unknown>}
        />
      )}
      {hasEntries(task.output_parameters) && (
        <ParametersTable
          title="Output Parameters"
          parameters={task.output_parameters as Record<string, unknown>}
          overrides={outputOverrides}
        />
      )}
      {hasEntries(task.run_parameters) && (
        <ParametersTable
          title="Run Parameters"
          parameters={task.run_parameters as Record<string, unknown>}
        />
      )}
    </div>
  );
}

interface TaskDetailsHeaderProps {
  /** Position text such as "2 / 5", or null to show none. */
  position: ReactNode;
  /** Selected task among `total` tasks that Prev and Next step through. */
  index: number;
  total: number;
  onSelect: (index: number) => void;
}

/** "Task Details" heading with the selected position and Prev/Next for multiple tasks. */
export function TaskDetailsHeader({ position, index, total, onSelect }: TaskDetailsHeaderProps) {
  return (
    <>
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-base-content/60" />
          <h3 className="text-sm font-medium text-base-content">Task Details</h3>
        </div>
        {position != null && <div className="text-xs text-base-content/60">{position}</div>}
      </div>

      {total > 1 && (
        <div className="flex gap-2 mb-2 shrink-0">
          <button
            className="btn btn-xs btn-ghost"
            disabled={index === 0}
            onClick={() => onSelect(Math.max(0, index - 1))}
          >
            ← Prev
          </button>
          <button
            className="btn btn-xs btn-ghost"
            disabled={index === total - 1}
            onClick={() => onSelect(Math.min(total - 1, index + 1))}
          >
            Next →
          </button>
        </div>
      )}
    </>
  );
}

interface ExecutionTasksColumnProps {
  executionId: string | null;
  tasks: Task[];
  isLoading: boolean;
  /** Shows a failure message instead of the list; omit when failures are not reported. */
  isError?: boolean;
  /** Whether a listed task is the selected one. */
  isSelected: (task: Task, index: number) => boolean;
  onSelect: (index: number) => void;
  /** Task or metric name; tasks whose name contains it get a badge. */
  matchName: string;
  targetId: string;
  targetNoun: "qubit" | "coupling";
}

/** Middle column of a history modal: the target's tasks in the selected execution. */
export function ExecutionTasksColumn({
  executionId,
  tasks,
  isLoading,
  isError = false,
  isSelected: isTaskSelected,
  onSelect,
  matchName,
  targetId,
  targetNoun,
}: ExecutionTasksColumnProps) {
  return (
    <div className="flex flex-col min-h-0 h-full">
      <div className="mb-3 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <ListTodo className="h-4 w-4 text-base-content/60" />
          <h3 className="text-sm font-medium text-base-content">Tasks in Execution</h3>
        </div>
        {executionId && (
          <p className="text-xs text-base-content/50 font-mono truncate">{executionId}</p>
        )}
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <span className="loading loading-spinner loading-md"></span>
          </div>
        ) : isError ? (
          <div className="text-sm text-error py-4">Failed to load execution</div>
        ) : tasks.length === 0 ? (
          <div className="text-center py-8">
            <ListTodo className="h-8 w-8 mx-auto text-base-content/30 mb-2" />
            <p className="text-sm text-base-content/50">
              No {matchName}-related tasks found for {targetId}
            </p>
            <p className="text-xs text-base-content/40 mt-1">
              This execution may not include calibration for this {targetNoun}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {tasks.map((task, idx) => {
              const isSelected = isTaskSelected(task, idx);
              const isMatching = task.name?.toLowerCase().includes(matchName.toLowerCase());
              return (
                <button
                  key={task.task_id || `${task.name}-${idx}`}
                  onClick={() => onSelect(idx)}
                  className={`w-full text-left p-3 rounded-lg transition-all border-2 ${
                    isSelected
                      ? "bg-secondary text-secondary-content border-secondary"
                      : "bg-base-200 hover:bg-base-300 border-transparent hover:border-secondary/30"
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm truncate">
                          {task.name || "Unnamed"}
                        </span>
                        {isMatching && (
                          <span
                            className={`badge badge-xs ${
                              isSelected ? "badge-secondary-content" : "badge-accent"
                            }`}
                          >
                            {matchName}
                          </span>
                        )}
                      </div>
                      <div className="text-xs opacity-70 mt-1">
                        {task.start_at ? formatDateTimeCompact(String(task.start_at)) : ""}
                      </div>
                      <span
                        className={`badge badge-xs mt-1 ${
                          task.status === "completed"
                            ? "badge-success"
                            : task.status === "failed"
                              ? "badge-error"
                              : "badge-warning"
                        }`}
                      >
                        {task.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-xs opacity-60">#{idx + 1}</span>
                      <ChevronRight
                        className={`h-4 w-4 opacity-40 ${isSelected ? "opacity-80" : ""}`}
                      />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
