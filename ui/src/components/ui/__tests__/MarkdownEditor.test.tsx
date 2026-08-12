import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarkdownEditor } from "@/components/ui/MarkdownEditor";

describe("MarkdownEditor", () => {
  afterEach(() => cleanup());

  it("gives every icon-only toolbar action an accessible name", () => {
    render(<MarkdownEditor value="" onChange={vi.fn()} onImageUpload={vi.fn()} />);

    for (const name of [
      "Bold",
      "Italic",
      "Strikethrough",
      "Code",
      "Link",
      "Quote",
      "Bullet List",
      "Ordered List",
      "Upload image",
    ]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
  });
});
