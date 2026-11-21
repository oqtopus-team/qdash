import { describe, expect, it } from "vitest";

import { sessionToFollow } from "../followStreamingChat";

describe("sessionToFollow", () => {
  it("follows the active chat when it is streaming and the user leaves /chat", () => {
    expect(sessionToFollow("/chat", "/overview", "a", ["a", "b"])).toBe("a");
  });

  it("follows another streaming chat when the active one is idle", () => {
    expect(sessionToFollow("/chat", "/overview", "idle", ["b"])).toBe("b");
    expect(sessionToFollow("/chat", "/overview", null, ["b"])).toBe("b");
  });

  it("does nothing when nothing streams, when arriving on /chat, or between other pages", () => {
    expect(sessionToFollow("/chat", "/overview", "a", [])).toBeNull();
    expect(sessionToFollow("/overview", "/chat", "a", ["a"])).toBeNull();
    expect(sessionToFollow("/overview", "/metrics", "a", ["a"])).toBeNull();
    expect(sessionToFollow(null, "/overview", "a", ["a"])).toBeNull();
  });
});
