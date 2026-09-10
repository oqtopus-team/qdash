"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  MessageSquare,
  Plus,
  Lock,
  Unlock,
  RefreshCw,
  ExternalLink,
  CheckCircle,
  UserRound,
  Pencil,
} from "lucide-react";
import { useGetTaskResult } from "@/client/task/task";
import { useCreateIssue, getGetTaskResultIssuesQueryKey } from "@/client/issue/issue";
import { useQueryClient } from "@tanstack/react-query";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ExecutionTaskProgress } from "@/components/features/execution/ExecutionTaskProgress";
import { TaskArtifactDownloads } from "@/components/features/chip/TaskArtifactDownloads";
import { SpectroscopyManualCorrection } from "@/components/features/task-results/SpectroscopyManualCorrection";
import { CalibrationGitHubSyncNotice } from "@/components/features/task-results/CalibrationGitHubSyncNotice";
import type { CalibrationGitHubSync } from "@/schemas";
import { ParametersTable } from "@/components/features/metrics/ParametersTable";
import { TaskResultAiReviewNote } from "@/components/features/metrics/TaskResultAiReviewNote";
import { TaskResultMemo } from "@/components/features/metrics/TaskResultMemo";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";
import { TaskMessagePanel } from "@/components/ui/TaskMessagePanel";
import { useImageUpload } from "@/hooks/useImageUpload";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  useTaskResultIssues,
  type StatusFilter,
  type TaskResultIssue,
} from "@/hooks/useTaskResultIssues";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { formatDateTime, formatRelativeTime } from "@/lib/utils/datetime";

const REANALYZABLE_TASKS = new Set(["CheckResonatorSpectroscopy", "CheckQubitSpectroscopy"]);

type ActorFields = {
  user_id?: string | null;
  username?: string;
};

function formatActorLabel(actor?: ActorFields | null) {
  if (actor?.username) return `@${actor.username}`;
  return actor?.user_id || "Unknown";
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "success"
      ? "badge-success"
      : status === "failed"
        ? "badge-error"
        : status === "running"
          ? "badge-warning"
          : "badge-ghost";
  return <span className={`badge badge-sm ${color}`}>{status}</span>;
}

function IssueCard({
  issue,
  onClose,
  onReopen,
  canManage,
}: {
  issue: TaskResultIssue;
  onClose: (id: string) => void;
  onReopen: (id: string) => void;
  canManage: boolean;
}) {
  const router = useRouter();

  return (
    <div
      onClick={() => router.push(`/issues/${issue.id}`)}
      className={`bg-base-100 rounded-lg border border-base-300 cursor-pointer hover:border-primary/50 transition-colors ${issue.is_closed === true ? "opacity-70" : ""}`}
    >
      <div className="p-4">
        <div className="flex items-center gap-3 mb-2 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="badge badge-sm badge-neutral">{issue.username}</span>
            <span className="text-xs text-base-content/40">
              {formatRelativeTime(issue.created_at)}
            </span>
            {issue.is_closed === true && <span className="badge badge-sm badge-ghost">Closed</span>}
          </div>
          <span className="text-xs text-base-content/50 flex items-center gap-1 ml-auto">
            <MessageSquare className="h-3 w-3" />
            {issue.reply_count ?? 0} {issue.reply_count === 1 ? "reply" : "replies"}
          </span>
        </div>
        {issue.title && <h3 className="text-sm font-semibold mb-1">{issue.title}</h3>}
        <div className="text-sm text-base-content/80 mb-3 line-clamp-3">
          <MarkdownContent content={issue.content} preview />
        </div>
        <div className="flex items-center gap-3">
          {canManage &&
            (issue.is_closed === true ? (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onReopen(issue.id);
                }}
                className="btn btn-ghost btn-xs gap-1"
              >
                <Unlock className="h-3 w-3" />
                Reopen
              </button>
            ) : (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onClose(issue.id);
                }}
                className="btn btn-ghost btn-xs gap-1"
              >
                <Lock className="h-3 w-3" />
                Close
              </button>
            ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Full page view of a single task result.
 *
 * Shows figures, artifacts, and parameters, and links to the task workbench for re-execution.
 * Also hosts the AI review note, the memo editor, and linked issues.
 */
export function TaskResultDetailPage({ taskId }: { taskId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { username: currentUser } = useAuth();
  const { isOwner } = useProject();
  const [showEditor, setShowEditor] = useState(false);
  const [newIssueTitle, setNewIssueTitle] = useState("");
  const [newIssueContent, setNewIssueContent] = useState("");
  const { uploadImage } = useImageUpload();
  // Task result
  const { data: taskResultResponse, isLoading: taskResultLoading } = useGetTaskResult(taskId, {
    query: {
      enabled: !!taskId,
      refetchInterval: (query) => {
        const status = query.state.data?.data.status;
        return status === "running" || status === "scheduled" || status === "pending"
          ? 2000
          : false;
      },
      refetchIntervalInBackground: true,
    },
  });
  const taskResult = taskResultResponse?.data;

  // Issues
  const {
    issues,
    total,
    isLoading: issuesLoading,
    statusFilter,
    setStatusFilter,
    closeIssue,
    reopenIssue,
    invalidateList,
  } = useTaskResultIssues(taskId);

  // Create issue
  const createMutation = useCreateIssue();

  const handleCreateIssue = async () => {
    const trimmedTitle = newIssueTitle.trim();
    const trimmedContent = newIssueContent.trim();
    if (!trimmedTitle || !trimmedContent) return;
    await createMutation.mutateAsync({
      taskId,
      data: { title: trimmedTitle, content: trimmedContent, parent_id: null },
    });
    setNewIssueTitle("");
    setNewIssueContent("");
    setShowEditor(false);
    invalidateList();
    queryClient.invalidateQueries({
      queryKey: getGetTaskResultIssuesQueryKey(taskId),
    });
  };

  const canReExecute = !!taskResult;

  if (taskResultLoading) {
    return (
      <div className="flex justify-center py-16">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  // Not found
  if (!taskResult) {
    return (
      <EmptyState
        title="Task result not found"
        description="The requested task result does not exist or has been removed."
        emoji="magnifying-glass"
        action={
          <button onClick={() => router.back()} className="btn btn-sm btn-ghost gap-1">
            <ArrowLeft className="h-4 w-4" />
            Go back
          </button>
        }
      />
    );
  }

  const manualCorrections = (taskResult.re_executions ?? []).filter(
    (result) => result.task_name === "ManualParameterEdit",
  );
  const relatedExecutions = (taskResult.re_executions ?? []).filter(
    (result) => result.task_name !== "ManualParameterEdit",
  );

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => router.back()} className="btn btn-sm btn-ghost btn-square">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex items-center gap-3 flex-wrap flex-1 min-w-0">
          <span className="font-mono text-sm font-semibold truncate">{taskId}</span>
          <span className="badge badge-sm badge-neutral">{taskResult.qid}</span>
          <StatusBadge status={taskResult.status} />
          {canReExecute && (
            <button
              onClick={() => router.push(`/tasks?sourceTaskId=${encodeURIComponent(taskId)}`)}
              className="btn btn-sm btn-primary gap-1 ml-auto"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Re-execute
            </button>
          )}
        </div>
      </div>

      {/* Task Info Box */}
      {taskResult.task_name === "ManualParameterEdit" && taskResult.status === "completed" && (
        <CalibrationGitHubSyncNotice
          key={taskId}
          result={{
            task_id: taskId,
            github_sync: taskResult.note?.github_sync as CalibrationGitHubSync | undefined,
          }}
        />
      )}
      {taskResult.task_name === "ManualParameterEdit" && (
        <div className="mb-4 overflow-hidden rounded-xl border border-success/30 bg-success/5">
          <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-success/15 p-2 text-success">
                <CheckCircle size={18} />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-semibold">Manual correction applied</h2>
                  <span className="badge badge-sm badge-success">Calibration DB updated</span>
                </div>
                <p className="mt-1 text-xs text-base-content/60">
                  {Object.keys(taskResult.output_parameters ?? {}).length} calibration
                  {Object.keys(taskResult.output_parameters ?? {}).length === 1
                    ? " value was"
                    : " values were"}{" "}
                  manually corrected. The source measurement remains unchanged.
                </p>
              </div>
            </div>
            {taskResult.source_task_id && (
              <a
                href={`/task-results/${taskResult.source_task_id}`}
                className="btn btn-sm btn-outline shrink-0 gap-2"
              >
                View source result
                <ExternalLink size={14} />
              </a>
            )}
          </div>
        </div>
      )}

      <div className="bg-base-200/50 rounded-lg p-4 mb-4">
        <h2 className="text-sm font-semibold mb-2">{taskResult.task_name}</h2>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
          <div>
            <span className="text-base-content/50">Execution ID</span>
            <p className="font-mono truncate" title={taskResult.execution_id}>
              {taskResult.execution_id}
            </p>
          </div>
          <div>
            <span className="text-base-content/50">User</span>
            <p className="inline-flex max-w-full items-center gap-1 truncate">
              <UserRound className="h-3 w-3 flex-shrink-0" />
              <span className="truncate">{formatActorLabel(taskResult)}</span>
            </p>
          </div>
          <div>
            <span className="text-base-content/50">Start</span>
            <p>
              {formatDateTime(taskResult.start_at as string | null | undefined, "MM/dd HH:mm:ss")}
            </p>
          </div>
          <div>
            <span className="text-base-content/50">End</span>
            <p>
              {formatDateTime(taskResult.end_at as string | null | undefined, "MM/dd HH:mm:ss")}
            </p>
          </div>
          <div>
            <span className="text-base-content/50">Elapsed</span>
            <p>{taskResult.elapsed_time != null ? `${taskResult.elapsed_time}s` : "-"}</p>
          </div>
        </div>
      </div>

      <ExecutionTaskProgress status={taskResult.status} note={taskResult.note} />

      {/* Cross-references: parent and children */}
      {(taskResult.source_task_id ||
        (taskResult.re_executions && taskResult.re_executions.length > 0)) && (
        <div className="bg-base-200/50 rounded-lg p-4 mb-4 space-y-3">
          {/* Parent: re-executed from */}
          {taskResult.source_task_id && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-base-content/50">
                {taskResult.task_name === "ManualParameterEdit"
                  ? "Corrected from:"
                  : "Created from:"}
              </span>
              <a
                href={`/task-results/${taskResult.source_task_id}`}
                className="font-mono text-primary hover:underline"
              >
                {taskResult.source_task_id.slice(0, 8)}...
                <ExternalLink className="h-3 w-3 inline ml-1" />
              </a>
            </div>
          )}
          {manualCorrections.length > 0 && (
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-base-content/60">
                <Pencil className="h-3 w-3" />
                Manual corrections ({manualCorrections.length})
              </h3>
              <div className="space-y-1">
                {manualCorrections.map((correction) => (
                  <a
                    key={correction.task_id}
                    href={`/task-results/${correction.task_id}`}
                    className="flex items-center gap-2 rounded-lg border border-success/20 bg-success/5 p-2.5 text-xs transition-colors hover:bg-success/10"
                  >
                    <span className="font-medium">Manual correction</span>
                    <span className="font-mono text-primary">
                      {correction.task_id.slice(0, 8)}...
                    </span>
                    <StatusBadge status={correction.status} />
                    <span className="text-base-content/40">
                      {correction.start_at ? formatRelativeTime(correction.start_at as string) : ""}
                    </span>
                    <ExternalLink className="h-3 w-3 text-base-content/30 ml-auto" />
                  </a>
                ))}
              </div>
            </div>
          )}
          {relatedExecutions.length > 0 && (
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-base-content/50">
                <RefreshCw className="h-3 w-3" />
                Related executions ({relatedExecutions.length})
              </h3>
              <div className="space-y-1">
                {relatedExecutions.map((execution) => (
                  <a
                    key={execution.task_id}
                    href={`/task-results/${execution.task_id}`}
                    className="flex items-center gap-2 rounded p-2 text-xs transition-colors hover:bg-base-200"
                  >
                    <span className="font-mono text-primary">
                      {execution.task_id.slice(0, 8)}...
                    </span>
                    <span className="badge badge-sm badge-outline">{execution.task_name}</span>
                    <StatusBadge status={execution.status} />
                    <span className="text-base-content/40">
                      {execution.start_at ? formatRelativeTime(execution.start_at as string) : ""}
                    </span>
                    <ExternalLink className="ml-auto h-3 w-3 text-base-content/30" />
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {((taskResult.json_figure_path && taskResult.json_figure_path.length > 0) ||
        (taskResult.raw_data_path && taskResult.raw_data_path.length > 0)) && (
        <div className="mb-4 rounded-lg bg-base-200/50 p-4">
          <h2 className="mb-3 text-sm font-semibold">Artifacts</h2>
          <TaskArtifactDownloads
            jsonFigurePaths={taskResult.json_figure_path}
            rawDataPaths={taskResult.raw_data_path}
          />
        </div>
      )}

      {/* Figure */}
      {((taskResult.figure_path && taskResult.figure_path.length > 0) ||
        (taskResult.json_figure_path && taskResult.json_figure_path.length > 0)) && (
        <div className="h-[280px] overflow-x-auto overflow-y-hidden flex items-center justify-start gap-3 mb-4">
          {(taskResult.figure_path ?? []).map((fig, i) => (
            <TaskFigure
              key={i}
              path={fig}
              jsonFigurePath={(taskResult.json_figure_path ?? [])[i]}
              qid={taskResult.qid}
              className="h-full w-auto object-contain rounded flex-shrink-0"
            />
          ))}
        </div>
      )}

      {/* Parameters */}
      <div className="space-y-4 mb-6">
        {taskResult.input_parameters && Object.keys(taskResult.input_parameters).length > 0 && (
          <ParametersTable
            title="Input Parameters"
            parameters={taskResult.input_parameters as Record<string, unknown>}
          />
        )}

        {taskResult.output_parameters && Object.keys(taskResult.output_parameters).length > 0 && (
          <ParametersTable
            title="Output Parameters"
            parameters={taskResult.output_parameters as Record<string, unknown>}
          />
        )}

        {taskResult.chip_id && REANALYZABLE_TASKS.has(taskResult.task_name) && (
          <SpectroscopyManualCorrection
            chipId={taskResult.chip_id}
            qid={taskResult.qid}
            taskId={taskResult.task_id}
            taskName={taskResult.task_name}
            taskStatus={taskResult.status}
            outputParameters={(taskResult.output_parameters ?? {}) as Record<string, unknown>}
            outputParameterNames={taskResult.output_parameter_names ?? []}
            jsonFigurePaths={taskResult.json_figure_path ?? []}
          />
        )}

        {taskResult.run_parameters && Object.keys(taskResult.run_parameters).length > 0 && (
          <ParametersTable
            title="Run Parameters"
            parameters={taskResult.run_parameters as Record<string, unknown>}
          />
        )}

        <TaskMessagePanel
          status={taskResult.status}
          message={taskResult.message}
          stackTrace={taskResult.stack_trace}
        />
      </div>

      <TaskResultAiReviewNote note={taskResult.ai_review_note} hideWhenEmpty />
      <TaskResultMemo taskId={taskId} chipId={taskResult.chip_id} />

      {/* Divider: Issues */}
      <div className="divider text-xs text-base-content/40">
        <MessageSquare className="h-3.5 w-3.5" />
        Issues ({total})
      </div>

      {/* Issues toolbar */}
      <div className="flex items-center justify-between mb-4">
        <div className="tabs tabs-boxed w-fit">
          {(["open", "closed", "all"] as const).map((status) => (
            <button
              key={status}
              className={`tab tab-sm ${statusFilter === status ? "tab-active" : ""}`}
              onClick={() => setStatusFilter(status as StatusFilter)}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>
        <button className="btn btn-sm btn-primary gap-1" onClick={() => setShowEditor(!showEditor)}>
          <Plus className="h-3.5 w-3.5" />
          New Issue
        </button>
      </div>

      {/* New issue editor */}
      {showEditor && (
        <div className="mb-4 border border-base-300 rounded-lg p-4 bg-base-100 space-y-3">
          <input
            type="text"
            className="input input-bordered w-full"
            placeholder="Issue title"
            value={newIssueTitle}
            onChange={(e) => setNewIssueTitle(e.target.value)}
            maxLength={200}
          />
          <MarkdownEditor
            value={newIssueContent}
            onChange={setNewIssueContent}
            onSubmit={handleCreateIssue}
            placeholder="Describe the issue... (Ctrl+Enter to submit)"
            rows={4}
            submitLabel="Submit Issue"
            isSubmitting={createMutation.isPending}
            onImageUpload={uploadImage}
          />
        </div>
      )}

      {/* Issues list */}
      {issuesLoading ? (
        <div className="flex justify-center py-8">
          <span className="loading loading-spinner loading-md"></span>
        </div>
      ) : issues.length === 0 ? (
        <EmptyState
          title="No issues"
          description={
            statusFilter !== "all"
              ? `No ${statusFilter} issues for this task.`
              : "No issues have been created for this task yet."
          }
          emoji="speech-balloon"
          size="sm"
        />
      ) : (
        <div className="space-y-3 pb-8">
          {issues.map((issue) => (
            <IssueCard
              key={issue.id}
              issue={issue}
              onClose={closeIssue}
              onReopen={reopenIssue}
              canManage={isOwner || currentUser === issue.username}
            />
          ))}
        </div>
      )}
    </div>
  );
}
