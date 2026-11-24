import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatStatusLine, chatStatus } from "@/components/features/chat/ChatTurnStatus";
import type { SessionRun } from "@/contexts/AgentChatSessionContext";
import type { ChatMessage } from "@/types/agentChat";

const NOW = 1_800_000_000_000;

const run = (over: Partial<SessionRun> = {}): SessionRun => ({
  turn: {
    startedAt: NOW - 600_000,
    steps: [
      {
        kind: "tool",
        id: "w1",
        tool: "qdash_wait_agent_intervention",
        label: "Wait",
        status: "running",
        startedAt: NOW - 500_000,
      },
    ],
  },
  statusMessage: null,
  connection: { state: "live", lastUpdateAt: NOW - 300_000, attempt: 0 },
  ...over,
});

const assistant = (payload: unknown): ChatMessage => ({
  role: "assistant",
  content: typeof payload === "string" ? payload : JSON.stringify(payload),
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("the chat's status", () => {
  it("comes from the live turn: its waiting tool, or its lost connection", () => {
    expect(chatStatus({ run: run(), messages: [] })).toMatchObject({
      kind: "waiting_expert",
      label: "Waiting for the expert's answer",
    });
    expect(
      chatStatus({
        run: run({
          connection: { state: "reconnecting", lastUpdateAt: NOW, attempt: 2 },
        }),
        messages: [],
      }),
    ).toMatchObject({ kind: "reconnecting" });
  });

  it("marks what it last knew of an unwatched turn as stale", () => {
    const status = chatStatus({
      detached: {
        reason: "other_project",
        requestId: "r1",
        projectId: "p1",
        startedAt: NOW - 900_000,
        activity: { tool: "qdash_wait_agent_intervention", label: "Wait" },
        lastUpdateAt: NOW - 120_000,
      },
      messages: [],
    });
    expect(status).toMatchObject({
      kind: "other_project",
      stale: true,
      lastActivity: "Waiting for the expert's answer",
    });
  });

  it("says how the last answer ended when no turn runs", () => {
    const blocks = (type: string) => ({
      blocks: [{ type, content: "x" }],
      assessment: null,
    });
    expect(chatStatus({ messages: [assistant(blocks("text"))] })?.kind).toBe("answered");
    expect(chatStatus({ messages: [assistant(blocks("approval"))] })?.kind).toBe("approval");
    expect(chatStatus({ messages: [assistant(blocks("ask"))] })?.kind).toBe("question");
    expect(
      chatStatus({
        messages: [assistant({ ...blocks("text"), stopped: true })],
      })?.kind,
    ).toBe("stopped");
    expect(
      chatStatus({
        messages: [assistant({ ...blocks("text"), interrupted: true })],
      }),
    ).toMatchObject({ kind: "interrupted", label: "Interrupted" });
    expect(chatStatus({ messages: [assistant("Error: down")] })?.kind).toBe("failed");
    expect(chatStatus({ messages: [{ role: "user", content: "hi" }] })).toBeNull();
  });
});

describe("ChatStatusLine during a live turn", () => {
  const tool = (name: string) => ({
    turn: {
      startedAt: NOW - 1000,
      steps: [
        {
          kind: "tool" as const,
          id: "t",
          tool: name,
          label: "Bash",
          status: "running" as const,
          startedAt: NOW - 1000,
        },
      ],
    },
  });

  it("leaves what the streaming turn does to its footer: no dot, label or live region", () => {
    const statuses = [
      chatStatus({ run: run(tool("bash")), messages: [] }),
      chatStatus({ run: run(), messages: [] }),
      chatStatus({ run: run(tool("qdash_wait_execution")), messages: [] }),
    ];
    expect(statuses.map((s) => s?.kind)).toEqual([
      "working",
      "waiting_expert",
      "waiting_execution",
    ]);
    for (const status of statuses) {
      const { container } = render(<ChatStatusLine status={status} />);
      expect(container.innerHTML).toBe("");
      expect(screen.queryByRole("status")).toBeNull();
      cleanup();
    }
  });
});

describe("ChatStatusLine for a turn no footer follows", () => {
  it("calls a stale turn's time the last known update", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(NOW);
    render(
      <ChatStatusLine
        status={chatStatus({
          detached: {
            reason: "restoring",
            requestId: "r1",
            projectId: "p1",
            startedAt: NOW - 60_000,
            activity: null,
            lastUpdateAt: NOW - 10_000,
          },
          messages: [],
        })}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Reconnecting to the running answer");
    expect(screen.getByTestId("chat-status")).toHaveTextContent("last known update 10s ago");
  });
});

describe("ChatStatusLine waiting on the user", () => {
  const blocks = (type: string) => ({ blocks: [{ type, content: "x" }], assessment: null });
  const mark = () => screen.queryByTestId("activity-logo");
  const dot = () => screen.getByTestId("chat-status").querySelector(".status");

  it.each([
    ["approval", "Waiting for your approval"],
    ["ask", "Waiting for your answer"],
  ])("shows the waiting mark in place of the dot for a %s", (type, label) => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    render(<ChatStatusLine status={chatStatus({ messages: [assistant(blocks(type))] })} />);
    expect(mark()).toHaveAttribute("data-mode", "waiting");
    expect(dot()).toBeNull();
    expect(screen.getByRole("status").textContent).toBe(label);
    vi.restoreAllMocks();
  });

  it("keeps the dot for a lost connection and a failure", () => {
    const statuses = [
      chatStatus({
        run: run({ connection: { state: "reconnecting", lastUpdateAt: NOW, attempt: 1 } }),
        messages: [],
      }),
      chatStatus({ messages: [{ role: "assistant", content: "Error: boom" } as ChatMessage] }),
    ];
    expect(statuses.map((s) => s?.kind)).toEqual(["reconnecting", "failed"]);
    for (const status of statuses) {
      render(<ChatStatusLine status={status} />);
      expect(mark()).toBeNull();
      expect(dot()).not.toBeNull();
      cleanup();
    }
  });
});
