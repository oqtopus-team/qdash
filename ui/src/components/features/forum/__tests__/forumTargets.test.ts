import { describe, expect, it } from "vitest";

import type { ForumPostResponse } from "@/schemas";

import {
  formatCooldownPeriod,
  formatTargetLabel,
  normalizeTargetType,
  postTargetContext,
} from "@/components/features/forum/forumTargets";

function post(fields: Partial<ForumPostResponse>): ForumPostResponse {
  return { content: "", ...fields } as ForumPostResponse;
}

describe("forum target helpers", () => {
  it("accepts only qubit and coupling target types", () => {
    expect(normalizeTargetType("qubit")).toBe("qubit");
    expect(normalizeTargetType("coupling")).toBe("coupling");
    expect(normalizeTargetType("chip")).toBeNull();
    expect(normalizeTargetType(undefined)).toBeNull();
  });

  it("labels qubit and coupling targets", () => {
    expect(formatTargetLabel("qubit", "3")).toBe("Q3");
    expect(formatTargetLabel("coupling", "0-1")).toBe("Q0 -> Q1");
    expect(formatTargetLabel("coupling", "odd")).toBe("odd");
  });

  it("describes a cooldown period, open-ended while ongoing", () => {
    expect(formatCooldownPeriod(undefined)).toBe("");
    expect(formatCooldownPeriod({ started_at: null })).toBe("");
    expect(formatCooldownPeriod({ started_at: "2026-11-01T00:00:00Z" })).toMatch(/ - ongoing$/);
  });

  it("prefers structured target fields over the draft text", () => {
    const context = postTargetContext(
      post({
        chip_id: "64Q",
        target_type: "coupling",
        target_id: "0-1",
        content: "Chip: 16Q\nTarget: Q5",
      }),
    );

    expect(context).toEqual({ chipId: "64Q", targetType: "coupling", targetId: "0-1" });
  });

  it("reads older posts from their Chip and Target lines", () => {
    expect(postTargetContext(post({ content: "Chip: 64Q\nTarget: Q0 -> Q1\n" }))).toEqual({
      chipId: "64Q",
      targetType: "coupling",
      targetId: "0-1",
    });
    expect(postTargetContext(post({ content: "Chip: 64Q\nTarget: Q7" }))).toEqual({
      chipId: "64Q",
      targetType: "qubit",
      targetId: "7",
    });
    expect(postTargetContext(post({ content: "Target: Q7" }))).toBeNull();
  });
});
