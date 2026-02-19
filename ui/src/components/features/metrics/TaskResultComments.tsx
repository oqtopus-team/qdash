"use client";

import React, { useState } from "react";
import Link from "next/link";
import { MessageSquare, Trash2, ExternalLink } from "lucide-react";
import { useTaskResultComments } from "@/hooks/useTaskResultComments";
import { formatRelativeTime } from "@/utils/datetime";

function getCurrentUsername(): string {
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith("username="));
  return match ? decodeURIComponent(match.split("=")[1]) : "";
}

interface TaskResultCommentsProps {
  taskId: string;
}

export function TaskResultComments({ taskId }: TaskResultCommentsProps) {
  const { comments, isLoading, isSubmitting, addComment, deleteComment } =
    useTaskResultComments(taskId);
  const [newComment, setNewComment] = useState("");
  const currentUser = getCurrentUsername();

  const handleSubmit = async () => {
    const trimmed = newComment.trim();
    if (!trimmed) return;
    await addComment(trimmed);
    setNewComment("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="mt-3 bg-base-200 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-base-content/60" />
          <h4 className="text-xs font-bold text-base-content/70">
            Comments ({comments.length})
          </h4>
        </div>
        <Link
          href="/forum"
          className="text-xs text-primary hover:underline flex items-center gap-1"
        >
          View all <ExternalLink className="h-3 w-3" />
        </Link>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-4">
          <span className="loading loading-spinner loading-sm"></span>
        </div>
      ) : comments.length === 0 ? (
        <p className="text-xs text-base-content/40 py-2">No comments yet</p>
      ) : (
        <div className="space-y-2 mb-3 max-h-60 overflow-y-auto">
          {comments.map((comment) => (
            <div
              key={comment.id}
              className="bg-base-100 rounded-md px-3 py-2 text-xs"
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="badge badge-xs badge-neutral">
                    {comment.username}
                  </span>
                  <span className="text-base-content/40">
                    {formatRelativeTime(comment.created_at)}
                  </span>
                  {comment.is_closed && (
                    <span className="badge badge-xs badge-ghost">Closed</span>
                  )}
                </div>
                {currentUser === comment.username && (
                  <button
                    onClick={() => deleteComment(comment.id)}
                    className="btn btn-ghost btn-xs p-0 h-auto min-h-0 text-base-content/30 hover:text-error"
                    title="Delete comment"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </div>
              <p className="text-base-content/80 whitespace-pre-wrap">
                {comment.content}
              </p>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <textarea
          className="textarea textarea-bordered textarea-xs flex-1 min-h-[2.5rem] resize-none text-xs"
          placeholder="Add a comment... (Ctrl+Enter to submit)"
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
        />
        <button
          className="btn btn-xs btn-primary self-end"
          disabled={isSubmitting || !newComment.trim()}
          onClick={handleSubmit}
        >
          {isSubmitting ? (
            <span className="loading loading-spinner loading-xs"></span>
          ) : (
            "Add"
          )}
        </button>
      </div>
    </div>
  );
}
