import { describe, expect, it } from "vitest";

import {
  observedTurnPlacement,
  parseRecordedTurn,
  parseTurnStart,
  type RecordedTurn,
  recordedTurnPlacement,
  transcriptDigest,
  turnStartOf,
} from "@/lib/copilotObservedTurn";
import type { ChatMessage } from "@/types/copilotChat";

const user = (content: string): ChatMessage => ({ role: "user", content });
const answer = (content: string): ChatMessage => ({ role: "assistant", content });
const steer = (content: string, requestId: string): ChatMessage => ({
  role: "user",
  content,
  steer: { requestId, entryId: null, placement: "exact" },
});

describe("turnStartOf and transcriptDigest", () => {
  it("names the messages before the turn and fingerprints them with the turn's message", () => {
    const history = [user("hi"), answer("hello")];
    const start = turnStartOf(history, user("calibrate Q0"));
    expect(start.index).toBe(2);
    expect(start.digest).toMatch(/^[0-9a-f]{16}$/);
    expect(start.digest).toBe(transcriptDigest([...history, user("calibrate Q0")]));
    // A continue adds no message of its own.
    expect(turnStartOf(history, null)).toEqual({ index: 2, digest: transcriptDigest(history) });
  });

  it("tells transcripts apart by role, text, and steer, but not by local-only fields", () => {
    const base = transcriptDigest([user("a"), answer("b")]);
    expect(transcriptDigest([user("a"), answer("c")])).not.toBe(base);
    expect(transcriptDigest([answer("a"), answer("b")])).not.toBe(base);
    expect(transcriptDigest([steer("a", "s1"), answer("b")])).not.toBe(base);
    expect(transcriptDigest([user("ab")])).not.toBe(transcriptDigest([user("a"), user("b")]));
    expect(
      transcriptDigest([
        { ...user("a"), attachments: ["data:x"] },
        { ...answer("b"), entryId: "9" },
      ]),
    ).toBe(base);
  });

  it("accepts only a well-formed start from the API", () => {
    expect(parseTurnStart({ index: 0, digest: "0123456789abcdef" })).toEqual({
      index: 0,
      digest: "0123456789abcdef",
    });
    for (const bad of [
      null,
      undefined,
      "x",
      { index: -1, digest: "0123456789abcdef" },
      { index: 1.5, digest: "0123456789abcdef" },
      { index: 0, digest: "0123456789ABCDEF" },
      { index: 0, digest: "short" },
      { digest: "0123456789abcdef" },
    ]) {
      expect(parseTurnStart(bad)).toBeNull();
    }
  });
});

describe("observedTurnPlacement", () => {
  const older = [user("What is T1 of Q0?"), answer("T1 is 50 us.")];
  const question = user("Calibrate Q1");

  it("places a turn at its own message once the saved transcript holds its start", () => {
    const start = turnStartOf(older, question);
    const saved = [...older, question];
    expect(observedTurnPlacement(saved, false, start)).toEqual({
      history: older,
      shown: saved,
      userAt: 2,
    });
  });

  it("refuses the transcript saved before the turn's message, never answering the old question", () => {
    // The starting window queued the save of its message; the older conversation is
    // what the server still holds when the other window looks.
    const start = turnStartOf(older, question);
    expect(observedTurnPlacement(older, false, start)).toBeNull();
    // Nor an older transcript that ends in a user message of its own.
    expect(observedTurnPlacement([user("What is T1 of Q0?")], false, start)).toBeNull();
  });

  it("refuses another transcript at the same place: the turn was sent after other messages", () => {
    // Saved earlier: a longer conversation whose message at the turn's index differs.
    const start = turnStartOf(older, question);
    const other = [...older, user("Calibrate Q2"), answer("Done.")];
    expect(observedTurnPlacement(other, false, start)).toBeNull();
    // Same message, different history before it.
    const edited = [user("What is T2 of Q0?"), answer("T1 is 50 us."), question];
    expect(observedTurnPlacement(edited, false, start)).toBeNull();
  });

  it("leaves out what the turn placed after its message, which the replay places again", () => {
    const start = turnStartOf([], user("calibrate Q0"));
    const messages = [user("calibrate Q0"), answer("part"), steer("use 5 GHz", "s1")];
    expect(observedTurnPlacement(messages, false, start)).toEqual({
      history: [],
      shown: [messages[0]],
      userAt: 0,
    });
  });

  it("never takes a steer for the turn's own message", () => {
    const history = [user("calibrate Q0"), answer("part")];
    const s = steer("use 5 GHz", "s1");
    const start = { index: 2, digest: transcriptDigest([...history, s]) };
    expect(observedTurnPlacement([...history, s], false, start)).toBeNull();
  });

  it("starts a continue at its exact start, less the steers it placed, never the answer it continues", () => {
    const base = [user("calibrate Q0"), answer("stopped part")];
    const start = turnStartOf(base, null);
    expect(observedTurnPlacement(base, true, start)).toEqual({
      history: base,
      shown: base,
      userAt: -1,
    });
    const placed = [...base, answer("continued part"), steer("faster", "s2")];
    expect(observedTurnPlacement(placed, true, start)).toEqual({
      history: base,
      shown: base,
      userAt: -1,
    });
    // A steer right after the answer it continued keeps that answer.
    expect(observedTurnPlacement([...base, steer("faster", "s2")], true, start)?.shown).toEqual(
      base,
    );
  });

  it("refuses a continue over a transcript that does not hold the answer it continues", () => {
    const base = [user("calibrate Q0"), answer("stopped part")];
    const start = turnStartOf(base, null);
    // The stopped answer's save has not landed yet.
    expect(observedTurnPlacement([user("calibrate Q0")], true, start)).toBeNull();
    expect(observedTurnPlacement([], true, start)).toBeNull();
    // A different answer at the same place.
    expect(
      observedTurnPlacement([user("calibrate Q0"), answer("another answer")], true, start),
    ).toBeNull();
  });

  it("follows nothing when the runtime reported no start", () => {
    expect(observedTurnPlacement([...older, question], false, null)).toBeNull();
    expect(observedTurnPlacement(older, true, null)).toBeNull();
  });
});

describe("recordedTurnPlacement", () => {
  const user = (content: string, turnRequestId?: string): ChatMessage => ({
    role: "user",
    content,
    ...(turnRequestId ? { turnRequestId } : {}),
  });
  const answer = (payload: object, turnRequestId: string): ChatMessage => ({
    role: "assistant",
    content: JSON.stringify(payload),
    turnRequestId,
  });
  const running = (requestId: string, startIndex: number, continuing = false): RecordedTurn => ({
    requestId,
    projectId: "p1",
    status: "running",
    startIndex,
    continuing,
    startedAt: 0,
  });

  it("finds a running turn by its request ID, wherever it moved", () => {
    const messages: ChatMessage[] = [
      user("Hi"),
      { role: "assistant", content: "Hello" } as ChatMessage,
      // A recovered run's answer and a steer the server placed before the turn's message.
      answer({ blocks: [] }, "r1"),
      {
        ...user("also T2", "r1"),
        steer: { requestId: "s1", entryId: null, placement: "approximate" },
      },
      user("Calibrate Q0", "r1"),
      answer({ blocks: [], in_progress: true }, "r1"),
    ];
    const placed = recordedTurnPlacement(messages, "r1", false, running("r1", 2));
    expect(placed).toMatchObject({ state: "running", continuing: false, userAt: 2 });
    if (placed?.state !== "running") throw new Error("not placed");
    expect(placed.shown.map((m) => m.content)).toEqual(["Hi", "Hello", "Calibrate Q0"]);
  });

  it("says a turn ended when its record does, or a later turn replaced it", () => {
    const messages = [user("Q", "r1"), answer({ blocks: [] }, "r1"), user("Q2", "r2")];
    expect(recordedTurnPlacement(messages, "r1", false, running("r2", 2))).toEqual({
      state: "ended",
    });
    expect(
      recordedTurnPlacement(messages.slice(0, 2), "r1", false, {
        ...running("r1", 0),
        status: "completed",
      }),
    ).toEqual({ state: "ended" });
    // Without a record: its saved answer is its end, saved progress is not.
    expect(recordedTurnPlacement(messages.slice(0, 2), "r1", false, null)).toEqual({
      state: "ended",
    });
    expect(
      recordedTurnPlacement(
        [user("Q", "r1"), answer({ blocks: [], in_progress: true }, "r1")],
        "r1",
        false,
        null,
      ),
    ).toMatchObject({ state: "running" });
  });

  it("places a continue that saved nothing yet where the server recorded it", () => {
    const messages = [user("Hi"), { role: "assistant", content: "Hello" } as ChatMessage];
    expect(recordedTurnPlacement(messages, "r1", false, running("r1", 2, true))).toMatchObject({
      state: "running",
      continuing: true,
      userAt: -1,
      history: messages,
    });
    expect(recordedTurnPlacement(messages, "r1", true, null)).toBeNull();
  });

  it("parses the session's recorded turn", () => {
    expect(
      parseRecordedTurn({
        request_id: "r1",
        project_id: "p1",
        status: "running",
        start_index: 2,
        continuing: false,
        started_at: "2026-11-23T01:00:00",
      }),
    ).toEqual({
      requestId: "r1",
      projectId: "p1",
      status: "running",
      startIndex: 2,
      continuing: false,
      startedAt: Date.parse("2026-11-23T01:00:00Z"),
    });
    expect(parseRecordedTurn({ request_id: "r1", status: "lost", start_index: 0 })).toBeNull();
    expect(parseRecordedTurn(null)).toBeNull();
  });
});
