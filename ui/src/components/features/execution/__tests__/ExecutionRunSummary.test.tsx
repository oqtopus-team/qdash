import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ExecutionRunSummary } from "@/components/features/execution/ExecutionRunSummary";

afterEach(cleanup);

const tasks = [
  { name: "CheckRabi", qid: "0", status: "completed" },
  { name: "CheckRabi", qid: "1", status: "failed" },
  { name: "CreateHPIPulse", qid: "0", status: "running" },
  { name: "CreateHPIPulse", qid: "1", status: "scheduled" },
];

describe("ExecutionRunSummary", () => {
  it("counts finished tasks and names the one being measured, without a total", () => {
    render(<ExecutionRunSummary status="running" tasks={tasks} />);

    const summary = screen.getByRole("status");
    expect(summary).toHaveTextContent("Running");
    expect(summary).toHaveTextContent("2 tasks done");
    expect(summary).not.toHaveTextContent("of 4");
    expect(summary).toHaveTextContent("now CreateHPIPulse");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("says when the run is waiting or being cancelled", () => {
    render(<ExecutionRunSummary status="scheduled" tasks={tasks.slice(3)} />);
    expect(screen.getByRole("status")).toHaveTextContent("Waiting to start");
    expect(screen.getByRole("status")).not.toHaveTextContent("done");
    cleanup();

    render(<ExecutionRunSummary status="cancelling" tasks={tasks} />);
    const summary = screen.getByRole("status");
    expect(summary).toHaveTextContent("Cancelling");
    expect(summary).toHaveTextContent("2 tasks done");
    expect(summary).not.toHaveTextContent("now");
  });

  it("renders nothing once the execution has finished", () => {
    const { container } = render(<ExecutionRunSummary status="completed" tasks={tasks} />);
    expect(container).toBeEmptyDOMElement();
  });
});
