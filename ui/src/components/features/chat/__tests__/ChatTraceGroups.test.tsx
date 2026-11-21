import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { endTool, startTool } from "@/lib/copilotChatStream";

import type { TraceStep } from "@/types/copilotChat";

import { ChatTraceSummary, LiveTrace, groupTraceSteps } from "../ChatTrace";

const useGetExecution = vi.fn();
vi.mock("@/client/execution/execution", () => ({
  useGetExecution: (...args: unknown[]) => useGetExecution(...args),
}));

afterEach(() => {
  cleanup();
  useGetExecution.mockReset();
});

type ToolStep = Extract<TraceStep, { kind: "tool" }>;

function tool(overrides: Partial<ToolStep>): ToolStep {
  return {
    kind: "tool",
    id: "t1",
    tool: "qdash_get_figure",
    label: "Get figure",
    status: "done",
    startedAt: 0,
    endedAt: 1000,
    ...overrides,
  };
}

const bash = (id: string, command: string): Parameters<typeof startTool>[1] => ({
  id,
  tool: "bash",
  label: "Bash",
  args: { command },
});

const summary = () => screen.getByTestId("tool-group-summary");

describe("groupTraceSteps", () => {
  it("splits work at prose and keeps thinking with the calls around it", () => {
    const steps: TraceStep[] = [
      { kind: "thinking", text: "plan", startedAt: 0, endedAt: 1 },
      tool({ id: "a" }),
      tool({ id: "b" }),
      { kind: "text", text: "Now the fit." },
      tool({ id: "c" }),
      { kind: "thinking", text: "hm", startedAt: 2, endedAt: 3 },
    ];
    expect(
      groupTraceSteps(steps).map((s) =>
        s.kind === "work" ? `work@${s.start}x${s.steps.length}` : `text@${s.index}`,
      ),
    ).toEqual(["work@0x3", "text@3", "work@4x2"]);
  });
});

describe("live tool groups", () => {
  it("folds a run into one summary from its second call and updates it as calls arrive", () => {
    let steps = startTool([], bash("e1", "ls"));
    const { rerender } = render(<LiveTrace steps={steps} />);
    // One call is its own row.
    expect(screen.queryByTestId("tool-group-summary")).toBeNull();
    expect(screen.getByRole("button", { name: /Running ls/ })).toBeTruthy();

    steps = startTool(endTool(steps, { id: "e1", tool: "bash", output: "ok" }), bash("e2", "uv"));
    rerender(<LiveTrace steps={steps} />);
    const group = summary();
    expect(group.getAttribute("aria-expanded")).toBe("false");
    expect(group.getAttribute("data-active")).toBe("true");
    expect(group.textContent).toContain("Running uv");
    expect(group.textContent).toContain("2 tools");
    // The rows are folded away, not just covered.
    expect(screen.queryByRole("button", { name: /Ran ls/ })).toBeNull();

    steps = startTool(endTool(steps, { id: "e2", tool: "bash", output: "ok" }), bash("e3", "bun"));
    rerender(<LiveTrace steps={steps} />);
    // The same summary, now counting three.
    expect(summary()).toBe(group);
    expect(group.textContent).toContain("Running bun");
    expect(group.textContent).toContain("3 tools");

    steps = endTool(steps, { id: "e3", tool: "bash", output: "ok" });
    rerender(<LiveTrace steps={steps} />);
    expect(summary()).toBe(group);
    expect(group.getAttribute("data-active")).toBe("false");
    expect(group.textContent).toContain("Used 3 tools");
    expect(group.getAttribute("aria-expanded")).toBe("false");

    // Opened, the individual calls are there to inspect.
    fireEvent.click(group);
    expect(group.getAttribute("aria-expanded")).toBe("true");
    for (const name of [/Ran ls/, /Ran uv/, /Ran bun/]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
  });

  it("keeps a group the user opened open, and a row they opened open, as calls arrive", () => {
    let steps = startTool([], bash("e1", "ls"));
    const { rerender } = render(<LiveTrace steps={steps} />);
    fireEvent.click(screen.getByRole("button", { name: /Running ls/ }));

    steps = startTool(steps, bash("e2", "uv"));
    rerender(<LiveTrace steps={steps} />);
    fireEvent.click(summary());
    // The row opened before the run became a group kept its state.
    expect(screen.getByRole("button", { name: /Running ls/ }).getAttribute("aria-expanded")).toBe(
      "true",
    );

    steps = startTool(steps, bash("e3", "bun"));
    rerender(<LiveTrace steps={steps} />);
    expect(summary().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("button", { name: /Running bun/ })).toBeTruthy();
  });

  it("names a thought inside the run as its live activity", () => {
    render(
      <LiveTrace
        steps={[
          tool({ id: "a" }),
          tool({ id: "b" }),
          { kind: "thinking", text: "which qubit next", startedAt: Date.now() },
        ]}
      />,
    );
    expect(summary().textContent).toContain("Thinking");
    expect(summary().textContent).toContain("2 tools");
  });

  it("keeps prose between calls outside every group", () => {
    render(
      <LiveTrace
        steps={[
          tool({ id: "a" }),
          tool({ id: "b" }),
          { kind: "text", text: "The fit failed, so I will check the readout." },
          tool({ id: "c" }),
          tool({ id: "d", status: "running", endedAt: undefined }),
        ]}
      />,
    );
    const groups = screen.getAllByTestId("tool-group-summary");
    expect(groups).toHaveLength(2);
    const prose = screen.getByText("The fit failed, so I will check the readout.");
    expect(prose.closest("[hidden]")).toBeNull();
    expect(prose.closest("[data-testid=trace-work]")).toBeNull();
  });

  it("keeps a failure readable on the folded group until it is opened", () => {
    render(
      <LiveTrace
        steps={[
          tool({ id: "a" }),
          tool({
            id: "b",
            tool: "bash",
            label: "Bash",
            status: "error",
            args: { command: "python fit.py" },
            output: "Traceback (most recent call last):\nFileNotFoundError: data.csv",
            exitCode: 1,
          }),
          tool({ id: "c", status: "running", endedAt: undefined }),
        ]}
      />,
    );
    expect(summary().textContent).toContain("1 failed");
    const failure = screen.getByTestId("tool-group-failure");
    expect(failure.textContent).toContain("Ran python");
    expect(failure.textContent).toContain("FileNotFoundError: data.csv");
    // The folded rows do not repeat it.
    expect(screen.queryByTestId("tool-failure-line")).toBeNull();

    fireEvent.click(summary());
    expect(screen.queryByTestId("tool-group-failure")).toBeNull();
    expect(screen.getByTestId("tool-failure-line").textContent).toBe("FileNotFoundError: data.csv");
  });

  it("keeps the live execution card, then its link, on a folded group", () => {
    useGetExecution.mockReturnValue({
      data: {
        data: { name: "one-qubit", status: "running", chip_id: "64Qv3", note: {}, task: [] },
      },
    });
    const wait = tool({
      id: "w",
      tool: "qdash_wait_execution",
      label: "Wait for execution",
      args: { executionId: "exec-1" },
      status: "running",
      endedAt: undefined,
    });
    const { rerender } = render(<LiveTrace steps={[tool({ id: "a" }), wait]} />);
    expect(summary().getAttribute("aria-expanded")).toBe("false");
    // Drawn once, by the group, not again by the hidden row.
    expect(screen.getAllByTestId("execution-progress")).toHaveLength(1);

    rerender(<LiveTrace steps={[tool({ id: "a" }), { ...wait, status: "done", endedAt: 2000 }]} />);
    expect(screen.queryByTestId("execution-progress")).toBeNull();
    expect(screen.getByRole("link", { name: "View execution exec-1" }).getAttribute("href")).toBe(
      "/executions/exec-1",
    );
  });

  it("shows the run's figures while folded unless the message already shows them", () => {
    const steps = [
      tool({ id: "a", figures: ["/data/CheckRabi_0.png"] }),
      tool({ id: "b", figures: ["/data/CheckT1_0.png"] }),
    ];
    const { rerender } = render(<LiveTrace steps={steps} />);
    expect(screen.getByAltText("CheckRabi_0")).toBeTruthy();
    expect(screen.getByAltText("CheckT1_0")).toBeTruthy();

    rerender(<LiveTrace steps={steps} figuresOutside />);
    expect(screen.queryByAltText("CheckRabi_0")).toBeNull();
  });
});

describe("finished tool groups", () => {
  it("stays folded after the turn, with its prose visible", () => {
    render(
      <ChatTraceSummary
        trace={{
          durationMs: 5000,
          steps: [
            tool({ id: "a", startedAt: 0, endedAt: 1000 }),
            tool({ id: "b", startedAt: 1000, endedAt: 3000, status: "cancelled" }),
            { kind: "text", text: "Checking the readout next." },
            tool({ id: "c", startedAt: 3000, endedAt: 4000 }),
          ],
        }}
      />,
    );
    const group = summary();
    expect(group.getAttribute("aria-expanded")).toBe("false");
    expect(group.textContent).toContain("Used 2 tools");
    expect(group.textContent).toContain("1 not run");
    expect(group.textContent).toContain("3s");
    expect(screen.getByText("Checking the readout next.").closest("[hidden]")).toBeNull();
    // The lone call after the prose is a row of its own.
    expect(screen.getAllByTestId("tool-group-summary")).toHaveLength(1);
    const rows = screen.getAllByTestId("trace-work");
    expect(within(rows[1]).getByRole("button", { name: /Get figure.*Done/ })).toBeTruthy();
  });
});
