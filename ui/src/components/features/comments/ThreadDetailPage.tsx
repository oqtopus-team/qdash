"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Lock, Unlock, Trash2, MessageSquare } from "lucide-react";
import { useGetTaskResult } from "@/client/task/task";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ParametersTable } from "@/components/features/metrics/ParametersTable";
import { formatDateTime, formatRelativeTime } from "@/utils/datetime";
import { useCommentReplies, type ForumComment } from "@/hooks/useCommentsForum";
import {
  useGetComment,
  getGetCommentQueryKey,
  useCloseCommentThread,
  useReopenCommentThread,
} from "@/client/task-result/task-result";
import { useProject } from "@/contexts/ProjectContext";
import { useQueryClient } from "@tanstack/react-query";

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

export function ThreadDetailPage({ commentId }: { commentId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { isOwner } = useProject();
  const currentUser = getCurrentUsername();
  const [replyText, setReplyText] = useState("");

  // Fetch comment
  const { data: commentResponse, isLoading: commentLoading } = useGetComment(
    commentId,
    { query: { staleTime: 30_000 } },
  );
  const comment = commentResponse?.data ?? null;

  // Fetch task result (only when we have a task_id)
  const { data: taskResultResponse, isLoading: taskResultLoading } =
    useGetTaskResult(comment?.task_id ?? "", {
      query: { enabled: !!comment?.task_id },
    });
  const taskResult = taskResultResponse?.data;

  // Fetch replies
  const {
    replies,
    isLoading: repliesLoading,
    isSubmitting,
    addReply,
    deleteReply,
  } = useCommentReplies(commentId);

  // Close/Reopen mutations
  const closeMutation = useCloseCommentThread();
  const reopenMutation = useReopenCommentThread();

  const canManage = isOwner || currentUser === comment?.username;

  const handleClose = () => {
    closeMutation.mutate(
      { commentId },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getGetCommentQueryKey(commentId),
          });
        },
      },
    );
  };

  const handleReopen = () => {
    reopenMutation.mutate(
      { commentId },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getGetCommentQueryKey(commentId),
          });
        },
      },
    );
  };

  const handleAddReply = async () => {
    const trimmed = replyText.trim();
    if (!trimmed || !comment) return;
    await addReply(comment.task_id, trimmed);
    setReplyText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleAddReply();
    }
  };

  const handleDeleteReply = async (replyId: string) => {
    if (!comment) return;
    await deleteReply(comment.task_id, replyId);
  };

  // Loading state
  if (commentLoading) {
    return (
      <div className="flex justify-center py-16">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  // Not found
  if (!comment) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-4">
        <p className="text-base-content/60">Comment not found</p>
        <Link href="/forum" className="btn btn-sm btn-ghost">
          <ArrowLeft className="h-4 w-4" />
          Back to Comments
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* Back navigation + header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => router.push("/forum")}
          className="btn btn-sm btn-ghost btn-square"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex items-center gap-3 flex-wrap flex-1 min-w-0">
          <Link
            href={`/execution?task_id=${comment.task_id}`}
            className="font-mono text-sm font-semibold text-primary hover:underline truncate"
          >
            {comment.task_id}
          </Link>
          <div className="flex items-center gap-1.5">
            {taskResult && (
              <>
                <span className="badge badge-sm badge-neutral">
                  {taskResult.qid}
                </span>
                <StatusBadge status={taskResult.status} />
              </>
            )}
            {comment.is_closed && (
              <span className="badge badge-sm badge-ghost">Closed</span>
            )}
          </div>
        </div>
        {canManage &&
          (comment.is_closed ? (
            <button
              onClick={handleReopen}
              className="btn btn-sm btn-ghost gap-1"
              disabled={reopenMutation.isPending}
            >
              <Unlock className="h-3.5 w-3.5" />
              Reopen
            </button>
          ) : (
            <button
              onClick={handleClose}
              className="btn btn-sm btn-ghost gap-1"
              disabled={closeMutation.isPending}
            >
              <Lock className="h-3.5 w-3.5" />
              Close
            </button>
          ))}
      </div>

      {/* Task Result Summary */}
      {taskResultLoading ? (
        <div className="flex justify-center py-8">
          <span className="loading loading-spinner loading-md"></span>
        </div>
      ) : (
        taskResult && (
          <div className="space-y-4 mb-6">
            {/* Task info */}
            <div className="bg-base-200/50 rounded-lg p-4">
              <h2 className="text-sm font-semibold mb-2">
                {taskResult.task_name}
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div>
                  <span className="text-base-content/50">Execution ID</span>
                  <p
                    className="font-mono truncate"
                    title={taskResult.execution_id}
                  >
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
              <div className="h-[220px] overflow-x-auto flex gap-2">
                <TaskFigure
                  taskId={comment.task_id}
                  qid={taskResult.qid}
                  className="h-full w-auto object-contain rounded"
                />
              </div>
            )}

            {/* Input Parameters */}
            {taskResult.input_parameters &&
              Object.keys(taskResult.input_parameters).length > 0 && (
                <ParametersTable
                  title="Input Parameters"
                  parameters={
                    taskResult.input_parameters as Record<string, unknown>
                  }
                />
              )}

            {/* Output Parameters */}
            {taskResult.output_parameters &&
              Object.keys(taskResult.output_parameters).length > 0 && (
                <ParametersTable
                  title="Output Parameters"
                  parameters={
                    taskResult.output_parameters as Record<string, unknown>
                  }
                />
              )}

            {/* Run Parameters */}
            {taskResult.run_parameters &&
              Object.keys(taskResult.run_parameters).length > 0 && (
                <ParametersTable
                  title="Run Parameters"
                  parameters={
                    taskResult.run_parameters as Record<string, unknown>
                  }
                />
              )}
          </div>
        )
      )}

      {/* Divider */}
      <div className="divider text-xs text-base-content/40">
        <MessageSquare className="h-3.5 w-3.5" />
        Conversation
      </div>

      {/* Root comment */}
      <div className="bg-base-100 rounded-lg border border-base-300 p-4 mb-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="badge badge-sm badge-neutral">
            {comment.username}
          </span>
          <span className="text-xs text-base-content/40">
            {formatRelativeTime(comment.created_at)}
          </span>
        </div>
        <p className="text-sm text-base-content/80 whitespace-pre-wrap">
          {comment.content}
        </p>
      </div>

      {/* Replies */}
      <div className="ml-4 border-l-2 border-base-300 pl-4 space-y-2 mb-4">
        {repliesLoading ? (
          <div className="flex justify-center py-3">
            <span className="loading loading-spinner loading-sm"></span>
          </div>
        ) : replies.length > 0 ? (
          replies.map((reply: ForumComment) => (
            <div
              key={reply.id}
              className="bg-base-100 rounded-md border border-base-300 px-3 py-2 text-sm"
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="badge badge-xs badge-neutral">
                    {reply.username}
                  </span>
                  <span className="text-xs text-base-content/40">
                    {formatRelativeTime(reply.created_at)}
                  </span>
                </div>
                {currentUser === reply.username && (
                  <button
                    onClick={() => handleDeleteReply(reply.id)}
                    className="btn btn-ghost btn-xs p-0 h-auto min-h-0 text-base-content/30 hover:text-error"
                    title="Delete reply"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </div>
              <p className="text-base-content/80 whitespace-pre-wrap">
                {reply.content}
              </p>
            </div>
          ))
        ) : (
          <p className="text-xs text-base-content/40 py-2">No replies yet</p>
        )}
      </div>

      {/* Reply input */}
      <div className="ml-4 pl-4 flex gap-2 pb-8">
        <textarea
          className="textarea textarea-bordered flex-1 min-h-[3rem] resize-none text-sm"
          placeholder="Write a reply... (Ctrl+Enter to submit)"
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
        />
        <button
          className="btn btn-sm btn-primary self-end"
          disabled={isSubmitting || !replyText.trim()}
          onClick={handleAddReply}
        >
          {isSubmitting ? (
            <span className="loading loading-spinner loading-xs"></span>
          ) : (
            "Reply"
          )}
        </button>
      </div>
    </div>
  );
}
