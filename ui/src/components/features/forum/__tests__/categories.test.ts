import { describe, expect, it } from "vitest";

import type { ForumLabelResponse } from "@/schemas";

import {
  getForumLabel,
  NEUTRAL_FORUM_LABEL_COLOR,
  toForumLabelDefinition,
  type ForumLabelDefinition,
} from "../categories";

describe("toForumLabelDefinition", () => {
  it("maps a forum label response to a label definition", () => {
    const response: ForumLabelResponse = {
      key: "anomaly",
      name: "Anomaly",
      description: "Unexpected behavior",
      color: "#f59e0b",
    };

    expect(toForumLabelDefinition(response)).toEqual({
      id: "anomaly",
      label: "Anomaly",
      description: "Unexpected behavior",
      color: "#f59e0b",
    });
  });

  it("defaults description to an empty string when omitted", () => {
    const response: ForumLabelResponse = {
      key: "custom",
      name: "Custom",
      color: "#2563eb",
    };

    expect(toForumLabelDefinition(response)).toEqual({
      id: "custom",
      label: "Custom",
      description: "",
      color: "#2563eb",
    });
  });
});

describe("getForumLabel", () => {
  const labels: ForumLabelDefinition[] = [
    {
      id: "anomaly",
      label: "Anomaly",
      description: "Unexpected behavior",
      color: "#f59e0b",
    },
    {
      id: "review",
      label: "Review",
      description: "Needs review",
      color: "#2563eb",
    },
  ];

  it("returns the matching label definition for a known key", () => {
    expect(getForumLabel("anomaly", labels)).toEqual(labels[0]);
  });

  it("falls back to a gray definition for an unknown key", () => {
    expect(getForumLabel("deprecated", labels)).toEqual({
      id: "deprecated",
      label: "deprecated",
      description: "",
      color: NEUTRAL_FORUM_LABEL_COLOR,
    });
  });

  it("falls back to the gray default when no labels are provided", () => {
    expect(getForumLabel("anomaly")).toEqual({
      id: "anomaly",
      label: "anomaly",
      description: "",
      color: "#6b7280",
    });
  });
});
