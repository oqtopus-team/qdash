/**
 * The review of a reviewed QDash write in the pi terminal UI: the complete
 * argument listing scrolls inside the terminal, approval needs the last line
 * on screen and an explicit key, and decline, Escape, and pi's abort signal
 * never approve. The view runs inside pi-tui's real `TuiMainScreen` (fake
 * terminal, real overlay compositing and input routing, pi's default
 * keybindings); `ctx.ui.custom()` is reproduced from pi 1.7.0's interactive
 * mode overlay path. RPC mode keeps `ctx.ui.confirm()` with the full text.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { KeybindingsManager, setKeybindings, stripTerminalSequences, TUI_KEYBINDINGS, TuiMainScreen, visibleWidth } from "@earendil-works/pi-tui";

import { canonicalArgs, requireWriteApproval } from "../.test-dist/lib/write-approval.js";
import { gateDialogMessage } from "../.test-dist/lib/write-gate.js";
import { reviewWrite, WriteReviewView } from "../.test-dist/lib/write-review.js";

const KEY = { down: "\x1b[B", up: "\x1b[A", pageDown: "\x1b[6~", pageUp: "\x1b[5~", home: "\x1b[H", end: "\x1b[F", escape: "\x1b" };
const keybindings = new KeybindingsManager(TUI_KEYBINDINGS);
setKeybindings(keybindings);
const plainTheme = { fg: (_color, text) => text, bold: (text) => text };
const settle = () => new Promise((resolve) => setTimeout(resolve, 60));

/** pi-tui's real main screen on a fake terminal of `columns` x `rows`. */
function screen(columns, rows) {
  let onInput;
  let output = "";
  const terminal = {
    start(input) {
      onInput = input;
    },
    stop() {},
    drainInput: async () => {},
    write(data) {
      output += data;
    },
    get columns() {
      return columns;
    },
    get rows() {
      return rows;
    },
    get kittyProtocolActive() {
      return false;
    },
    moveBy() {},
    hideCursor() {},
    showCursor() {},
    clearLine() {},
    clearFromCursor() {},
    clearScreen() {},
    setTitle() {},
    setProgress() {},
    setProgramStatus() {},
  };
  const tui = new TuiMainScreen(terminal);
  tui.start();
  return {
    tui,
    press: async (...keys) => {
      for (const key of keys) onInput(key);
      await settle();
    },
    output: () => stripTerminalSequences(output),
    stop: () => tui.stop(),
  };
}

/** pi 1.7.0 InteractiveMode.showExtensionCustom, overlay branch. */
function tuiUi(tui, opened = []) {
  return {
    confirm: async () => assert.fail("the terminal UI never uses confirm() for a write review"),
    custom(factory, options) {
      return new Promise((resolve) => {
        let handle;
        let closed = false;
        const close = (result) => {
          if (closed) return;
          closed = true;
          handle?.hide();
          resolve(result);
        };
        const component = factory(tui, plainTheme, keybindings, close);
        opened.push({ component, options });
        if (closed) return;
        handle = tui.showOverlay(component, options.overlayOptions);
      });
    },
  };
}

const longArgs = () => ({
  name: "flow",
  code: Array.from({ length: 80 }, (_, index) => `line ${index}: calibrate`).join("\n"),
  parameters: { z_target: "important-target" },
});

test("a long review scrolls inside the terminal and approves only after its end was shown", async () => {
  const term = screen(48, 16);
  try {
    const text = gateDialogMessage("qdash_save_flow", canonicalArgs(longArgs()));
    const opened = [];
    const decision = reviewWrite({ mode: "tui", ui: tuiUi(term.tui, opened) }, "Approve QDash write operation?", text);
    await settle();
    const [{ component: view, options }] = opened;
    assert.ok(view instanceof WriteReviewView);
    assert.equal(options.overlay, true);
    assert.equal(options.blocked.kind, "permission");
    const frame = view.render(48);
    // The view never draws more rows than the overlay has, nor wider ones.
    assert.ok(frame.length <= 16 - 2, `${frame.length} rows`);
    assert.ok(frame.every((line) => visibleWidth(line) <= 48));
    assert.match(term.output(), /Lines 1-9 of \d+ · approve after the end/);
    assert.match(frame.at(-2), /^n\/Esc decline · y approve/);
    assert.doesNotMatch(frame.join("\n"), /important-target/);

    // An early approval is refused with guidance; the review stays open.
    await term.press("y");
    assert.equal(view.reviewedToEnd, false);
    assert.match(view.render(48).join("\n"), /Scroll to the end before approving/);

    // Scrolling line by line shows every row of the text exactly once in order.
    const seen = [];
    let previous;
    for (let step = 0; step < 400 && !view.reviewedToEnd; step += 1) {
      const rows = view.render(48).slice(2, 2 + 9);
      if (previous === undefined) seen.push(...rows);
      else seen.push(rows.at(-1));
      previous = rows;
      await term.press(KEY.down);
    }
    seen.push(view.render(48).slice(2, 2 + 9).at(-1));
    const shown = seen.join("\n");
    assert.match(shown, /line 79: calibrate/);
    assert.match(shown, /important-target/);
    assert.equal(view.reviewedToEnd, true);
    // Page keys and Home/End move by pages and to either end.
    await term.press(KEY.home);
    assert.match(view.render(48)[1], /^Lines 1-9 of/);
    await term.press(KEY.pageDown);
    assert.match(view.render(48)[1], /^Lines 9-17 of/);
    await term.press(KEY.end, "y");
    assert.equal(await decision, true);
  } finally {
    term.stop();
  }
});

test("long lines wrap without losing characters and terminal escapes are not interpreted", () => {
  const value = `${"a  b".repeat(30)}\u001b[31mred`;
  const view = new WriteReviewView({ terminal: { rows: 200 }, requestRender() {} }, plainTheme, keybindings, "t", `x\n${value}`, () => {});
  const rows = view.render(20).slice(2).filter((row) => row.startsWith("│") || row.startsWith("┆"));
  assert.ok(rows.every((row) => visibleWidth(row) <= 20));
  const joined = rows.slice(1).map((row) => row.slice(2)).join("");
  assert.equal(joined, `${"a  b".repeat(30)} [31mred`);
  assert.ok(rows.slice(2).every((row) => row.startsWith("┆ ")), "continuations are marked");
});

test("decline, Escape, a terminal too small to review, and pi's abort never approve", async () => {
  for (const key of ["n", KEY.escape]) {
    const term = screen(60, 30);
    try {
      const decision = reviewWrite({ mode: "tui", ui: tuiUi(term.tui) }, "t", "short text");
      await term.press(key);
      assert.equal(await decision, false, JSON.stringify(key));
    } finally {
      term.stop();
    }
  }
  {
    const term = screen(60, 6);
    const opened = [];
    try {
      const decision = reviewWrite({ mode: "tui", ui: tuiUi(term.tui, opened) }, "t", "short text");
      await term.press("y", KEY.end, "y");
      assert.match(opened[0].component.render(60).join("\n"), /Terminal too small to review/);
      await term.press("n");
      assert.equal(await decision, false);
    } finally {
      term.stop();
    }
  }
  {
    const term = screen(60, 30);
    const controller = new AbortController();
    const opened = [];
    try {
      const decision = reviewWrite({ mode: "tui", ui: tuiUi(term.tui, opened) }, "t", "short text", controller.signal);
      await settle();
      controller.abort();
      assert.equal(await decision, false);
      // The closed view ignores keys pressed afterwards.
      await term.press("y");
      assert.equal(await decision, false);
    } finally {
      term.stop();
    }
  }
  {
    const aborted = new AbortController();
    aborted.abort();
    const opened = [];
    assert.equal(await reviewWrite({ mode: "tui", ui: tuiUi(null, opened) }, "t", "x", aborted.signal), false);
    assert.equal(opened.length, 0, "an aborted turn opens no review");
  }
  // A host whose custom() yields nothing (pi's RPC stub) approves nothing.
  assert.equal(await reviewWrite({ mode: "tui", ui: { confirm: async () => true, custom: async () => undefined } }, "t", "x"), false);
});

test("RPC mode sends the complete text to the client through confirm()", async () => {
  const text = gateDialogMessage("qdash_save_flow", canonicalArgs(longArgs()));
  const received = [];
  const signal = new AbortController().signal;
  const ui = { confirm: async (title, message, opts) => (received.push({ title, message, opts }), true), custom: () => assert.fail("RPC has no custom UI") };
  assert.equal(await reviewWrite({ mode: "rpc", ui }, "Approve?", text, signal), true);
  assert.equal(received[0].message, text);
  assert.deepEqual(received[0].opts, { signal, blockedKind: "permission" });
});

test("confirm() reports the review as a permission wait with or without an abort signal", async () => {
  const received = [];
  const ui = (answer) => ({ confirm: async (title, message, opts) => (received.push(opts), answer) });
  assert.equal(await reviewWrite({ mode: "rpc", ui: ui(true) }, "t", "x"), true);
  assert.deepEqual(received[0], { blockedKind: "permission" });
  assert.equal("signal" in received[0], false, "no signal key without an abort signal");
  // A declined review stays declined.
  assert.equal(await reviewWrite({ mode: "rpc", ui: ui(false) }, "t", "x", new AbortController().signal), false);
  assert.equal(received[1].blockedKind, "permission");
  assert.ok(received[1].signal instanceof AbortSignal);
  // An aborted turn opens no dialog.
  const aborted = new AbortController();
  aborted.abort();
  assert.equal(await reviewWrite({ mode: "rpc", ui: ui(true) }, "t", "x", aborted.signal), false);
  assert.equal(received.length, 2);
});

test("a tool's own dialog in the terminal shows every argument and needs the end before approval", async () => {
  const term = screen(50, 14);
  const opened = [];
  try {
    const params = longArgs();
    const approval = requireWriteApproval("qdash_save_flow", "own-tui", params, { hasUI: true, mode: "tui", ui: tuiUi(term.tui, opened) }, { title: "Save QDash flow?", message: "This writes flow 'flow'." });
    await settle();
    const view = opened[0].component;
    const all = [];
    for (let step = 0; step < 400 && !view.reviewedToEnd; step += 1) {
      all.push(...view.render(50).slice(2, 2 + 7));
      await term.press(KEY.pageDown);
    }
    all.push(...view.render(50).slice(2, 2 + 7));
    const text = all.join("\n");
    assert.match(text, /qdash_save_flow: This writes flow 'flow'\./);
    assert.match(text, /Arguments \(the approval covers exactly these\):/);
    assert.match(text, /important-target/);
    await term.press("y");
    await approval;
  } finally {
    term.stop();
  }
});

test("narrow widths cannot approve hidden text, including after a resize", () => {
  for (const width of [1, 2, 3, 19]) {
    const approvals = [];
    const view = new WriteReviewView({ terminal: { rows: 24 }, requestRender() {} }, plainTheme, keybindings, "Review", "SECRET", (value) => approvals.push(value));
    view.render(width);
    view.handleInput("y");
    assert.equal(view.reviewedToEnd, false);
    assert.deepEqual(approvals, []);
    view.render(60);
    assert.equal(view.reviewedToEnd, true);
    view.render(width);
    view.handleInput("y");
    assert.equal(view.reviewedToEnd, false);
    assert.deepEqual(approvals, []);
    view.handleInput("n");
    assert.deepEqual(approvals, [false]);
  }
});

test("key hints reflect remapped and unbound keybindings and still keep minimal mocks working", () => {
  const body = Array.from({ length: 20 }, (_, i) => `row ${i}`).join("\n");
  const customKb = new KeybindingsManager(TUI_KEYBINDINGS, {
    "tui.select.cancel": "ctrl+x",
    "tui.select.up": "ctrl+p",
    "tui.select.down": "ctrl+n",
    "tui.select.pageUp": "ctrl+u",
    "tui.select.pageDown": "ctrl+d",
  });
  const declined = [];
  const customView = new WriteReviewView({ terminal: { rows: 16 }, requestRender() {} }, plainTheme, customKb, "Review", body, (v) => declined.push(v));
  const normalHint = customView.render(80).at(-2);
  assert.match(normalHint, /^n\/Ctrl\+X decline · y approve · Ctrl\+P\/Ctrl\+N Ctrl\+U\/Ctrl\+D Home\/End$/);
  const smallView = new WriteReviewView({ terminal: { rows: 6 }, requestRender() {} }, plainTheme, customKb, "Review", body, () => {});
  assert.match(smallView.render(60)[1], /press n or Ctrl\+X to decline/);
  customView.handleInput("\x18");
  assert.deepEqual(declined, [false]);

  const altKb = new KeybindingsManager(TUI_KEYBINDINGS, { "tui.select.cancel": "alt+k" });
  const altView = new WriteReviewView({ terminal: { rows: 16 }, requestRender() {} }, plainTheme, altKb, "Review", "ok", () => {});
  const expectedAlt = process.platform === "darwin" ? "Option+K" : "Alt+K";
  assert.match(altView.render(80).at(-2), new RegExp(`^n/${expectedAlt.replace("+", "\\+")} decline`));

  const unboundKb = new KeybindingsManager(TUI_KEYBINDINGS, {
    "tui.select.cancel": [],
    "tui.select.up": [],
    "tui.select.down": [],
    "tui.select.pageUp": [],
    "tui.select.pageDown": [],
  });
  const unboundView = new WriteReviewView({ terminal: { rows: 16 }, requestRender() {} }, plainTheme, unboundKb, "Review", body, () => {});
  assert.match(unboundView.render(80).at(-2), /^n decline · y approve · k\/j b\/Space Home\/End$/);
  const unboundSmall = new WriteReviewView({ terminal: { rows: 6 }, requestRender() {} }, plainTheme, unboundKb, "Review", body, () => {});
  assert.match(unboundSmall.render(60)[1], /press n to decline\.$/);

  // Minimal { matches } mocks without getKeys fall back cleanly to default hints.
  const minimalKb = { matches: (data, binding) => keybindings.matches(data, binding) };
  const minimalView = new WriteReviewView({ terminal: { rows: 16 }, requestRender() {} }, plainTheme, minimalKb, "Review", body, () => {});
  assert.match(minimalView.render(80).at(-2), /^n\/Esc decline · y approve · ↑↓ PgUp\/PgDn Home\/End$/);

  // Approval and decline keys (y/Y/n/N) are excluded from the alternate cancel hint so y is never advertised as decline.
  for (const shadowed of ["y", "Y", "n", "N"]) {
    const shadowedKb = new KeybindingsManager(TUI_KEYBINDINGS, { "tui.select.cancel": shadowed });
    const normal = new WriteReviewView({ terminal: { rows: 16 }, requestRender() {} }, plainTheme, shadowedKb, "Review", body, () => {});
    assert.match(normal.render(80).at(-2), /^n decline · y approve/, shadowed);
    const small = new WriteReviewView({ terminal: { rows: 6 }, requestRender() {} }, plainTheme, shadowedKb, "Review", body, () => {});
    assert.match(small.render(60)[1], /press n to decline\.$/, shadowed);
  }
  const mixedKb = new KeybindingsManager(TUI_KEYBINDINGS, { "tui.select.cancel": ["y", "ctrl+x"] });
  const mixedView = new WriteReviewView({ terminal: { rows: 16 }, requestRender() {} }, plainTheme, mixedKb, "Review", body, () => {});
  assert.match(mixedView.render(80).at(-2), /^n\/Ctrl\+X decline · y approve/);
});
