"use client";

import { MessageSquare, MessagesSquare, Plus } from "lucide-react";
import Link from "next/link";

import { useListForumPosts } from "@/client/forum/forum";
import { useGetTaskResult } from "@/client/task/task";
import { useProject } from "@/contexts/ProjectContext";
import { formatRelativeTime } from "@/lib/utils/datetime";

import { formatForumPostNumber, getForumStatus } from "./categories";

interface TaskResultThreadsProps {
  taskId: string;
  /** Known on the result page; a modal that only has the id lets the section fetch them. */
  taskName?: string;
  chipId?: string | null;
  qid?: string;
}

/** The forum URL that opens a new thread about this task result, with its context prefilled. */
export function newThreadHref(input: {
  taskId: string;
  taskName: string;
  chipId: string | null | undefined;
  qid: string;
}): string {
  const targetType = input.qid.includes("-") ? "coupling" : "qubit";
  const params = new URLSearchParams({
    task_id: input.taskId,
    category: targetType,
    title: `${input.taskName} on ${input.qid}`,
    target_type: targetType,
    target_id: input.qid,
  });
  if (input.chipId) params.set("chip_id", input.chipId);
  return `/forum/new?${params.toString()}`;
}

/**
 * The forum threads about one task result, newest first, and a shortcut to
 * start another. A thread opened from here carries the result's chip and
 * target and links back to it.
 */
export function TaskResultThreads({
  taskId,
  taskName: givenTaskName,
  chipId: givenChipId,
  qid: givenQid,
}: TaskResultThreadsProps) {
  const { canEdit } = useProject();
  const needsResult = !givenTaskName || !givenQid;
  const { data: resultResponse } = useGetTaskResult(taskId, {
    query: { enabled: !!taskId && needsResult, staleTime: 60_000 },
  });
  const taskName = givenTaskName ?? resultResponse?.data.task_name ?? "";
  const qid = givenQid ?? resultResponse?.data.qid ?? "";
  const chipId = givenChipId ?? resultResponse?.data.chip_id ?? null;
  const { data, isLoading } = useListForumPosts(
    { task_id: taskId, status: "all", limit: 20 },
    { query: { enabled: !!taskId, staleTime: 30_000 } },
  );
  const threads = data?.data.posts ?? [];

  return (
    <section className="mb-6">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <MessagesSquare className="h-4 w-4 text-primary" />
          Threads about this result
          {threads.length > 0 && (
            <span className="badge badge-ghost badge-sm">{threads.length}</span>
          )}
        </div>
        {canEdit && taskName && qid && (
          <Link
            href={newThreadHref({ taskId, taskName, chipId, qid })}
            className="btn btn-sm btn-outline gap-1"
          >
            <Plus className="h-4 w-4" />
            New thread
          </Link>
        )}
      </div>
      {isLoading ? (
        <div className="flex justify-center py-4">
          <span className="loading loading-spinner loading-sm" />
        </div>
      ) : threads.length === 0 ? (
        <p className="text-sm text-base-content/50">
          No forum thread is about this result yet. Start one to discuss it with the team; it will
          link back here.
        </p>
      ) : (
        <ul className="divide-y divide-base-300 rounded-lg border border-base-300 bg-base-100">
          {threads.map((post) => {
            const status = getForumStatus(post.status);
            const StatusIcon = status.icon;
            return (
              <li key={post.id}>
                <Link
                  href={`/forum/${post.id}`}
                  className="flex items-center gap-3 px-3 py-2 hover:bg-base-200/60"
                >
                  {formatForumPostNumber(post.number) && (
                    <span className="badge badge-outline badge-sm shrink-0">
                      {formatForumPostNumber(post.number)}
                    </span>
                  )}
                  <span className="min-w-0 flex-1 truncate text-sm">{post.title}</span>
                  <span className={`badge badge-sm gap-1 ${status.badgeClass}`}>
                    <StatusIcon className="h-3 w-3" />
                    {status.label}
                  </span>
                  <span className="flex shrink-0 items-center gap-1 text-xs text-base-content/50">
                    <MessageSquare className="h-3 w-3" />
                    {post.reply_count}
                  </span>
                  <span className="shrink-0 text-xs text-base-content/50">
                    {formatRelativeTime(post.updated_at)}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
