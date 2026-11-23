import { cleanup, fireEvent, render as rtlRender, screen } from "@testing-library/react";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionDetailClient } from "../ExecutionClient";

const investigate = vi.fn();
let execution: Record<string, unknown> = {};

vi.mock("@/client/execution/execution", () => ({
  useGetExecution: () => ({ data: { data: execution }, isLoading: false, isError: false }),
  useCancelExecution: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: "lab-a" }),
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

/** Renders the page as opened with `searchParams`, the Executions view it links back to. */
function render(ui: ReactElement, searchParams = "") {
  return rtlRender(ui, { wrapper: withNuqsTestingAdapter({ searchParams }) });
}

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

  it("links a measurement to its agent session graph", () => {
    execution = {
      name: "agent:CheckRabi",
      status: "completed",
      chip_id: "64Q",
      task: [],
      agent_session: { session_id: "s-1", linked: true, action_id: "a-1", status: "active" },
    };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    expect(screen.getByRole("note").textContent).toContain("One measurement of agent session");
    expect(screen.getByRole("link", { name: "Open session graph" }).getAttribute("href")).toBe(
      "/execution/64Q/sessions/s-1",
    );
  });

  it("shows the agent as the actor and the session creator as responsible", () => {
    execution = {
      name: "agent:CheckRabi",
      status: "completed",
      chip_id: "64Q",
      username: "alice",
      task: [],
      agent_session: {
        session_id: "s-1",
        linked: true,
        action_id: "a-1",
        status: "active",
        created_by: "alice",
      },
    };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    const actor = screen.getByText("Run by:").parentElement as HTMLElement;
    expect(actor.textContent).toBe("Run by:Agent·@alice");
    expect(screen.getByRole("note").textContent).toContain(
      "@alice created the session and is responsible for it",
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
    expect(screen.queryByRole("link", { name: "Open session graph" })).toBeNull();
    expect(screen.queryByText("Run by:")).toBeNull();
    expect(screen.queryByText("Agent")).toBeNull();
  });

  it("shows nothing for an execution outside agent sessions", () => {
    execution = { name: "Daily run", status: "completed", chip_id: "64Q", task: [] };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    expect(screen.queryByRole("note")).toBeNull();
  });
});

describe("ExecutionDetailClient calibration session", () => {
  const member = {
    calibration_session_id: "cs-1",
    chip_id: "64Q",
    objective: "Bring up qubits",
    status: "closed",
    via: "pipeline_run",
    pipeline_run_id: "cpr-1",
  };

  const crumbs = () =>
    Array.from(
      screen.getByRole("navigation", { name: "Breadcrumb" }).querySelectorAll("a"),
      (link) => [link.textContent, link.getAttribute("href")],
    );

  it("places a pipeline step under Execution, its session's objective, and its run", () => {
    execution = {
      name: "Pipeline step",
      status: "completed",
      chip_id: "64Q",
      task: [],
      calibration_session: member,
    };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    expect(crumbs()).toEqual([
      ["Execution", "/execution?chip=64Q&project=lab-a"],
      ["Bring up qubits", "/calibration-sessions/cs-1?project=lab-a&from=executions&chip=64Q"],
      ["Run cpr-1", "/calibration-sessions/cs-1?project=lab-a&from=executions&chip=64Q#run-cpr-1"],
    ]);
  });

  it("returns to the Executions view it was opened from, through its session too", () => {
    execution = {
      name: "Pipeline step",
      status: "completed",
      chip_id: "64Q",
      task: [],
      calibration_session: member,
    };
    render(
      <ExecutionDetailClient chipId="64Q" executionId="exec-1" />,
      "project=lab-a&date=20261120&flat=true&page=2",
    );
    const session =
      "/calibration-sessions/cs-1?project=lab-a&from=executions&chip=64Q&date=20261120&flat=true&page=2";
    expect(crumbs()).toEqual([
      ["Execution", "/execution?chip=64Q&date=20261120&flat=true&page=2&project=lab-a"],
      ["Bring up qubits", session],
      ["Run cpr-1", `${session}#run-cpr-1`],
    ]);
  });

  it("ignores an invalid view in its URL", () => {
    execution = { name: "Daily run", status: "completed", chip_id: "64Q", task: [] };
    render(
      <ExecutionDetailClient chipId="64Q" executionId="exec-1" />,
      "date=tomorrow&flat=no&page=0&status=closed",
    );
    expect(crumbs()).toEqual([["Execution", "/execution?chip=64Q&project=lab-a"]]);
  });

  it("places an agent session's execution under its session without a run", () => {
    execution = {
      name: "Agent step",
      status: "completed",
      chip_id: "64Q",
      task: [],
      calibration_session: {
        ...member,
        via: "agent_session",
        pipeline_run_id: undefined,
        agent_session_id: "as-1",
      },
    };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    expect(crumbs().map(([label]) => label)).toEqual(["Execution", "Bring up qubits"]);
  });

  it("places a standalone execution directly under Execution on its chip", () => {
    execution = { name: "Daily run", status: "completed", chip_id: "64Q", task: [] };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    expect(crumbs()).toEqual([["Execution", "/execution?chip=64Q&project=lab-a"]]);
  });

  it("links a manual pipeline step back to its calibration session, without an agent label", () => {
    execution = {
      name: "Pipeline step",
      status: "completed",
      chip_id: "64Q",
      username: "carol",
      task: [],
      calibration_session: member,
    };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    const note = screen.getByTestId("execution-calibration-notice");
    expect(note.textContent).toContain("Bring up qubits (closed)");
    expect(
      screen.getByRole("link", { name: "Open calibration session" }).getAttribute("href"),
    ).toBe("/calibration-sessions/cs-1?project=lab-a&from=executions&chip=64Q");
    expect(screen.queryByText("Agent")).toBeNull();
    expect(screen.queryByTestId("reported-origin-badge")).toBeNull();
  });

  it("keeps the recorded user and marks a reported agent tool origin as reported", () => {
    execution = {
      name: "Pipeline step",
      status: "completed",
      chip_id: "64Q",
      username: "carol",
      task: [],
      reported_origin: { source: "agent_tool", tool: "qdash_run_pipeline", client: "pi-qdash" },
    };
    render(<ExecutionDetailClient chipId="64Q" executionId="exec-1" />);
    expect(screen.getByText("@carol")).toBeTruthy();
    expect(screen.getByTestId("reported-origin-badge").textContent).toBe("Agent tool, reported");
    expect(screen.queryByText("Agent")).toBeNull();
    expect(screen.queryByRole("link", { name: "Open calibration session" })).toBeNull();
  });
});
