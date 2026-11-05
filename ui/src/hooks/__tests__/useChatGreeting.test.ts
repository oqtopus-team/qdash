import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChatGreeting } from "../useChatGreeting";

describe("useChatGreeting", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it.each([
    [0, "Good evening"],
    [4, "Good evening"],
    [5, "Good morning"],
    [11, "Good morning"],
    [12, "Good afternoon"],
    [17, "Good afternoon"],
    [18, "Good evening"],
    [23, "Good evening"],
  ])("greets by local time at %i:00", (hour, expected) => {
    vi.setSystemTime(new Date(2026, 10, 4, hour));
    const { result } = renderHook(() => useChatGreeting("Alice"));
    expect(result.current).toBe(`${expected}, Alice`);
  });

  it("updates at noon while open and releases the timer on unmount", () => {
    vi.setSystemTime(new Date(2026, 10, 4, 11, 59));
    const { result, unmount } = renderHook(() => useChatGreeting());
    expect(result.current).toBe("Good morning");
    act(() => vi.advanceTimersByTime(60_000));
    expect(result.current).toBe("Good afternoon");
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("handles missing names and updates when the profile arrives", () => {
    vi.setSystemTime(new Date(2026, 10, 4, 9));
    const { result, rerender } = renderHook(({ name }) => useChatGreeting(name), {
      initialProps: { name: " " },
    });
    expect(result.current).toBe("Good morning");
    rerender({ name: " Alice " });
    expect(result.current).toBe("Good morning, Alice");
  });
});
