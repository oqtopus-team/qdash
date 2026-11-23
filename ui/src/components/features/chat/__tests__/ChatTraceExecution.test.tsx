import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TraceStep } from "@/types/agentChat";

import { LiveTrace } from "../ChatTrace";
import { ChatLinkPreviewContext } from "../ChatPreviewLink";

const useGetExecution = vi.fn();
vi.mock("@/client/execution/execution", () => ({
  useGetExecution: (...args: unknown[]) => useGetExecution(...args),
}));

afterEach(() => {
  cleanup();
  useGetExecution.mockReset();
});

type ToolStep = Extract<TraceStep, { kind: "tool" }>;

function waitStep(status: ToolStep["status"], tool = "qdash_wait_execution"): ToolStep {
  return {
    kind: "tool",
    id: "w1",
    tool,
    label: "Wait for execution",
    args: { executionId: "exec-1" },
    status,
    startedAt: 0,
    ...(status === "running" ? {} : { endedAt: 1000 }),
  };
}

describe("a wait-for-execution step", () => {
  it("shows the live execution card while it waits", () => {
    useGetExecution.mockReturnValue({
      data: {
        data: { name: "one-qubit", status: "running", chip_id: "64Qv3", note: {}, task: [] },
      },
    });
    render(<LiveTrace steps={[waitStep("running")]} />);
    expect(screen.getByTestId("execution-progress")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open execution" }).getAttribute("href")).toBe(
      "/execution/64Qv3/exec-1",
    );
    expect(screen.queryByText("View execution exec-1")).toBeNull();
  });

  it.each(["done", "error"] as const)(
    "keeps a link to the execution once the wait is %s",
    (status) => {
      const preview = vi.fn(() => true);
      render(
        <ChatLinkPreviewContext.Provider value={{ preview }}>
          <LiveTrace steps={[waitStep(status)]} />
        </ChatLinkPreviewContext.Provider>,
      );
      // The live card stops polling with the wait; it is not drawn for a finished step.
      expect(useGetExecution).not.toHaveBeenCalled();
      const link = screen.getByRole("link", { name: "View execution exec-1" });
      expect(link.getAttribute("href")).toBe("/executions/exec-1");
      fireEvent.click(link);
      expect(preview).toHaveBeenCalledWith("/executions/exec-1");
    },
  );

  it("offers no execution link for a call that never ran or another tool", () => {
    render(<LiveTrace steps={[waitStep("cancelled"), waitStep("done", "qdash_get_execution")]} />);
    expect(screen.queryByRole("link", { name: /View execution/ })).toBeNull();
    expect(useGetExecution).not.toHaveBeenCalled();
  });
});
