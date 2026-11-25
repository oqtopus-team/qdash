import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentAuditEvent } from "@/schemas";

import {
  AuditTimeline,
  auditKindLabel,
  auditProvenanceLabel,
  gateOutcomeLabel,
  type AuditPageLike,
  type AuditScope,
} from "../AuditTimeline";

function event(sequence: number, fields: Partial<AgentAuditEvent>): AgentAuditEvent {
  return {
    event_id: `e-${sequence}`,
    sequence,
    at: `2026-11-23T00:0${sequence}:00Z`,
    state_version: 0,
    kind: "decision",
    summary: `event ${sequence}`,
    provenance: "server_record",
    missing: [],
    data: {},
    ...fields,
  };
}

function page(events: AgentAuditEvent[], next: string | null): AuditPageLike {
  return {
    snapshot_id: "snap-1",
    events,
    total_events: 3,
    complete: next === null,
    next_cursor: next,
    generated_at: "2026-11-23T01:00:00Z",
  };
}

const FIRST = [
  event(0, { kind: "session_created", summary: "cs-1 opened by alice" }),
  event(1, {
    kind: "intervention_opened",
    summary: "The agent asked an expert",
    agent_session_id: "ses-123456789",
    intervention_id: "int-1",
    data: { question: "Which amplitude?" },
  }),
];
const SECOND = [event(2, { kind: "session_closed", summary: "alice closed cs-1" })];

function setup(scope?: AuditScope) {
  const cursors: (string | null)[] = [];
  const fetchPage = vi.fn(async (cursor: string | null) => {
    cursors.push(cursor);
    return cursor ? page(SECOND, null) : page(FIRST, "snap-1:2");
  });
  const exportAll = vi.fn(async () => page([...FIRST, ...SECOND], null));
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AuditTimeline
        scope={scope}
        title="Audit"
        description="Shared timeline"
        header={(first) => <p>Header of {first?.snapshot_id ?? "nothing"}</p>}
        source={{
          queryKey: ["audit-test", scope ?? "default"],
          fetchPage,
          exportAll,
          filename: "cs-1-audit.json",
          sessionId: "cs-1",
        }}
      />
    </QueryClientProvider>,
  );
  return { cursors, fetchPage, exportAll };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AuditTimeline", () => {
  it("renders the caller's title, header, and pages read through its source", async () => {
    const { cursors } = setup("calibration_session");
    expect(await screen.findByText("cs-1 opened by alice")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Audit" })).toBeTruthy();
    expect(screen.getByText("Shared timeline")).toBeTruthy();
    expect(screen.getByText("Header of snap-1")).toBeTruthy();
    // A calibration session's own creation is not called an approval.
    expect(screen.getByText("Session opened")).toBeTruthy();
    expect(screen.getByText("Showing 2 of 3 events", { exact: false })).toBeTruthy();
    // An agent session's event links to that agent session, not to the calibration session.
    expect(screen.getByRole("link", { name: "Intervention" }).getAttribute("href")).toBe(
      "/agent-sessions/ses-123456789/interventions/int-1",
    );
    expect(screen.getByText("Agent session ses-1234")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("alice closed cs-1")).toBeTruthy();
    expect(screen.getByText("End of the timeline")).toBeTruthy();
    expect(cursors).toEqual([null, "snap-1:2"]);
  });

  it("keeps the agent session label for a session's creation by default", async () => {
    setup();
    expect(await screen.findByText("Session approved")).toBeTruthy();
  });

  it("exports the source's whole audit under the caller's file name", async () => {
    const createObjectURL = vi.fn((_blob: Blob) => "blob:audit");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    let downloaded = "";
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloaded = this.download;
    });
    const { exportAll } = setup("calibration_session");
    fireEvent.click(await screen.findByRole("button", { name: "Export JSON" }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(exportAll).toHaveBeenCalledTimes(1);
    expect(downloaded).toBe("cs-1-audit.json");
    const body = JSON.parse(await createObjectURL.mock.calls[0]![0].text());
    expect(body.events).toHaveLength(3);
    click.mockRestore();
  });
});

describe("AuditTimeline event disclosure", () => {
  function renderEvents(events: AgentAuditEvent[]) {
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <AuditTimeline
          title="Audit"
          source={{
            queryKey: ["audit-disclosure", events[0]!.event_id],
            fetchPage: async () => ({ ...page(events, null), total_events: events.length }),
            exportAll: async () => page(events, null),
            filename: "audit.json",
            sessionId: "ses-1",
          }}
        />
      </QueryClientProvider>,
    );
  }

  it("keeps summary, source, warnings, and links visible and folds payload and metadata", async () => {
    renderEvents([
      event(0, {
        kind: "measurement",
        summary: "CheckRabi on Q00: completed",
        provenance: "server_record",
        actor: "alice",
        execution_id: "exec-1",
        task_id: "task-1",
        status: "completed",
        status_is_current: true,
        missing: ["decision"],
        data: {
          outputs: { control_amplitude: { value: 0.05, unit: "a.u." } },
          gate: [
            { parameter_name: "control_amplitude", accepted: false, rejection: "quality_gate" },
            { parameter_name: "t1", accepted: false, rejection: "not_in_scope" },
          ],
        },
      }),
    ]);
    expect(await screen.findByText("CheckRabi on Q00: completed")).toBeTruthy();
    // Source, live status, failed gates, unrecorded facts, and navigation stay in view.
    expect(screen.getByText("QDash record").closest("details")).toBeNull();
    expect(screen.getByText("now completed").closest("details")).toBeNull();
    // An out-of-scope output is reference only and is not counted as a failed check.
    expect(screen.getByText("1 gate check failed").closest("details")).toBeNull();
    expect(screen.getByText("Not recorded: decision").closest("details")).toBeNull();
    expect(screen.getByRole("link", { name: "Execution" }).closest("details")).toBeNull();
    expect(screen.getByRole("link", { name: "Result and figures" }).closest("details")).toBeNull();

    // Who recorded it and the payload sit in a closed per-event disclosure named for the event.
    const details = screen.getByTestId("audit-event-details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    const summary = details.querySelector("summary")!;
    expect(summary.textContent).toMatch(/^Details: Measurement, /);
    expect(screen.getByText("alice").closest("details")).toBe(details);
    expect(screen.getByText("control_amplitude 0.05 a.u.").closest("details")).toBe(details);
    expect(
      screen
        .getByText(
          "control_amplitude rejected: quality gate, t1 not in session scope (reference only)",
        )
        .closest("details"),
    ).toBe(details);
    fireEvent.click(summary);
    expect(details.open).toBe(true);
  });

  it("marks a superseded decision and renders no disclosure for an event with nothing more", async () => {
    renderEvents([
      event(0, {
        summary: "Assessed pass",
        data: { interpretation: "Passes", superseded_by_decision_id: "cd-2" },
      }),
      event(1, { kind: "session_closed", summary: "alice closed cs-1" }),
    ]);
    expect(await screen.findByText("Superseded")).toBeTruthy();
    expect(screen.getByText("cd-2").closest("details")).toBeTruthy();
    expect(screen.getAllByTestId("audit-event-details")).toHaveLength(1);
  });
});

describe("audit labels", () => {
  it("names kinds and sources in plain words", () => {
    expect(auditKindLabel("intervention_response")).toBe("Expert answered");
    expect(auditProvenanceLabel("server_record")).toBe("QDash record");
    expect(auditKindLabel("future_kind")).toBe("future_kind");
    expect(auditKindLabel("decision", "client_reported")).toBe("Decision");
    expect(auditKindLabel("session_created", "server_record", "calibration_session")).toBe(
      "Session opened",
    );
    expect(auditKindLabel("session_created", "server_record", "calibration_session", "ses-1")).toBe(
      "Session approved",
    );
  });

  it("tells an out-of-scope output apart from a failed gate", () => {
    expect(gateOutcomeLabel({ accepted: true, rejection: null })).toBe("accepted");
    expect(gateOutcomeLabel({ accepted: false, rejection: "not_in_scope" })).toBe(
      "not in session scope (reference only)",
    );
    expect(gateOutcomeLabel({ accepted: false, rejection: "outside_bounds" })).toBe(
      "rejected: outside bounds",
    );
    expect(gateOutcomeLabel({ accepted: false, rejection: "quality_gate" })).toBe(
      "rejected: quality gate",
    );
    // An audit recorded before the code existed keeps its plain wording.
    expect(gateOutcomeLabel({ accepted: false })).toBe("rejected");
  });
});
