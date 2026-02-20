"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MessageSquare, ExternalLink, Plus, Lock, Unlock } from "lucide-react";
import {
  useCreateIssue,
  getGetTaskResultIssuesQueryKey,
} from "@/client/issue/issue";
import { useQueryClient } from "@tanstack/react-query";
import {
  useTaskResultIssues,
  type TaskResultIssue,
} from "@/hooks/useTaskResultIssues";
import { useProject } from "@/contexts/ProjectContext";
import { formatRelativeTime } from "@/utils/datetime";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";

function getCurrentUsername(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith("username="));
  return match ? decodeURIComponent(match.split("=")[1]) : "";
}

function IssueRow({
  issue,
  canManage,
  onClose,
  onReopen,
}: {
  issue: TaskResultIssue;
  canManage: boolean;
  onClose: (id: string) => void;
  onReopen: (id: string) => void;
}) {
  const router = useRouter();

  return (
    <div
      onClick={() => router.push(`/issues/${issue.id}`)}
      className={`bg-base-100 rounded-md px-3 py-2 text-xs cursor-pointer hover:bg-base-100/80 transition-colors ${issue.is_closed ? "opacity-60" : ""}`}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="badge badge-xs badge-neutral">{issue.username}</span>
          <span className="text-base-content/40">
            {formatRelativeTime(issue.created_at)}
          </span>
          {issue.is_closed && (
            <span className="badge badge-xs badge-ghost">Closed</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <span className="text-base-content/40 flex items-center gap-0.5">
            <MessageSquare className="h-2.5 w-2.5" />
            {issue.reply_count ?? 0}
          </span>
          {canManage &&
            (issue.is_closed ? (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onReopen(issue.id);
                }}
                className="btn btn-ghost btn-xs p-0 h-auto min-h-0 text-base-content/30 hover:text-success"
                title="Reopen"
              >
                <Unlock className="h-3 w-3" />
              </button>
            ) : (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onClose(issue.id);
                }}
                className="btn btn-ghost btn-xs p-0 h-auto min-h-0 text-base-content/30 hover:text-warning"
                title="Close"
              >
                <Lock className="h-3 w-3" />
              </button>
            ))}
        </div>
      </div>
      {issue.title && (
        <p className="font-semibold text-xs mb-0.5">{issue.title}</p>
      )}
      <div className="line-clamp-2">
        <MarkdownContent
          content={issue.content}
          className="text-base-content/80 text-xs"
        />
      </div>
    </div>
  );
}

interface TaskResultCommentsProps {
  taskId: string;
}

export function TaskResultComments({ taskId }: TaskResultCommentsProps) {
  const queryClient = useQueryClient();
  const { isOwner } = useProject();
  const currentUser = getCurrentUsername();
  const [showEditor, setShowEditor] = useState(false);
  const [newIssueTitle, setNewIssueTitle] = useState("");
  const [newIssue, setNewIssue] = useState("");

  const { issues, total, isLoading, closeIssue, reopenIssue, invalidateList } =
    useTaskResultIssues(taskId);

  const createMutation = useCreateIssue();

  const handleSubmit = async () => {
    const trimmedTitle = newIssueTitle.trim();
    const trimmed = newIssue.trim();
    if (!trimmedTitle || !trimmed) return;
    await createMutation.mutateAsync({
      taskId,
      data: { title: trimmedTitle, content: trimmed, parent_id: null },
    });
    setNewIssueTitle("");
    setNewIssue("");
    setShowEditor(false);
    invalidateList();
    queryClient.invalidateQueries({
      queryKey: getGetTaskResultIssuesQueryKey(taskId),
    });
  };

  return (
    <div className="mt-3 bg-base-200 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-base-content/60" />
          <h4 className="text-xs font-bold text-base-content/70">
            Issues ({total})
          </h4>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowEditor(!showEditor)}
            className="btn btn-ghost btn-xs gap-1 text-primary"
          >
            <Plus className="h-3 w-3" />
            New Issue
          </button>
          <Link
            href={`/task-results/${taskId}`}
            className="text-xs text-primary hover:underline flex items-center gap-1"
          >
            View all <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
      </div>

      {showEditor && (
        <div className="mb-3 space-y-2">
          <input
            type="text"
            className="input input-bordered input-sm w-full"
            placeholder="Issue title"
            value={newIssueTitle}
            onChange={(e) => setNewIssueTitle(e.target.value)}
            maxLength={200}
          />
          <MarkdownEditor
            value={newIssue}
            onChange={setNewIssue}
            onSubmit={handleSubmit}
            placeholder="Describe the issue... (Ctrl+Enter to submit)"
            rows={2}
            submitLabel="Submit"
            isSubmitting={createMutation.isPending}
          />
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-4">
          <span className="loading loading-spinner loading-sm"></span>
        </div>
      ) : issues.length === 0 ? (
        <p className="text-xs text-base-content/40 py-2">No issues yet</p>
      ) : (
        <div className="space-y-2 max-h-60 overflow-y-auto">
          {issues.map((issue) => (
            <IssueRow
              key={issue.id}
              issue={issue}
              canManage={isOwner || currentUser === issue.username}
              onClose={closeIssue}
              onReopen={reopenIssue}
            />
          ))}
        </div>
      )}
    </div>
  );
}
