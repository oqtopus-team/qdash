import { afterEach, describe, expect, it, vi } from "vitest";

import {
  animateWindowEntry,
  clampWindowRect,
  defaultWindowRect,
} from "@/components/features/execution/useFloatingDetailWindow";

describe("floating details window geometry", () => {
  it("places the first window at the right, below the app header", () => {
    expect(defaultWindowRect({ width: 1440, height: 900 })).toEqual({
      x: 1440 - 520 - 32,
      y: 72,
      width: 520,
      height: 720,
    });
  });

  it("keeps a window inside the viewport with its minimum size", () => {
    expect(
      clampWindowRect({ x: -200, y: 5000, width: 100, height: 50 }, { width: 1280, height: 800 }),
    ).toEqual({ x: 16, y: 800 - 280 - 16, width: 360, height: 280 });
  });

  it("shrinks below the minimum only when the viewport cannot fit it", () => {
    expect(
      clampWindowRect({ x: 0, y: 0, width: 900, height: 900 }, { width: 1024, height: 300 }),
    ).toEqual({ x: 16, y: 16, width: 900, height: 268 });
  });
});

describe("animateWindowEntry", () => {
  const originalMatchMedia = window.matchMedia;

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  function element() {
    const node = document.createElement("div");
    const animate = vi.fn();
    const cancel = vi.fn();
    node.animate = animate as unknown as typeof node.animate;
    node.getAnimations = () => [{ cancel } as unknown as Animation];
    node.getBoundingClientRect = () => new DOMRect(100, 100, 400, 600);
    return { node, animate, cancel };
  }

  it("cancels a running animation and morphs from the previous rectangle", () => {
    const { node, animate, cancel } = element();
    animateWindowEntry(node, new DOMRect(0, 0, 200, 300));
    expect(cancel).toHaveBeenCalled();
    const [keyframes, options] = animate.mock.calls[0];
    expect(keyframes[0].transform).toBe("translate(-100px, -100px) scale(0.5, 0.5)");
    expect(keyframes[1].transform).toBe("none");
    expect(options.duration).toBeLessThanOrEqual(200);
  });

  it("does nothing when reduced motion is preferred", () => {
    window.matchMedia = ((query: string) => ({
      matches: query.includes("reduced-motion"),
    })) as unknown as typeof window.matchMedia;
    const { node, animate } = element();
    animateWindowEntry(node, null);
    expect(animate).not.toHaveBeenCalled();
  });
});
