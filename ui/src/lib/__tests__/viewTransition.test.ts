import { afterEach, describe, expect, it, vi } from "vitest";

import { canViewTransition, withViewTransition } from "../viewTransition";

// jsdom has no View Transitions; the tests add and remove the hook themselves.
const doc = document as unknown as { startViewTransition?: (update: () => void) => unknown };

afterEach(() => {
  delete doc.startViewTransition;
  vi.restoreAllMocks();
});

describe("viewTransition", () => {
  it("applies the update directly when the browser cannot transition", () => {
    const update = vi.fn();
    expect(canViewTransition()).toBe(false);
    withViewTransition(update);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("runs the update inside startViewTransition when supported", () => {
    const start = vi.fn((cb: () => void) => {
      cb();
      return {};
    });
    doc.startViewTransition = start;
    const update = vi.fn();

    expect(canViewTransition()).toBe(true);
    withViewTransition(update);
    expect(start).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("skips the transition when the user prefers reduced motion", () => {
    doc.startViewTransition = vi.fn();
    const matchMedia = vi
      .spyOn(window, "matchMedia")
      .mockImplementation(
        (query: string) => ({ matches: query.includes("reduce") }) as MediaQueryList,
      );
    const update = vi.fn();

    expect(canViewTransition()).toBe(false);
    withViewTransition(update);
    expect(update).toHaveBeenCalledTimes(1);
    expect(doc.startViewTransition).not.toHaveBeenCalled();
    matchMedia.mockRestore();
  });
});
