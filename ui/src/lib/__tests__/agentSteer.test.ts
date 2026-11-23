import { describe, expect, it } from "vitest";
import {
  advanceSteer,
  canCheckSteer,
  canResendSteer,
  isUnresolvedSteer,
  placeLateSteer,
  settleOpenSteers,
  steerReplyStatus,
  steerStatusText,
  type PendingSteer,
} from "@/lib/agentSteer";

const steer = (status: PendingSteer["status"], requestId = "r1"): PendingSteer => ({
  requestId,
  text: "Use Q5",
  status,
});

describe("agent steers", () => {
  it("only move forward, so a late reply cannot undo a settled steer", () => {
    expect(advanceSteer([steer("sending")], "r1", "queued")[0].status).toBe("queued");
    expect(advanceSteer([steer("withdrawn")], "r1", "queued")[0].status).toBe("withdrawn");
    expect(advanceSteer([steer("unconfirmed")], "r1", "rejected", "idle")[0]).toMatchObject({
      status: "rejected",
      reason: "idle",
    });
    expect(advanceSteer([steer("queued", "other")], "r1", "failed")[0].status).toBe("queued");
  });

  it("are unconfirmed, never withdrawn, when the stream ends before saying where they landed", () => {
    const list = [steer("queued", "a"), steer("sending", "b"), steer("rejected", "c")];
    // A stop says nothing about a steer the runtime may have placed just before.
    expect(settleOpenSteers(list).map((s) => s.status)).toEqual([
      "unconfirmed",
      "sending",
      "rejected",
    ]);
    expect(isUnresolvedSteer(steer("unconfirmed"))).toBe(true);
    expect(isUnresolvedSteer(steer("delivered"))).toBe(true);
    expect(isUnresolvedSteer({ ...steer("delivered"), unplaced: true })).toBe(false);
    // Placed in the conversation the chat shows: resolved there, while its save is awaited.
    expect(isUnresolvedSteer({ ...steer("delivered"), saving: true })).toBe(false);
    expect(isUnresolvedSteer(steer("withdrawn"))).toBe(false);
    expect(canCheckSteer(steer("unconfirmed"))).toBe(true);
    expect(canCheckSteer({ ...steer("unconfirmed"), checking: true })).toBe(false);
  });

  it("read the steer reply and say where each one stands", () => {
    expect(steerReplyStatus({ status: "queued" })).toEqual({ status: "queued" });
    expect(steerReplyStatus({ status: "applied", entry_id: "7" })).toEqual({
      status: "delivered",
      entryId: "7",
    });
    expect(steerReplyStatus({ status: "not_found" })).toEqual({
      status: "rejected",
      reason: "not_found",
    });
    expect(steerReplyStatus({ status: "rejected", reason: "idle" })).toEqual({
      status: "rejected",
      reason: "idle",
    });
    // A reply the chat cannot read settles nothing: the steer may have been admitted.
    expect(steerReplyStatus(null).status).toBe("unconfirmed");
    expect(steerStatusText({ ...steer("rejected"), reason: "not_found" })).toMatch(/Not delivered/);
    expect(steerStatusText(steer("queued"))).toBe("Read after the current step");
    expect(steerStatusText({ ...steer("withdrawn"), reason: "aborted" })).toMatch(/stopped/);
    expect(steerStatusText({ ...steer("withdrawn"), reason: "run_failed" })).toMatch(/ended/);
    expect(canResendSteer(steer("queued"))).toBe(false);
    expect(canResendSteer(steer("delivered"))).toBe(false);
    expect(canResendSteer(steer("rejected"))).toBe(true);
    // Not confirmed either way: sending it again could make the answer read it twice.
    expect(canResendSteer(steer("unconfirmed"))).toBe(false);
  });
});

describe("placing a steer the stream did not place", () => {
  const user = (content: string) => ({ role: "user" as const, content });
  const answer = (content: string) => ({ role: "assistant" as const, content });
  const placed = (content: string, requestId: string, entryId: string) => ({
    role: "user" as const,
    content,
    steer: { requestId, entryId, placement: "exact" as const },
  });
  const anchor = { start: 1, userText: "Calibrate Q4" };
  const late = (requestId: string, entryId: string | null) => ({
    requestId,
    text: `late ${requestId}`,
    entryId,
    anchor,
  });

  it("goes after the part of the answer it interrupted, before the next turn", () => {
    const messages = [
      user("Hi"),
      user("Calibrate Q4"),
      answer("stopped"),
      user("Next turn"),
      answer("x"),
    ];
    const out = placeLateSteer(messages, late("a", "6"))!;
    expect(out.map((m) => m.content)).toEqual([
      "Hi",
      "Calibrate Q4",
      "stopped",
      "late a",
      "Next turn",
      "x",
    ]);
    expect(out[3].steer).toEqual({ requestId: "a", entryId: "6", placement: "approximate" });
    // Exactly once: placing it again changes nothing.
    expect(placeLateSteer(out, late("a", "6"))).toBe(out);
  });

  it("keeps transcript order among the turn's steers whatever order the receipts arrive in", () => {
    const messages = [
      user("Hi"),
      user("Calibrate Q4"),
      answer("one"),
      placed("p", "p", "5"),
      answer("two"),
    ];
    let out = placeLateSteer(messages, late("c", "9"))!;
    out = placeLateSteer(out, late("a", "3"))!;
    out = placeLateSteer(out, late("b", "7"))!;
    expect(out.map((m) => m.content)).toEqual([
      "Hi",
      "Calibrate Q4",
      "one",
      "late a",
      "p",
      "two",
      "late b",
      "late c",
    ]);
  });

  it("is not placed once the turn it was sent to is no longer where it was", () => {
    expect(placeLateSteer([user("Hi"), user("Edited")], late("a", "4"))).toBeNull();
    expect(placeLateSteer([user("Hi")], { ...late("a", "4"), anchor: undefined })).toBeNull();
  });
});
