import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchInput } from "@/components/ui/SearchInput";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
function makeVisible(input: HTMLElement) {
  vi.spyOn(input, "getClientRects").mockReturnValue(
    Object.assign([new DOMRect()], { item: () => new DOMRect() }),
  );
}

describe("SearchInput", () => {
  it("focuses and selects the query with / without typing a slash", () => {
    const onChange = vi.fn();
    render(<SearchInput value="rabi" onChange={onChange} />);
    const input = screen.getByRole("textbox", { name: "Search" }) as HTMLInputElement;
    makeVisible(input);
    expect(fireEvent.keyDown(window, { key: "/" })).toBe(false);
    expect(input).toHaveFocus();
    expect(input.selectionStart).toBe(0);
    expect(input.selectionEnd).toBe(4);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("clears with Escape, keeps focus and lets empty-search Escape propagate", () => {
    const onChange = vi.fn();
    const onKeyDown = vi.fn();
    const { rerender } = render(
      <div onKeyDown={onKeyDown}>
        <SearchInput value="rabi" onChange={onChange} />
      </div>,
    );
    const input = screen.getByRole("textbox");
    fireEvent.keyDown(input, { key: "Escape", isComposing: true });
    expect(onChange).not.toHaveBeenCalled();
    onKeyDown.mockClear();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onChange).toHaveBeenCalledWith("");
    expect(input).toHaveFocus();
    expect(onKeyDown).not.toHaveBeenCalled();
    rerender(
      <div onKeyDown={onKeyDown}>
        <SearchInput value="" onChange={onChange} />
      </div>,
    );
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onKeyDown).toHaveBeenCalledOnce();
  });

  it("uses the custom clear handler and returns focus after clicking clear", () => {
    const onClear = vi.fn();
    const onChange = vi.fn();
    render(<SearchInput value="rabi" onChange={onChange} onClear={onClear} />);
    const button = screen.getByRole("button", { name: "Clear search" });
    button.focus();
    fireEvent.click(button);
    expect(onClear).toHaveBeenCalledOnce();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox")).toHaveFocus();
  });

  it.each(["input", "textarea", "select", "contenteditable"])(
    "does not interrupt typing in %s",
    (tag) => {
      render(<SearchInput value="" onChange={vi.fn()} />);
      makeVisible(screen.getByRole("textbox"));
      const editor = document.createElement(tag === "contenteditable" ? "div" : tag);
      if (tag === "contenteditable") editor.setAttribute("contenteditable", "true");
      editor.tabIndex = 0;
      document.body.appendChild(editor);
      editor.focus();
      fireEvent.keyDown(editor, { key: "/" });
      expect(editor).toHaveFocus();
      editor.remove();
    },
  );

  it("ignores shortcuts while a dialog is open", () => {
    render(
      <>
        <SearchInput value="" onChange={vi.fn()} />
        <div role="dialog" />
      </>,
    );
    const input = screen.getByRole("textbox");
    makeVisible(input);
    fireEvent.keyDown(window, { key: "/" });
    expect(input).not.toHaveFocus();
  });

  it("ignores modifiers, composition and repeated key presses", () => {
    render(<SearchInput value="" onChange={vi.fn()} />);
    const input = screen.getByRole("textbox");
    makeVisible(input);
    for (const modifier of ["ctrlKey", "metaKey", "altKey", "isComposing", "repeat"]) {
      fireEvent.keyDown(window, { key: "/", [modifier]: true });
      expect(input).not.toHaveFocus();
    }
  });

  it("skips hidden fields and focuses only the first visible search", () => {
    render(
      <>
        <SearchInput value="" onChange={vi.fn()} placeholder="Hidden" />
        <SearchInput value="" onChange={vi.fn()} placeholder="First" />
        <SearchInput value="" onChange={vi.fn()} placeholder="Second" />
      </>,
    );
    makeVisible(screen.getByRole("textbox", { name: "First" }));
    makeVisible(screen.getByRole("textbox", { name: "Second" }));
    fireEvent.keyDown(window, { key: "/" });
    expect(screen.getByRole("textbox", { name: "First" })).toHaveFocus();
  });
});
