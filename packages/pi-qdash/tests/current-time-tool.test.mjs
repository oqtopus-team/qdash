import assert from "node:assert/strict";
import { test } from "node:test";

import { inZone, NON_UTC_ZONES } from "./helpers/time-zone.mjs";
import { canonicalTimeZone, readCurrentTime, registerCurrentTimeTool, zonedTime } from "../.test-dist/tools/current-time.js";

// 2026-11-22 02:53:20.768 UTC: winter, so New York is on EST.
const WINTER = new Date(Date.UTC(2026, 10, 22, 2, 53, 20, 768));
// 2026-07-01 12:00:00 UTC: summer, so New York is on EDT.
const SUMMER = new Date(Date.UTC(2026, 6, 1, 12, 0, 0, 0));

function registered(now) {
  const tools = new Map();
  registerCurrentTimeTool({ registerTool(tool) { tools.set(tool.name, tool); } }, { now });
  return tools.get("qdash_current_time");
}

test("without a time zone the answer is UTC and says the user's zone is unknown", async () => {
  const tool = registered(() => WINTER);
  const result = await tool.execute("t", {}, undefined, undefined, {});
  const text = result.content[0].text;
  assert.match(text, /UTC: 2026-11-22T02:53:20\.768Z \(Sunday\)/);
  assert.match(text, /time zone is not known, so this answer is in UTC/);
  assert.match(text, /machine running pi CLI/);
  assert.match(text, /not the QDash server's or the measurement hardware's/);
  assert.match(text, /does not verify it against a time service/);
  const data = result.details.data;
  assert.equal(data.utc, "2026-11-22T02:53:20.768Z");
  assert.equal(data.epoch_ms, WINTER.getTime());
  assert.equal(data.requested, null);
  assert.equal(data.user_time_zone_known, false);
  assert.deepEqual(data.source, { kind: "host_os_clock", host: "pi", verified: false });
});

test("the web agent host is named as the runtime's container", async () => {
  const tool = registered(() => WINTER);
  const result = await tool.execute("t", {}, undefined, undefined, { qdashHostName: "qdash-web-agent" });
  assert.match(result.content[0].text, /QDash web agent runtime's container/);
  assert.equal(result.details.data.source.host, "qdash-web-agent");
  // A malformed host name falls back to pi rather than echoing it.
  const odd = await tool.execute("t", {}, undefined, undefined, { qdashHostName: "Bad Host!" });
  assert.equal(odd.details.data.source.host, "pi");
});

test("an explicit IANA zone renders the instant with that zone's offset, across daylight saving", () => {
  assert.deepEqual(zonedTime(WINTER, "Asia/Tokyo"), { time_zone: "Asia/Tokyo", local: "2026-11-22T11:53:20.768+09:00", offset: "+09:00", weekday: "Sunday" });
  assert.deepEqual(zonedTime(WINTER, "America/New_York"), { time_zone: "America/New_York", local: "2026-11-21T21:53:20.768-05:00", offset: "-05:00", weekday: "Saturday" });
  assert.deepEqual(zonedTime(SUMMER, "America/New_York"), { time_zone: "America/New_York", local: "2026-07-01T08:00:00.000-04:00", offset: "-04:00", weekday: "Wednesday" });
  assert.deepEqual(zonedTime(WINTER, "UTC"), { time_zone: "UTC", local: "2026-11-22T02:53:20.768+00:00", offset: "+00:00", weekday: "Sunday" });
  assert.equal(zonedTime(new Date(Date.UTC(2026, 0, 1, 0, 0)), "Asia/Kolkata").offset, "+05:30");
});

test("the UTC instant and an explicit zone's rendering do not depend on the process time zone", async () => {
  const baseline = readCurrentTime(WINTER, { requestedZone: "America/New_York" });
  for (const zone of NON_UTC_ZONES) {
    await inZone(zone, async () => {
      const reading = readCurrentTime(WINTER, { requestedZone: "America/New_York" });
      assert.deepEqual(reading, baseline, zone);
      // Without a requested zone the process zone is not reported or used as the user's.
      const tool = registered(() => WINTER);
      const result = await tool.execute("t", {}, undefined, undefined, {});
      assert.equal(result.details.data.utc, "2026-11-22T02:53:20.768Z", zone);
      assert.equal(result.details.data.requested, null, zone);
      assert.doesNotMatch(result.content[0].text, /Asia\/Tokyo|America\/New_York|\+09:00|-05:00/, zone);
    });
  }
});

test("an unknown or non-IANA zone is refused, not guessed", async () => {
  const tool = registered(() => WINTER);
  for (const zone of ["Asia/Tokio", "+09:00", "UTC+9", "", "  ", "Japanese"]) {
    await assert.rejects(tool.execute("t", { timeZone: zone }, undefined, undefined, {}), /Unknown time zone .*IANA time zone name.*No time was converted/, JSON.stringify(zone));
  }
  assert.equal(canonicalTimeZone("Asia/Tokyo"), "Asia/Tokyo");
  assert.equal(canonicalTimeZone(" America/New_York "), "America/New_York");
  assert.equal(canonicalTimeZone("Not/AZone"), undefined);
});

test("a requested zone is the user's statement, and the tool reads the clock again at every call", async () => {
  const instants = [WINTER, SUMMER];
  let calls = 0;
  const tool = registered(() => instants[calls++]);
  const first = await tool.execute("t1", { timeZone: "Asia/Tokyo" }, undefined, undefined, {});
  assert.match(first.content[0].text, /- Asia\/Tokyo: 2026-11-22T11:53:20\.768\+09:00 \(Sunday, UTC\+09:00\)/);
  assert.doesNotMatch(first.content[0].text, /not known/);
  assert.equal(first.details.data.user_time_zone_known, true);
  const second = await tool.execute("t2", { timeZone: "Asia/Tokyo" }, undefined, undefined, {});
  assert.equal(second.details.data.utc, "2026-07-01T12:00:00.000Z");
  assert.equal(calls, 2);
});

test("the tool description and guidance never tie the zone to the user's language", () => {
  const tool = registered(() => WINTER);
  const guidance = [tool.description, ...tool.promptGuidelines].join("\n");
  assert.match(guidance, /never infer it from the user's language/);
  assert.match(guidance, /no approval/);
  assert.deepEqual(Object.keys(tool.parameters.properties), ["timeZone"]);
});
