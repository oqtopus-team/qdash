import { describe, expect, it, vi } from "vitest";

vi.mock("@/client/forum/forum", () => ({ useListForumPosts: vi.fn() }));

import {
  formatNoteTarget,
  forumDraftHref,
  matchesForumTarget,
} from "@/components/features/overview/targetForumLinks";

describe("formatNoteTarget", () => {
  it("labels qubits and couplings, with the arrow the caller uses", () => {
    expect(formatNoteTarget("3")).toBe("Q3");
    expect(formatNoteTarget("0-1")).toBe("Q0 → Q1");
    expect(formatNoteTarget("0-1", "->")).toBe("Q0 -> Q1");
  });
});

describe("forumDraftHref", () => {
  it("prefills a coupling topic with the cooldown and the given label", () => {
    const url = new URL(forumDraftHref("64Q", "0-1", "cd-1", "Q0 -> Q1"), "http://x");
    const params = url.searchParams;

    expect(url.pathname).toBe("/forum/new");
    expect(params.get("category")).toBe("coupling");
    expect(params.get("target_type")).toBe("coupling");
    expect(params.get("target_label")).toBe("Q0 -> Q1");
    expect(params.get("title")).toBe("Q0 -> Q1: ");
    expect(params.get("content")).toBe("Chip: 64Q\nTarget: Q0 -> Q1\n\nNotes:");
    expect(params.get("cooldown_id")).toBe("cd-1");
  });

  it("omits an empty cooldown for a qubit", () => {
    const params = new URL(forumDraftHref("64Q", "3", null), "http://x").searchParams;

    expect(params.get("category")).toBe("qubit");
    expect(params.get("target_label")).toBe("Q3");
    expect(params.has("cooldown_id")).toBe(false);
  });
});

describe("matchesForumTarget", () => {
  it("matches structured targets after normalizing padded IDs", () => {
    const post = { chip_id: "64Q", target_type: "coupling", target_id: "Q00-Q01" };

    expect(matchesForumTarget(post, "64Q", "0-1")).toBe(true);
    expect(matchesForumTarget(post, "64Q", "1-0")).toBe(false);
    expect(matchesForumTarget({ ...post, target_type: "qubit" }, "64Q", "0-1")).toBe(false);
  });

  it("falls back to the prefilled Chip and Target lines of older posts", () => {
    const content = "Chip: 64Q\nTarget: Q0 → Q1\n\nNotes:";

    expect(matchesForumTarget({ content }, "64Q", "0-1")).toBe(true);
    expect(matchesForumTarget({ content }, "16Q", "0-1")).toBe(false);
  });
});
