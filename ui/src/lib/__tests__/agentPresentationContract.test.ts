import { describe, expect, it } from "vitest";

import {
  appendArgsDelta,
  appendDelta,
  appendLiveBlock,
  endTool,
  startDraft,
  startTool,
} from "@/lib/agentChatStream";
import { consumeSSEEvents } from "@/lib/sse-utils";
import type { LiveTurn } from "@/types/agentChat";

import sharedCases from "../../../../agent-runtime/testdata/presentation-v1.json";

// The runtime's presentation cases, relayed by the API as this SSE; see
// agent-runtime/testdata/presentation-v1.json.
interface SharedCase {
  name: string;
  sse: Array<":" | [string, Record<string, unknown>]>;
}
const shared = sharedCases as unknown as { cases: SharedCase[] };

/** The SSE text the API writes for a case, as the chat's stream reader receives it. */
function wire(scenario: SharedCase): string {
  return scenario.sse
    .map((sse) => (sse === ":" ? ":\n\n" : `event: ${sse[0]}\ndata: ${JSON.stringify(sse[1])}\n\n`))
    .join("");
}

/** Fold a case's live events the way the chat's stream loop does, up to its last event. */
function fold(scenario: SharedCase) {
  const { events, remainder } = consumeSSEEvents(wire(scenario));
  let turn: LiveTurn = { steps: [], startedAt: 0 };
  const other: Array<[string, Record<string, unknown>]> = [];
  for (const evt of events) {
    const payload = JSON.parse(evt.data);
    if (evt.event === "delta")
      turn = { ...turn, steps: appendDelta(turn.steps, "text", payload.text) };
    else if (evt.event === "thinking")
      turn = {
        ...turn,
        steps: appendDelta(turn.steps, "thinking", payload.text),
      };
    else if (evt.event === "tool_draft") turn = { ...turn, steps: startDraft(turn.steps, payload) };
    else if (evt.event === "tool_args_delta")
      turn = { ...turn, steps: appendArgsDelta(turn.steps, payload) };
    else if (evt.event === "tool_start") turn = { ...turn, steps: startTool(turn.steps, payload) };
    else if (evt.event === "tool_end") turn = { ...turn, steps: endTool(turn.steps, payload) };
    else if (evt.event === "ui") turn = appendLiveBlock(turn, payload);
    else other.push([evt.event, payload]);
  }
  return { turn, other, remainder };
}

const byName = (name: string) => {
  const found = shared.cases.find((c) => c.name === name);
  if (!found) throw new Error(`missing shared case ${name}`);
  return found;
};

describe("the runtime presentation contract, as the chat reads it", () => {
  it("folds a tool round into labelled, finished steps with their output", () => {
    const { turn, other, remainder } = fold(byName("tool_round_then_answer"));
    expect(remainder).toBe("");
    const tools = turn.steps.filter((s) => s.kind === "tool");
    expect(tools.map((s) => [s.tool, s.label, s.status])).toEqual([
      ["bash", "Bash", "done"],
      ["qdash_get_task_figures", "Get task figures", "error"],
      ["codemode", "Code mode script", "done"],
    ]);
    expect(tools[0]).toMatchObject({ output: "fit.py", exitCode: 0 });
    expect(tools[1]).toMatchObject({ figures: ["exec/1/CheckRabi_0.png"] });
    expect(turn.steps[turn.steps.length - 1]).toMatchObject({
      kind: "text",
      text: "The fit is good.",
    });
    expect(other[other.length - 1]).toEqual([
      "result",
      {
        blocks: [{ type: "text", content: "The fit is good.", chart: null }],
        assessment: null,
        entry_id: "12",
      },
    ]);
  });

  it("shows a composed UI live, and a malformed one by its fallback", () => {
    const { turn, other } = fold(byName("visuals_and_cards"));
    expect(turn.blocks?.map((b) => b.type)).toEqual(["ui", "text"]);
    const result = other.find(([name]) => name === "result")?.[1] as {
      blocks: Array<{ type: string }>;
    };
    expect(result.blocks.map((b) => b.type)).toEqual([
      "chart",
      "ui",
      "text",
      "text",
      "ask",
      "approval",
      "edit",
    ]);
  });

  it("shows an evaluation, a classification and a created session under their steps", () => {
    const { turn } = fold(byName("evaluation_classification_session"));
    const tools = turn.steps.filter((s) => s.kind === "tool");
    expect(tools[0]).toMatchObject({
      evaluation: { prompt: "Reference for CheckRabi" },
    });
    expect(tools[1]).toMatchObject({
      classification: { outcome: "classified", category: "readout_problem" },
    });
    expect(tools[2]).toMatchObject({
      calibrationSession: { calibrationSessionId: "sess-1", chipId: "64Qv3" },
    });
  });

  it("receives segment boundaries, steers and terminal events in order", () => {
    const names = (scenario: string) =>
      fold(byName(scenario))
        .other.map(([name, payload]) => (name === "steer" ? `steer:${payload.status}` : name))
        .filter((name) => name !== "status");
    expect(names("steers_and_recovered_turn_start")).toEqual([
      "steer:applied",
      "turn_start",
      "steer:applied",
      "steer:withdrawn",
      "result",
    ]);
    expect(names("noop")).toEqual(["noop"]);
    expect(names("stream_ends_without_terminal")).toEqual(["error"]);
    const lost = fold(byName("stream_ends_without_terminal")).other;
    expect(lost[lost.length - 1]?.[1]).toMatchObject({ code: "stream_lost" });
  });
});
