"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { ExternalLink, MessageSquarePlus, Pencil, Save, StickyNote, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getGetChipNotesSummaryQueryKey,
  useDeleteCouplingNote,
  useDeleteQubitNote,
  useUpsertCouplingNote,
  useUpsertQubitNote,
} from "@/client/note/note";
import type { GetChipNotesSummaryParams, NoteCommentModel } from "@/schemas";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor, type MentionCandidate } from "@/components/ui/MarkdownEditor";
import { useForumLabels } from "@/hooks/useForumLabels";
import { formatDateTime } from "@/lib/utils/datetime";

import { formatForumPostTitle, getForumLabel } from "../forum/categories";
import { ForumLabelBadge } from "../forum/ForumLabelBadge";
import { formatNoteTarget, forumDraftHref, useLinkedForumPosts } from "./targetForumLinks";

export interface NoteEntry {
  targetId: string;
  metricKey: string;
  content: string;
  username: string;
  updatedAt: string;
}

export interface TargetNoteEntry {
  targetId: string;
  content: string;
  username: string;
  updatedAt: string;
  comments?: NoteCommentModel[];
}

export interface NoteEntryWithMetric extends NoteEntry {
  metricTitle: string;
}

interface MetricNotePanelProps {
  chipId: string;
  /** "0" for a qubit, "0-1" for a coupling. */
  targetId: string;
  metricKey: string;
  metricTitle: string;
  /** Cooldown scope identifier used by the backend for metric notes. */
  cooldownId?: string | null;
  /** Optional human-readable label for the current cooldown/session. */
  cooldownLabel?: string | null;
  noteScopeParams?: GetChipNotesSummaryParams;
  existing?: TargetNoteEntry;
  /** Legacy note for this exact metric, shown as read-only context. */
  legacyMetricNote?: NoteEntry;
  /** Legacy notes on the same target, shown as read-only context. */
  legacyMetricNotes?: NoteEntryWithMetric[];
  mentionCandidates?: MentionCandidate[];
}

/**
 * Inline panel for reading and editing the pinned target summary within the
 * dashboard. Forum topics carry separate notes, images, and discussion.
 */
export function MetricNotePanel({
  chipId,
  targetId,
  metricKey,
  metricTitle,
  cooldownId,
  cooldownLabel,
  noteScopeParams,
  existing,
  legacyMetricNote,
  legacyMetricNotes,
  mentionCandidates,
}: MetricNotePanelProps) {
  const queryClient = useQueryClient();
  const isCoupling = targetId.includes("-");

  const [mode, setMode] = useState<"view" | "edit">("view");
  const [draft, setDraft] = useState(existing?.content ?? "");
  const [localExisting, setLocalExisting] = useState<TargetNoteEntry | undefined>(existing);

  const upsertQubit = useUpsertQubitNote();
  const upsertCoupling = useUpsertCouplingNote();
  const deleteQubit = useDeleteQubitNote();
  const deleteCoupling = useDeleteCouplingNote();
  const mutationPending = isCoupling
    ? upsertCoupling.isPending || deleteCoupling.isPending
    : upsertQubit.isPending || deleteQubit.isPending;
  const relatedForumPosts = useLinkedForumPosts(chipId, targetId, cooldownId);
  const { labels: forumLabels } = useForumLabels();

  useEffect(() => {
    setLocalExisting(existing);
    setDraft(existing?.content ?? "");
    setMode("view");
  }, [
    existing,
    targetId,
    metricKey,
    noteScopeParams?.cooldown_id,
    noteScopeParams?.start_at,
    noteScopeParams?.end_at,
  ]);

  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: getGetChipNotesSummaryQueryKey(chipId, noteScopeParams),
    });

  const handleSave = async () => {
    const trimmed = draft.trim();
    if (draft.length > 5000) {
      return;
    }
    if (!trimmed) {
      if (!localExisting) return;
      if (isCoupling) {
        await deleteCoupling.mutateAsync({
          chipId,
          couplingId: targetId,
          params: noteScopeParams,
        });
      } else {
        await deleteQubit.mutateAsync({
          chipId,
          qid: targetId,
          params: noteScopeParams,
        });
      }
      setLocalExisting(undefined);
      setDraft("");
      setMode("view");
      await invalidate();
      return;
    }
    if (isCoupling) {
      const saved = await upsertCoupling.mutateAsync({
        chipId,
        couplingId: targetId,
        data: { content: draft },
        params: noteScopeParams,
      });
      setLocalExisting({
        targetId,
        content: saved.data.content ?? trimmed,
        username: saved.data.updated_by ?? "",
        updatedAt: saved.data.updated_at ?? "",
      });
    } else {
      const saved = await upsertQubit.mutateAsync({
        chipId,
        qid: targetId,
        data: { content: draft },
        params: noteScopeParams,
      });
      setLocalExisting({
        targetId,
        content: saved.data.content ?? trimmed,
        username: saved.data.updated_by ?? "",
        updatedAt: saved.data.updated_at ?? "",
      });
    }
    setDraft(trimmed);
    setMode("view");
    await invalidate();
  };

  const handleCancel = () => {
    setDraft(localExisting?.content ?? "");
    setMode("view");
  };

  const scopeLabel = cooldownLabel
    ? `Current cooldown · ${cooldownLabel}`
    : cooldownId
      ? `Current cooldown · ${cooldownId}`
      : noteScopeParams?.start_at
        ? "Selected time range"
        : "Global note context";

  return (
    <aside
      className="flex lg:h-full flex-col bg-base-200/40 lg:border-l border-base-300 lg:overflow-hidden"
      aria-label="Pinned summary"
    >
      {/* Section header */}
      <div className="px-4 pt-4 pb-2 border-b border-base-300/70">
        <div className="flex items-center gap-2 text-sm font-medium">
          <StickyNote className="h-4 w-4 text-warning" />
          Pinned summary
        </div>
        <div className="mt-0.5 text-xs text-base-content/60">{scopeLabel}</div>
        <div className="mt-1 text-xs text-base-content/50">
          For {formatNoteTarget(targetId)} while viewing {metricTitle}. Use forum topics for
          separate issues, images, and multi-person discussion.
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 lg:overflow-auto p-4 space-y-3">
        {mode === "view" ? (
          <ViewState existing={localExisting} onEdit={() => setMode("edit")} />
        ) : (
          <EditState
            existing={localExisting}
            draft={draft}
            onChange={setDraft}
            onSave={handleSave}
            onCancel={handleCancel}
            mutationPending={mutationPending}
            mentionCandidates={mentionCandidates}
          />
        )}

        <div className="rounded-md bg-base-100 border border-base-300 p-3 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div>
              <span className="text-xs font-medium">Linked forum discussions</span>
              <p className="mt-0.5 text-xs leading-snug text-base-content/50">
                Use for separate issues, images, MTG discussion, and resolved follow-up.
              </p>
            </div>
            <Link
              href={forumDraftHref(chipId, targetId, cooldownId)}
              className="btn btn-xs btn-outline"
            >
              <MessageSquarePlus data-icon="inline-start" />
              New
            </Link>
          </div>
          {relatedForumPosts.length > 0 ? (
            <ul className="space-y-1.5 text-xs">
              {relatedForumPosts.slice(0, 4).map((post) => (
                <li key={post.id}>
                  <Link
                    href={`/forum/${post.id}`}
                    className="flex items-center justify-between gap-2 rounded px-2 py-1.5 hover:bg-base-200"
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
                    <span className="flex shrink-0 items-center gap-1 text-base-content/50">
                      {post.reply_count ?? 0}
                      <ExternalLink className="h-3 w-3" />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-xs text-base-content/55">No linked forum discussions yet.</div>
          )}
        </div>

        {(legacyMetricNote || (legacyMetricNotes && legacyMetricNotes.length > 0)) && (
          <details className="rounded-md bg-base-100 border border-base-300">
            <summary className="px-3 py-2 cursor-pointer text-xs font-medium flex items-center justify-between">
              <span>
                Legacy metric notes
                <span className="ml-1 text-base-content/60 font-normal">
                  ({(legacyMetricNote ? 1 : 0) + (legacyMetricNotes?.length ?? 0)})
                </span>
              </span>
              <span className="text-base-content/40 font-normal">old dashboard notes</span>
            </summary>
            <div className="px-3 pb-2 text-xs text-base-content/50">
              Read-only notes originally written on individual metric cells. Use pinned summary or
              forum discussions for new notes.
            </div>
            <ul className="px-3 pb-3 pt-1 space-y-2 text-xs">
              {legacyMetricNote && (
                <li className="border-l-2 border-warning pl-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{metricTitle}</span>
                    <span className="text-base-content/50">
                      {legacyMetricNote.username} · {formatDateTime(legacyMetricNote.updatedAt)}
                    </span>
                  </div>
                  <div className="mt-1 text-base-content/80">
                    <MarkdownContent content={legacyMetricNote.content} />
                  </div>
                </li>
              )}
              {(legacyMetricNotes ?? []).map((note) => (
                <li key={note.metricKey} className="border-l-2 border-base-300 pl-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{note.metricTitle}</span>
                    <span className="text-base-content/50">
                      {note.username} · {formatDateTime(note.updatedAt)}
                    </span>
                  </div>
                  <div className="mt-1 text-base-content/80">
                    <MarkdownContent content={note.content} />
                  </div>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </aside>
  );
}

function ViewState({ existing, onEdit }: { existing?: TargetNoteEntry; onEdit: () => void }) {
  if (!existing || !existing.content.trim()) {
    return (
      <div className="rounded-lg border border-dashed border-base-300 p-4 text-center space-y-3 bg-base-100">
        <div className="flex justify-center text-base-content/40">
          <StickyNote className="h-7 w-7" />
        </div>
        <div className="text-sm text-base-content/70">No pinned summary yet.</div>
        <button className="btn btn-sm btn-primary" onClick={onEdit} type="button">
          <Pencil data-icon="inline-start" />
          Add summary
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="rounded-md bg-base-100 border border-base-300 p-3">
        <MarkdownContent content={existing.content} />
      </div>
      <div className="text-xs text-base-content/60 flex flex-wrap gap-x-2">
        <span>
          Last edited by{" "}
          <span className="font-medium text-base-content/80">{existing.username || "—"}</span>
        </span>
        {existing.updatedAt && <span>· {formatDateTime(existing.updatedAt)}</span>}
      </div>
      <div className="flex gap-2 pt-1">
        <button className="btn btn-sm btn-primary" onClick={onEdit} type="button">
          <Pencil data-icon="inline-start" />
          Edit
        </button>
      </div>
    </div>
  );
}

function EditState({
  existing,
  draft,
  onChange,
  onSave,
  onCancel,
  mutationPending,
  mentionCandidates,
}: {
  existing?: TargetNoteEntry;
  draft: string;
  onChange: (v: string) => void;
  onSave: () => void;
  onCancel: () => void;
  mutationPending: boolean;
  mentionCandidates?: MentionCandidate[];
}) {
  const trimmed = draft.trim();
  const isTooLong = draft.length > 5000;
  return (
    <div className="space-y-2">
      <MarkdownEditor
        value={draft}
        onChange={onChange}
        onSubmit={onSave}
        placeholder="Pinned one-paragraph status or index. Put separate topics, images, and discussion in forum threads..."
        rows={8}
        disabled={mutationPending}
        mentionCandidates={mentionCandidates}
      />
      <div className="flex items-center justify-between text-xs text-base-content/50">
        <span className={isTooLong ? "text-error" : undefined}>{draft.length} / 5000</span>
        {existing?.updatedAt && (
          <span>
            Last edited {formatDateTime(existing.updatedAt)} by {existing.username || "—"}
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
        <div className="flex gap-2">
          <button className="btn btn-sm btn-ghost" onClick={onCancel} type="button">
            <X data-icon="inline-start" />
            Cancel
          </button>
          <button
            className="btn btn-sm btn-primary"
            onClick={onSave}
            disabled={mutationPending || (!trimmed && !existing) || isTooLong}
            type="button"
          >
            <Save data-icon="inline-start" />
            {mutationPending ? "Saving…" : trimmed ? "Save summary" : "Clear summary"}
          </button>
        </div>
      </div>
    </div>
  );
}
