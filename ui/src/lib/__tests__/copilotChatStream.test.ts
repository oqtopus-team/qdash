import { describe, expect, it } from "vitest";

import {
  appendArgsDelta,
  endTool,
  startDraft,
  startTool,
  toPersistedTrace,
} from "@/lib/copilotChatStream";
import type { TraceStep } from "@/types/copilotChat";

function tool(steps: TraceStep[], i = steps.length - 1) {
  const step = steps[i];
  if (step.kind !== "tool") throw new Error("not a tool step");
  return step;
}

describe("copilotChatStream", () => {
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
});
