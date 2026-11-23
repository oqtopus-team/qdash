import { describe, expect, it } from "vitest";

import { endTool, startTool, toPersistedTrace } from "@/lib/copilotChatStream";
import {
  calibrationSessionHref,
  dispatchStatusStyle,
  linkedCalibrationSessions,
} from "@/lib/chatCalibrationSession";
import type { ChatMessage, TraceStep } from "@/types/copilotChat";

const tool = (
  name: string,
  status: "done" | "running" | "error" | "drafting",
  calibrationSessionId: unknown,
): TraceStep => ({
  kind: "tool",
  id: `${name}-${String(calibrationSessionId)}`,
  tool: name,
  label: name,
  status,
  startedAt: 0,
  args: { calibrationSessionId },
});

const answer = (steps: TraceStep[]): ChatMessage => ({
  role: "assistant",
  content: JSON.stringify({ blocks: [], assessment: null, trace: { steps, durationMs: 1 } }),
});

describe("the calibration sessions a chat's work belongs to", () => {
  it("come from calls that name one, never from text, failed calls, or other tools", () => {
    const messages: ChatMessage[] = [
      { role: "user", content: "Continue cs-from-text" },
      answer([
        tool("qdash_get_calibration_session", "done", "cs-1"),
        tool("qdash_run_pipeline", "error", "cs-failed"),
        tool("qdash_list_calibration_sessions", "done", "cs-list"),
        tool("qdash_create_agent_session", "drafting", "cs-draft"),
        tool("qdash_run_pipeline", "done", undefined),
      ]),
      { role: "assistant", content: "Recorded in cs-prose" },
    ];
    expect(linkedCalibrationSessions(messages)).toEqual(["cs-1"]);
  });

  it("keeps several objectives of one chat, the latest named last", () => {
    const messages = [
      answer([
        tool("qdash_get_calibration_session", "done", "cs-1"),
        tool("qdash_run_pipeline", "done", "cs-2"),
      ]),
    ];
    expect(
      linkedCalibrationSessions(messages, [tool("qdash_create_agent_session", "running", "cs-1")]),
    ).toEqual(["cs-2", "cs-1"]);
    expect(
      linkedCalibrationSessions([answer([tool("qdash_run_pipeline", "done", "../x")])]),
    ).toEqual([]);
  });

  it("finds a newly created session from the create call's typed result, live and restored", () => {
    const create = "qdash_create_calibration_session";
    // The live turn: the call runs, then QDash answers through the tool_end event.
    let steps = startTool([], {
      id: "s1",
      tool: create,
      label: "Create",
      args: { objective: "Bring up qubits 0 and 1", calibrationSessionId: "cs-from-args" },
    });
    // Running: nothing is created yet, and the model's arguments never name it.
    expect(linkedCalibrationSessions([], steps)).toEqual([]);
    steps = endTool(steps, {
      id: "s1",
      tool: create,
      calibration_session: { calibration_session_id: "cs-new", chip_id: "64Qv3" },
    });
    expect(linkedCalibrationSessions([], steps)).toEqual(["cs-new"]);

    // The stored answer, as a reopened chat reads it from the saved conversation.
    const trace = toPersistedTrace(
      { steps: [...steps, { kind: "text", text: "Created." }], startedAt: 0 },
      5,
    );
    const restored: ChatMessage[] = [
      { role: "user", content: "Bring up qubits 0 and 1" },
      {
        role: "assistant",
        content: JSON.stringify({ blocks: [], assessment: null, trace }),
      },
    ];
    expect(linkedCalibrationSessions(JSON.parse(JSON.stringify(restored)))).toEqual(["cs-new"]);
  });

  it("never shows a create call that failed, was cancelled, or has no typed result", () => {
    const created = (status: "done" | "error" | "cancelled" | "running"): TraceStep => ({
      kind: "tool",
      id: `c-${status}`,
      tool: "qdash_create_calibration_session",
      label: "Create",
      status,
      startedAt: 0,
      args: { calibrationSessionId: `cs-args-${status}` },
      calibrationSession: { calibrationSessionId: `cs-${status}` },
    });
    const untyped: TraceStep = {
      kind: "tool",
      id: "c-untyped",
      tool: "qdash_create_calibration_session",
      label: "Create",
      status: "done",
      startedAt: 0,
      args: { calibrationSessionId: "cs-args-untyped" },
    };
    const messages = [
      answer([created("error"), created("cancelled"), created("running"), untyped]),
      { role: "assistant" as const, content: "Created calibration session cs-prose." },
    ];
    expect(linkedCalibrationSessions(messages)).toEqual([]);
    expect(linkedCalibrationSessions(messages, [created("done")])).toEqual(["cs-done"]);
  });

  it("links to the session page in its project and names launch states", () => {
    expect(calibrationSessionHref("cs-1", "lab a")).toBe(
      "/calibration-sessions/cs-1?project=lab%20a",
    );
    expect(calibrationSessionHref("cs-1")).toBe("/calibration-sessions/cs-1");
    expect(dispatchStatusStyle("unknown")).toEqual({
      label: "Start unknown",
      badge: "badge-warning",
    });
    expect(dispatchStatusStyle("other").label).toBe("other");
  });

  it("finds a session named by the audit and decision tools", () => {
    const messages = [
      answer([
        tool("qdash_record_calibration_decision", "done", "cs-audit"),
        tool("qdash_get_calibration_session_audit", "done", "cs-read"),
      ]),
    ];
    expect(linkedCalibrationSessions(messages, [])).toEqual(["cs-audit", "cs-read"]);
  });
});
