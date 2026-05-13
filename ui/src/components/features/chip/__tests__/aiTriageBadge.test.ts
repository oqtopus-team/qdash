import { describe, expect, it } from "vitest";

import { getAiTriageBadgeState } from "@/components/features/chip/aiTriageBadge";

describe("getAiTriageBadgeState", () => {
  it("returns pass badge for canonical English triage notes", () => {
    const badge = getAiTriageBadgeState(
      [
        "## AI triage",
        "",
        "**Review triage**",
        "- Decision: `PASS`",
        "- Needs review: none",
      ].join("\n"),
    );

    expect(badge?.label).toBe("Pass");
    expect(badge?.badgeClass).toBe("badge-success");
  });

  it("returns pass badge for Korean decision labels in persisted triage notes", () => {
    const badge = getAiTriageBadgeState(
      [
        "## AI triage",
        "",
        "검토 분류",
        "결정: PASS",
        "검토 필요: none",
      ].join("\n"),
    );

    expect(badge?.label).toBe("Pass");
    expect(badge?.badgeClass).toBe("badge-success");
  });
});
