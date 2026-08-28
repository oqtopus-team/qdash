import { describe, expect, it } from "vitest";

import { extractLinkedTaskResultIds } from "../taskResultLinks";

describe("extractLinkedTaskResultIds", () => {
  it("extracts relative and absolute task-result links", () => {
    expect(
      extractLinkedTaskResultIds(
        "Compare [first](/task-results/task-001) with https://qdash.example/task-results/task-002?tab=figure.",
        [],
      ),
    ).toEqual(["task-001", "task-002"]);
  });

  it("extracts links from BlockNote values and removes duplicates", () => {
    const blocks = [
      {
        type: "paragraph",
        content: [{ type: "link", href: "/task-results/task-003", content: "result" }],
      },
    ];

    expect(extractLinkedTaskResultIds("/task-results/task-003", blocks)).toEqual(["task-003"]);
  });

  it("limits previews to three linked results", () => {
    expect(
      extractLinkedTaskResultIds(
        [1, 2, 3, 4].map((id) => `/task-results/task-${id}`).join(" "),
        [],
      ),
    ).toEqual(["task-1", "task-2", "task-3"]);
  });

  it("ignores unrelated links", () => {
    expect(extractLinkedTaskResultIds("See /forum/123 and https://example.com", [])).toEqual([]);
  });
});
