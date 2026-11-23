import { afterEach, describe, expect, it } from "vitest";

import {
  MAX_STORED_TURNS,
  forgetChatTabState,
  forgetOtherTurnOwners,
  forgetStoredTurn,
  patchStoredTurn,
  readStoredTurns,
  storeTurn,
  type StoredTurn,
} from "@/lib/copilotTurnStore";

const turn = (over: Partial<StoredTurn> = {}): StoredTurn => ({
  sessionId: "s1",
  requestId: "r1",
  projectId: "p1",
  start: 2,
  continuing: false,
  startedAt: 1000,
  ...over,
});

afterEach(() => sessionStorage.clear());

describe("the stored turn pointers", () => {
  it("keeps one pointer per session for its user only", () => {
    storeTurn("alice", turn());
    storeTurn("alice", turn({ requestId: "r2" }));
    storeTurn("bob", turn({ sessionId: "s9" }));
    expect(Object.keys(readStoredTurns("alice"))).toEqual(["s1"]);
    expect(readStoredTurns("alice").s1.requestId).toBe("r2");
    forgetOtherTurnOwners("alice");
    expect(readStoredTurns("bob")).toEqual({});
    expect(readStoredTurns("alice").s1).toBeDefined();
  });

  it("never lets an older turn's update or cleanup touch a newer turn's pointer", () => {
    storeTurn("alice", turn({ requestId: "new" }));
    patchStoredTurn("alice", "s1", "old", { ended: true });
    forgetStoredTurn("alice", "s1", "old");
    expect(readStoredTurns("alice").s1).toMatchObject({ requestId: "new" });
    expect(readStoredTurns("alice").s1.ended).toBeUndefined();
    forgetStoredTurn("alice", "s1", "new");
    expect(readStoredTurns("alice")).toEqual({});
  });

  it("is bounded: short activity labels, and the newest turns only", () => {
    storeTurn("alice", turn({ activity: { tool: "t", label: "x".repeat(500) } }));
    expect(readStoredTurns("alice").s1.activity?.label).toHaveLength(120);
    for (let i = 0; i < MAX_STORED_TURNS + 5; i++) {
      storeTurn("alice", turn({ sessionId: `s${i}`, startedAt: 2000 + i }));
    }
    const kept = readStoredTurns("alice");
    expect(Object.keys(kept)).toHaveLength(MAX_STORED_TURNS);
    expect(kept.s0).toBeUndefined();
    expect(kept[`s${MAX_STORED_TURNS + 4}`]).toBeDefined();
  });

  it("drops unreadable entries and fields it does not know", () => {
    sessionStorage.setItem(
      "qdash.copilot.activeTurns.v1:alice",
      JSON.stringify({
        s1: { ...turn(), text: "secret question", args: { token: "x" } },
        s2: { sessionId: "s2", requestId: 3 },
      }),
    );
    const read = readStoredTurns("alice");
    expect(Object.keys(read)).toEqual(["s1"]);
    expect(read.s1).not.toHaveProperty("text");
    expect(read.s1).not.toHaveProperty("args");
    sessionStorage.setItem("qdash.copilot.activeTurns.v1:alice", "{not json");
    expect(readStoredTurns("alice")).toEqual({});
  });

  it("forgets every user's turns and steers on sign-out", () => {
    storeTurn("alice", turn());
    sessionStorage.setItem("qdash.copilot.pendingSteers.v1:alice", "{}");
    sessionStorage.setItem("unrelated", "1");
    forgetChatTabState();
    expect(readStoredTurns("alice")).toEqual({});
    expect(sessionStorage.getItem("qdash.copilot.pendingSteers.v1:alice")).toBeNull();
    expect(sessionStorage.getItem("unrelated")).toBe("1");
  });
});
