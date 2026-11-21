"use client";

import { useEffect } from "react";
import { useStickToBottomContext } from "use-stick-to-bottom";

/** Keys that scroll a focused scroller up or down. */
const UP_KEYS = new Set(["ArrowUp", "PageUp", "Home"]);
const DOWN_KEYS = new Set(["ArrowDown", "PageDown", "End"]);

/** How long a key press or wheel turn counts as the reason for the scroll that follows it. */
const INTENT_MS = 400;

/** Finger travel, in pixels, that counts as a deliberate drag rather than a tap. */
const TOUCH_SLOP_PX = 4;

/** A field that takes the keys for itself, so they move a caret rather than the thread. */
function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  );
}

/** A control that Space presses instead of scrolling the page. */
function isPressable(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement && target.closest("button, a, summary, [role=button]") !== null
  );
}

/**
 * Makes the user's own scrolling decide whether a stick-to-bottom thread keeps
 * following new content. `use-stick-to-bottom` notices an upward mouse wheel at
 * once, but reads every other scroll from scroll events, and it drops those
 * while the content is resizing, which is all the time while an answer streams.
 * So dragging the scrollbar, swiping, or pressing PageUp mid-stream could be
 * undone by the next chunk. This reads those gestures directly:
 *
 * - any upward gesture stops following, and the jump-to-latest control appears;
 * - a downward gesture that reaches the bottom resumes following, as does that
 *   control or sending a message.
 *
 * Call it from a component rendered inside `<StickToBottom>`.
 */
export function useChatScrollIntent(): void {
  const { scrollRef, state, stopScroll, scrollToBottom } = useStickToBottomContext();

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return;

    let downIntentAt = -Infinity;
    let dragging = false;
    let touchY: number | null = null;
    let lastScrollTop = scroller.scrollTop;

    const scrollable = () => scroller.scrollHeight > scroller.clientHeight;
    const escape = () => {
      if (scrollable() && state.isAtBottom) stopScroll();
    };
    const intendDown = () => {
      downIntentAt = performance.now();
    };
    const nestedScrollerConsumes = (target: EventTarget | null, down: boolean) => {
      let element = target instanceof Element ? target : null;
      while (element && element !== scroller) {
        const style = getComputedStyle(element);
        if (/(auto|scroll|overlay)/.test(style.overflowY)) {
          const remaining = down
            ? element.scrollHeight - element.clientHeight - element.scrollTop
            : element.scrollTop;
          if (remaining > 0) return true;
          if (/contain|none/.test(style.overscrollBehaviorY)) return true;
        }
        element = element.parentElement;
      }
      return false;
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      if (isEditable(event.target)) return;
      const space = event.key === " " && !isPressable(event.target);
      if (UP_KEYS.has(event.key) || (space && event.shiftKey)) {
        if (!nestedScrollerConsumes(event.target, false)) escape();
      } else if (DOWN_KEYS.has(event.key) || space) {
        if (!nestedScrollerConsumes(event.target, true)) intendDown();
      }
    };

    const onWheel = (event: WheelEvent) => {
      // The library already escapes on an upward wheel; a downward one may resume.
      if (event.deltaY > 0 && !nestedScrollerConsumes(event.target, true)) intendDown();
    };

    const onPointerDown = (event: PointerEvent) => {
      // Only a press on the scroller itself, its scrollbar, starts a drag; a
      // click on content (a group folding up) is not a scroll.
      if (event.target === scroller) dragging = true;
    };
    const onPointerUp = () => {
      dragging = false;
    };

    const onTouchStart = (event: TouchEvent) => {
      touchY = event.touches[0]?.clientY ?? null;
    };
    const onTouchMove = (event: TouchEvent) => {
      const y = event.touches[0]?.clientY;
      if (touchY === null || y === undefined) return;
      // A finger moving down pulls the content down: the user scrolls up.
      if (y - touchY > TOUCH_SLOP_PX) {
        if (!nestedScrollerConsumes(event.target, false)) escape();
      } else if (touchY - y > TOUCH_SLOP_PX) {
        if (!nestedScrollerConsumes(event.target, true)) intendDown();
      }
      touchY = y;
    };
    const onTouchEnd = () => {
      touchY = null;
    };

    const onScroll = () => {
      const top = scroller.scrollTop;
      const delta = top - lastScrollTop;
      lastScrollTop = top;
      if (dragging) {
        if (delta < 0) escape();
        else if (delta > 0) intendDown();
      }
      // Back at the bottom by the user's own hand: follow new content again.
      if (!state.isAtBottom && state.isNearBottom && performance.now() - downIntentAt < INTENT_MS) {
        void scrollToBottom();
      }
    };

    scroller.addEventListener("keydown", onKeyDown);
    scroller.addEventListener("wheel", onWheel, { passive: true });
    scroller.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
    scroller.addEventListener("touchstart", onTouchStart, { passive: true });
    scroller.addEventListener("touchmove", onTouchMove, { passive: true });
    scroller.addEventListener("touchend", onTouchEnd, { passive: true });
    scroller.addEventListener("touchcancel", onTouchEnd, { passive: true });
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      scroller.removeEventListener("keydown", onKeyDown);
      scroller.removeEventListener("wheel", onWheel);
      scroller.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
      scroller.removeEventListener("touchstart", onTouchStart);
      scroller.removeEventListener("touchmove", onTouchMove);
      scroller.removeEventListener("touchend", onTouchEnd);
      scroller.removeEventListener("touchcancel", onTouchEnd);
      scroller.removeEventListener("scroll", onScroll);
    };
  }, [scrollRef, state, stopScroll, scrollToBottom]);
}
