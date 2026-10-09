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
      is_system: true,
    };

    expect(toForumLabelDefinition(response)).toEqual({
      id: "anomaly",
      label: "Anomaly",
      description: "Unexpected behavior",
      color: "#f59e0b",
      isSystem: true,
    });
  });

  it("defaults description to an empty string and isSystem to false when omitted", () => {
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
      isSystem: false,
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
      isSystem: true,
    },
    {
      id: "review",
      label: "Review",
      description: "Needs review",
      color: "#2563eb",
      isSystem: false,
    },
  ];

  it("returns the matching label definition for a known key", () => {
    expect(getForumLabel("anomaly", labels)).toEqual(labels[0]);
  });

  it("falls back to a gray, non-system definition for an unknown key", () => {
    expect(getForumLabel("deprecated", labels)).toEqual({
      id: "deprecated",
      label: "deprecated",
      description: "",
      color: NEUTRAL_FORUM_LABEL_COLOR,
      isSystem: false,
    });
  });

  it("falls back to the gray default when no labels are provided", () => {
    expect(getForumLabel("anomaly")).toEqual({
      id: "anomaly",
      label: "anomaly",
      description: "",
      color: "#6b7280",
      isSystem: false,
    });
  });
});
