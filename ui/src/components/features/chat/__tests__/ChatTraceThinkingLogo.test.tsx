import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TraceStep } from "@/types/agentChat";

import { ChatTraceSummary, LiveTrace, TurnActivity } from "../ChatTrace";

vi.mock("@/client/execution/execution", () => ({ useGetExecution: vi.fn() }));

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

const thinking = (endedAt?: number): TraceStep => ({
  kind: "thinking",
  text: "which qubit next",
  startedAt: Date.now() - 2000,
  ...(endedAt === undefined ? {} : { endedAt }),
});

const logos = () => screen.queryAllByTestId("thinking-logo");

beforeEach(() => {
  // jsdom has no 2D canvas; the mark's drawing is covered in ThinkingLogo.test.tsx.
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ChatTrace thinking mark", () => {
  it("animates a live thought and keeps its readable label", () => {
    render(<LiveTrace steps={[thinking()]} />);
    const row = screen.getByRole("button", { name: /Thinking/ });
    expect(within(row).getByTestId("thinking-logo")).toBeTruthy();
    expect(within(row).getByText("Thinking")).toHaveClass("loader-text-shimmer");
    expect(logos()).toHaveLength(1);
    // A 24px mark held to the 14px icon slot, so the row does not shift when the thought ends.
    const [mark] = logos();
    expect(mark.style.width).toBe("24px");
    expect(mark).toHaveClass("-m-[5px]");
  });

  it("keeps the static icon for a finished thought, live or in history", () => {
    const steps = [thinking(Date.now() - 1000), tool({ id: "a", status: "running" })];
    render(<LiveTrace steps={steps} />);
    expect(screen.getByText(/Thought for/)).toBeTruthy();
    expect(logos()).toHaveLength(0);
    cleanup();

    // A saved trace never animates, even with a thought that never recorded its end.
    render(<ChatTraceSummary trace={{ steps: [thinking()], durationMs: 2000 }} />);
    expect(logos()).toHaveLength(0);
  });

  it("shows one mark: on the folded summary, then on the row once opened", () => {
    render(<LiveTrace steps={[tool({ id: "a" }), tool({ id: "b" }), thinking()]} />);
    const summary = screen.getByTestId("tool-group-summary");
    expect(within(summary).getByTestId("thinking-logo")).toBeTruthy();
    expect(logos()).toHaveLength(1);

    fireEvent.click(summary);
    expect(within(summary).queryByTestId("thinking-logo")).toBeNull();
    const row = screen
      .getAllByRole("button", { name: /^Thinking/ })
      .find((button) => button !== summary)!;
    expect(within(row).getByTestId("thinking-logo")).toBeTruthy();
    expect(logos()).toHaveLength(1);
  });

  it("does not animate a group summary for tool activity", () => {
    render(
      <LiveTrace
        steps={[tool({ id: "a" }), tool({ id: "b", status: "running", endedAt: undefined })]}
      />,
    );
    expect(screen.getByTestId("tool-group-summary").textContent).not.toContain("Thinking");
    expect(logos()).toHaveLength(0);
  });
});

describe("TurnActivity thinking mark", () => {
  it("shows the mark and a readable status before the first event, without typing dots", () => {
    render(<TurnActivity steps={[]} startedAt={Date.now() - 2000} statusMessage={null} />);
    const footer = screen.getByTestId("turn-activity");
    const status = screen.getByRole("status");
    expect(within(status).getByTestId("thinking-logo")).toBeTruthy();
    expect(status.textContent).toBe("Thinking");
    expect(footer.textContent).toMatch(/^Thinking\d+s$/);
    expect(footer.querySelector('[style*="loader-typing"]')).toBeNull();
    expect(logos()).toHaveLength(1);
  });

  it("leaves the mark to the thought row once one is live", () => {
    render(
      <>
        <LiveTrace steps={[thinking()]} />
        <TurnActivity steps={[thinking()]} startedAt={Date.now()} statusMessage={null} />
      </>,
    );
    const footer = screen.getByTestId("turn-activity");
    expect(footer.className).toBe("sr-only");
    expect(within(footer).queryByTestId("thinking-logo")).toBeNull();
    expect(logos()).toHaveLength(1);
  });

  it("shows the server's status as text without the mark", () => {
    render(<TurnActivity steps={[]} startedAt={Date.now()} statusMessage="Compacting context" />);
    expect(screen.getByRole("status").textContent).toBe("Compacting context");
    expect(logos()).toHaveLength(0);
  });
});
