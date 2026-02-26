"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Brain,
  Lock,
  Unlock,
  Trash2,
  MessageSquare,
  Pencil,
  Bot,
} from "lucide-react";
import { useGetTaskResult } from "@/client/task/task";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ParametersTable } from "@/components/features/metrics/ParametersTable";
import { formatDateTime, formatRelativeTime } from "@/lib/utils/datetime";
import { useIssueReplies } from "@/hooks/useIssues";
import { useIssueAiReply } from "@/hooks/useIssueAiReply";
import type { IssueResponse } from "@/schemas";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";
import { useImageUpload } from "@/hooks/useImageUpload";
import {
  useGetIssue,
  getGetIssueQueryKey,
  useCloseIssue,
  useReopenIssue,
} from "@/client/issue/issue";
import { useProject } from "@/contexts/ProjectContext";
import { useQueryClient } from "@tanstack/react-query";
import { useExtractKnowledge } from "@/hooks/useIssueKnowledge";

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

function isEdited(createdAt: string, updatedAt: string): boolean {
  return (
    Math.abs(new Date(updatedAt).getTime() - new Date(createdAt).getTime()) >
    1000
  );
}

export function IssueDetailPage({ issueId }: { issueId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { isOwner } = useProject();
  const currentUser = getCurrentUsername();
  const [replyText, setReplyText] = useState("");
  const [editingIssue, setEditingIssue] = useState(false);
  const [editIssueTitle, setEditIssueTitle] = useState("");
  const [editIssueContent, setEditIssueContent] = useState("");
  const [editingReplyId, setEditingReplyId] = useState<string | null>(null);
  const [editReplyContent, setEditReplyContent] = useState("");
  const { uploadImage } = useImageUpload();

  // Fetch issue
  const { data: issueResponse, isLoading: issueLoading } = useGetIssue(
    issueId,
    { query: { staleTime: 30_000 } },
  );
  const issue = issueResponse?.data ?? null;

  // Fetch task result (only when we have a task_id)
  const { data: taskResultResponse, isLoading: taskResultLoading } =
    useGetTaskResult(issue?.task_id ?? "", {
      query: { enabled: !!issue?.task_id },
    });
  const taskResult = taskResultResponse?.data;

  // Fetch replies
  const {
    replies,
    isLoading: repliesLoading,
    isSubmitting,
    addReply,
    deleteReply,
    editReply,
    fetchReplies: invalidateReplies,
  } = useIssueReplies(issueId);

  // AI reply
  const {
    isGenerating,
    statusMessage: aiStatus,
    error: aiError,
    triggerAiReply,
  } = useIssueAiReply();

  // Close/Reopen mutations
  const closeMutation = useCloseIssue();
  const reopenMutation = useReopenIssue();

  // Knowledge extraction
  const { extract: extractKnowledge, isExtracting } = useExtractKnowledge();

  const canManage = isOwner || currentUser === issue?.username;

  const handleClose = () => {
    closeMutation.mutate(
      { issueId: issueId },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getGetIssueQueryKey(issueId),
          });
        },
      },
    );
  };

  const handleReopen = () => {
    reopenMutation.mutate(
      { issueId: issueId },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getGetIssueQueryKey(issueId),
          });
        },
      },
    );
  };

  const handleAddReply = async () => {
    const trimmed = replyText.trim();
    if (!trimmed || !issue) return;
    await addReply(issue.task_id, trimmed);
    setReplyText("");
    if (/@qdash\b/i.test(trimmed)) {
      triggerAiReply(issueId, trimmed, invalidateReplies);
    }
  };

  const handleDeleteReply = async (replyId: string) => {
    if (!issue) return;
    await deleteReply(issue.task_id, replyId);
  };

  const handleStartEditIssue = () => {
    if (!issue) return;
    setEditIssueTitle(issue.title ?? "");
    setEditIssueContent(issue.content);
    setEditingIssue(true);
  };

  const handleSaveEditIssue = async () => {
    if (!issue) return;
    const trimmed = editIssueContent.trim();
    if (!trimmed) return;
    await editReply(issueId, trimmed, editIssueTitle || null);
    setEditingIssue(false);
  };

  const handleStartEditReply = (reply: IssueResponse) => {
    setEditReplyContent(reply.content);
    setEditingReplyId(reply.id);
  };

  const handleSaveEditReply = async () => {
    if (!editingReplyId) return;
    const trimmed = editReplyContent.trim();
    if (!trimmed) return;
    await editReply(editingReplyId, trimmed);
    setEditingReplyId(null);
  };

  // Loading state
  if (issueLoading) {
    return (
      <div className="flex justify-center py-16">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  // Not found
  if (!issue) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-4">
        <p className="text-base-content/60">Issue not found</p>
        <Link href="/issues" className="btn btn-sm btn-ghost">
          <ArrowLeft className="h-4 w-4" />
          Back to Issues
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* Back navigation + header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => router.push("/issues")}
          className="btn btn-sm btn-ghost btn-square"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex flex-col gap-1 flex-1 min-w-0">
          {issue.title != null &&
            (editingIssue ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  className="input input-bordered input-sm flex-1"
                  value={editIssueTitle}
                  onChange={(e) => setEditIssueTitle(e.target.value)}
                  placeholder="Title"
                />
                <button
                  className="btn btn-sm btn-ghost"
                  onClick={() => setEditingIssue(false)}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={handleSaveEditIssue}
                  disabled={!editIssueContent.trim()}
                >
                  Save
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 min-w-0">
                <h1 className="text-lg font-bold truncate">{issue.title}</h1>
                {currentUser === issue.username && (
                  <button
                    onClick={handleStartEditIssue}
                    className="btn btn-ghost btn-xs p-0 h-auto min-h-0 text-base-content/30 hover:text-primary shrink-0"
                    title="Edit issue"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
          <div className="flex items-center gap-3 flex-wrap">
            <Link
              href={`/task-results/${issue.task_id}`}
              className="font-mono text-sm font-semibold text-primary hover:underline truncate"
            >
              {issue.task_id}
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
              {issue.is_closed && (
                <span className="badge badge-sm badge-ghost">Closed</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {issue.is_closed && canManage && (
            <button
              onClick={() => {
                extractKnowledge(issueId).then(() => {
                  router.push("/issue-knowledge");
                });
              }}
              className="btn btn-sm btn-primary gap-1"
              disabled={isExtracting}
            >
              {isExtracting ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <Brain className="h-3.5 w-3.5" />
              )}
              Extract Knowledge
            </button>
          )}
          {canManage &&
            (issue.is_closed ? (
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
                  taskId={issue.task_id}
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

      {/* Root issue */}
      <div className="bg-base-100 rounded-lg border border-base-300 p-4 mb-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="badge badge-sm badge-neutral">{issue.username}</span>
          <span className="text-xs text-base-content/40">
            {formatRelativeTime(issue.created_at)}
          </span>
          {isEdited(issue.created_at, issue.updated_at) && (
            <span className="text-xs text-base-content/30 italic">
              (edited)
            </span>
          )}
        </div>
        {editingIssue ? (
          <MarkdownEditor
            value={editIssueContent}
            onChange={setEditIssueContent}
            onSubmit={handleSaveEditIssue}
            placeholder="Edit issue content..."
            rows={4}
            onImageUpload={uploadImage}
          />
        ) : (
          <MarkdownContent
            content={issue.content}
            className="text-sm text-base-content/80"
          />
        )}
      </div>

      {/* Replies */}
      <div className="ml-4 border-l-2 border-base-300 pl-4 space-y-2 mb-4">
        {repliesLoading ? (
          <div className="flex justify-center py-3">
            <span className="loading loading-spinner loading-sm"></span>
          </div>
        ) : replies.length > 0 ? (
          replies.map((reply: IssueResponse) => {
            const isAi = reply.username === "qdash-ai";
            return (
              <div
                key={reply.id}
                className={`rounded-md px-3 py-2 text-sm ${
                  isAi
                    ? "bg-primary/5 border border-primary/30"
                    : "bg-base-100 border border-base-300"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {isAi ? (
                      <span className="badge badge-xs badge-primary gap-1">
                        <Bot className="h-2.5 w-2.5" />
                        {reply.username}
                      </span>
                    ) : (
                      <span className="badge badge-xs badge-neutral">
                        {reply.username}
                      </span>
                    )}
                    <span className="text-xs text-base-content/40">
                      {formatRelativeTime(reply.created_at)}
                    </span>
                    {isEdited(reply.created_at, reply.updated_at) && (
                      <span className="text-xs text-base-content/30 italic">
                        (edited)
                      </span>
                    )}
                  </div>
                  {currentUser === reply.username &&
                    editingReplyId !== reply.id && (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleStartEditReply(reply)}
                          className="btn btn-ghost btn-xs p-0 h-auto min-h-0 text-base-content/30 hover:text-primary"
                          title="Edit reply"
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                        <button
                          onClick={() => handleDeleteReply(reply.id)}
                          className="btn btn-ghost btn-xs p-0 h-auto min-h-0 text-base-content/30 hover:text-error"
                          title="Delete reply"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                </div>
                {editingReplyId === reply.id ? (
                  <div className="space-y-2">
                    <MarkdownEditor
                      value={editReplyContent}
                      onChange={setEditReplyContent}
                      onSubmit={handleSaveEditReply}
                      placeholder="Edit reply..."
                      rows={3}
                      onImageUpload={uploadImage}
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        className="btn btn-sm btn-ghost"
                        onClick={() => setEditingReplyId(null)}
                      >
                        Cancel
                      </button>
                      <button
                        className="btn btn-sm btn-primary"
                        onClick={handleSaveEditReply}
                        disabled={!editReplyContent.trim()}
                      >
                        Save
                      </button>
                    </div>
                  </div>
                ) : (
                  <MarkdownContent
                    content={reply.content}
                    className="text-base-content/80"
                  />
                )}
              </div>
            );
          })
        ) : (
          <p className="text-xs text-base-content/40 py-2">No replies yet</p>
        )}
        {/* AI thinking indicator */}
        {isGenerating && (
          <div className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm animate-pulse">
            <div className="flex items-center gap-2">
              <span className="badge badge-xs badge-primary gap-1">
                <Bot className="h-2.5 w-2.5" />
                qdash-ai
              </span>
              <span className="loading loading-dots loading-xs" />
              <span className="text-xs text-base-content/60">{aiStatus}</span>
            </div>
          </div>
        )}
        {/* AI error */}
        {aiError && (
          <div className="text-xs text-error px-2 py-1">{aiError}</div>
        )}
      </div>

      {/* Reply input */}
      <div className="ml-4 pl-4 pb-8">
        <MarkdownEditor
          value={replyText}
          onChange={setReplyText}
          onSubmit={handleAddReply}
          placeholder="Write a reply... (@ to mention AI, Ctrl+Enter to submit)"
          rows={2}
          submitLabel="Reply"
          isSubmitting={isSubmitting || isGenerating}
          onImageUpload={uploadImage}
          mentionCandidates={[{ id: "qdash", label: "AI Assistant" }]}
        />
      </div>
    </div>
  );
}
