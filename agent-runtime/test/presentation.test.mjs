import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { encodeLine } from "../src/events.ts";
import {
  acceptsPresentation,
  MAX_UI_BLOCK_CHARS,
  PresentationStream,
  streamEncoder,
  toolLabel,
  uiBlock,
} from "../src/presentation.ts";
import { TurnFeed } from "../src/turn-feed.ts";

// Shared with the API relay and the chat: the same runtime events, the envelopes
// the runtime sends for them, and the SSE the API relays.
const shared = JSON.parse(readFileSync(new URL("../testdata/presentation-v1.json", import.meta.url), "utf8"));

const mapAll = (events) => {
  const stream = new PresentationStream();
  return events.flatMap((event) => stream.map(event));
};

for (const scenario of shared.cases) {
  test(`presentation case ${scenario.name}: ${scenario.description}`, () => {
    assert.deepEqual(mapAll(scenario.runtime_events), scenario.presentation);
  });
}

test("every shared envelope's data is what the chat reads, minus the API's own fields", () => {
  for (const scenario of shared.cases) {
    const relayed = scenario.presentation.map((e) => (e.event === "keepalive" ? ":" : [e.event, e.data]));
    const expected = scenario.sse
      .map((sse) => (sse === ":" ? sse : [sse[0], sse[0] === "error" ? withoutStep(sse[1]) : sse[1]]))
      // The API, not the runtime, reports a stream that ended without its terminal event.
      .filter((sse, i, all) => !(i === all.length - 1 && sse[1]?.code === "stream_lost"));
    assert.deepEqual(relayed, expected, scenario.name);
    // Evaluation records go to the API only, never into what the chat reads.
    assert.ok(!JSON.stringify(relayed).includes('"record"'), scenario.name);
  }
});

function withoutStep({ step: _step, ...rest }) {
  return rest;
}

test("an evaluation record travels in internal, with the entry that names the call", () => {
  const [, end] = mapAll([
    { type: "tool_start", name: "qcal_evaluate", id: "e1" },
    {
      type: "tool_end",
      name: "qcal_evaluate",
      id: "e1",
      isError: false,
      entry_id: "5",
      before_turn: true,
      evaluation: { prompt: "p", record: { task_id: "t" } },
    },
  ]).filter((e) => e.event === "tool_end" || e.event === "tool_start");
  assert.deepEqual(end.data.evaluation, { prompt: "p" });
  assert.deepEqual(end.internal, { evaluation_record: { record: { task_id: "t" }, entry_id: "5", before_turn: true } });
});

test("nothing is mapped after a terminal event", () => {
  const stream = new PresentationStream();
  assert.equal(stream.map({ type: "noop", reason: "nothing_to_answer" }).length, 1);
  assert.deepEqual(stream.map({ type: "text_delta", delta: "late" }), []);
});

test("tool labels are derived, with the runtime's own tools looked up", () => {
  assert.equal(toolLabel("qdash_get_timeseries"), "Get timeseries");
  assert.equal(toolLabel("render_chart"), "Render chart");
  assert.equal(toolLabel("codemode"), "Code mode script");
  assert.equal(toolLabel("tool_search"), "Search tools");
  assert.equal(toolLabel("toString"), "Tostring");
  assert.equal(toolLabel("qdash_"), "qdash_");
});

test("a ui block over its bound keeps only its fallback", () => {
  const spec = { root: "a", elements: { a: { type: "Text", props: { text: "x".repeat(MAX_UI_BLOCK_CHARS) } } } };
  assert.deepEqual(uiBlock({ version: 1, spec, fallback: "short" }), { type: "text", content: "short", chart: null });
  assert.equal(uiBlock({ version: 1, spec }), undefined);
});

test("only a request for this contract's media type and version gets it", () => {
  assert.equal(acceptsPresentation(undefined), false);
  assert.equal(acceptsPresentation("application/x-ndjson"), false);
  assert.equal(acceptsPresentation("application/vnd.qdash.agent-presentation+x-ndjson"), true);
  assert.equal(
    acceptsPresentation("application/vnd.qdash.agent-presentation+x-ndjson; version=1, application/x-ndjson;q=0.5"),
    true,
  );
  assert.equal(acceptsPresentation("application/vnd.qdash.agent-presentation+x-ndjson; version=2"), false);
  assert.equal(acceptsPresentation("application/vnd.qdash.agent-presentation+x-ndjson; q=0"), false);
  assert.equal(acceptsPresentation(["text/plain", "application/vnd.qdash.agent-presentation+x-ndjson"]), true);
});

test("a subscriber that attaches late maps the replayed turn to the same segments and result", () => {
  const feed = new TurnFeed();
  const live = [];
  const liveEncode = streamEncoder(true, encodeLine);
  feed.subscribe((event) => live.push(liveEncode(event)));
  const turn = shared.cases.find((c) => c.name === "steers_and_recovered_turn_start").runtime_events;
  for (const event of turn.slice(0, 7)) feed.write(event);
  const late = [];
  const lateEncode = streamEncoder(true, encodeLine);
  feed.subscribe((event) => late.push(lateEncode(event)));
  for (const event of turn.slice(7)) feed.write(event);
  feed.end();

  const parse = (chunks) => chunks.join("").split("\n").filter(Boolean).map((line) => JSON.parse(line));
  const shaped = (envelopes) =>
    envelopes.filter((e) => ["steer", "turn_start", "result", "tool_end"].includes(e.event));
  assert.deepEqual(shaped(parse(late)), shaped(parse(live)));
  assert.deepEqual(parse(live), mapAll(turn));
  // The raw encoder is unchanged for a stream that did not ask for the contract.
  assert.equal(streamEncoder(false, encodeLine)({ type: "ping" }), '{"type":"ping"}\n');
});
