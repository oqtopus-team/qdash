"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MessageSquare, X, Lock, Unlock } from "lucide-react";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { SearchInput } from "@/components/ui/SearchInput";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { useIssues } from "@/hooks/useIssues";
import { useProject } from "@/contexts/ProjectContext";
import { formatRelativeTime } from "@/lib/utils/datetime";
import type { IssueResponse } from "@/schemas";

function IssueThread({
  issue,
  onClose,
  onReopen,
  canManage,
}: {
  issue: IssueResponse;
  onClose: (issueId: string) => void;
  onReopen: (issueId: string) => void;
  canManage: boolean;
}) {
  const router = useRouter();

  const handleCardClick = () => {
    router.push(`/issues/${issue.id}`);
  };

  return (
    <div
      onClick={handleCardClick}
      className={`bg-base-100 rounded-lg border border-base-300 cursor-pointer hover:border-primary/50 transition-colors ${issue.is_closed === true ? "opacity-70" : ""}`}
    >
      <div className="p-4">
        <div className="flex items-center gap-3 mb-2 flex-wrap">
          <UserAvatar username={issue.username} avatarKey={issue.avatar_key} size={28} />
          <Link
            href={`/task-results/${issue.task_id}`}
            onClick={(e) => e.stopPropagation()}
            className="font-mono text-xs font-semibold text-primary hover:underline"
          >
            {issue.task_id}
          </Link>
          <div className="flex items-center gap-1.5">
            <span className="badge badge-sm badge-neutral">{issue.username}</span>
            <span className="text-xs text-base-content/40">
              {formatRelativeTime(issue.created_at)}
            </span>
            {issue.is_closed === true && <span className="badge badge-sm badge-ghost">Closed</span>}
          </div>
        </div>
        {issue.title && <h3 className="text-sm font-semibold mb-1">{issue.title}</h3>}
        <div className="text-sm text-base-content/80 mb-3 line-clamp-3">
          <MarkdownContent content={issue.content} preview />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-base-content/50 flex items-center gap-1">
            <MessageSquare className="h-3 w-3" />
            {issue.reply_count ?? 0} {issue.reply_count === 1 ? "reply" : "replies"}
          </span>
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

export function IssuesPageContent() {
  const {
    issues,
    total,
    skip,
    pageSize,
    isLoading,
    taskIdFilter,
    filterByTaskId,
    statusFilter,
    setStatusFilter,
    closeIssue,
    reopenIssue,
    goToPage,
  } = useIssues();
  const { isOwner } = useProject();
  const { username: currentUser } = useAuth();
  const [filterInput, setFilterInput] = useState("");

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
      <PageHeader title="Issues" description="Track and discuss issues on task results" />

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
        <form onSubmit={handleFilterSubmit} className="flex flex-wrap gap-2 items-center">
          <SearchInput
            value={filterInput}
            onChange={setFilterInput}
            onClear={clearFilter}
            placeholder="Filter by task ID..."
            className="flex-1 max-w-sm"
          />
          <button type="submit" className="btn btn-sm btn-primary">
            Filter
          </button>
          {taskIdFilter && (
            <div className="flex items-center gap-1 basis-full sm:basis-auto min-w-0">
              <span className="badge badge-sm badge-outline min-w-0">
                <span className="min-w-0 truncate">task: {taskIdFilter}</span>
              </span>
              <button
                onClick={clearFilter}
                className="btn btn-ghost btn-xs p-0 h-auto min-h-0 shrink-0"
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
      ) : issues.length === 0 ? (
        <EmptyState
          title="No issues yet"
          description={
            taskIdFilter
              ? "No issues found for this task. Try removing the filter."
              : "Issues on task results will appear here."
          }
          emoji="speech-balloon"
        />
      ) : (
        <>
          <div className="space-y-3">
            {issues.map((issue) => (
              <IssueThread
                key={issue.id}
                issue={issue}
                onClose={closeIssue}
                onReopen={reopenIssue}
                canManage={isOwner || currentUser === issue.username}
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
