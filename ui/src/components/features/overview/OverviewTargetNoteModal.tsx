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
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { useForumLabels } from "@/hooks/useForumLabels";
import { formatDateTime } from "@/lib/utils/datetime";
import type { GetChipNotesSummaryParams, NoteCommentModel, SystemRole } from "@/schemas";

import { formatForumPostTitle, getForumLabel } from "../forum/categories";
import { ForumLabelBadge } from "../forum/ForumLabelBadge";
import { formatNoteTarget, forumDraftHref, useLinkedForumPosts } from "./targetForumLinks";

export interface TargetNoteEntry {
  targetId: string;
  content: string;
  username: string;
  updatedAt: string;
  comments?: NoteCommentModel[];
}

interface OverviewTargetNoteModalProps {
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

export function OverviewTargetNoteModal({
  chipId,
  targetId,
  cooldownId,
  noteScopeParams,
  existing,
  mentionCandidates = [],
  currentUsername,
  currentSystemRole,
  onClose,
}: OverviewTargetNoteModalProps) {
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
  const relatedForumPosts = useLinkedForumPosts(chipId, targetId, cooldownId);
  const { labels: forumLabels } = useForumLabels();

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
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !entryDraft.trim() && !editingEntryId && !mutationPending) {
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-3xl p-0 !overflow-hidden">
        <div className="px-5 py-4 border-b border-base-300 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <DialogTitle className="flex items-center gap-2">
              <StickyNote className="h-5 w-5 text-warning" />
              <span className="truncate">
                Summary notes · {formatNoteTarget(targetId, "->")}
                {cooldownId ? ` · ${cooldownId}` : ""}
              </span>
            </DialogTitle>
            <DialogDescription className="text-sm text-base-content/60 mt-1">
              Post target-level observations with author history. Use forum topics for separate
              discussions and images.
            </DialogDescription>
          </div>
          <button
            className="btn btn-ghost btn-sm btn-circle"
            onClick={onClose}
            type="button"
            aria-label="Close"
            disabled={mutationPending}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[calc(100vh-9rem)] overflow-y-auto p-5 space-y-5">
          <div className="rounded-md bg-base-200/60 border border-base-300 p-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="text-sm font-medium">Linked forum discussions</span>
                <p className="mt-0.5 text-xs leading-snug text-base-content/55">
                  Use for separate issues, images, MTG discussion, and resolved follow-up.
                </p>
              </div>
              <Link
                href={forumDraftHref(
                  chipId,
                  targetId,
                  cooldownId,
                  formatNoteTarget(targetId, "->"),
                )}
                className="btn btn-xs btn-outline"
              >
                <MessageSquarePlus data-icon="inline-start" />
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
                            {(post.labels ?? []).map((label) => (
                              <ForumLabelBadge
                                key={label}
                                size="xs"
                                label={getForumLabel(label, forumLabels)}
                              />
                            ))}
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
                <h3 className="text-sm font-medium">Note entries</h3>
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
                          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-base-content/50">
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
                                className="btn btn-xs btn-primary"
                                onClick={() => handleUpdateEntry(entryId)}
                                disabled={
                                  !editingEntryDraft.trim() ||
                                  isEditingEntryTooLong ||
                                  mutationPending
                                }
                                type="button"
                              >
                                <Save data-icon="inline-start" />
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
              <span className="text-sm font-medium">Post entry</span>
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
                className="btn btn-sm btn-primary"
                onClick={handleCreateEntry}
                disabled={!entryDraft.trim() || isEntryTooLong || mutationPending}
                type="button"
              >
                <Send data-icon="inline-start" />
                Post
              </button>
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
