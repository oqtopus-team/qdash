"use client";

import { useEffect, useState } from "react";

import { Pencil, Save, StickyNote, Trash2, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";

import {
  getGetChipNotesSummaryQueryKey,
  getGetTaskNoteQueryKey,
  useDeleteTaskNote,
  useGetTaskNote,
  useUpsertTaskNote,
} from "@/client/note/note";
import { MarkdownContent } from "@/components/ui/MarkdownContent";

interface TaskResultMemoProps {
  taskId: string;
  /** Optional chip_id to invalidate the chip-wide list query after edits. */
  chipId?: string;
  /** Hide the component when the task has no note yet. */
  hideWhenEmpty?: boolean;
}

/**
 * Free-form note attached to a task result. Renders right above the issues
 * thread inside QubitMetricHistoryModal.
 */
export function TaskResultMemo({
  taskId,
  chipId,
  hideWhenEmpty = false,
}: TaskResultMemoProps) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useGetTaskNote(taskId, {
    query: {
      enabled: !!taskId,
      retry: false,
      staleTime: 30_000,
    },
  });

  const note = data?.data;
  const noteContent = note?.content ?? "";
  const upsertMutation = useUpsertTaskNote();
  const deleteMutation = useDeleteTaskNote();

  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(noteContent);
  const aiTriageSummary = getAiTriageSummary(noteContent);
  const [isExpanded, setIsExpanded] = useState(!aiTriageSummary);

  useEffect(() => {
    setDraft(noteContent);
  }, [noteContent]);

  useEffect(() => {
    setIsExpanded(!aiTriageSummary);
  }, [aiTriageSummary]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({
      queryKey: getGetTaskNoteQueryKey(taskId),
    });
    if (chipId) {
      await queryClient.invalidateQueries({
        queryKey: getGetChipNotesSummaryQueryKey(chipId),
      });
    }
  };

  const handleSave = async () => {
    await upsertMutation.mutateAsync({
      taskId,
      data: { content: draft },
    });
    await invalidate();
    setIsEditing(false);
  };

  const handleDelete = async () => {
    await deleteMutation.mutateAsync({ taskId });
    await invalidate();
    setIsEditing(false);
  };

  // Distinguish "no note yet" (404) from "real error". 404 is expected.
  const showNotFound =
    !isLoading &&
    !note &&
    !isEditing &&
    // useGetTaskNote returns no data on 404 — treat that as the "create" state.
    true;

  if (hideWhenEmpty && showNotFound) {
    return null;
  }

  return (
    <div className="mt-6 mb-3 rounded-lg border border-base-300 bg-base-200/40">
      <div className="flex items-center justify-between px-3 py-2 border-b border-base-300">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <StickyNote className="h-4 w-4" />
          Note
          {note?.updated_by && (
            <span className="text-xs font-normal text-base-content/60">
              · last edit by {note.updated_by}
              {note.updated_at && (
                <> · {new Date(note.updated_at).toLocaleString()}</>
              )}
            </span>
          )}
        </h3>
        {!isEditing && (
          <button
            onClick={() => setIsEditing(true)}
            className="btn btn-xs btn-ghost gap-1"
          >
            <Pencil className="h-3 w-3" />
            {note ? "Edit" : "Add note"}
          </button>
        )}
      </div>

      <div className="p-3 text-sm">
        {isEditing ? (
          <>
            <textarea
              className="textarea textarea-bordered w-full h-32 text-sm"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Anything notable about this measurement (anomaly, parameter intent, follow-up…). Notes show up above issues."
              maxLength={5000}
              autoFocus
            />
            <div className="flex items-center justify-between mt-2">
              <button
                className="btn btn-xs btn-ghost text-error"
                onClick={handleDelete}
                disabled={!note || deleteMutation.isPending}
                title={note ? "Delete this note" : "No note to delete"}
              >
                <Trash2 className="h-3 w-3" />
                Delete
              </button>
              <div className="flex gap-2">
                <button
                  className="btn btn-xs btn-ghost"
                  onClick={() => {
                    setDraft(noteContent);
                    setIsEditing(false);
                  }}
                >
                  <X className="h-3 w-3" />
                  Cancel
                </button>
                <button
                  className="btn btn-xs btn-primary"
                  onClick={handleSave}
                  disabled={upsertMutation.isPending}
                >
                  <Save className="h-3 w-3" />
                  {upsertMutation.isPending ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
            {(upsertMutation.error || deleteMutation.error) && (
              <div className="text-xs text-error mt-1">
                {extractErrorMessage(
                  upsertMutation.error ?? deleteMutation.error,
                )}
              </div>
            )}
          </>
        ) : isLoading ? (
          <div className="text-xs text-base-content/50 italic">Loading…</div>
        ) : note ? (
          <>
            <MarkdownContent
              content={
                aiTriageSummary && !isExpanded
                  ? aiTriageSummary.summary
                  : noteContent
              }
              className="break-words [&>:first-child]:mt-0 [&>:last-child]:mb-0 [&_ul]:my-1.5 [&_ol]:my-1.5 [&_li]:my-0.5 [&_li>p]:my-0"
            />
            {aiTriageSummary && (
              <button
                type="button"
                className="btn btn-xs btn-ghost mt-2"
                onClick={() => setIsExpanded((value) => !value)}
              >
                {isExpanded ? "Show summary" : "Show full note"}
              </button>
            )}
          </>
        ) : showNotFound ? (
          <p className="text-xs text-base-content/50 italic">
            No note yet. Click &ldquo;Add note&rdquo; to write one.
          </p>
        ) : null}
      </div>
    </div>
  );
}

function getAiTriageSummary(content: string): { summary: string } | null {
  const header = "## AI triage";
  const headerIndex = content.indexOf(header);
  if (headerIndex === -1) return null;

  const separatorIndex = content.indexOf("\n\n---\n\n", headerIndex);
  const section =
    separatorIndex === -1
      ? content.slice(headerIndex)
      : content.slice(headerIndex, separatorIndex);
  const body = section.slice(header.length).trim();
  if (!body) return null;

  const lines = body.split(/\r?\n/);
  const summaryLines: string[] = [header];
  const importantLinePattern =
    /^(Review triage|Decision:|判定:|Human label suggestion:|Accepted parameter\(s\):|受理されたパラメータ:|Needs review:|要レビュー:|Primary reason:|主な理由:|Closest knowledge case:|最も近い知識事例:|Suggested labels:|推奨ラベル:|Recommended action:|推奨アクション:|Optional note:)/i;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (summaryLines[summaryLines.length - 1] !== "") {
        summaryLines.push("");
      }
      continue;
    }
    if (importantLinePattern.test(trimmed)) {
      summaryLines.push(line);
      continue;
    }
    if (summaryLines.length <= 2) {
      summaryLines.push(line);
    }
  }

  const summary = summaryLines.join("\n").trim();
  if (!summary || summary === section.trim()) return null;
  return { summary };
}

function extractErrorMessage(err: unknown): string {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  if (err instanceof Error) return err.message;
  return "Failed to save note.";
}
