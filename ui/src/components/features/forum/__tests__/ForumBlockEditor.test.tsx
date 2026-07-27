import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ForumBlockViewer } from "../ForumBlockEditor";

describe("ForumBlockViewer", () => {
  afterEach(cleanup);

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
});
