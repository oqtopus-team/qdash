import { describe, expect, it } from "vitest";

import { sessionToFollow } from "../followStreamingChat";

describe("sessionToFollow", () => {
  it("follows the active chat when it is streaming and the user leaves /chat", () => {
    expect(sessionToFollow("/chat", "/dashboard", "a", ["a", "b"])).toBe("a");
  });

  it("follows another streaming chat when the active one is idle", () => {
    expect(sessionToFollow("/chat", "/dashboard", "idle", ["b"])).toBe("b");
    expect(sessionToFollow("/chat", "/dashboard", null, ["b"])).toBe("b");
  });

  it("does nothing when nothing streams, when arriving on /chat, or between other pages", () => {
    expect(sessionToFollow("/chat", "/dashboard", "a", [])).toBeNull();
    expect(sessionToFollow("/dashboard", "/chat", "a", ["a"])).toBeNull();
    expect(sessionToFollow("/dashboard", "/metrics", "a", ["a"])).toBeNull();
    expect(sessionToFollow(null, "/dashboard", "a", ["a"])).toBeNull();
  });
});
