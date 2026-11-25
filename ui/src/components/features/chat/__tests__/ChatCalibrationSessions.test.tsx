import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatCalibrationSessions } from "@/components/features/chat/ChatCalibrationSessions";
import { linkedCalibrationSessions } from "@/lib/chatCalibrationSession";
import type { ChatMessage } from "@/types/agentChat";

const state = vi.hoisted(() => ({
  sessions: {} as Record<string, Record<string, unknown>>,
  requests: [] as Array<{ id: string; project: unknown }>,
}));

vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => ({ projectId: "p1" }) }));
vi.mock("@/client/calibration-session/calibration-session", () => ({
  getGetCalibrationSessionQueryKey: (id: string) => [`/calibration-sessions/${id}`],
  useGetCalibrationSession: (
    id: string,
    options: { request?: { headers: Record<string, string> } },
  ) => {
    state.requests.push({ id, project: options.request?.headers["X-Project-Id"] });
    const data = state.sessions[id];
    return { data: data ? { data } : undefined, isError: !data };
  },
}));

afterEach(cleanup);
beforeEach(() => {
  state.requests = [];
  state.sessions = {
    "cs-1": {
      calibration_session_id: "cs-1",
      objective: "Bring up qubits 0 and 1",
      status: "open",
      pipeline_runs: [{ run_id: "cpr-1" }, { run_id: "cpr-2" }],
      pipeline_run_total: 2,
      agent_sessions: [{ session_id: "as-1" }],
      agent_session_total: 1,
      close_blockers: ["pipeline run cpr-2 is running"],
    },
    "cs-2": {
      calibration_session_id: "cs-2",
      objective: "Two-qubit gates on 0-1",
      status: "closed",
      pipeline_runs: [],
      agent_sessions: [],
      close_blockers: [],
    },
  };
});

describe("the calibration sessions shown in a chat", () => {
  it("reads each named session from QDash and links to its page, the latest first", () => {
    render(<ChatCalibrationSessions calibrationSessionIds={["cs-2", "cs-1", "cs-missing"]} />);
    expect(state.requests.every((request) => request.project === "p1")).toBe(true);
    const rows = screen.getAllByTestId("chat-calibration-session");
    // The ID QDash does not know shows nothing.
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Bring up qubits 0 and 1");
    expect(rows[0].textContent).toContain("2 runs · 1 agent session · 1 running or waiting");
    expect(rows[1].textContent).toContain("Closed");
    const links = screen.getAllByRole("link", { name: "Open" });
    expect(links[0].getAttribute("href")).toBe("/calibration-sessions/cs-1?project=p1");
  });

  it("shows a session a restored chat created, from the saved create call alone", () => {
    state.sessions["cs-new"] = {
      calibration_session_id: "cs-new",
      objective: "Recalibrate qubit 3",
      status: "open",
      pipeline_runs: [],
      pipeline_run_total: 0,
      agent_sessions: [],
      agent_session_total: 0,
      close_blockers: [],
    };
    const saved: ChatMessage[] = [
      {
        role: "assistant",
        content: JSON.stringify({
          blocks: [],
          assessment: null,
          trace: {
            durationMs: 1,
            steps: [
              {
                kind: "tool",
                id: "s1",
                tool: "qdash_create_calibration_session",
                label: "Create",
                status: "done",
                startedAt: 0,
                args: { objective: "Recalibrate qubit 3" },
                calibrationSession: { calibrationSessionId: "cs-new", chipId: "64Qv3" },
              },
            ],
          },
        }),
      },
    ];
    render(<ChatCalibrationSessions calibrationSessionIds={linkedCalibrationSessions(saved)} />);
    const [row] = screen.getAllByTestId("chat-calibration-session");
    expect(row.textContent).toContain("Recalibrate qubit 3");
    expect(state.requests.map((request) => request.id)).toEqual(["cs-new"]);
  });

  it("counts every child from the totals, beyond the listed page", () => {
    state.sessions["cs-1"] = {
      ...state.sessions["cs-1"],
      pipeline_run_total: 140,
    };
    render(<ChatCalibrationSessions calibrationSessionIds={["cs-1"]} />);
    expect(screen.getByTestId("chat-calibration-session").textContent).toContain("140 runs");
  });

  it("shows nothing without a named session", () => {
    const { container } = render(<ChatCalibrationSessions calibrationSessionIds={[]} />);
    expect(container.innerHTML).toBe("");
  });
});
