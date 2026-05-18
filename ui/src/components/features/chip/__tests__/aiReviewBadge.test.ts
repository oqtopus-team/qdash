import { describe, expect, it } from "vitest";

import { getAiReviewBadgeState } from "@/components/features/chip/aiReviewBadge";

describe("getAiReviewBadgeState", () => {
  it("returns pass badge for canonical English review notes", () => {
    const badge = getAiReviewBadgeState(
      ["## AI review", "", "**AI review**", "- Decision: `PASS`", "- Needs review: none"].join(
        "\n",
      ),
    );

    expect(badge?.label).toBe("Pass");
    expect(badge?.badgeClass).toBe("badge-success");
  });

  it("returns pass badge for Korean decision labels in persisted review notes", () => {
    const badge = getAiReviewBadgeState(
      ["## AI review", "", "검토 분류", "결정: PASS", "검토 필요: none"].join("\n"),
    );

    expect(badge?.label).toBe("Pass");
    expect(badge?.badgeClass).toBe("badge-success");
  });
});
