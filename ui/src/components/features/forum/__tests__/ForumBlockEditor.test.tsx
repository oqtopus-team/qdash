import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { filterForumMentionCandidates, ForumBlockViewer } from "../ForumBlockEditor";

describe("filterForumMentionCandidates", () => {
  const candidates = [
    { id: "qdash", label: "QDash" },
    { id: "project", label: "Project", secondaryLabel: "Notify all project members" },
    { id: "alice", label: "Alice Smith", secondaryLabel: "Quantum team" },
  ];

  it("matches mention IDs and display labels case-insensitively", () => {
    expect(filterForumMentionCandidates(candidates, "DAS")).toEqual([candidates[0]]);
    expect(filterForumMentionCandidates(candidates, "smith")).toEqual([candidates[2]]);
  });

  it("matches secondary labels", () => {
    expect(filterForumMentionCandidates(candidates, "all project")).toEqual([candidates[1]]);
    expect(filterForumMentionCandidates(candidates, "quantum")).toEqual([candidates[2]]);
  });
});

describe("ForumBlockViewer", () => {
  afterEach(cleanup);

  it("renders a selected mention with persistent emphasis", () => {
    render(
      <ForumBlockViewer
        blocks={[
          {
            id: "paragraph-1",
            type: "paragraph",
            content: [
              {
                type: "text",
                text: "@alice",
                styles: { bold: true, textColor: "blue", backgroundColor: "blue" },
              },
              { type: "text", text: " please review", styles: {} },
            ],
          },
        ]}
      />,
    );

    const mention = screen.getByText("@alice");
    expect(mention.closest('[data-style-type="textColor"]')?.getAttribute("data-value")).toBe(
      "blue",
    );
    expect(mention.closest('[data-style-type="backgroundColor"]')?.getAttribute("data-value")).toBe(
      "blue",
    );
  });

  it("renders links in BlockNote inline content", () => {
    render(
      <ForumBlockViewer
        blocks={[
          {
            id: "paragraph-1",
            type: "paragraph",
            content: [
              { type: "text", text: "See ", styles: {} },
              {
                type: "link",
                href: "https://example.com/docs",
                content: [{ type: "text", text: "the documentation", styles: {} }],
              },
              { type: "text", text: " for details.", styles: {} },
            ],
          },
        ]}
      />,
    );

    const link = screen.getByRole("link", { name: "the documentation" });
    expect(link.getAttribute("href")).toBe("https://example.com/docs");
    expect(link.closest("p")?.textContent).toBe("See the documentation for details.");
  });

  it("renders unsafe link text without making it clickable", () => {
    render(
      <ForumBlockViewer
        blocks={[
          {
            id: "paragraph-1",
            type: "paragraph",
            content: [
              {
                type: "link",
                href: "javascript:alert(1)",
                content: [{ type: "text", text: "unsafe link", styles: {} }],
              },
            ],
          },
        ]}
      />,
    );

    expect(screen.getByText("unsafe link")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("renders BlockNote tables in read-only previews", () => {
    render(
      <ForumBlockViewer
        blocks={[
          {
            id: "table-1",
            type: "table",
            props: { textColor: "default" },
            content: {
              type: "tableContent",
              columnWidths: [120, 120],
              rows: [
                {
                  cells: [
                    {
                      type: "tableCell",
                      props: {
                        backgroundColor: "default",
                        textColor: "default",
                        textAlignment: "left",
                        colspan: 1,
                        rowspan: 1,
                      },
                      content: [{ type: "text", text: "Qubit", styles: {} }],
                    },
                    {
                      type: "tableCell",
                      props: {
                        backgroundColor: "default",
                        textColor: "default",
                        textAlignment: "left",
                        colspan: 1,
                        rowspan: 1,
                      },
                      content: [{ type: "text", text: "Frequency", styles: {} }],
                    },
                  ],
                },
              ],
            },
            children: [],
          },
        ]}
      />,
    );

    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("Qubit")).toBeTruthy();
    expect(screen.getByText("Frequency")).toBeTruthy();
  });
});
