import { describe, expect, it } from "vitest";

import { sharedChatPath, sharedChatUrl } from "@/lib/utils/sharedChat";

describe("sharedChat links", () => {
  it("names the share's project in the path, encoded", () => {
    expect(sharedChatPath("chatshare_a", "p 1")).toBe("/chat/shared/chatshare_a?project=p%201");
  });

  it("builds an absolute link on the current origin", () => {
    expect(sharedChatUrl("chatshare_a", "p1")).toBe(
      `${window.location.origin}/chat/shared/chatshare_a?project=p1`,
    );
  });
});
