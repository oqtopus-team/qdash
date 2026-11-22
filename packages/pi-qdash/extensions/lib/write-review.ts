/**
 * The user's review of one reviewed QDash write before it runs.
 *
 * pi's `ctx.ui.confirm()` shows its message in the input dock, which pi
 * clips to the terminal without scrolling, so a long argument listing would
 * be approved partly unseen. In the pi terminal UI (`ctx.mode === "tui"`) the
 * review is therefore a full-height overlay (`ctx.ui.custom()`) that scrolls
 * through the complete text and accepts an approval only after the user has
 * displayed its last line. In pi's RPC mode, where `custom()` is not
 * available, the RPC client receives the complete text through
 * `ctx.ui.confirm()` and is responsible for showing it. No other mode reviews
 * a write; callers refuse it there (no UI).
 *
 * The text is fixed when the review opens: the caller builds it from the
 * canonical snapshot of the arguments, and the view keeps only its own copy.
 */

import type { Component, KeybindingsManager, TUI } from "@earendil-works/pi-tui";
import { replaceControlCharacters, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";

/** The parts of pi's extension UI the review uses. */
export interface WriteReviewUI {
  confirm(title: string, message: string, opts?: { signal?: AbortSignal }): Promise<boolean>;
  custom?<T>(
    factory: (tui: TUI, theme: ReviewTheme, keybindings: KeybindingsManager, done: (result: T) => void) => Component & { dispose?(): void },
    options?: {
      overlay?: boolean;
      overlayOptions?: { width?: number | `${number}%`; maxHeight?: number | `${number}%`; anchor?: "center"; margin?: number };
      blocked?: { kind: "permission"; message: string };
    },
  ): Promise<T>;
}

export interface WriteReviewContext {
  mode?: string;
  ui: WriteReviewUI;
}

/** The theme helpers the view uses (pi's `Theme` provides them). */
export interface ReviewTheme {
  fg(color: "accent" | "warning" | "dim" | "muted" | "success" | "error", text: string): string;
  bold(text: string): string;
}

/** The terminal size and render request the view needs from pi's TUI. */
export interface ReviewTui {
  terminal: { rows: number };
  requestRender(): void;
}

// Rows the overlay keeps free around itself, and rows the view uses for its
// title, position line, and key hints.
const OVERLAY_MARGIN = 1;
const CHROME_ROWS = 5;
/** Below this many body rows the view cannot be reviewed and refuses approval. */
export const MIN_BODY_ROWS = 3;
const MIN_REVIEW_COLUMNS = 20;

const segmenter = new Intl.Segmenter();

/**
 * Split one line into rows of at most `width` columns without dropping or
 * changing a character, so whitespace inside an argument stays visible.
 */
function hardWrap(line: string, width: number): string[] {
  if (line === "") return [""];
  const rows: string[] = [];
  let row = "";
  let used = 0;
  for (const { segment } of segmenter.segment(line)) {
    const cells = visibleWidth(segment);
    if (used + cells > width && row !== "") {
      rows.push(row);
      row = "";
      used = 0;
    }
    row += segment;
    used += cells;
  }
  rows.push(row);
  return rows;
}

/**
 * A scrollable review of `text` with explicit approve and decline keys.
 * `done(true)` is called only from the approve key after the last line was
 * on screen; decline, cancel, and abort call `done(false)`.
 */
export class WriteReviewView implements Component {
  /** Fullscreen pi sends page and scroll keys to this view instead of the transcript. */
  readonly capturesViewportInput = true;
  private readonly lines: readonly string[];
  private offset = 0;
  private seenEnd = false;
  private notice: string | undefined;
  private wrapped: { width: number; rows: string[] } | undefined;
  private bodyRows = MIN_BODY_ROWS;
  private finished = false;
  private reviewable = false;

  constructor(
    private readonly tui: ReviewTui,
    private readonly theme: ReviewTheme,
    private readonly keybindings: Pick<KeybindingsManager, "matches">,
    private readonly title: string,
    text: string,
    private readonly done: (approved: boolean) => void,
  ) {
    // The view's own copy: control characters (terminal escapes) are shown
    // as spaces rather than interpreted.
    this.lines = Object.freeze(text.split("\n").map((line) => replaceControlCharacters(line)));
  }

  /** Whether the last line has been on screen, which approval requires. */
  get reviewedToEnd(): boolean {
    return this.seenEnd;
  }

  private rowsFor(width: number): string[] {
    if (this.wrapped?.width !== width) {
      const textWidth = Math.max(1, width - 2);
      const rows: string[] = [];
      for (const line of this.lines) {
        hardWrap(line, textWidth).forEach((row, index) => rows.push(`${index === 0 ? "│" : "┆"} ${row}`));
      }
      this.wrapped = { width, rows };
    }
    return this.wrapped.rows;
  }

  render(width: number): string[] {
    const height = Math.max(1, this.tui.terminal.rows - 2 * OVERLAY_MARGIN);
    this.bodyRows = height - CHROME_ROWS;
    const fit = (line: string) => truncateToWidth(line, width);
    this.reviewable = false;
    if (this.bodyRows < MIN_BODY_ROWS || width < MIN_REVIEW_COLUMNS) {
      this.seenEnd = false;
      return [
        this.theme.fg("warning", "Terminal too small to review this QDash write."),
        "Enlarge the terminal, or press n or Esc to decline.",
      ].slice(0, height).map(fit);
    }
    const rows = this.rowsFor(width);
    if (rows.some((row) => visibleWidth(row) > width)) {
      this.seenEnd = false;
      return ["Enlarge the terminal to review; n/Esc declines."].map(fit);
    }
    this.reviewable = true;
    const maxOffset = Math.max(0, rows.length - this.bodyRows);
    this.offset = Math.min(Math.max(0, this.offset), maxOffset);
    const visible = rows.slice(this.offset, this.offset + this.bodyRows);
    if (this.offset + this.bodyRows >= rows.length) this.seenEnd = true;
    while (visible.length < this.bodyRows) visible.push("");
    const last = Math.min(rows.length, this.offset + this.bodyRows);
    const position = `Lines ${this.offset + 1}-${last} of ${rows.length}${this.seenEnd ? "" : " · approve after the end"}`;
    // Decline and approve come first so a narrow terminal never cuts them off.
    const approve = this.seenEnd ? this.theme.fg("success", "y approve") : this.theme.fg("dim", "y approve");
    const hints = `n/Esc decline · ${approve} · ↑↓ PgUp/PgDn Home/End`;
    return [
      this.theme.bold(this.theme.fg("accent", this.title)),
      this.theme.fg("muted", position),
      ...visible,
      this.notice ? this.theme.fg("warning", this.notice) : "",
      hints,
      "",
    ].map(fit);
  }

  private finish(approved: boolean): void {
    if (this.finished) return;
    this.finished = true;
    this.done(approved);
  }

  /** Close as declined: used for pi's abort signal. */
  cancel(): void {
    this.finish(false);
  }

  handleInput(data: string): void {
    if (this.finished) return;
    const page = Math.max(1, this.bodyRows - 1);
    const kb = this.keybindings;
    this.notice = undefined;
    if (data === "y" || data === "Y") {
      if (this.seenEnd && this.reviewable && this.bodyRows >= MIN_BODY_ROWS) {
        this.finish(true);
        return;
      }
      this.notice = "Scroll to the end before approving.";
    } else if (data === "n" || data === "N" || kb.matches(data, "tui.select.cancel")) {
      this.finish(false);
      return;
    } else if (kb.matches(data, "tui.select.up") || data === "k") {
      this.offset -= 1;
    } else if (kb.matches(data, "tui.select.down") || data === "j") {
      this.offset += 1;
    } else if (kb.matches(data, "tui.select.pageUp") || data === "b") {
      this.offset -= page;
    } else if (kb.matches(data, "tui.select.pageDown") || data === " ") {
      this.offset += page;
    } else if (data === "\x1b[H" || data === "\x1b[1~" || data === "\x1bOH" || data === "g") {
      this.offset = 0;
    } else if (data === "\x1b[F" || data === "\x1b[4~" || data === "\x1bOF" || data === "G") {
      this.offset = Number.MAX_SAFE_INTEGER;
    } else {
      return;
    }
    this.tui.requestRender();
  }

  invalidate(): void {
    this.wrapped = undefined;
  }
}

/**
 * Show `text` for review and resolve true only when the user approved it.
 * An abort of `signal` before or during the review resolves false.
 */
export async function reviewWrite(ctx: WriteReviewContext, title: string, text: string, signal?: AbortSignal): Promise<boolean> {
  if (signal?.aborted) return false;
  if (ctx.mode !== "tui" || typeof ctx.ui.custom !== "function") {
    // RPC mode: the client receives the complete text.
    return ctx.ui.confirm(title, text, signal ? { signal } : undefined);
  }
  let onAbort: (() => void) | undefined;
  try {
    const result = await ctx.ui.custom<boolean>(
      (tui, theme, keybindings, done) => {
        const view = new WriteReviewView(tui, theme, keybindings, title, text, done);
        onAbort = () => view.cancel();
        signal?.addEventListener("abort", onAbort, { once: true });
        if (signal?.aborted) view.cancel();
        return view;
      },
      {
        overlay: true,
        overlayOptions: { width: "100%", maxHeight: "100%", anchor: "center", margin: OVERLAY_MARGIN },
        blocked: { kind: "permission", message: title },
      },
    );
    // Anything but an explicit approval (pi returns undefined where custom UI is unavailable) declines.
    return result === true && !signal?.aborted;
  } finally {
    if (onAbort) signal?.removeEventListener("abort", onAbort);
  }
}
