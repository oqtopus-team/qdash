import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionDetailClient } from "../ExecutionClient";

const investigate = vi.fn();
let execution: Record<string, unknown> = {};

vi.mock("@/client/execution/execution", () => ({
  useGetExecution: () => ({ data: { data: execution }, isLoading: false, isError: false }),
  useCancelExecution: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/contexts/ChatDockContext", () => ({
  useOptionalChatDock: () => ({ investigate }),
}));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("../ExecutionDAG", () => ({ ExecutionDAG: () => null }));
vi.mock("../ExecutionParameterChanges", () => ({ ExecutionParameterChanges: () => null }));
vi.mock("@/components/features/execution/ExecutionTopologyView", () => ({
  ExecutionTopologyView: () => null,
}));

afterEach(() => {
  cleanup();
  investigate.mockClear();
});

describe("ExecutionDetailClient failure investigation", () => {
  it("shows the error log with its action and opens the floating chat", () => {
    const log = `RuntimeError: ${"x".repeat(2_000)}`;
    execution = { name: "Daily run", status: "failed", chip_id: "64Q", message: log, task: [] };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);

    const body = screen.getByText(log);
    expect(body.tagName).toBe("PRE");
    expect(body.className).toContain("overflow-auto");
    expect(body.className).toContain("break-all");
    const button = screen.getByRole("button", { name: "Investigate with AI" });
    expect(screen.getByText("Error Log").parentElement).toContainElement(button);
    expect(screen.queryByRole("alert")).toBeNull();

    fireEvent.click(button);

    expect(investigate).toHaveBeenCalledWith({ executionId: "exec-1", chipId: "64Q" }, "mini");
  });

  it("offers nothing for an execution that did not fail", () => {
    execution = { name: "Daily run", status: "completed", chip_id: "64Q", task: [] };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);

    expect(screen.queryByRole("button", { name: "Investigate with AI" })).toBeNull();
  });
});
