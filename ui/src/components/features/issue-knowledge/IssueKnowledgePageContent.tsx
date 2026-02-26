"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Search, X, GitPullRequest, XCircle, Trash2 } from "lucide-react";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { useIssueKnowledgeList } from "@/hooks/useIssueKnowledge";
import { formatRelativeTime } from "@/lib/utils/datetime";
import type { IssueKnowledgeResponse } from "@/schemas";

function SeverityBadge({ severity }: { severity?: string }) {
  const color =
    severity === "critical"
      ? "badge-error"
      : severity === "warning"
        ? "badge-warning"
        : "badge-info";
  return (
    <span className={`badge badge-sm ${color}`}>{severity ?? "info"}</span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "approved"
      ? "badge-success"
      : status === "rejected"
        ? "badge-error"
        : "badge-ghost";
  return <span className={`badge badge-sm ${color}`}>{status}</span>;
}

function KnowledgeCard({
  item,
  onApprove,
  onReject,
  onDelete,
}: {
  item: IssueKnowledgeResponse;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const router = useRouter();

  return (
    <div
      onClick={() => router.push(`/issue-knowledge/${item.id}`)}
      className={`bg-base-100 rounded-lg border border-base-300 cursor-pointer hover:border-primary/50 transition-colors ${
        item.status === "rejected" ? "opacity-60" : ""
      }`}
    >
      <div className="p-4">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <StatusBadge status={item.status} />
          <SeverityBadge severity={item.severity} />
          <span className="font-mono text-xs text-primary">
            {item.task_name}
          </span>
          {item.qid && (
            <span className="text-xs text-base-content/40">{item.qid}</span>
          )}
          <span className="text-xs text-base-content/40">
            {formatRelativeTime(item.created_at)}
          </span>
        </div>

        <h3 className="text-sm font-semibold mb-1">{item.title}</h3>

        {item.symptom && (
          <p className="text-sm text-base-content/70 line-clamp-2 mb-2">
            {item.symptom}
          </p>
        )}

        {item.lesson_learned && item.lesson_learned.length > 0 && (
          <div className="text-xs text-base-content/50 mb-2">
            {item.lesson_learned.length} lesson
            {item.lesson_learned.length !== 1 ? "s" : ""}
          </div>
        )}

        {item.status === "draft" && (
          <div className="flex items-center gap-2 mt-2">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onApprove(item.id);
              }}
              className="btn btn-success btn-xs gap-1"
            >
              <GitPullRequest className="h-3 w-3" />
              Create PR
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onReject(item.id);
              }}
              className="btn btn-ghost btn-xs gap-1"
            >
              <XCircle className="h-3 w-3" />
              Reject
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(item.id);
              }}
              className="btn btn-ghost btn-xs gap-1 text-error"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        )}

        {item.reviewed_by && (
          <div className="text-xs text-base-content/40 mt-1">
            Reviewed by {String(item.reviewed_by)}
          </div>
        )}
      </div>
    </div>
  );
}

export function IssueKnowledgePageContent() {
  const {
    items,
    total,
    skip,
    pageSize,
    isLoading,
    statusFilter,
    setStatusFilter,
    taskNameFilter,
    filterByTaskName,
    approve,
    reject,
    deleteKnowledge,
    goToPage,
  } = useIssueKnowledgeList();

  const [filterInput, setFilterInput] = useState("");

  const currentPage = Math.floor(skip / pageSize);
  const totalPages = Math.ceil(total / pageSize);

  const handleFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    filterByTaskName(filterInput.trim());
  };

  const clearFilter = () => {
    setFilterInput("");
    filterByTaskName("");
  };

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Knowledge"
        description="Issue-derived knowledge cases for calibration tasks"
      />

      {/* Status tabs */}
      <div className="mb-4">
        <div className="tabs tabs-boxed w-fit">
          {(["draft", "approved", "rejected", "all"] as const).map((status) => (
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
              placeholder="Filter by task name..."
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
          {taskNameFilter && (
            <div className="flex items-center gap-1">
              <span className="badge badge-sm badge-outline">
                task: {taskNameFilter}
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
      ) : items.length === 0 ? (
        <EmptyState
          title="No knowledge cases yet"
          description={
            statusFilter === "draft"
              ? "Knowledge drafts will appear here when issues are closed."
              : "No knowledge cases found with this filter."
          }
          emoji="brain"
        />
      ) : (
        <>
          <div className="space-y-3">
            {items.map((item) => (
              <KnowledgeCard
                key={item.id}
                item={item}
                onApprove={approve}
                onReject={reject}
                onDelete={deleteKnowledge}
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
