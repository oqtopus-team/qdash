export type AiReviewBadgeState = {
  badgeClass: string;
  iconClass: string;
  label: string;
  title: string;
  tooltip: string;
};

export function getAiReviewBadgeState(content: string): AiReviewBadgeState | null {
  if (!content.includes("## AI review")) return null;

  const decision = extractAiReviewDecision(content);
  if (decision === "PASS" || decision === "PASS_WITH_NOTE") {
    return {
      badgeClass: "badge-success",
      iconClass: "bg-success text-success-content",
      label: "Pass",
      title: "AI reviewed",
      tooltip: "AI reviewed",
    };
  }
  if (decision === "REVIEW" || decision === "FAIL") {
    return reviewRequiredBadge;
  }

  return hasAiReviewNeedsReview(content) ? reviewRequiredBadge : null;
}

function extractAiReviewDecision(content: string): string | null {
  const match = content.match(
    /(?:^|\n)\s*(?:-?\s*)?(?:Decision|判定|決定|결정)\s*:\s*`?([A-Z_]+)`?/i,
  );
  return match?.[1]?.toUpperCase() ?? null;
}

function hasAiReviewNeedsReview(content: string): boolean {
  const needsReviewMatch = content.match(
    /(?:^|\n)\s*(?:-?\s*)?(?:Needs review|要レビュー|検討必要|검토 필요)\s*:\s*([^\n]+)/i,
  );
  if (!needsReviewMatch) return false;

  const needsReview = needsReviewMatch[1].replace(/[`*]/g, "").trim().toLowerCase();
  return Boolean(
    needsReview && needsReview !== "none" && needsReview !== "なし" && needsReview !== "없음",
  );
}

const reviewRequiredBadge: AiReviewBadgeState = {
  badgeClass: "badge-warning",
  iconClass: "bg-warning text-warning-content",
  label: "Review",
  title: "AI review needs review",
  tooltip: "AI review needs review",
};
