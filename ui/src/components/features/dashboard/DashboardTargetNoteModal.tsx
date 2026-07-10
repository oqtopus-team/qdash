"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import {
  ExternalLink,
  MessageSquarePlus,
  Pencil,
  Save,
  Send,
  StickyNote,
  Trash2,
  X,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { useListForumPosts } from "@/client/forum/forum";
import {
  getGetChipNotesSummaryQueryKey,
  useCreateCouplingNoteComment,
  useCreateQubitNoteComment,
  useDeleteCouplingNoteComment,
  useDeleteQubitNoteComment,
  useUpdateCouplingNoteComment,
  useUpdateQubitNoteComment,
} from "@/client/note/note";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor, type MentionCandidate } from "@/components/ui/MarkdownEditor";
import { formatDateTime } from "@/lib/utils/datetime";
import type { GetChipNotesSummaryParams, NoteCommentModel, SystemRole } from "@/schemas";

import { formatForumPostTitle, getForumLabel } from "../forum/categories";

export interface TargetNoteEntry {
  targetId: string;
  content: string;
  username: string;
  updatedAt: string;
  comments?: NoteCommentModel[];
}

interface DashboardTargetNoteModalProps {
  chipId: string;
  targetId: string;
  cooldownId?: string | null;
  noteScopeParams?: GetChipNotesSummaryParams;
  existing?: TargetNoteEntry;
  mentionCandidates?: MentionCandidate[];
  currentUsername?: string | null;
  currentSystemRole?: SystemRole | null;
  onClose: () => void;
}

function formatTarget(targetId: string): string {
  if (targetId.includes("-")) {
    const [a, b] = targetId.split("-");
    return `Q${a} -> Q${b}`;
  }
  return `Q${targetId}`;
}

function forumDraftHref(chipId: string, targetId: string, cooldownId?: string | null): string {
  const isCoupling = targetId.includes("-");
  const targetLabel = formatTarget(targetId);
  const params = new URLSearchParams({
    category: isCoupling ? "coupling" : "qubit",
    chip_id: chipId,
    target_id: targetId,
    target_type: isCoupling ? "coupling" : "qubit",
    target_label: targetLabel,
    title: `${targetLabel}: `,
    content: [`Chip: ${chipId}`, `Target: ${targetLabel}`, "", "Notes:"].join("\n"),
  });
  if (cooldownId) params.set("cooldown_id", cooldownId);
  return `/forum/new?${params.toString()}`;
}

function normalizeQid(value: string): string {
  const normalized = Number.parseInt(value, 10);
  return Number.isNaN(normalized) ? value : String(normalized);
}

function normalizeTargetId(
  value: string | null | undefined,
  targetType: "qubit" | "coupling",
): string | null {
  const raw = value?.trim();
  if (!raw) return null;
  const qids = Array.from(raw.matchAll(/Q?\s*(\d+)/gi)).map((match) => normalizeQid(match[1]));
  if (targetType === "coupling") {
    if (qids.length >= 2) return `${qids[0]}-${qids[1]}`;
    return raw.replace(/\s+/g, "");
  }
  if (qids.length >= 1) return qids[0];
  return raw.replace(/^Q/i, "").replace(/\s+/g, "");
}

function matchesForumTarget(
  post: {
    chip_id?: string | null;
    target_type?: string | null;
    target_id?: string | null;
    content?: string;
  },
  chipId: string,
  targetId: string,
): boolean {
  const targetType = targetId.includes("-") ? "coupling" : "qubit";
  if (post.chip_id && post.target_id) {
    return (
      post.chip_id === chipId &&
      post.target_type === targetType &&
      normalizeTargetId(post.target_id, targetType) === targetId
    );
  }

  const content = post.content ?? "";
  const contentChipId = content.match(/^Chip:\s*(.+)$/m)?.[1]?.trim();
  const contentTarget = content.match(/^Target:\s*(.+)$/m)?.[1]?.trim();
  return contentChipId === chipId && normalizeTargetId(contentTarget, targetType) === targetId;
}

export function DashboardTargetNoteModal({
  chipId,
  targetId,
  cooldownId,
  noteScopeParams,
  existing,
  mentionCandidates = [],
  currentUsername,
  currentSystemRole,
  onClose,
}: DashboardTargetNoteModalProps) {
  const queryClient = useQueryClient();
  const isCoupling = targetId.includes("-");
  const createQubitComment = useCreateQubitNoteComment();
  const createCouplingComment = useCreateCouplingNoteComment();
  const updateQubitComment = useUpdateQubitNoteComment();
  const updateCouplingComment = useUpdateCouplingNoteComment();
  const deleteQubitComment = useDeleteQubitNoteComment();
  const deleteCouplingComment = useDeleteCouplingNoteComment();
  const mutationPending = isCoupling
    ? createCouplingComment.isPending ||
      updateCouplingComment.isPending ||
      deleteCouplingComment.isPending
    : createQubitComment.isPending || updateQubitComment.isPending || deleteQubitComment.isPending;
  const { data: forumPostsResponse } = useListForumPosts(
    {
      chip_id: chipId,
      target_type: isCoupling ? "coupling" : "qubit",
      target_id: targetId,
      cooldown_id: cooldownId || undefined,
      status: null,
      limit: 50,
    },
    { query: { staleTime: 30_000 } },
  );
  const relatedForumPosts =
    forumPostsResponse?.data.posts.filter((post) => matchesForumTarget(post, chipId, targetId)) ??
    [];

  const [entryDraft, setEntryDraft] = useState("");
  const [editingEntryId, setEditingEntryId] = useState<string | null>(null);
  const [editingEntryDraft, setEditingEntryDraft] = useState("");
  const previousTargetIdRef = useRef(targetId);

  useEffect(() => {
    const targetChanged = previousTargetIdRef.current !== targetId;
    previousTargetIdRef.current = targetId;

    if (targetChanged) {
      setEntryDraft("");
      setEditingEntryId(null);
      setEditingEntryDraft("");
    }
  }, [targetId]);

  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: getGetChipNotesSummaryQueryKey(chipId, noteScopeParams),
    });

  const handleCreateEntry = async () => {
    const trimmed = entryDraft.trim();
    if (!trimmed || entryDraft.length > 5000) return;
    if (isCoupling) {
      await createCouplingComment.mutateAsync({
        chipId,
        couplingId: targetId,
        data: { content: entryDraft },
        params: noteScopeParams,
      });
    } else {
      await createQubitComment.mutateAsync({
        chipId,
        qid: targetId,
        data: { content: entryDraft },
        params: noteScopeParams,
      });
    }
    setEntryDraft("");
    await invalidate();
  };

  const handleUpdateEntry = async (entryId: string) => {
    const trimmed = editingEntryDraft.trim();
    if (!trimmed || editingEntryDraft.length > 5000) return;
    if (isCoupling) {
      await updateCouplingComment.mutateAsync({
        chipId,
        couplingId: targetId,
        commentId: entryId,
        data: { content: editingEntryDraft },
        params: noteScopeParams,
      });
    } else {
      await updateQubitComment.mutateAsync({
        chipId,
        qid: targetId,
        commentId: entryId,
        data: { content: editingEntryDraft },
        params: noteScopeParams,
      });
    }
    setEditingEntryId(null);
    setEditingEntryDraft("");
    await invalidate();
  };

  const handleDeleteEntry = async (entryId: string) => {
    if (isCoupling) {
      await deleteCouplingComment.mutateAsync({
        chipId,
        couplingId: targetId,
        commentId: entryId,
        params: noteScopeParams,
      });
    } else {
      await deleteQubitComment.mutateAsync({
        chipId,
        qid: targetId,
        commentId: entryId,
        params: noteScopeParams,
      });
    }
    if (editingEntryId === entryId) {
      setEditingEntryId(null);
      setEditingEntryDraft("");
    }
    await invalidate();
  };

  const entries = existing?.comments ?? [];
  const isEntryTooLong = entryDraft.length > 5000;
  const isEditingEntryTooLong = editingEntryDraft.length > 5000;

  return (
    <div
      className="modal modal-open"
      onClick={(e) => {
        if (!entryDraft.trim() && !editingEntryId && e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="modal-box w-full max-w-3xl p-0 overflow-hidden">
        <div className="px-5 py-4 border-b border-base-300 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-lg font-bold">
              <StickyNote className="h-5 w-5 text-warning" />
              <span className="truncate">
                Summary notes · {formatTarget(targetId)}
                {cooldownId ? ` · ${cooldownId}` : ""}
              </span>
            </div>
            <p className="text-sm text-base-content/60 mt-1">
              Post target-level observations with author history. Use forum topics for separate
              discussions and images.
            </p>
          </div>
          <button
            className="btn btn-ghost btn-sm btn-circle"
            onClick={onClose}
            type="button"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[calc(100vh-9rem)] overflow-y-auto p-5 space-y-5">
          <div className="rounded-md bg-base-200/60 border border-base-300 p-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="text-sm font-semibold">Linked forum discussions</span>
                <p className="mt-0.5 text-xs leading-snug text-base-content/55">
                  Use for separate issues, images, MTG discussion, and resolved follow-up.
                </p>
              </div>
              <Link
                href={forumDraftHref(chipId, targetId, cooldownId)}
                className="btn btn-xs btn-outline gap-1"
              >
                <MessageSquarePlus className="h-3.5 w-3.5" />
                New
              </Link>
            </div>
            {relatedForumPosts.length > 0 ? (
              <ul className="divide-y divide-base-300 text-sm">
                {relatedForumPosts.slice(0, 5).map((post) => (
                  <li key={post.id}>
                    <Link
                      href={`/forum/${post.id}`}
                      className="flex items-center justify-between gap-3 py-2 hover:text-primary"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">
                          {formatForumPostTitle(post.title, post.number)}
                        </span>
                        {(post.labels ?? []).length > 0 && (
                          <span className="mt-1 flex flex-wrap gap-1">
                            {(post.labels ?? []).map((label) => {
                              const labelDef = getForumLabel(label);
                              return (
                                <span
                                  key={label}
                                  className={`badge badge-xs ${labelDef.badgeClass}`}
                                >
                                  {labelDef.label}
                                </span>
                              );
                            })}
                          </span>
                        )}
                      </span>
                      <span className="flex shrink-0 items-center gap-1 text-xs text-base-content/50">
                        {post.reply_count ?? 0} replies
                        <ExternalLink className="h-3 w-3" />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-base-content/60">
                No linked forum discussions yet. Start one for each separate issue or observation.
              </p>
            )}
          </div>

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">Note entries</h3>
                <p className="mt-0.5 text-xs text-base-content/55">
                  Each entry keeps its original author and latest editor.
                </p>
              </div>
              <span className="badge badge-outline">{entries.length}</span>
            </div>

            {entries.length > 0 ? (
              <ul className="space-y-3">
                {entries.map((entry) => {
                  const entryId = entry.comment_id ?? "";
                  const isEditing = editingEntryId === entryId;
                  const canModifyEntry =
                    currentSystemRole === "admin" || entry.created_by === currentUsername;
                  return (
                    <li
                      key={entryId || `${entry.created_by}-${entry.created_at}`}
                      className="rounded-md border border-base-300 bg-base-100 p-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 text-xs text-base-content/60">
                          <span className="font-medium text-base-content/80">
                            {entry.created_by || "-"}
                          </span>
                          {entry.created_at && <span> · {formatDateTime(entry.created_at)}</span>}
                          {entry.updated_at && (
                            <span>
                              {" "}
                              · edited by {entry.updated_by || "-"}{" "}
                              {formatDateTime(entry.updated_at)}
                            </span>
                          )}
                        </div>
                        {canModifyEntry && (
                          <div className="flex shrink-0 gap-1">
                            <button
                              className="btn btn-ghost btn-xs btn-square"
                              onClick={() => {
                                setEditingEntryId(entryId);
                                setEditingEntryDraft(entry.content ?? "");
                              }}
                              disabled={!entryId || mutationPending}
                              type="button"
                              aria-label="Edit entry"
                              title="Edit entry"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              className="btn btn-ghost btn-xs btn-square text-error"
                              onClick={() => handleDeleteEntry(entryId)}
                              disabled={!entryId || mutationPending}
                              type="button"
                              aria-label="Delete entry"
                              title="Delete entry"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        )}
                      </div>

                      {isEditing ? (
                        <div className="mt-3 space-y-2">
                          <MarkdownEditor
                            value={editingEntryDraft}
                            onChange={setEditingEntryDraft}
                            onSubmit={() => handleUpdateEntry(entryId)}
                            placeholder="Update this summary note entry..."
                            rows={5}
                            disabled={mutationPending}
                            mentionCandidates={mentionCandidates}
                          />
                          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-base-content/50">
                            <span className={isEditingEntryTooLong ? "text-error" : undefined}>
                              {editingEntryDraft.length} / 5000
                            </span>
                            <div className="flex gap-2">
                              <button
                                className="btn btn-xs btn-ghost"
                                onClick={() => {
                                  setEditingEntryId(null);
                                  setEditingEntryDraft("");
                                }}
                                type="button"
                                disabled={mutationPending}
                              >
                                Cancel
                              </button>
                              <button
                                className="btn btn-xs btn-primary gap-1"
                                onClick={() => handleUpdateEntry(entryId)}
                                disabled={
                                  !editingEntryDraft.trim() ||
                                  isEditingEntryTooLong ||
                                  mutationPending
                                }
                                type="button"
                              >
                                <Save className="h-3.5 w-3.5" />
                                Save
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 text-sm">
                          <MarkdownContent content={entry.content ?? ""} />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <div className="rounded-md border border-dashed border-base-300 bg-base-100 p-4 text-sm text-base-content/55">
                No summary note entries yet.
              </div>
            )}
          </section>

          <section className="rounded-md border border-base-300 bg-base-100 p-3 space-y-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-semibold">Post entry</span>
              <span
                className={isEntryTooLong ? "text-xs text-error" : "text-xs text-base-content/50"}
              >
                {entryDraft.length} / 5000
              </span>
            </div>
            <MarkdownEditor
              value={entryDraft}
              onChange={setEntryDraft}
              onSubmit={handleCreateEntry}
              placeholder="Post a target-level summary note entry..."
              rows={5}
              disabled={mutationPending}
              mentionCandidates={mentionCandidates}
            />
            <div className="flex justify-end">
              <button
                className="btn btn-sm btn-primary gap-1"
                onClick={handleCreateEntry}
                disabled={!entryDraft.trim() || isEntryTooLong || mutationPending}
                type="button"
              >
                <Send className="h-3.5 w-3.5" />
                Post
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
