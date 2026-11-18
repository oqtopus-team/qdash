import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarkdownEditor } from "@/components/ui/MarkdownEditor";

const candidates = [
  { id: "alice", label: "Alice" },
  { id: "alan", label: "Alan" },
];

function MentionEditor() {
  const [value, setValue] = useState("");
  return <MarkdownEditor value={value} onChange={setValue} mentionCandidates={candidates} />;
}

function typeInto(textarea: HTMLTextAreaElement, text: string) {
  fireEvent.change(textarea, { target: { value: text, selectionStart: text.length } });
}

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

  it("exposes mention suggestions as a listbox driven from the textarea", () => {
    render(<MentionEditor />);
    const textarea = screen.getByRole("combobox") as HTMLTextAreaElement;
    expect(textarea.getAttribute("aria-expanded")).toBe("false");

    typeInto(textarea, "Ping @al");

    const listbox = screen.getByRole("listbox", { name: "Mention suggestions" });
    expect(textarea.getAttribute("aria-expanded")).toBe("true");
    expect(textarea.getAttribute("aria-controls")).toBe(listbox.id);
    const options = screen.getAllByRole("option");
    expect(options.map((option) => option.getAttribute("aria-selected"))).toEqual([
      "true",
      "false",
    ]);

    fireEvent.keyDown(textarea, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[1].getAttribute("aria-selected")).toBe("true");
    expect(textarea.getAttribute("aria-activedescendant")).toBe(options[1].id);

    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(textarea.value).toBe("Ping @alan ");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("closes mention suggestions on Escape without changing the text", () => {
    render(<MentionEditor />);
    const textarea = screen.getByRole("combobox") as HTMLTextAreaElement;

    typeInto(textarea, "@a");
    expect(screen.getByRole("listbox")).toBeTruthy();

    fireEvent.keyDown(textarea, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(textarea.value).toBe("@a");
  });
});
