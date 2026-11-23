import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CalibrationSessionAuditTimeline } from "@/components/features/calibration-session/CalibrationSessionAuditTimeline";

const calls = vi.hoisted(() => [] as Array<{ id: string; params: unknown; project: unknown }>);

vi.mock("@/client/calibration-session/calibration-session", () => ({
  getGetCalibrationSessionAuditQueryKey: (id: string) => [`/calibration-sessions/${id}/audit`],
  exportCalibrationSessionAudit: vi.fn(),
  getCalibrationSessionAudit: async (
    id: string,
    params: unknown,
    request: { headers: Record<string, string> },
  ) => {
    calls.push({ id, params, project: request.headers["X-Project-Id"] });
    return {
      data: {
        schema_version: "qdash.calibration-session-audit.v1",
        snapshot_id: "snap",
        generated_at: "2026-11-23T01:00:00Z",
        total_events: 3,
        complete: true,
        next_cursor: null,
        calibration_session: { calibration_session_id: id },
        notes: [],
        events: [
          {
            event_id: "decision:cd-1",
            sequence: 0,
            at: "2026-11-23T00:00:00Z",
            state_version: 0,
            kind: "decision",
            summary:
              "Proposed screening of c03 on 0-1: CheckCrossResonance.adiabatic_safe_factor=0.8",
            actor: "alice",
            actor_kind: "unknown",
            provenance: "client_reported",
            missing: ["assessment", "model"],
            data: {
              interpretation: "The factor binds.",
              experiment: {
                stage: "screening",
                candidate_id: "c03",
                target: "0-1",
                requested_changes: [
                  {
                    task_name: "CheckCrossResonance",
                    parameter: "adiabatic_safe_factor",
                    value: 0.8,
                  },
                ],
              },
            },
          },
          {
            event_id: "pipeline_requested:cpr-1",
            sequence: 1,
            at: "2026-11-23T00:01:00Z",
            state_version: 0,
            kind: "pipeline_requested",
            summary: "alice requested pipeline 'zx90' for decision cd-1",
            actor: "alice",
            actor_kind: "agent",
            provenance: "server_record",
            missing: ["host_approval"],
            data: {
              requested_task_calls: [
                {
                  call_id: "cr_c03",
                  task_name: "CheckCrossResonance",
                  run: { adiabatic_safe_factor: 0.8 },
                },
              ],
            },
          },
          {
            event_id: "agent_session:ses-123456789:session_created:ses-123456789",
            sequence: 2,
            at: "2026-11-23T00:02:00Z",
            state_version: 0,
            kind: "session_created",
            summary: "alice approved a session",
            actor: "alice",
            actor_kind: "human",
            provenance: "server_record",
            agent_session_id: "ses-123456789",
            missing: [],
            data: {},
          },
        ],
      },
    };
  },
}));
vi.mock("@/components/features/agent-session/useLinkedProject", () => ({
  projectRequest: (projectId: string) => ({ headers: { "X-Project-Id": projectId } }),
}));

afterEach(cleanup);

describe("CalibrationSessionAuditTimeline", () => {
  it("shows the shared timeline with statements, unrecorded facts, and agent session events", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <CalibrationSessionAuditTimeline calibrationSessionId="cs-1" projectId="lab-a" />
      </QueryClientProvider>,
    );
    // A decision without a reported model is not called an agent's.
    expect(await screen.findByText("Decision")).toBeTruthy();
    expect(screen.getByText("Client statement")).toBeTruthy();
    expect(screen.getByText("Interpretation (client)")).toBeTruthy();
    expect(
      screen.getByText(/screening c03 on 0-1: CheckCrossResonance.adiabatic_safe_factor = 0.8/),
    ).toBeTruthy();
    expect(screen.getByText("Pipeline requested")).toBeTruthy();
    expect(screen.getByText("cr_c03: adiabatic_safe_factor 0.8")).toBeTruthy();
    expect(screen.getByText("Not recorded: host_approval")).toBeTruthy();
    expect(screen.getByText("Agent session ses-1234")).toBeTruthy();
    // The agent session's own creation keeps its label inside the calibration session's audit.
    expect(screen.getByText("Session approved")).toBeTruthy();
    expect(calls[0]).toEqual({ id: "cs-1", params: { limit: 50 }, project: "lab-a" });
  });
});
