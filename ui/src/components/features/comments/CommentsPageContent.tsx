"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MessageSquare, Search, X, Lock, Unlock } from "lucide-react";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { useCommentsForum, type ForumComment } from "@/hooks/useCommentsForum";
import { useProject } from "@/contexts/ProjectContext";
import { formatRelativeTime } from "@/utils/datetime";

function getCurrentUsername(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith("username="));
  return match ? decodeURIComponent(match.split("=")[1]) : "";
}

function CommentThread({
  comment,
  onClose,
  onReopen,
  canManage,
}: {
  comment: ForumComment;
  onClose: (commentId: string) => void;
  onReopen: (commentId: string) => void;
  canManage: boolean;
}) {
  const router = useRouter();

  const handleCardClick = () => {
    router.push(`/forum/${comment.id}`);
  };

  return (
    <div
      onClick={handleCardClick}
      className={`bg-base-100 rounded-lg border border-base-300 cursor-pointer hover:border-primary/50 transition-colors ${comment.is_closed === true ? "opacity-70" : ""}`}
    >
      {/* Root comment */}
      <div className="p-4">
        <div className="flex items-center gap-3 mb-2 flex-wrap">
          <Link
            href={`/execution?task_id=${comment.task_id}`}
            onClick={(e) => e.stopPropagation()}
            className="font-mono text-xs font-semibold text-primary hover:underline"
          >
            {comment.task_id}
          </Link>
          <div className="flex items-center gap-1.5">
            <span className="badge badge-sm badge-neutral">
              {comment.username}
            </span>
            <span className="text-xs text-base-content/40">
              {formatRelativeTime(comment.created_at)}
            </span>
            {comment.is_closed === true && (
              <span className="badge badge-sm badge-ghost">Closed</span>
            )}
          </div>
        </div>
        <p className="text-sm text-base-content/80 whitespace-pre-wrap mb-3 line-clamp-3">
          {comment.content}
        </p>
        <div className="flex items-center gap-3">
          <span className="text-xs text-base-content/50 flex items-center gap-1">
            <MessageSquare className="h-3 w-3" />
            {comment.reply_count ?? 0}{" "}
            {comment.reply_count === 1 ? "reply" : "replies"}
          </span>
          {canManage &&
            (comment.is_closed === true ? (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onReopen(comment.id);
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
                  onClose(comment.id);
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

export function CommentsPageContent() {
  const {
    comments,
    total,
    skip,
    pageSize,
    isLoading,
    taskIdFilter,
    filterByTaskId,
    statusFilter,
    setStatusFilter,
    closeComment,
    reopenComment,
    goToPage,
  } = useCommentsForum();
  const { isOwner } = useProject();
  const [filterInput, setFilterInput] = useState("");
  const currentUser = getCurrentUsername();

  const currentPage = Math.floor(skip / pageSize);
  const totalPages = Math.ceil(total / pageSize);

  const handleFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    filterByTaskId(filterInput.trim());
  };

  const clearFilter = () => {
    setFilterInput("");
    filterByTaskId("");
  };

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Forum"
        description="View and discuss task results across your project"
      />

      {/* Status tabs */}
      <div className="mb-4">
        <div className="tabs tabs-boxed w-fit">
          {(["open", "closed", "all"] as const).map((status) => (
            <button
              key={status}
              className={`tab tab-sm ${statusFilter === status ? "tab-active" : ""}`}
              onClick={() => setStatusFilter(status)}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Filter bar */}
      <div className="mb-4">
        <form onSubmit={handleFilterSubmit} className="flex gap-2 items-center">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-base-content/40" />
            <input
              type="text"
              className="input input-bordered input-sm w-full pl-9 pr-8"
              placeholder="Filter by task ID..."
              value={filterInput}
              onChange={(e) => setFilterInput(e.target.value)}
            />
            {filterInput && (
              <button
                type="button"
                onClick={clearFilter}
                className="absolute right-2 top-1/2 -translate-y-1/2 btn btn-ghost btn-xs p-0 h-auto min-h-0"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
          <button type="submit" className="btn btn-sm btn-primary">
            Filter
          </button>
          {taskIdFilter && (
            <div className="flex items-center gap-1">
              <span className="badge badge-sm badge-outline">
                task: {taskIdFilter}
              </span>
              <button
                onClick={clearFilter}
                className="btn btn-ghost btn-xs p-0 h-auto min-h-0"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          )}
        </form>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      ) : comments.length === 0 ? (
        <EmptyState
          title="No comments yet"
          description={
            taskIdFilter
              ? "No comments found for this task. Try removing the filter."
              : "Comments on task results will appear here."
          }
          emoji="speech-balloon"
        />
      ) : (
        <>
          <div className="space-y-3">
            {comments.map((comment) => (
              <CommentThread
                key={comment.id}
                comment={comment}
                onClose={closeComment}
                onReopen={reopenComment}
                canManage={isOwner || currentUser === comment.username}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-2 mt-6">
              <button
                className="btn btn-sm btn-ghost"
                disabled={currentPage === 0}
                onClick={() => goToPage(currentPage - 1)}
              >
                Previous
              </button>
              <span className="text-sm text-base-content/60">
                Page {currentPage + 1} of {totalPages}
              </span>
              <button
                className="btn btn-sm btn-ghost"
                disabled={currentPage >= totalPages - 1}
                onClick={() => goToPage(currentPage + 1)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </PageContainer>
  );
}
