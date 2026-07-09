"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { ExternalLink, MessageSquarePlus, Pencil, Save, StickyNote, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { useListForumPosts } from "@/client/forum/forum";
import {
  getGetChipNotesSummaryQueryKey,
  useUpsertCouplingNote,
  useUpsertQubitNote,
} from "@/client/note/note";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor, type MentionCandidate } from "@/components/ui/MarkdownEditor";
import { formatDateTime } from "@/lib/utils/datetime";
import type { GetChipNotesSummaryParams } from "@/schemas";

import { formatForumPostTitle, getForumLabel } from "../forum/categories";

export interface TargetNoteEntry {
  targetId: string;
  content: string;
  username: string;
  updatedAt: string;
}

interface DashboardTargetNoteModalProps {
  chipId: string;
  targetId: string;
  cooldownId?: string | null;
  noteScopeParams?: GetChipNotesSummaryParams;
  existing?: TargetNoteEntry;
  mentionCandidates?: MentionCandidate[];
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
  mentionCandidates,
  onClose,
}: DashboardTargetNoteModalProps) {
  const queryClient = useQueryClient();
  const isCoupling = targetId.includes("-");
  const upsertQubit = useUpsertQubitNote();
  const upsertCoupling = useUpsertCouplingNote();
  const upsertPending = isCoupling ? upsertCoupling.isPending : upsertQubit.isPending;
  const { data: forumPostsResponse } = useListForumPosts(
    {
      chip_id: chipId,
      target_type: isCoupling ? "coupling" : "qubit",
      target_id: targetId,
      status: null,
      limit: 50,
    },
    { query: { staleTime: 30_000 } },
  );
  const relatedForumPosts =
    forumPostsResponse?.data.posts.filter((post) => matchesForumTarget(post, chipId, targetId)) ??
    [];

  const [mode, setMode] = useState<"view" | "edit">(existing ? "view" : "edit");
  const [draft, setDraft] = useState(existing?.content ?? "");

  useEffect(() => {
    setDraft(existing?.content ?? "");
    setMode(existing ? "view" : "edit");
  }, [existing, targetId]);

  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: getGetChipNotesSummaryQueryKey(chipId, noteScopeParams),
    });

  const handleSave = async () => {
    if (!draft.trim() || draft.length > 5000) return;
    if (isCoupling) {
      await upsertCoupling.mutateAsync({
        chipId,
        couplingId: targetId,
        data: { content: draft },
      });
    } else {
      await upsertQubit.mutateAsync({
        chipId,
        qid: targetId,
        data: { content: draft },
      });
    }
    await invalidate();
    onClose();
  };

  const isTooLong = draft.length > 5000;

  return (
    <div
      className="modal modal-open"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-box w-full max-w-2xl p-0 overflow-hidden">
        <div className="px-5 py-4 border-b border-base-300 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-lg font-bold">
              <StickyNote className="h-5 w-5 text-warning" />
              <span className="truncate">Pinned summary · {formatTarget(targetId)}</span>
            </div>
            <p className="text-sm text-base-content/60 mt-1">
              Keep this as a short index. Use forum topics for separate issues, images, and
              discussion.
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

        <div className="p-5 space-y-4">
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

          {mode === "view" && existing ? (
            <div className="space-y-3">
              <div className="rounded-md bg-base-100 border border-base-300 p-3">
                <MarkdownContent content={existing.content} />
              </div>
              <div className="text-[11px] text-base-content/60 flex flex-wrap gap-x-2">
                <span>
                  Last edited by{" "}
                  <span className="font-medium text-base-content/80">
                    {existing.username || "-"}
                  </span>
                </span>
                {existing.updatedAt && <span>· {formatDateTime(existing.updatedAt)}</span>}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-sm btn-primary gap-1"
                  onClick={() => setMode("edit")}
                  type="button"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </button>
              </div>
            </div>
          ) : (
            <>
              <MarkdownEditor
                value={draft}
                onChange={setDraft}
                onSubmit={handleSave}
                placeholder="Pinned one-paragraph status or index. Put separate topics, images, and discussion in forum threads..."
                rows={8}
                disabled={upsertPending}
                mentionCandidates={mentionCandidates}
              />
              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-base-content/50">
                <span className={isTooLong ? "text-error" : undefined}>{draft.length} / 5000</span>
                {existing?.updatedAt && (
                  <span>
                    Last edited {formatDateTime(existing.updatedAt)} by {existing.username || "-"}
                  </span>
                )}
              </div>
            </>
          )}
        </div>

        {mode === "edit" && (
          <div className="px-5 py-4 border-t border-base-300 flex flex-wrap justify-end gap-2">
            <div className="flex gap-2">
              <button className="btn btn-sm btn-ghost" onClick={onClose} type="button">
                Cancel
              </button>
              <button
                className="btn btn-sm btn-primary gap-1"
                onClick={handleSave}
                disabled={!draft.trim() || isTooLong || upsertPending}
                type="button"
              >
                <Save className="h-4 w-4" />
                {upsertPending ? "Saving..." : "Save summary"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
