"use client";

import { useListForumPosts } from "@/client/forum/forum";

type NoteTargetType = "qubit" | "coupling";

function targetTypeOf(targetId: string): NoteTargetType {
  return targetId.includes("-") ? "coupling" : "qubit";
}

/** "Q0" for a qubit and "Q0 → Q1" for a coupling, with a configurable arrow. */
export function formatNoteTarget(targetId: string, arrow = "→"): string {
  if (targetId.includes("-")) {
    const [a, b] = targetId.split("-");
    return `Q${a} ${arrow} Q${b}`;
  }
  return `Q${targetId}`;
}

/** Link to a new forum topic prefilled with the chip, target, and cooldown. */
export function forumDraftHref(
  chipId: string,
  targetId: string,
  cooldownId: string | null | undefined,
  targetLabel: string = formatNoteTarget(targetId),
): string {
  const targetType = targetTypeOf(targetId);
  const params = new URLSearchParams({
    category: targetType,
    chip_id: chipId,
    target_id: targetId,
    target_type: targetType,
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
  targetType: NoteTargetType,
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

/**
 * Whether a forum post is about the target: by its structured target fields, or for older
 * posts by the "Chip:" and "Target:" lines of a prefilled draft.
 */
export function matchesForumTarget(
  post: {
    chip_id?: string | null;
    target_type?: string | null;
    target_id?: string | null;
    content?: string;
  },
  chipId: string,
  targetId: string,
): boolean {
  const targetType = targetTypeOf(targetId);
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

/** Forum posts linked to a qubit or coupling in the cooldown, newest first as listed. */
export function useLinkedForumPosts(
  chipId: string,
  targetId: string,
  cooldownId: string | null | undefined,
) {
  const { data } = useListForumPosts(
    {
      chip_id: chipId,
      target_type: targetTypeOf(targetId),
      target_id: targetId,
      cooldown_id: cooldownId || undefined,
      status: null,
      limit: 50,
    },
    { query: { staleTime: 30_000 } },
  );
  return data?.data.posts.filter((post) => matchesForumTarget(post, chipId, targetId)) ?? [];
}
