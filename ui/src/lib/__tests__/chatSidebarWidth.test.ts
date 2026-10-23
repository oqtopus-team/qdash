import { afterEach, describe, expect, it } from "vitest";

import {
  clampSidebarWidth,
  clearStoredSidebarWidth,
  DEFAULT_SIDEBAR_WIDTH,
  getStoredSidebarWidth,
  maxSidebarWidth,
  MIN_SIDEBAR_WIDTH,
  setStoredSidebarWidth,
} from "@/lib/chatSidebarWidth";

afterEach(() => clearStoredSidebarWidth());

describe("chatSidebarWidth", () => {
  it("keeps the width between the minimum and six tenths of the window", () => {
    expect(clampSidebarWidth(100, 1600)).toBe(MIN_SIDEBAR_WIDTH);
    expect(clampSidebarWidth(500.4, 1600)).toBe(500);
    expect(clampSidebarWidth(5000, 1600)).toBe(960);
    expect(clampSidebarWidth(5000, 1200)).toBe(720);
    expect(maxSidebarWidth(400)).toBe(MIN_SIDEBAR_WIDTH);
    expect(clampSidebarWidth(Number.NaN, 1600)).toBe(DEFAULT_SIDEBAR_WIDTH);
  });

  it("remembers a dragged width and forgets it on reset", () => {
    expect(getStoredSidebarWidth()).toBeNull();
    setStoredSidebarWidth(612.7);
    expect(getStoredSidebarWidth()).toBe(613);
    clearStoredSidebarWidth();
    expect(getStoredSidebarWidth()).toBeNull();
    localStorage.setItem("qdash_chat_sidebar_width", "garbage");
    expect(getStoredSidebarWidth()).toBeNull();
  });
});
