import assert from "node:assert/strict";
import { test } from "node:test";

import { inZone, NON_UTC_ZONES } from "./helpers/time-zone.mjs";
import { compareServerTimestamps, parseServerTimestamp, serverTimestampText } from "../.test-dist/lib/server-time.js";

const INSTANT = Date.UTC(2026, 10, 22, 2, 53, 20, 768);

test("a naive API timestamp is UTC, and an explicit Z or offset is kept, in any host zone", async () => {
  for (const zone of NON_UTC_ZONES) {
    await inZone(zone, () => {
      for (const value of [
        "2026-11-22T02:53:20.768000",
        "2026-11-22T02:53:20.768Z",
        "2026-11-22T02:53:20.768000z",
        "2026-11-22T11:53:20.768+09:00",
        "2026-11-22T11:53:20.768+0900",
        "2026-11-21T21:53:20.768-05:00",
        new Date(INSTANT),
      ]) {
        assert.equal(parseServerTimestamp(value), INSTANT, `${zone}: ${String(value)}`);
      }
      assert.equal(parseServerTimestamp("2026-11-22T02:53"), Date.UTC(2026, 10, 22, 2, 53));
    });
  }
});

test("a value that is not an ISO date-time is NaN, never a guessed local date", () => {
  for (const value of [
    undefined,
    null,
    "",
    1795316000768,
    "garbage",
    "2026-11-22",
    "2026-11-22 02:53:20",
    "11/22/2026 02:53",
    "Sun Nov 22 2026 11:53:20 GMT+0900",
    "2026-13-40T02:53:20",
    "2026-11-22T02:53:20+9",
    new Date(Number.NaN),
  ]) {
    assert.ok(Number.isNaN(parseServerTimestamp(value)), String(value));
  }
});

test("timestamp text names its instant: naive gains Z, an offset is unchanged", () => {
  assert.equal(serverTimestampText("2026-11-22T02:53:20.768000"), "2026-11-22T02:53:20.768000Z");
  assert.equal(serverTimestampText("2026-11-22T11:53:20+09:00"), "2026-11-22T11:53:20+09:00");
  assert.equal(serverTimestampText("2026-11-22T02:53:20Z"), "2026-11-22T02:53:20Z");
  assert.equal(serverTimestampText(new Date(INSTANT)), "2026-11-22T02:53:20.768Z");
  assert.equal(serverTimestampText("not a time"), "not a time");
  assert.equal(serverTimestampText(undefined), "");
});

test("ordering compares instants across formats and puts invalid values last", async () => {
  await inZone("Asia/Tokyo", () => {
    // 02:00 naive (UTC) is after 10:30+09:00 (01:30 UTC) and before 02:30Z.
    const values = ["2026-11-22T02:30:00Z", "bad", "2026-11-22T02:00:00", "2026-11-22T10:30:00+09:00"];
    assert.deepEqual([...values].sort(compareServerTimestamps), ["2026-11-22T10:30:00+09:00", "2026-11-22T02:00:00", "2026-11-22T02:30:00Z", "bad"]);
    assert.equal(compareServerTimestamps("x", "y"), 0);
  });
});
