import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { TraceStep, TurnConnection } from "@/types/agentChat";

import { QUIET_AFTER_MS, TurnActivity, connectionNote, currentActivity } from "../ChatTrace";

afterEach(cleanup);

type ToolStep = Extract<TraceStep, { kind: "tool" }>;

function waitStep(status: ToolStep["status"]): ToolStep {
  return {
    kind: "tool",
    id: "w1",
    tool: "qdash_wait_agent_intervention",
    label: "Wait agent intervention",
    status,
    startedAt: 0,
  };
}

function live(silentMs: number, state: TurnConnection["state"] = "live"): TurnConnection {
  return { state, lastUpdateAt: Date.now() - silentMs, attempt: state === "live" ? 0 : 1 };
}

describe("waiting tool titles", () => {
  it("say what the turn waits for while it waits, and what happened once it ends", () => {
    expect(currentActivity([waitStep("running")], null)).toBe("Waiting for the expert's answer");
    expect(
      currentActivity([{ ...waitStep("running"), tool: "qdash_wait_agent_action" }], null),
    ).toBe("Waiting for the calibration step to finish");
    expect(currentActivity([{ ...waitStep("running"), tool: "qdash_wait_execution" }], null)).toBe(
      "Waiting for the execution to finish",
    );
  });
});

describe("connection note", () => {
  it("says nothing while updates arrive, and when the last one came once the turn is quiet", () => {
    const now = Date.now();
    expect(connectionNote(null, now)).toBeNull();
    expect(connectionNote(live(QUIET_AFTER_MS - 1000), now)).toBeNull();
    expect(connectionNote(live(95_000), now)).toEqual({
      lost: false,
      text: "Connected · last update 1m 35s ago",
    });
  });

  it("says the connection is lost whatever the silence", () => {
    expect(connectionNote(live(2000, "reconnecting"), Date.now())).toEqual({
      lost: true,
      text: "Connection lost, reconnecting · last update 2s ago",
    });
  });
});

describe("TurnActivity with a connection", () => {
  it("names a busy turn's activity beside its mark, with no note while updates arrive", () => {
    render(
      <TurnActivity
        steps={[waitStep("running")]}
        startedAt={Date.now()}
        statusMessage={null}
        connection={live(1000)}
      />,
    );
    expect(screen.getByRole("status")).not.toHaveClass("sr-only");
    expect(screen.getByTestId("turn-activity")).toHaveAttribute("data-mode", "waiting");
    expect(screen.queryByTestId("turn-connection")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Waiting for the expert's answer");
  });

  it("shows how long a long expert wait has been quiet, on a connection that is fine", () => {
    render(
      <TurnActivity
        steps={[waitStep("running")]}
        startedAt={Date.now() - 600_000}
        statusMessage={null}
        connection={live(240_000)}
      />,
    );
    const note = screen.getByTestId("turn-connection");
    expect(note.textContent).toBe("Connected · last update 4m 0s ago");
    expect(note.dataset.state).toBe("live");
    expect(note.className).not.toMatch(/text-warning/);
    // The activity stays named beside the mark; the quiet time replaces the turn's timer.
    expect(screen.getByRole("status").textContent).toBe("Waiting for the expert's answer");
    expect(screen.getAllByTestId("activity-logo")).toHaveLength(1);
  });

  it("shows a lost connection instead of the last activity, which is no longer known", () => {
    render(
      <TurnActivity
        steps={[]}
        startedAt={Date.now() - 600_000}
        statusMessage="AI is thinking..."
        connection={live(70_000, "reconnecting")}
      />,
    );
    const note = screen.getByTestId("turn-connection");
    expect(note.textContent).toBe("Connection lost, reconnecting · last update 1m 10s ago");
    expect(note.className).toMatch(/text-warning/);
    expect(screen.getByRole("status").textContent).toBe("Connection lost, reconnecting");
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.queryByText("AI is thinking...")).toBeNull();
    expect(screen.queryByTestId("activity-logo")).toBeNull();
  });
});
