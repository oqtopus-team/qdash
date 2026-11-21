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
vi.mock("../ExecutionParameterChanges", () => ({
  ExecutionParameterChanges: () => <div>parameter changes body</div>,
}));
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

describe("ExecutionDetailClient parameter changes", () => {
  it("starts collapsed and loads the comparison only when the user expands it", () => {
    execution = { name: "Daily run", status: "completed", chip_id: "64Q", task: [] };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);

    const heading = screen.getByRole("heading", { name: "Parameter changes" });
    const details = heading.closest("details")!;
    expect(details.open).toBe(false);
    expect(screen.queryByText("parameter changes body")).toBeNull();

    fireEvent.click(details.querySelector("summary")!);
    expect(details.open).toBe(true);
    expect(screen.getByText("parameter changes body")).toBeTruthy();

    fireEvent.click(details.querySelector("summary")!);
    expect(details.open).toBe(false);
    expect(screen.queryByText("parameter changes body")).toBeNull();
  });
});

describe("ExecutionDetailClient agent session link", () => {
  afterEach(() => cleanup());

  it("links a measurement to its agent session journey", () => {
    execution = {
      name: "agent:CheckRabi",
      status: "completed",
      chip_id: "64Q",
      task: [],
      agent_session: { session_id: "s-1", linked: true, action_id: "a-1", status: "active" },
    };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    expect(screen.getByRole("note").textContent).toContain("One measurement of agent session");
    expect(screen.getByRole("link", { name: "Open journey" }).getAttribute("href")).toBe(
      "/execution/64Q/sessions/s-1",
    );
  });

  it("says a tag alone does not group the execution", () => {
    execution = {
      name: "agent:CheckRabi",
      status: "completed",
      chip_id: "64Q",
      task: [],
      agent_session: { session_id: "s-old", linked: false, action_id: null, status: null },
    };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    expect(screen.getByRole("note").textContent).toContain("listed as its own execution");
    expect(screen.queryByRole("link", { name: "Open journey" })).toBeNull();
  });

  it("shows nothing for an execution outside agent sessions", () => {
    execution = { name: "Daily run", status: "completed", chip_id: "64Q", task: [] };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    expect(screen.queryByRole("note")).toBeNull();
  });
});
