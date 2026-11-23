/**
 * Plain-text clipboard copy that also works when QDash is served over plain HTTP.
 *
 * Browsers expose `navigator.clipboard` only in secure contexts (HTTPS or localhost), so a
 * deployment reached by IP or hostname over HTTP has no Clipboard API at all. In that case,
 * and when the API rejects, `copyText` falls back to the legacy selection plus
 * `document.execCommand("copy")` path, which most browsers still honour during a user gesture.
 */

/** Matches open modal surfaces whose focus trap would pull focus away from <body>. */
const MODAL_SELECTOR = 'dialog[open], [role="dialog"], [role="alertdialog"]';

interface CopyTextOptions {
  /**
   * Element that receives the temporary textarea used by the legacy fallback.
   * Defaults to the modal containing the focused element, then the only active modal,
   * then `document.body`, so focus-trapping dialogs do not block the selection.
   */
  container?: HTMLElement;
}

/** Raised when the text could not be copied by any available mechanism. */
class ClipboardCopyError extends Error {
  readonly cause: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = "ClipboardCopyError";
    this.cause = cause;
  }
}

/** Excludes closed surfaces and dialogs hidden or disabled by an ancestor. */
function isActiveModal(modal: HTMLElement): boolean {
  for (let element: HTMLElement | null = modal; element; element = element.parentElement) {
    if (
      element.hidden ||
      element.hasAttribute("inert") ||
      element.getAttribute("aria-hidden") === "true" ||
      element.getAttribute("data-state") === "closed" ||
      (element.tagName === "DIALOG" && !element.hasAttribute("open"))
    ) {
      return false;
    }
    const style = getComputedStyle(element);
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      style.visibility === "collapse"
    ) {
      return false;
    }
  }
  return true;
}

/** Picks where the temporary textarea goes so a modal focus trap keeps it focusable. */
function resolveContainer(activeElement: Element | null): HTMLElement {
  const activeModal = activeElement?.closest<HTMLElement>(MODAL_SELECTOR);
  if (activeModal && isActiveModal(activeModal)) return activeModal;
  const openModals = Array.from(document.querySelectorAll<HTMLElement>(MODAL_SELECTOR)).filter(
    isActiveModal,
  );
  // DOM order does not establish stacking order. Only infer an unambiguous modal.
  return openModals.length === 1 ? openModals[0] : document.body;
}

type FieldSelection = {
  start: number | null;
  end: number | null;
  direction: "forward" | "backward" | "none" | null;
};

/** Reads a text field's selection; input types without selection support report nulls. */
function saveFieldSelection(field: HTMLInputElement | HTMLTextAreaElement): FieldSelection {
  try {
    return {
      start: field.selectionStart,
      end: field.selectionEnd,
      direction: field.selectionDirection,
    };
  } catch {
    return { start: null, end: null, direction: null };
  }
}

/** Puts back a selection captured by `saveFieldSelection`, when the field supports one. */
function restoreFieldSelection(
  field: HTMLInputElement | HTMLTextAreaElement,
  saved: FieldSelection,
): void {
  if (saved.start === null || saved.end === null) return;
  try {
    field.setSelectionRange(saved.start, saved.end, saved.direction ?? undefined);
  } catch {
    // Some input types (e.g. email, number) reject selection APIs; leave the caret as is.
  }
}

/**
 * Copies `text` with a hidden textarea and `document.execCommand("copy")`.
 *
 * Runs synchronously so it stays inside the user gesture, then removes the textarea and
 * restores the previous focus and document selection. Returns whether the browser reported
 * a successful copy.
 */
function copyTextWithSelection(text: string, options: CopyTextOptions = {}): boolean {
  if (typeof document === "undefined" || typeof document.execCommand !== "function") {
    return false;
  }

  const activeElement =
    document.activeElement instanceof HTMLElement ? document.activeElement : null;
  // Text fields keep their own selection; everything else uses the document selection.
  const activeField =
    activeElement instanceof HTMLInputElement || activeElement instanceof HTMLTextAreaElement
      ? activeElement
      : null;
  const fieldSelection = activeField ? saveFieldSelection(activeField) : null;
  const selection = document.getSelection();
  const savedRanges: Range[] = [];
  if (selection && !activeField) {
    for (let index = 0; index < selection.rangeCount; index += 1) {
      savedRanges.push(selection.getRangeAt(index).cloneRange());
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.setAttribute("aria-hidden", "true");
  textarea.tabIndex = -1;
  // Keep it renderable (display:none cannot be selected) but invisible and out of layout.
  // A 16px font stops iOS Safari from zooming when the textarea gains focus.
  Object.assign(textarea.style, {
    position: "fixed",
    top: "0",
    left: "0",
    width: "1px",
    height: "1px",
    padding: "0",
    border: "0",
    margin: "0",
    opacity: "0",
    pointerEvents: "none",
    fontSize: "16px",
  });

  const container = options.container ?? resolveContainer(activeElement);
  container.appendChild(textarea);

  try {
    textarea.focus({ preventScroll: true });
    textarea.select();
    textarea.setSelectionRange(0, text.length);
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    textarea.remove();
    // Refocus first: focusing can move the selection, which is restored afterwards.
    if (activeElement && activeElement !== document.body && activeElement.isConnected) {
      activeElement.focus({ preventScroll: true });
    }
    if (activeField && fieldSelection) {
      restoreFieldSelection(activeField, fieldSelection);
    } else if (selection) {
      selection.removeAllRanges();
      for (const range of savedRanges) selection.addRange(range);
    }
  }
}

/**
 * Copies plain text to the clipboard.
 *
 * Uses the asynchronous Clipboard API when the browser exposes it and falls back to the
 * legacy selection copy when the API is missing (insecure HTTP origins) or rejects.
 * Resolves only after a copy succeeded; rejects with `ClipboardCopyError` otherwise, so
 * callers can show failure feedback instead of a false "Copied" state.
 */
export async function copyText(text: string, options: CopyTextOptions = {}): Promise<void> {
  const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;

  if (typeof clipboard?.writeText !== "function") {
    // Stay synchronous up to execCommand so the call remains inside the user gesture.
    if (copyTextWithSelection(text, options)) return;
    throw new ClipboardCopyError("Clipboard is not available in this browser context");
  }

  try {
    await clipboard.writeText(text);
  } catch (error) {
    if (copyTextWithSelection(text, options)) return;
    throw new ClipboardCopyError("Failed to copy to clipboard", error);
  }
}
