import { describe, expect, it } from "vitest";

import {
  appendArgsDelta,
  appendDelta,
  appendLiveBlock,
  endTool,
  failedTurnPayload,
  progressTool,
  startDraft,
  startTool,
  stoppedBlocks,
  toPersistedTrace,
} from "@/lib/agentChatStream";
import type { LiveTurn, TraceStep } from "@/types/agentChat";

function tool(steps: TraceStep[], i = steps.length - 1) {
  const step = steps[i];
  if (step.kind !== "tool") throw new Error("not a tool step");
  return step;
}

describe("agentChatStream", () => {
  it("shows a tool call as it is written, then runs it as the same step", () => {
    let steps: TraceStep[] = [{ kind: "thinking", text: "fit", startedAt: 1 }];
    steps = startDraft(steps, { index: 1, id: "call_1", tool: "write", label: "Write" });
    expect(steps[0]).toMatchObject({ kind: "thinking", endedAt: expect.any(Number) });
    expect(tool(steps)).toMatchObject({ status: "drafting", draft: {}, draftIndex: 1 });

    steps = appendArgsDelta(steps, { index: 1, path: ["path"], delta: "fit.py" });
    steps = appendArgsDelta(steps, { index: 1, path: ["content"], delta: "import numpy" });
    steps = appendArgsDelta(steps, { index: 1, path: ["content"], delta: " as np\n" });
    steps = appendArgsDelta(steps, { index: 2, path: ["content"], delta: "other call" });
    expect(tool(steps).draft).toEqual({ path: "fit.py", content: "import numpy as np\n" });
    expect(steps).toHaveLength(2);

    const args = { path: "fit.py", content: "import numpy as np\n" };
    steps = startTool(steps, { id: "call_1", tool: "write", label: "Write", args });
    expect(steps).toHaveLength(2);
    expect(tool(steps)).toMatchObject({ id: "call_1", status: "running", args });
    expect(tool(steps).draft).toBeUndefined();

    steps = endTool(steps, { id: "call_1", tool: "write", output: "Wrote 19 bytes", exit_code: 0 });
    expect(tool(steps)).toMatchObject({ status: "done", output: "Wrote 19 bytes", exitCode: 0 });
  });

  it("ends the running call when the model reused an id that already ended", () => {
    // A local model gives every call of the turn the same id.
    let steps = startTool([], { id: "call_0", tool: "qcal_evaluate", label: "Evaluate" });
    steps = endTool(steps, { id: "call_0", tool: "qcal_evaluate", is_error: false });
    steps = startTool(steps, { id: "call_0", tool: "qcal_evaluate", label: "Evaluate" });
    expect(steps).toHaveLength(2);
    steps = endTool(steps, { id: "call_0", tool: "qcal_evaluate", is_error: true });
    expect(tool(steps, 0)).toMatchObject({ status: "done" });
    expect(tool(steps, 1)).toMatchObject({ status: "error" });
  });

  it("keeps a classify decision on its step through a reload", () => {
    const classification = {
      classifier: "system-one-classifier/Open-Jev",
      outcome: "classified",
      category: "readout_problem",
      probability: 0.8,
      margin: 0.65,
      probabilities: [
        { category: "readout_problem", probability: 0.8 },
        { category: "drive_problem", probability: 0.2 },
      ],
    };
    let steps = startTool([], {
      id: "k1",
      tool: "classify",
      label: "Classify",
      args: { question: "Why?", categories: [], context: "Q04 fit failed" },
    });
    steps = endTool(steps, { id: "k1", tool: "classify", classification });
    expect(tool(steps)).toMatchObject({ status: "done", classification });

    const trace = toPersistedTrace(
      { steps: [...steps, { kind: "text", text: "ok" }], startedAt: 0 },
      10,
    );
    const stored = JSON.parse(JSON.stringify(trace)) as typeof trace;
    expect(tool(stored!.steps, 0).classification).toEqual(classification);
  });

  it("keeps the calibration session a create call made, and only that, through a reload", () => {
    const create = "qdash_create_calibration_session";
    const started = startTool([], { id: "s1", tool: create, label: "Create", args: {} });
    const created = { calibration_session_id: "cs-new", chip_id: "64Qv3" };
    const steps = endTool(started, { id: "s1", tool: create, calibration_session: created });
    expect(tool(steps)).toMatchObject({
      status: "done",
      calibrationSession: { calibrationSessionId: "cs-new", chipId: "64Qv3" },
    });
    const trace = toPersistedTrace(
      { steps: [...steps, { kind: "text", text: "ok" }], startedAt: 0 },
      10,
    );
    const stored = JSON.parse(JSON.stringify(trace)) as typeof trace;
    expect(tool(stored!.steps, 0).calibrationSession).toEqual({
      calibrationSessionId: "cs-new",
      chipId: "64Qv3",
    });

    // A failed call, another tool, a result for a call of another tool, or a malformed ID.
    expect(
      tool(
        endTool(started, { id: "s1", tool: create, is_error: true, calibration_session: created }),
      ),
    ).not.toHaveProperty("calibrationSession");
    const other = startTool([], { id: "g1", tool: "qdash_get_calibration_session", label: "Get" });
    expect(
      tool(
        endTool(other, {
          id: "g1",
          tool: "qdash_get_calibration_session",
          calibration_session: created,
        }),
      ),
    ).not.toHaveProperty("calibrationSession");
    expect(
      tool(endTool(other, { id: "g1", tool: create, calibration_session: created })),
    ).not.toHaveProperty("calibrationSession");
    expect(
      tool(
        endTool(started, {
          id: "s1",
          tool: create,
          calibration_session: { calibration_session_id: "../x" },
        }),
      ),
    ).not.toHaveProperty("calibrationSession");
  });

  it("keeps a failed classification as an error step and drops malformed ones", () => {
    const started = startTool([], { id: "k1", tool: "classify", label: "Classify" });
    const failed = endTool(started, {
      id: "k1",
      tool: "classify",
      is_error: true,
      classification: { classifier: "c/m", outcome: "failed", reason: "timed out after 5 s" },
    });
    expect(tool(failed)).toMatchObject({
      status: "error",
      classification: { classifier: "c/m", outcome: "failed", reason: "timed out after 5 s" },
    });
    for (const classification of [
      "bogus",
      { classifier: "c/m", outcome: "template" },
      { outcome: "failed" },
    ]) {
      expect(
        tool(endTool(started, { id: "k1", tool: "classify", classification })),
      ).not.toHaveProperty("classification");
    }
    const partial = endTool(started, {
      id: "k1",
      tool: "classify",
      classification: {
        classifier: "c/m",
        outcome: "ambiguous",
        probability: 3,
        probabilities: [
          "x",
          { category: "a", probability: 0.5 },
          { category: "b", probability: -1 },
        ],
      },
    });
    expect(tool(partial).classification).toEqual({
      classifier: "c/m",
      outcome: "ambiguous",
      probabilities: [{ category: "a", probability: 0.5 }],
    });
  });

  it("follows a delegation's research tasks and leaves none running once it ends", () => {
    const running = { id: "1", title: "Chip A", status: "running", tool_calls: 2, started_at: 5 };
    let steps: TraceStep[] = startTool([], { id: "d1", tool: "delegate_research", label: "R" });
    steps = progressTool(steps, {
      id: "d1",
      subagents: [running, { id: "2", title: "Chip B", status: "queued" }, { id: 3 }],
    });
    expect(tool(steps).subagents).toEqual([
      { id: "1", title: "Chip A", status: "running", toolCalls: 2, startedAt: 5 },
      { id: "2", title: "Chip B", status: "queued", toolCalls: 0 },
    ]);
    // Malformed progress and progress for another call change nothing.
    expect(progressTool(steps, { id: "d1", subagents: "x" })).toBe(steps);
    expect(progressTool(steps, { id: "other", subagents: [running] })).toBe(steps);

    // A stopped turn saves the last progress with no task still running.
    const saved = toPersistedTrace({ steps, startedAt: 0 }, 10);
    const stored = saved?.steps[0];
    if (stored?.kind !== "tool") throw new Error("not a tool step");
    expect(stored.subagents?.map((t) => t.status)).toEqual(["interrupted", "interrupted"]);

    // The end carries the final tasks; one it left running was cut off.
    steps = endTool(steps, {
      id: "d1",
      tool: "delegate_research",
      subagents: [
        { ...running, status: "done", result: "T1 is 40 us" },
        { id: "2", title: "Chip B", status: "running", activity: "thinking" },
      ],
    });
    expect(tool(steps).subagents).toEqual([
      {
        id: "1",
        title: "Chip A",
        status: "done",
        toolCalls: 2,
        startedAt: 5,
        result: "T1 is 40 us",
      },
      { id: "2", title: "Chip B", status: "interrupted", toolCalls: 0 },
    ]);
    // An aborted call that ends without its tasks keeps the last progress, settled.
    const aborted = endTool(
      progressTool(startTool([], { id: "d2", tool: "delegate_research" }), {
        id: "d2",
        subagents: [running],
      }),
      { id: "d2", tool: "delegate_research", is_error: true },
    );
    expect(tool(aborted).subagents?.[0].status).toBe("interrupted");
  });

  it("opens a new step for a call that was never drafted", () => {
    const steps = startTool([], { id: "c1", tool: "qdash_list_chips", label: "List chips" });
    expect(tool(steps)).toMatchObject({ status: "running", id: "c1" });
  });

  it("adopts the latest draft of the same tool when the call starts without a matching id", () => {
    let steps: TraceStep[] = startDraft([], { index: 0, id: "", tool: "write", label: "Write" });
    steps = appendArgsDelta(steps, { index: 0, path: ["path"], delta: "fit.py" });
    expect(tool(steps).id).toMatch(/^draft-write-0-/);
    steps = startTool(steps, {
      id: "call_9",
      tool: "write",
      label: "Write",
      args: { path: "fit.py" },
    });
    expect(steps).toHaveLength(1);
    expect(tool(steps)).toMatchObject({
      status: "running",
      id: "call_9",
      args: { path: "fit.py" },
    });
    // A draft with a real id that differs is a different call.
    const other = startTool(
      startDraft([], { index: 0, id: "call_1", tool: "bash", label: "Bash" }),
      {
        id: "call_2",
        tool: "bash",
        label: "Bash",
      },
    );
    expect(other).toHaveLength(2);
  });

  it("persists an abandoned draft as cancelled with its arguments and keeps an output's tail", () => {
    let steps: TraceStep[] = startDraft([], { index: 0, id: "c1", tool: "bash", label: "Bash" });
    steps = appendArgsDelta(steps, { index: 0, path: ["command"], delta: "python fit.py" });
    steps = [
      ...steps,
      ...endTool(
        startTool([], { id: "c2", tool: "bash", label: "Bash", args: { command: "ls" } }),
        {
          id: "c2",
          tool: "bash",
          output: `${"x".repeat(3000)}END`,
        },
      ),
      { kind: "text", text: "done" },
    ];
    const trace = toPersistedTrace({ steps, startedAt: 0 }, 10);
    expect(trace?.steps).toHaveLength(2);
    expect(trace?.steps[0]).toMatchObject({
      status: "cancelled",
      args: { command: "python fit.py" },
    });
    expect(trace?.steps[0]).not.toHaveProperty("draft");
    const output = tool(trace!.steps, 1).output!;
    expect(output.length).toBe(2001);
    expect(output.endsWith("END")).toBe(true);
  });

  it("keeps finished UI blocks when the user stops, before the partial text", () => {
    const ui = { version: 1, spec: { root: "m", elements: {} }, fallback: "- T1: 42" };
    let turn: LiveTurn = { steps: [], startedAt: 0 };
    turn = appendLiveBlock(turn, { type: "ui", content: "- T1: 42", chart: null, ui });
    turn = appendLiveBlock(turn, { type: "text", content: "fallback only", chart: null });
    // Anything else the stream might carry is ignored.
    turn = appendLiveBlock(turn, null);
    turn = appendLiveBlock(turn, { type: "ui" });
    turn = appendLiveBlock(turn, { type: "chart", chart: {} });
    turn = { ...turn, steps: appendDelta(turn.steps, "text", "T1 is") };

    expect(stoppedBlocks(turn)).toEqual([
      { type: "ui", content: "- T1: 42", chart: null, ui },
      { type: "text", content: "fallback only", chart: null },
      { type: "text", content: "T1 is", chart: null },
    ]);
    expect(stoppedBlocks({ steps: [], startedAt: 0 })).toEqual([]);
  });

  it("stores finished writes in full within a shared budget, and marks interrupted calls", () => {
    const finished = (id: string, path: string, content: string) =>
      endTool(startTool([], { id, tool: "write", label: "Write", args: { path, content } }), {
        id,
        tool: "write",
        output: "ok",
      });
    const large = "x".repeat(40_000);
    const steps: TraceStep[] = [
      ...finished("w1", "a.txt", large),
      // Does not fit in what the first write left.
      ...finished("w2", "b.txt", large),
      ...finished("w3", "small.txt", "tiny"),
      ...endTool(
        startTool([], {
          id: "w4",
          tool: "write",
          label: "Write",
          args: { path: "e", content: large },
        }),
        { id: "w4", tool: "write", is_error: true },
      ),
      ...startTool([], { id: "b1", tool: "bash", label: "Bash", args: { command: large } }),
      ...startTool([], {
        id: "w5",
        tool: "write",
        label: "Write",
        args: { path: "r", content: "x" },
      }),
      { kind: "text", text: "stopped" },
    ];
    const trace = toPersistedTrace({ steps, startedAt: 0 }, 10)!;
    const stored = JSON.parse(JSON.stringify(trace)) as typeof trace;

    expect(tool(stored.steps, 0).args).toEqual({ path: "a.txt", content: large });
    expect(typeof tool(stored.steps, 1).args).toBe("string");
    expect((tool(stored.steps, 1).args as string).length).toBe(4001);
    expect(tool(stored.steps, 2).args).toEqual({ path: "small.txt", content: "tiny" });
    expect(tool(stored.steps, 3)).toMatchObject({ status: "error" });
    expect(typeof tool(stored.steps, 3).args).toBe("string");
    // Calls still running when the turn ended are stored done, marked interrupted.
    expect(tool(stored.steps, 4)).toMatchObject({ status: "done", interrupted: true });
    expect(typeof tool(stored.steps, 4).args).toBe("string");
    expect(tool(stored.steps, 5)).toMatchObject({
      status: "done",
      interrupted: true,
      args: { path: "r", content: "x" },
    });
    expect(tool(stored.steps, 0)).not.toHaveProperty("interrupted");
    // A stored trace stored again keeps the mark and the full write.
    const again = toPersistedTrace(
      { steps: [...stored.steps, { kind: "text", text: "" }], startedAt: 0 },
      20,
    )!;
    expect(tool(again.steps, 0).args).toEqual({ path: "a.txt", content: large });
    expect(tool(again.steps, 5).interrupted).toBe(true);
  });

  it("keeps a failed turn's progress updates in its trace, apart from the answer so far", () => {
    let turn: LiveTurn = { steps: [], startedAt: 0 };
    turn = { ...turn, steps: appendDelta(turn.steps, "text", "Checking the latest T1 results.") };
    turn = { ...turn, steps: startTool(turn.steps, { id: "c1", tool: "qdash_get_task_results" }) };
    turn = { ...turn, steps: endTool(turn.steps, { id: "c1", tool: "qdash_get_task_results" }) };
    turn = { ...turn, steps: appendDelta(turn.steps, "thinking", "compare Q3") };
    turn = { ...turn, steps: appendDelta(turn.steps, "text", "Q3 looks low; comparing") };

    const payload = failedTurnPayload(turn, 5_000)!;
    expect(payload.interrupted).toBe(true);
    expect(payload.stopped).toBeUndefined();
    // The update before the tool is work; thinking stays its own step; the tail is the answer so far.
    expect(payload.trace?.steps.map((s) => s.kind)).toEqual(["text", "tool", "thinking"]);
    expect(payload.trace?.steps[0]).toEqual({
      kind: "text",
      text: "Checking the latest T1 results.",
    });
    expect(payload.blocks).toEqual([
      { type: "text", content: "Q3 looks low; comparing", chart: null },
    ]);
    // Same key order as the server's copy, so both serialize alike.
    expect(Object.keys(payload)).toEqual(["blocks", "assessment", "interrupted", "trace"]);

    expect(failedTurnPayload({ steps: [], startedAt: 0 }, 1)).toBeNull();
  });
});
