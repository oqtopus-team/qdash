"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { ExternalLink, MessageSquarePlus, Pencil, Save, StickyNote, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { useListForumPosts } from "@/client/forum/forum";
import {
  getGetChipNotesSummaryQueryKey,
  useDeleteCouplingNote,
  useDeleteQubitNote,
  useUpsertCouplingNote,
  useUpsertQubitNote,
} from "@/client/note/note";
import type { GetChipNotesSummaryParams } from "@/schemas";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor, type MentionCandidate } from "@/components/ui/MarkdownEditor";
import { formatDateTime } from "@/lib/utils/datetime";

import { formatForumPostTitle, getForumLabel } from "../forum/categories";

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

function formatTarget(targetId: string): string {
  if (targetId.includes("-")) {
    const [a, b] = targetId.split("-");
    return `Q${a} → Q${b}`;
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
      className="flex flex-col bg-base-200/40 border-l border-base-300 lg:h-full overflow-hidden"
      aria-label="Pinned summary"
    >
      {/* Section header */}
      <div className="px-4 pt-4 pb-2 border-b border-base-300/70">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <StickyNote className="h-4 w-4 text-warning" />
          Pinned summary
        </div>
        <div className="mt-0.5 text-xs text-base-content/60">{scopeLabel}</div>
        <div className="mt-1 text-xs text-base-content/50">
          For {formatTarget(targetId)} while viewing {metricTitle}. Use forum topics for separate
          issues, images, and multi-person discussion.
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto p-4 space-y-3">
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
              <span className="text-xs font-semibold">Linked forum discussions</span>
              <p className="mt-0.5 text-[11px] leading-snug text-base-content/50">
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
                          {(post.labels ?? []).map((label) => {
                            const labelDef = getForumLabel(label);
                            return (
                              <span key={label} className={`badge badge-xs ${labelDef.badgeClass}`}>
                                {labelDef.label}
                              </span>
                            );
                          })}
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
            <summary className="px-3 py-2 cursor-pointer text-xs font-semibold flex items-center justify-between">
              <span>
                Legacy metric notes
                <span className="ml-1 text-base-content/60 font-normal">
                  ({(legacyMetricNote ? 1 : 0) + (legacyMetricNotes?.length ?? 0)})
                </span>
              </span>
              <span className="text-base-content/40 font-normal">old dashboard notes</span>
            </summary>
            <div className="px-3 pb-2 text-[11px] text-base-content/50">
              Read-only notes originally written on individual metric cells. Use pinned summary or
              forum discussions for new notes.
            </div>
            <ul className="px-3 pb-3 pt-1 space-y-2 text-xs">
              {legacyMetricNote && (
                <li className="border-l-2 border-warning pl-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{metricTitle}</span>
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
                    <span className="font-semibold">{note.metricTitle}</span>
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
        <button className="btn btn-sm btn-primary gap-1" onClick={onEdit} type="button">
          <Pencil className="h-3.5 w-3.5" />
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
      <div className="text-[11px] text-base-content/60 flex flex-wrap gap-x-2">
        <span>
          Last edited by{" "}
          <span className="font-medium text-base-content/80">{existing.username || "—"}</span>
        </span>
        {existing.updatedAt && <span>· {formatDateTime(existing.updatedAt)}</span>}
      </div>
      <div className="flex gap-2 pt-1">
        <button className="btn btn-sm btn-primary gap-1" onClick={onEdit} type="button">
          <Pencil className="h-3.5 w-3.5" />
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
      <div className="flex items-center justify-between text-[11px] text-base-content/50">
        <span className={isTooLong ? "text-error" : undefined}>{draft.length} / 5000</span>
        {existing?.updatedAt && (
          <span>
            Last edited {formatDateTime(existing.updatedAt)} by {existing.username || "—"}
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
        <div className="flex gap-2">
          <button className="btn btn-sm btn-ghost gap-1" onClick={onCancel} type="button">
            <X className="h-3.5 w-3.5" />
            Cancel
          </button>
          <button
            className="btn btn-sm btn-primary gap-1"
            onClick={onSave}
            disabled={mutationPending || (!trimmed && !existing) || isTooLong}
            type="button"
          >
            <Save className="h-3.5 w-3.5" />
            {mutationPending ? "Saving…" : trimmed ? "Save summary" : "Clear summary"}
          </button>
        </div>
      </div>
    </div>
  );
}
