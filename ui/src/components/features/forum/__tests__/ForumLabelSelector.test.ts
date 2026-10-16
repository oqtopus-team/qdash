import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";

import { getForumLabelErrorMessage, type ForumLabelDefinition } from "../categories";
import {
  filterForumLabels,
  getForumLabelEnterAction,
  shouldShowCreateForumLabelOption,
} from "../ForumLabelSelector";

const LABELS: ForumLabelDefinition[] = [
  { id: "bug", label: "Bug", description: "Something is broken", color: "#ef4444" },
  {
    id: "enhancement",
    label: "Enhancement",
    description: "New feature or request",
    color: "#22c55e",
  },
  { id: "readout", label: "Readout", description: "", color: "#3b82f6" },
];

describe("filterForumLabels", () => {
  it("returns all labels when the query is empty", () => {
    expect(filterForumLabels(LABELS, "")).toEqual(LABELS);
  });

  it("returns all labels when the query is only whitespace", () => {
    expect(filterForumLabels(LABELS, "   ")).toEqual(LABELS);
  });

  it("matches the display name case-insensitively", () => {
    expect(filterForumLabels(LABELS, "bug")).toEqual([LABELS[0]]);
    expect(filterForumLabels(LABELS, "BUG")).toEqual([LABELS[0]]);
  });

  it("matches the key case-insensitively", () => {
    expect(filterForumLabels(LABELS, "read")).toEqual([LABELS[2]]);
  });

  it("matches the description case-insensitively", () => {
    expect(filterForumLabels(LABELS, "broken")).toEqual([LABELS[0]]);
  });

  it("trims surrounding whitespace before matching", () => {
    expect(filterForumLabels(LABELS, "  bug  ")).toEqual([LABELS[0]]);
  });

  it("returns an empty array when nothing matches", () => {
    expect(filterForumLabels(LABELS, "no-such-label")).toEqual([]);
  });
});

describe("shouldShowCreateForumLabelOption", () => {
  it("returns false for an empty query", () => {
    expect(shouldShowCreateForumLabelOption("", LABELS)).toBe(false);
  });

  it("returns false for a whitespace-only query", () => {
    expect(shouldShowCreateForumLabelOption("   ", LABELS)).toBe(false);
  });

  it("returns true when the query does not match any existing label name or key", () => {
    expect(shouldShowCreateForumLabelOption("flaky-qubit", LABELS)).toBe(true);
  });

  it("returns false when the query exactly matches an existing label name, case-insensitively", () => {
    expect(shouldShowCreateForumLabelOption("bug", LABELS)).toBe(false);
    expect(shouldShowCreateForumLabelOption("BUG", LABELS)).toBe(false);
  });

  it("returns false when the query exactly matches an existing label key, case-insensitively", () => {
    expect(shouldShowCreateForumLabelOption("ENHANCEMENT", LABELS)).toBe(false);
  });

  it("returns true for a partial match that is not an exact name or key match", () => {
    expect(shouldShowCreateForumLabelOption("bu", LABELS)).toBe(true);
  });

  it("ignores leading/trailing whitespace when comparing for an exact match", () => {
    expect(shouldShowCreateForumLabelOption("  bug  ", LABELS)).toBe(false);
  });
});

describe("getForumLabelEnterAction", () => {
  it("toggles the first filtered label when there are matches", () => {
    expect(getForumLabelEnterAction([LABELS[0], LABELS[1]], true)).toEqual({
      type: "toggle",
      labelId: "bug",
    });
  });

  it("creates a label when there are no filtered matches and the create option is visible", () => {
    expect(getForumLabelEnterAction([], true)).toEqual({ type: "create" });
  });

  it("does nothing when there are no filtered matches and the create option is hidden", () => {
    expect(getForumLabelEnterAction([], false)).toEqual({ type: "none" });
  });
});

describe("getForumLabelErrorMessage", () => {
  it("returns a duplicate-name message for a 409 response", () => {
    const error = new AxiosError("Conflict", "ERR_BAD_REQUEST", undefined, undefined, {
      status: 409,
    } as AxiosError["response"]);
    expect(getForumLabelErrorMessage(error, "Failed to create label")).toBe(
      "A label with this name already exists",
    );
  });

  it("returns the fallback message for a non-409 axios error", () => {
    const error = new AxiosError("Server error", "ERR_BAD_RESPONSE", undefined, undefined, {
      status: 500,
    } as AxiosError["response"]);
    expect(getForumLabelErrorMessage(error, "Failed to create label")).toBe(
      "Failed to create label",
    );
  });

  it("returns the fallback message for a non-axios error", () => {
    expect(getForumLabelErrorMessage(new Error("boom"), "Failed to delete label")).toBe(
      "Failed to delete label",
    );
  });
});
