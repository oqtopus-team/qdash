import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useFullscreenPanel } from "../useFullscreenPanel";

function pressEscape() {
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
}

afterEach(() => {
  document.body.style.overflow = "";
  document.body.innerHTML = "";
});

describe("useFullscreenPanel", () => {
  it("locks body scrolling only while fullscreen", () => {
    const { result, unmount } = renderHook(() => useFullscreenPanel());

    expect(document.body.style.overflow).toBe("");

    act(() => result.current.toggleFullscreen());
    expect(result.current.isFullscreen).toBe(true);
    expect(document.body.style.overflow).toBe("hidden");

    act(() => result.current.exitFullscreen());
    expect(document.body.style.overflow).toBe("");

    unmount();
  });

  it("restores scrolling only after the last panel exits", () => {
    const first = renderHook(() => useFullscreenPanel());
    const second = renderHook(() => useFullscreenPanel());

    act(() => first.result.current.toggleFullscreen());
    act(() => second.result.current.toggleFullscreen());
    expect(document.body.style.overflow).toBe("hidden");

    act(() => first.result.current.exitFullscreen());
    expect(document.body.style.overflow).toBe("hidden");

    act(() => second.result.current.exitFullscreen());
    expect(document.body.style.overflow).toBe("");

    first.unmount();
    second.unmount();
  });

  it("closes only the topmost panel on Escape", () => {
    const first = renderHook(() => useFullscreenPanel());
    const second = renderHook(() => useFullscreenPanel());

    act(() => first.result.current.toggleFullscreen());
    act(() => second.result.current.toggleFullscreen());

    act(() => pressEscape());
    expect(second.result.current.isFullscreen).toBe(false);
    expect(first.result.current.isFullscreen).toBe(true);

    act(() => pressEscape());
    expect(first.result.current.isFullscreen).toBe(false);
    expect(document.body.style.overflow).toBe("");

    first.unmount();
    second.unmount();
  });

  it("leaves Escape to an open modal", () => {
    const { result, unmount } = renderHook(() => useFullscreenPanel());
    act(() => result.current.toggleFullscreen());

    const dialog = document.createElement("dialog");
    dialog.setAttribute("open", "");
    document.body.appendChild(dialog);

    act(() => pressEscape());
    expect(result.current.isFullscreen).toBe(true);

    dialog.remove();
    act(() => pressEscape());
    expect(result.current.isFullscreen).toBe(false);

    unmount();
  });

  it("keeps the panel open when Escape closes a Radix dialog", () => {
    const { result, unmount } = renderHook(() => useFullscreenPanel());
    act(() => result.current.toggleFullscreen());

    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("data-state", "open");
    document.body.appendChild(dialog);

    const dismiss = () => dialog.remove();
    document.addEventListener("keydown", dismiss, { capture: true });

    act(() => {
      dialog.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    document.removeEventListener("keydown", dismiss, { capture: true });

    expect(dialog.isConnected).toBe(false);
    expect(result.current.isFullscreen).toBe(true);

    act(() => pressEscape());
    expect(result.current.isFullscreen).toBe(false);

    unmount();
  });

  it("releases the scroll lock when a fullscreen panel unmounts", () => {
    const { result, unmount } = renderHook(() => useFullscreenPanel());

    act(() => result.current.toggleFullscreen());
    expect(document.body.style.overflow).toBe("hidden");

    unmount();
    expect(document.body.style.overflow).toBe("");
  });
});
