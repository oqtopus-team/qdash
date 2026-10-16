import { afterEach, describe, expect, it } from "vitest";

import {
  getStoredThinkingChoice,
  levelOfEffort,
  setStoredThinkingChoice,
  thinkingLevelForRequest,
} from "../chatThinking";

afterEach(() => localStorage.clear());

describe("chat thinking", () => {
  it("sends nothing for Auto and the level otherwise", () => {
    expect(thinkingLevelForRequest("auto")).toBeUndefined();
    expect(thinkingLevelForRequest("high")).toBe("high");
  });

  it("maps the configured reasoning effort the way the backend does", () => {
    expect(levelOfEffort("none")).toBe("off");
    expect(levelOfEffort("MINIMAL")).toBe("low");
    expect(levelOfEffort("high")).toBe("high");
    expect(levelOfEffort(null)).toBeNull();
    expect(levelOfEffort("xhigh")).toBeNull();
  });

  it("remembers the choice and ignores junk", () => {
    expect(getStoredThinkingChoice()).toBe("auto");
    setStoredThinkingChoice("low");
    expect(getStoredThinkingChoice()).toBe("low");
    localStorage.setItem("qdash_chat_thinking", "turbo");
    expect(getStoredThinkingChoice()).toBe("auto");
  });
});
