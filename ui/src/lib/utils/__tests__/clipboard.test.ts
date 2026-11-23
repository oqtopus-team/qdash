import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { copyText } from "../clipboard";

type ClipboardStub = { writeText: ReturnType<typeof vi.fn> } | undefined;

/** Replaces `navigator.clipboard`, leaving other `navigator` properties untouched. */
function stubClipboard(clipboard: ClipboardStub) {
  vi.stubGlobal(
    "navigator",
    new Proxy(navigator, {
      get(target, property) {
        if (property === "clipboard") return clipboard;
        return Reflect.get(target, property, target);
      },
    }),
  );
}

interface ExecSnapshot {
  command: string;
  textareaValue: string | null;
  selectedText: string | null;
  textareaFocused: boolean;
  textareaParent: Element | null;
}

/**
 * Installs `document.execCommand` (absent in jsdom) and records the DOM state at the moment the
 * legacy copy runs, so tests can assert what would have been on the clipboard.
 */
function stubExecCommand(result: boolean | (() => boolean)) {
  const snapshots: ExecSnapshot[] = [];
  const execCommand = vi.fn((command: string) => {
    const textarea = document.querySelector("textarea");
    snapshots.push({
      command,
      textareaValue: textarea?.value ?? null,
      selectedText:
        textarea && textarea.selectionStart !== null && textarea.selectionEnd !== null
          ? textarea.value.slice(textarea.selectionStart, textarea.selectionEnd)
          : null,
      textareaFocused: textarea !== null && document.activeElement === textarea,
      textareaParent: textarea?.parentElement ?? null,
    });
    return typeof result === "function" ? result() : result;
  });
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    writable: true,
    value: execCommand,
  });
  return { execCommand, snapshots };
}

describe("copyText", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(document, "execCommand");
    document.getSelection()?.removeAllRanges();
    document.body.innerHTML = "";
  });

  it("uses the Clipboard API when it is available", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard({ writeText });
    const { execCommand } = stubExecCommand(true);

    await expect(copyText("hello")).resolves.toBeUndefined();

    expect(writeText).toHaveBeenCalledWith("hello");
    expect(execCommand).not.toHaveBeenCalled();
  });

  it("falls back to a legacy selection copy when the Clipboard API is missing (HTTP)", async () => {
    stubClipboard(undefined);
    const { execCommand, snapshots } = stubExecCommand(true);

    await expect(copyText("token-123")).resolves.toBeUndefined();

    expect(execCommand).toHaveBeenCalledOnce();
    expect(snapshots[0]).toMatchObject({
      command: "copy",
      textareaValue: "token-123",
      selectedText: "token-123",
      textareaFocused: true,
      textareaParent: document.body,
    });
  });

  it("runs the legacy copy synchronously so it stays inside the user gesture", () => {
    stubClipboard(undefined);
    const { execCommand } = stubExecCommand(true);

    void copyText("sync");

    expect(execCommand).toHaveBeenCalledOnce();
  });

  it("rejects when the Clipboard API is missing and the legacy copy is refused", async () => {
    stubClipboard(undefined);
    stubExecCommand(false);

    await expect(copyText("x")).rejects.toThrow("Clipboard is not available");
    expect(document.querySelector("textarea")).toBeNull();
  });

  it("rejects when neither the Clipboard API nor execCommand exists", async () => {
    stubClipboard(undefined);

    await expect(copyText("x")).rejects.toThrow("Clipboard is not available");
  });

  it("rejects when execCommand throws, and still cleans up", async () => {
    stubClipboard(undefined);
    stubExecCommand(() => {
      throw new Error("SecurityError");
    });

    await expect(copyText("x")).rejects.toThrow("Clipboard is not available");
    expect(document.querySelector("textarea")).toBeNull();
  });

  it("falls back to the legacy copy when the Clipboard API rejects", async () => {
    stubClipboard({
      writeText: vi.fn().mockRejectedValue(new Error("NotAllowedError")),
    });
    const { execCommand } = stubExecCommand(true);

    await expect(copyText("retry")).resolves.toBeUndefined();
    expect(execCommand).toHaveBeenCalledOnce();
  });

  it("rejects with the original error as cause when both mechanisms fail", async () => {
    const original = new Error("NotAllowedError");
    stubClipboard({ writeText: vi.fn().mockRejectedValue(original) });
    stubExecCommand(false);

    const failure = await copyText("x").catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(Error);
    expect((failure as Error).message).toBe("Failed to copy to clipboard");
    expect((failure as Error & { cause: unknown }).cause).toBe(original);
  });

  it("removes the temporary textarea and restores focus and selection", async () => {
    stubClipboard(undefined);
    stubExecCommand(true);

    const paragraph = document.createElement("p");
    paragraph.textContent = "selected text";
    const button = document.createElement("button");
    document.body.append(paragraph, button);
    button.focus();
    const range = document.createRange();
    range.selectNodeContents(paragraph);
    // addRange is ignored while a range exists, so clear the caret focus() may have placed.
    document.getSelection()?.removeAllRanges();
    document.getSelection()?.addRange(range);

    await copyText("copied");

    expect(document.querySelector("textarea")).toBeNull();
    expect(document.activeElement).toBe(button);
    const selection = document.getSelection();
    expect(selection?.rangeCount).toBe(1);
    const restored = selection?.getRangeAt(0);
    expect(restored?.startContainer).toBe(paragraph);
    expect(restored?.startOffset).toBe(0);
    expect(restored?.endContainer).toBe(paragraph);
    expect(restored?.endOffset).toBe(paragraph.childNodes.length);
  });

  it("restores the caret of a focused text field", async () => {
    stubClipboard(undefined);
    stubExecCommand(true);

    const input = document.createElement("input");
    input.value = "abcdef";
    document.body.append(input);
    input.focus();
    input.setSelectionRange(2, 4);

    await copyText("copied");

    expect(document.activeElement).toBe(input);
    expect([input.selectionStart, input.selectionEnd]).toEqual([2, 4]);
  });

  it("places the textarea inside the focused modal so its focus trap keeps the selection", async () => {
    stubClipboard(undefined);
    const { snapshots } = stubExecCommand(true);

    const outerDialog = document.createElement("div");
    outerDialog.setAttribute("role", "dialog");
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    const button = document.createElement("button");
    dialog.append(button);
    document.body.append(dialog, outerDialog);
    button.focus();

    await copyText("password");

    expect(snapshots[0].textareaParent).toBe(dialog);
    expect(document.activeElement).toBe(button);
  });

  it("uses the only active modal when focus is not inside one", async () => {
    stubClipboard(undefined);
    const { snapshots } = stubExecCommand(true);

    const lower = document.createElement("div");
    lower.setAttribute("role", "dialog");
    lower.hidden = true;
    const upper = document.createElement("dialog");
    upper.setAttribute("open", "");
    document.body.append(lower, upper);

    await copyText("value");

    expect(snapshots[0].textareaParent).toBe(upper);
  });

  it.each(["hidden", "inert", "aria-hidden", "closed", "display", "visibility", "ancestor"])(
    "ignores a dialog hidden by %s",
    async (reason) => {
      stubClipboard(undefined);
      const { snapshots } = stubExecCommand(true);
      const ancestor = document.createElement("div");
      const dialog = document.createElement(reason === "closed" ? "dialog" : "div");
      dialog.setAttribute("role", "dialog");
      if (reason === "hidden") dialog.hidden = true;
      if (reason === "inert") dialog.setAttribute("inert", "");
      if (reason === "aria-hidden") dialog.setAttribute("aria-hidden", "true");
      if (reason === "display") dialog.style.display = "none";
      if (reason === "visibility") dialog.style.visibility = "hidden";
      if (reason === "ancestor") ancestor.style.display = "none";
      ancestor.append(dialog);
      document.body.append(ancestor);

      await copyText("value");

      expect(snapshots[0].textareaParent).toBe(document.body);
    },
  );

  it("does not infer modal stacking order from DOM order", async () => {
    stubClipboard(undefined);
    const { snapshots } = stubExecCommand(true);
    for (let index = 0; index < 2; index += 1) {
      const dialog = document.createElement("div");
      dialog.setAttribute("role", "dialog");
      document.body.append(dialog);
    }

    await copyText("value");

    expect(snapshots[0].textareaParent).toBe(document.body);
  });

  it("honours an explicit container", async () => {
    stubClipboard(undefined);
    const { snapshots } = stubExecCommand(true);
    const container = document.createElement("section");
    document.body.append(container);

    await copyText("value", { container });

    expect(snapshots[0].textareaParent).toBe(container);
  });
});
