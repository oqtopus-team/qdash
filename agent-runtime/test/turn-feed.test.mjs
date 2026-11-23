import assert from "node:assert/strict";
import { test } from "node:test";

import { TurnFeed } from "../src/turn-feed.ts";

test("a late subscriber gets the turn so far, merged, then the live events; pings are not replayed", () => {
  const feed = new TurnFeed();
  const live = [];
  feed.subscribe((event) => live.push(event));
  feed.write({ type: "text_delta", delta: "Ask" });
  feed.write({ type: "text_delta", delta: "ing." });
  feed.write({ type: "ping" });
  feed.write({ type: "tool_args_delta", index: 0, path: ["code"], delta: "a" });
  feed.write({ type: "tool_args_delta", index: 0, path: ["code"], delta: "b" });
  feed.write({ type: "tool_args_delta", index: 0, path: ["note"], delta: "c" });
  feed.write({ type: "tool_start", name: "wait_expert", id: "w1" });
  // The original subscriber saw every event as written, the ping included.
  assert.equal(live.length, 7);

  const late = [];
  feed.subscribe((event) => late.push(event));
  assert.deepEqual(late, [
    { type: "text_delta", delta: "Asking." },
    { type: "tool_args_delta", index: 0, path: ["code"], delta: "ab" },
    { type: "tool_args_delta", index: 0, path: ["note"], delta: "c" },
    { type: "tool_start", name: "wait_expert", id: "w1" },
  ]);

  feed.write({ type: "ping" });
  feed.write({ type: "tool_end", name: "wait_expert", id: "w1", isError: false });
  feed.write({ type: "done", text: "ok", entry_id: "9" });
  assert.deepEqual(late.slice(4), [
    { type: "ping" },
    { type: "tool_end", name: "wait_expert", id: "w1", isError: false },
    { type: "done", text: "ok", entry_id: "9" },
  ]);
  assert.equal(feed.terminal, true);
});

test("a detached subscriber gets nothing more; after the end only the log is replayed and closed settles", async () => {
  const feed = new TurnFeed();
  const seen = [];
  const detach = feed.subscribe((event) => seen.push(event));
  feed.write({ type: "text_delta", delta: "a" });
  detach();
  feed.write({ type: "text_delta", delta: "b" });
  assert.deepEqual(seen, [{ type: "text_delta", delta: "a" }]);
  assert.equal(feed.terminal, false);
  feed.end();
  await feed.closed;
  feed.write({ type: "text_delta", delta: "ignored" });
  const after = [];
  feed.subscribe((event) => after.push(event));
  assert.deepEqual(after, [{ type: "text_delta", delta: "ab" }]);
});

test("a subscriber that throws is dropped without keeping the event from the others", () => {
  const feed = new TurnFeed();
  const seen = [];
  feed.subscribe(() => {
    throw new Error("socket gone");
  });
  feed.subscribe((event) => seen.push(event));
  const warn = console.warn;
  console.warn = () => undefined;
  try {
    feed.write({ type: "text_delta", delta: "a" });
    feed.write({ type: "text_delta", delta: "b" });
  } finally {
    console.warn = warn;
  }
  assert.equal(seen.length, 2);
});
