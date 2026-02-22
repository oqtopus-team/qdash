"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, MessageSquare, Plus, Lock, Unlock } from "lucide-react";
import { useGetTaskResult } from "@/client/task/task";
import {
  useCreateIssue,
  getGetTaskResultIssuesQueryKey,
} from "@/client/issue/issue";
import { useQueryClient } from "@tanstack/react-query";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ParametersTable } from "@/components/features/metrics/ParametersTable";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";
import { useImageUpload } from "@/hooks/useImageUpload";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  useTaskResultIssues,
  type StatusFilter,
  type TaskResultIssue,
} from "@/hooks/useTaskResultIssues";
import { useProject } from "@/contexts/ProjectContext";
import { formatDateTime, formatRelativeTime } from "@/lib/utils/datetime";

function getCurrentUsername(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith("username="));
  return match ? decodeURIComponent(match.split("=")[1]) : "";
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
            <span className="badge badge-sm badge-neutral">
              {issue.username}
            </span>
            <span className="text-xs text-base-content/40">
              {formatRelativeTime(issue.created_at)}
            </span>
            {issue.is_closed === true && (
              <span className="badge badge-sm badge-ghost">Closed</span>
            )}
          </div>
          <span className="text-xs text-base-content/50 flex items-center gap-1 ml-auto">
            <MessageSquare className="h-3 w-3" />
            {issue.reply_count ?? 0}{" "}
            {issue.reply_count === 1 ? "reply" : "replies"}
          </span>
        </div>
        {issue.title && (
          <h3 className="text-sm font-semibold mb-1">{issue.title}</h3>
        )}
        <div className="text-sm text-base-content/80 mb-3 line-clamp-3">
          <MarkdownContent content={issue.content} />
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

export function TaskResultDetailPage({ taskId }: { taskId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { isOwner } = useProject();
  const currentUser = getCurrentUsername();
  const [showEditor, setShowEditor] = useState(false);
  const [newIssueTitle, setNewIssueTitle] = useState("");
  const [newIssueContent, setNewIssueContent] = useState("");
  const { uploadImage } = useImageUpload();

  // Task result
  const { data: taskResultResponse, isLoading: taskResultLoading } =
    useGetTaskResult(taskId, {
      query: { enabled: !!taskId },
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

  // Loading
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
          <button
            onClick={() => router.back()}
            className="btn btn-sm btn-ghost gap-1"
          >
            <ArrowLeft className="h-4 w-4" />
            Go back
          </button>
        }
      />
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => router.back()}
          className="btn btn-sm btn-ghost btn-square"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex items-center gap-3 flex-wrap flex-1 min-w-0">
          <span className="font-mono text-sm font-semibold truncate">
            {taskId}
          </span>
          <span className="badge badge-sm badge-neutral">{taskResult.qid}</span>
          <StatusBadge status={taskResult.status} />
        </div>
      </div>

      {/* Task Info Box */}
      <div className="bg-base-200/50 rounded-lg p-4 mb-4">
        <h2 className="text-sm font-semibold mb-2">{taskResult.task_name}</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <span className="text-base-content/50">Execution ID</span>
            <p className="font-mono truncate" title={taskResult.execution_id}>
              {taskResult.execution_id}
            </p>
          </div>
          <div>
            <span className="text-base-content/50">Start</span>
            <p>
              {formatDateTime(
                taskResult.start_at as string | null | undefined,
                "MM/dd HH:mm:ss",
              )}
            </p>
          </div>
          <div>
            <span className="text-base-content/50">End</span>
            <p>
              {formatDateTime(
                taskResult.end_at as string | null | undefined,
                "MM/dd HH:mm:ss",
              )}
            </p>
          </div>
          <div>
            <span className="text-base-content/50">Elapsed</span>
            <p>
              {taskResult.elapsed_time != null
                ? `${taskResult.elapsed_time}s`
                : "-"}
            </p>
          </div>
        </div>
      </div>

      {/* Figure */}
      {((taskResult.figure_path && taskResult.figure_path.length > 0) ||
        (taskResult.json_figure_path &&
          taskResult.json_figure_path.length > 0)) && (
        <div className="h-[220px] overflow-x-auto flex gap-2 mb-4">
          <TaskFigure
            taskId={taskId}
            qid={taskResult.qid}
            className="h-full w-auto object-contain rounded"
          />
        </div>
      )}

      {/* Parameters */}
      <div className="space-y-4 mb-6">
        {taskResult.input_parameters &&
          Object.keys(taskResult.input_parameters).length > 0 && (
            <ParametersTable
              title="Input Parameters"
              parameters={
                taskResult.input_parameters as Record<string, unknown>
              }
            />
          )}

        {taskResult.output_parameters &&
          Object.keys(taskResult.output_parameters).length > 0 && (
            <ParametersTable
              title="Output Parameters"
              parameters={
                taskResult.output_parameters as Record<string, unknown>
              }
            />
          )}

        {taskResult.run_parameters &&
          Object.keys(taskResult.run_parameters).length > 0 && (
            <ParametersTable
              title="Run Parameters"
              parameters={taskResult.run_parameters as Record<string, unknown>}
            />
          )}
      </div>

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
        <button
          className="btn btn-sm btn-primary gap-1"
          onClick={() => setShowEditor(!showEditor)}
        >
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
