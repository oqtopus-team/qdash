"use client";

import { Bot } from "lucide-react";

import type { NoteModel } from "@/schemas";

import { useGetTaskResult } from "@/client/task/task";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { formatDateTime } from "@/lib/utils/datetime";

interface TaskResultAiReviewNoteProps {
  note?: NoteModel | null;
  taskId?: string;
  hideWhenEmpty?: boolean;
}

export function TaskResultAiReviewNote({
  note,
  taskId,
  hideWhenEmpty = false,
}: TaskResultAiReviewNoteProps) {
  const shouldFetch = Boolean(taskId && !note?.content?.trim());
  const { data, isLoading } = useGetTaskResult(taskId ?? "", {
    query: {
      enabled: shouldFetch,
      retry: false,
      staleTime: 30_000,
    },
  });
  const aiReviewNote = note?.content?.trim() ? note : data?.data.ai_review_note;
  const content = aiReviewNote?.content?.trim() ?? "";
  if (!content && hideWhenEmpty) return null;

  return (
    <div className="mt-6 mb-3 rounded-lg border border-base-300 bg-base-200/40">
      <div className="flex items-center justify-between px-3 py-2 border-b border-base-300">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Bot className="h-4 w-4" />
          AI Review
          {content && aiReviewNote?.updated_by && (
            <span className="text-xs font-normal text-base-content/60">
              · by {aiReviewNote.updated_by}
              {aiReviewNote.updated_at && <> · {formatDateTime(aiReviewNote.updated_at)}</>}
            </span>
          )}
        </h3>
      </div>

      <div className="p-3 text-sm">
        {isLoading ? (
          <div className="text-xs text-base-content/50 italic">Loading…</div>
        ) : content ? (
          <MarkdownContent
            content={content}
            className="break-words [&>:first-child]:mt-0 [&>:last-child]:mb-0 [&_ul]:my-1.5 [&_ol]:my-1.5 [&_li]:my-0.5 [&_li>p]:my-0"
          />
        ) : (
          <p className="text-xs text-base-content/50 italic">No AI review note yet.</p>
        )}
      </div>
    </div>
  );
}
