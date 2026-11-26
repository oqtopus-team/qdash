import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Task } from "@/schemas";

import {
  ExecutionTasksColumn,
  TaskDetailsHeader,
  TaskParametersTables,
} from "@/components/features/task-history/TaskResultDetailParts";

vi.mock("@/components/features/metrics/ParametersTable", () => ({
  ParametersTable: ({ title, overrides }: { title: string; overrides?: object }) => (
    <div data-testid="parameters" data-has-overrides={String(Boolean(overrides))}>
      {title}
    </div>
  ),
}));

afterEach(() => cleanup());

describe("TaskParametersTables", () => {
  it("renders only non-empty groups and applies overrides to outputs", () => {
    render(
      <TaskParametersTables
        task={{ input_parameters: {}, output_parameters: { t1: 1 }, run_parameters: { shots: 1 } }}
        outputOverrides={{}}
        className="list"
      />,
    );
    const tables = screen.getAllByTestId("parameters");

    expect(tables.map((table) => table.textContent)).toEqual([
      "Output Parameters",
      "Run Parameters",
    ]);
    expect(tables[0].dataset.hasOverrides).toBe("true");
    expect(tables[1].dataset.hasOverrides).toBe("false");
  });
});

describe("TaskDetailsHeader", () => {
  it("steps through tasks and stops at both ends", () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <TaskDetailsHeader position="1 / 3" index={0} total={3} onSelect={onSelect} />,
    );

    expect(screen.getByText("1 / 3")).not.toBeNull();
    expect((screen.getByRole("button", { name: "← Prev" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    expect(onSelect).toHaveBeenLastCalledWith(1);

    rerender(<TaskDetailsHeader position="3 / 3" index={2} total={3} onSelect={onSelect} />);
    expect((screen.getByRole("button", { name: "Next →" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: "← Prev" }));
    expect(onSelect).toHaveBeenLastCalledWith(1);
  });

  it("hides navigation for a single task", () => {
    render(<TaskDetailsHeader position={null} index={0} total={1} onSelect={vi.fn()} />);

    expect(screen.queryByRole("button", { name: "Next →" })).toBeNull();
  });
});

describe("ExecutionTasksColumn", () => {
  const tasks = [
    { task_id: "a", name: "CheckRabi", status: "completed" },
    { task_id: "b", name: "CheckT1", status: "failed" },
  ] as Task[];

  function renderColumn(overrides: Partial<Parameters<typeof ExecutionTasksColumn>[0]> = {}) {
    const onSelect = vi.fn();
    render(
      <ExecutionTasksColumn
        executionId="exec-1"
        tasks={tasks}
        isLoading={false}
        isSelected={(_task, idx) => idx === 0}
        onSelect={onSelect}
        matchName="rabi"
        targetId="0-1"
        targetNoun="coupling"
        {...overrides}
      />,
    );
    return onSelect;
  }

  it("badges matching tasks and reports the chosen task", () => {
    const onSelect = renderColumn();

    expect(screen.getByText("exec-1")).not.toBeNull();
    expect(screen.getAllByText("rabi")).toHaveLength(1);
    fireEvent.click(screen.getByText("CheckT1"));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("highlights every task the caller's selection policy matches", () => {
    renderColumn({
      tasks: [
        { task_id: "a", name: "CheckRabi", status: "completed" },
        { task_id: "a", name: "CheckT1", status: "completed" },
        { task_id: "b", name: "CheckT2", status: "completed" },
      ] as Task[],
      isSelected: (task) => task.task_id === "a",
    });
    const selected = (name: string) =>
      screen.getByText(name).closest("button")!.className.includes("bg-secondary ");

    expect([selected("CheckRabi"), selected("CheckT1"), selected("CheckT2")]).toEqual([
      true,
      true,
      false,
    ]);
  });

  it("explains an execution without the target's tasks", () => {
    renderColumn({ tasks: [] });

    expect(screen.getByText("No rabi-related tasks found for 0-1")).not.toBeNull();
    expect(
      screen.getByText("This execution may not include calibration for this coupling"),
    ).not.toBeNull();
  });

  it("reports a failed execution load", () => {
    renderColumn({ isError: true });

    expect(screen.getByText("Failed to load execution")).not.toBeNull();
  });
});
