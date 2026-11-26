import type { ForumPostResponse } from "@/schemas";

import { formatDateTimeCompact } from "@/lib/utils/datetime";

export type ForumTargetType = "qubit" | "coupling";

export type ForumTargetContext = {
  chipId: string;
  targetType: ForumTargetType;
  targetId: string;
};

export function normalizeTargetType(value: string | null | undefined): ForumTargetType | null {
  return value === "qubit" || value === "coupling" ? value : null;
}

export function formatTargetLabel(targetType: ForumTargetType, targetId: string): string {
  if (targetType === "coupling") {
    const [a, b] = targetId.split("-");
    return b ? `Q${a} -> Q${b}` : targetId;
  }
  return `Q${targetId}`;
}

/** "start - end" of a cooldown, "ongoing" while it has not ended, or "" without a start. */
export function formatCooldownPeriod(
  cooldown: { started_at?: string | null; ended_at?: string | null } | undefined,
): string {
  if (!cooldown?.started_at) return "";
  const start = formatDateTimeCompact(cooldown.started_at);
  const end = cooldown.ended_at ? formatDateTimeCompact(cooldown.ended_at) : "ongoing";
  return `${start} - ${end}`;
}

function parseTargetId(
  targetLabel: string,
): { targetType: ForumTargetType; targetId: string } | null {
  const qids = Array.from(targetLabel.matchAll(/Q(\d+)/g)).map((match) => match[1]);
  if (qids.length >= 2) return { targetType: "coupling", targetId: `${qids[0]}-${qids[1]}` };
  if (qids.length === 1) return { targetType: "qubit", targetId: qids[0] };
  return null;
}

/**
 * The chip target a post is about: its structured target fields, or for older posts the
 * "Chip:" and "Target:" lines of a prefilled draft.
 */
export function postTargetContext(post: ForumPostResponse): ForumTargetContext | null {
  const targetType = normalizeTargetType(post.target_type);
  if (post.chip_id && targetType && post.target_id) {
    return {
      chipId: post.chip_id,
      targetType,
      targetId: post.target_id,
    };
  }
  const chip = post.content.match(/^Chip:\s*(.+)$/m)?.[1]?.trim();
  const target = post.content.match(/^Target:\s*(.+)$/m)?.[1]?.trim();
  const parsed = target ? parseTargetId(target) : null;
  if (!chip || !target || !parsed) return null;
  return {
    chipId: chip,
    targetType: parsed.targetType,
    targetId: parsed.targetId,
  };
}
