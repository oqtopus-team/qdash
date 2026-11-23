import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StickToBottom, type StickToBottomContext } from "use-stick-to-bottom";

import { useChatScrollIntent } from "../useChatScrollIntent";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const SCROLL_HEIGHT = 1000;
const CLIENT_HEIGHT = 200;
const BOTTOM = SCROLL_HEIGHT - CLIENT_HEIGHT - 1;

function Intent() {
  useChatScrollIntent();
  return null;
}

/** A thread scrolled to the bottom while an answer streams into it. */
function renderThread() {
  const ctx = createRef<StickToBottomContext>();
  render(
    <StickToBottom contextRef={ctx}>
      <StickToBottom.Content data-testid="content">
        <button type="button">Fold</button>
        <textarea aria-label="Edit message" />
      </StickToBottom.Content>
      <Intent />
    </StickToBottom>,
  );
  const scroller = screen.getByTestId("content").parentElement as HTMLElement;
  let top = BOTTOM;
  Object.defineProperty(scroller, "scrollHeight", {
    configurable: true,
    value: SCROLL_HEIGHT,
  });
  Object.defineProperty(scroller, "clientHeight", {
    configurable: true,
    value: CLIENT_HEIGHT,
  });
  Object.defineProperty(scroller, "scrollTop", {
    configurable: true,
    get: () => top,
    set: (value: number) => {
      top = value;
    },
  });
  const state = ctx.current!.state;
  // While content grows the library ignores scroll events; that is the case to cover.
  state.resizeDifference = 24;
  const scrollTo = (value: number) => {
    top = value;
    fireEvent.scroll(scroller);
  };
  return { scroller, state, scrollTo };
}

describe("useChatScrollIntent", () => {
  it.each(["keyboard", "touch"])("keeps following while %s scrolls nested output", (input) => {
    const { state } = renderThread();
    const output = document.createElement("pre");
    output.style.overflowY = "auto";
    const content = document.createElement("code");
    output.append(content);
    screen.getByTestId("content").append(output);
    Object.defineProperty(output, "scrollHeight", { value: 500 });
    Object.defineProperty(output, "clientHeight", { value: 100 });
    output.scrollTop = 100;
    const gesture = () => {
      if (input === "keyboard") fireEvent.keyDown(content, { key: "PageUp" });
      else {
        fireEvent.touchStart(content, { touches: [{ clientY: 200 }] });
        fireEvent.touchMove(content, { touches: [{ clientY: 240 }] });
      }
    };
    gesture();
    expect(state.isAtBottom).toBe(true);
    output.scrollTop = 0;
    gesture();
    expect(state.isAtBottom).toBe(false);
  });

  it("starts following the bottom", () => {
    const { state } = renderThread();
    expect(state.isAtBottom).toBe(true);
  });

  it.each(["PageUp", "ArrowUp", "Home"])("stops following on %s", (key) => {
    const { scroller, state } = renderThread();
    fireEvent.keyDown(scroller, { key });
    expect(state.isAtBottom).toBe(false);
    expect(state.escapedFromLock).toBe(true);
  });

  it("stops following on Shift+Space but not on keys meant for a field or control", () => {
    const { scroller, state } = renderThread();
    fireEvent.keyDown(screen.getByLabelText("Edit message"), {
      key: "ArrowUp",
    });
    fireEvent.keyDown(screen.getByRole("button", { name: "Fold" }), {
      key: " ",
      shiftKey: true,
    });
    expect(state.isAtBottom).toBe(true);
    fireEvent.keyDown(scroller, { key: " ", shiftKey: true });
    expect(state.isAtBottom).toBe(false);
  });

  it("stops following when a finger drags the thread down, not up", () => {
    const { scroller, state } = renderThread();
    fireEvent.touchStart(scroller, { touches: [{ clientY: 300 }] });
    fireEvent.touchMove(scroller, { touches: [{ clientY: 250 }] });
    expect(state.isAtBottom).toBe(true);
    fireEvent.touchMove(scroller, { touches: [{ clientY: 290 }] });
    expect(state.isAtBottom).toBe(false);
  });

  it("stops following when the scrollbar is dragged up, but not when content folds", () => {
    vi.useFakeTimers();
    const { scroller, state, scrollTo } = renderThread();
    // A click on content that shrinks the thread is not the user scrolling.
    fireEvent.pointerDown(screen.getByRole("button", { name: "Fold" }));
    scrollTo(BOTTOM - 100);
    fireEvent.pointerUp(window);
    vi.runAllTimers();
    expect(state.isAtBottom).toBe(true);

    fireEvent.pointerDown(scroller);
    scrollTo(BOTTOM - 300);
    expect(state.isAtBottom).toBe(false);
  });

  it("resumes following when the user scrolls back down to the bottom", () => {
    const { scroller, state, scrollTo } = renderThread();
    fireEvent.keyDown(scroller, { key: "PageUp" });
    scrollTo(200);
    expect(state.isAtBottom).toBe(false);

    // Scrolling down short of the bottom does not resume.
    fireEvent.keyDown(scroller, { key: "PageDown" });
    scrollTo(400);
    expect(state.isAtBottom).toBe(false);

    fireEvent.keyDown(scroller, { key: "End" });
    scrollTo(BOTTOM);
    expect(state.isAtBottom).toBe(true);
  });

  it("does not resume on its own when content shrinks under an escaped reader", () => {
    const { scroller, state, scrollTo } = renderThread();
    fireEvent.keyDown(scroller, { key: "PageUp" });
    // No downward gesture: a programmatic move near the bottom leaves it escaped.
    scrollTo(BOTTOM);
    expect(state.isAtBottom).toBe(false);
  });
});
