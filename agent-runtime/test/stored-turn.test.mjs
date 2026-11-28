import assert from "node:assert/strict";
import { test } from "node:test";

import { storedTurn, storedTurnFinal } from "../src/chat-control.ts";

// Submission records as the store keeps them; IDs grow in creation order.
const input = (id, requestId, fields) => ({ id, conversationId: 0, type: "input", requestId, ...fields });
const done = (id, requestId, entry, answer) => input(id, requestId, { status: "done", entry, answer });
const steer = (id, requestId, fields) => input(id, `steer:p1:${requestId}`, fields);

test("a turn followed by another ends right before the next turn's message", () => {
  const a = done(1, "A", 1, 4);
  const b = done(2, "B", 5, 8);
  assert.deepEqual(storedTurn(a, [b]), { status: "bounded", after: 1, through: 4, members: [] });
  // The latest turn has no later boundary: every later entry is its own.
  assert.deepEqual(storedTurn(b, []), { status: "bounded", after: 5, through: undefined, members: [] });
});

test("the latest final answer of a steer-continued turn bounds it, not the turn's own answer", () => {
  // A answered at 4; a steer sent after that answer was placed at 5 and answered at 7; B's message is 8.
  const a = done(1, "A", 1, 4);
  const s = steer(2, "s1", { status: "done", entry: 5, answer: 7 });
  const b = done(3, "B", 8, 9);
  const turn = storedTurn(a, [s, b]);
  assert.deepEqual(turn, { status: "bounded", after: 1, through: 7, members: [s] });
  assert.equal(storedTurnFinal(a, turn.members), s);
  // A runtime wrap-up steer (no request ID) is the turn's too.
  const wrapUp = input(2, undefined, { status: "done", entry: 5, answer: 7 });
  assert.deepEqual(storedTurn(a, [wrapUp, b]).members, [wrapUp]);
});

test("a steer of an earlier turn placed before the message, and a message never placed, bound nothing", () => {
  // A recovered run placed an earlier turn's steer at 2, before A's message at 3.
  const a = done(5, "A", 3, 6);
  const early = steer(6, "old", { status: "done", entry: 2, answer: 2 });
  const neverPlaced = input(7, "X", { status: "unanswered", reason: "rejected" });
  const b = done(8, "B", 7, 9);
  assert.deepEqual(storedTurn(a, [early, neverPlaced, b]), { status: "bounded", after: 3, through: 6, members: [] });
});

test("after a continue the turn ends at what its own submissions placed last", () => {
  const a = input(1, "A", { status: "unanswered", entry: 1, reason: "aborted" });
  const s = steer(2, "s1", { status: "unanswered", entry: 3, reason: "aborted" });
  const c = { id: 3, conversationId: 0, type: "continue", requestId: "C", status: "done", answer: 9 };
  assert.deepEqual(storedTurn(a, [s, c]), { status: "bounded", after: 1, through: 3, members: [s] });
});

test("an end the store does not establish is unknown, never guessed", () => {
  const a = done(1, "A", 1, 4);
  // The next message is still queued: where it lands is not known yet.
  assert.deepEqual(storedTurn(a, [input(2, "B", { status: "queued" })]), {
    status: "unknown",
    reason: "later_turn_queued",
  });
  // A continue after a turn whose steer has not settled.
  const s = steer(2, "s1", { status: "placed", entry: 5 });
  const c = { id: 3, conversationId: 0, type: "continue", requestId: "C", status: "placed" };
  assert.deepEqual(storedTurn(a, [s, c]), { status: "unknown", reason: "turn_unsettled" });
  // A turn whose message was never placed has no range.
  assert.deepEqual(storedTurn(input(1, "A", { status: "queued" }), []), { status: "unknown", reason: "own_not_placed" });
});
