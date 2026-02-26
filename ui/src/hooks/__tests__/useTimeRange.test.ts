import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useTimeRange } from "../useTimeRange";

describe("useTimeRange", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // jsdom uses UTC — set UTC noon so getHours() returns 12
    vi.setSystemTime(new Date("2024-06-15T12:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("formats dates with JST timezone (+09:00)", () => {
    const { result } = renderHook(() => useTimeRange());

    expect(result.current.timeRange.endAt).toMatch(/\+09:00$/);
    expect(result.current.timeRange.startAt).toMatch(/\+09:00$/);
  });

  it("initializes with default 7-day range", () => {
    const { result } = renderHook(() => useTimeRange());

    // endAt should be "now" and startAt should be 7 days ago
    expect(result.current.timeRange.endAt).toContain("2024-06-15");
    expect(result.current.timeRange.startAt).toContain("2024-06-08");
  });

  it("accepts custom initial days", () => {
    const { result } = renderHook(() => useTimeRange({ initialDays: 30 }));

    expect(result.current.timeRange.endAt).toContain("2024-06-15");
    expect(result.current.timeRange.startAt).toContain("2024-05-16");
  });

  it("starts with both locks unlocked", () => {
    const { result } = renderHook(() => useTimeRange());

    expect(result.current.timeRange.isStartAtLocked).toBe(false);
    expect(result.current.timeRange.isEndAtLocked).toBe(false);
  });

  it("toggleStartAtLock toggles the lock state", () => {
    const { result } = renderHook(() => useTimeRange());

    act(() => {
      result.current.toggleStartAtLock();
    });
    expect(result.current.timeRange.isStartAtLocked).toBe(true);

    act(() => {
      result.current.toggleStartAtLock();
    });
    expect(result.current.timeRange.isStartAtLocked).toBe(false);
  });

  it("toggleEndAtLock toggles the lock state", () => {
    const { result } = renderHook(() => useTimeRange());

    act(() => {
      result.current.toggleEndAtLock();
    });
    expect(result.current.timeRange.isEndAtLocked).toBe(true);

    act(() => {
      result.current.toggleEndAtLock();
    });
    expect(result.current.timeRange.isEndAtLocked).toBe(false);
  });

  it("updateStartAt sets value and locks start", () => {
    const { result } = renderHook(() => useTimeRange());

    act(() => {
      result.current.updateStartAt("2024-01-01T00:00:00.000+09:00");
    });

    expect(result.current.timeRange.startAt).toBe(
      "2024-01-01T00:00:00.000+09:00",
    );
    expect(result.current.timeRange.isStartAtLocked).toBe(true);
  });

  it("updateEndAt sets value and locks end", () => {
    const { result } = renderHook(() => useTimeRange());

    act(() => {
      result.current.updateEndAt("2024-12-31T23:59:59.000+09:00");
    });

    expect(result.current.timeRange.endAt).toBe(
      "2024-12-31T23:59:59.000+09:00",
    );
    expect(result.current.timeRange.isEndAtLocked).toBe(true);
  });

  it("refreshTimeRange updates unlocked times", () => {
    const { result } = renderHook(() => useTimeRange());

    // Advance time by 1 hour
    vi.advanceTimersByTime(60 * 60 * 1000);

    act(() => {
      result.current.refreshTimeRange();
    });

    // Both should update since neither is locked
    expect(result.current.timeRange.endAt).toContain("13:00:00");
  });

  it("refreshTimeRange preserves locked start time", () => {
    const { result } = renderHook(() => useTimeRange());

    const originalStartAt = result.current.timeRange.startAt;

    act(() => {
      result.current.toggleStartAtLock();
    });

    vi.advanceTimersByTime(60 * 60 * 1000);

    act(() => {
      result.current.refreshTimeRange();
    });

    expect(result.current.timeRange.startAt).toBe(originalStartAt);
  });

  it("refreshTimeRange preserves locked end time and does not update start", () => {
    const { result } = renderHook(() => useTimeRange());

    const originalEndAt = result.current.timeRange.endAt;
    const originalStartAt = result.current.timeRange.startAt;

    act(() => {
      result.current.toggleEndAtLock();
    });

    vi.advanceTimersByTime(60 * 60 * 1000);

    act(() => {
      result.current.refreshTimeRange();
    });

    // End is locked, so it stays the same
    expect(result.current.timeRange.endAt).toBe(originalEndAt);
    // Start also stays because end is locked (per hook logic)
    expect(result.current.timeRange.startAt).toBe(originalStartAt);
  });

  describe("getLockStatusDescription", () => {
    it("describes both unlocked", () => {
      const { result } = renderHook(() => useTimeRange());
      expect(result.current.getLockStatusDescription()).toBe(
        "Both times will update when refreshed manually",
      );
    });

    it("describes both locked", () => {
      const { result } = renderHook(() => useTimeRange());

      act(() => {
        result.current.toggleStartAtLock();
        result.current.toggleEndAtLock();
      });

      expect(result.current.getLockStatusDescription()).toBe(
        "Both times are fixed",
      );
    });

    it("describes only start locked", () => {
      const { result } = renderHook(() => useTimeRange());

      act(() => {
        result.current.toggleStartAtLock();
      });

      expect(result.current.getLockStatusDescription()).toBe(
        "Start time is fixed, end time will update when refreshed",
      );
    });

    it("describes only end locked", () => {
      const { result } = renderHook(() => useTimeRange());

      act(() => {
        result.current.toggleEndAtLock();
      });

      expect(result.current.getLockStatusDescription()).toBe(
        "End time is fixed, start time will update when refreshed",
      );
    });
  });
});
