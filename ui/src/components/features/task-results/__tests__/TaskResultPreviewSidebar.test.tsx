import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskResultPreviewSidebar } from "@/components/features/task-results/TaskResultPreviewSidebar";

const mocks = vi.hoisted(() => ({
  result: null as Record<string, unknown> | null,
}));

vi.mock("@/components/features/provenance/TaskLineageSection", () => ({
  TaskLineageSection: () => null,
}));

vi.mock("@/client/task/task", () => ({
  useGetTaskResult: (taskId: string) => ({
    data: taskId && mocks.result ? { data: mocks.result } : undefined,
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("@/client/task-file/task-file", () => ({
  useGetTaskFileSettings: () => ({ data: undefined }),
  useListTaskInfo: () => ({ data: undefined }),
}));

vi.mock("@/components/charts/TaskFigure", () => ({
  TaskFigure: ({ path }: { path?: string }) => <div data-testid="task-figure">{path}</div>,
}));

const failedResult = {
  task_id: "task-9",
  task_name: "CheckRabi",
  status: "failed",
  qid: "12",
  chip_id: "64Q",
  execution_id: "20261031-003",
  username: "admin",
  start_at: "2026-10-31T10:00:00Z",
  elapsed_time: "12s",
  message: "Fit did not converge",
  figure_path: ["rabi.png"],
  output_parameters: { rabi_frequency: { value: 10.5, unit: "MHz" } },
  input_parameters: { shots: 1000 },
};

afterEach(() => {
  cleanup();
  mocks.result = null;
});

describe("TaskResultPreviewSidebar", () => {
  it("stays closed and empty without a task id", () => {
    render(<TaskResultPreviewSidebar taskId={null} onClose={() => {}} />);

    const preview = screen.getByRole("complementary", { hidden: true });
    expect(preview).toHaveAttribute("aria-hidden", "true");
    expect(preview).toHaveClass("translate-x-full");
    expect(screen.queryByRole("link", { name: /Open full page/, hidden: true })).toBeNull();
  });

  it("shows the result's figures, metadata, message and parameters", () => {
    mocks.result = failedResult;
    render(<TaskResultPreviewSidebar taskId="task-9" onClose={() => {}} />);

    expect(screen.getByRole("heading", { name: "CheckRabi" })).toBeTruthy();
    expect(screen.getByText("failed")).toBeTruthy();
    expect(screen.getByTestId("task-figure")).toHaveTextContent("rabi.png");
    expect(screen.getByText("64Q")).toBeTruthy();
    expect(screen.getByText("Fit did not converge")).toBeTruthy();
    expect(screen.getByText("10.5 MHz")).toBeTruthy();
    expect(screen.getByText("shots")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open full page/ })).toHaveAttribute(
      "href",
      "/task-results/task-9",
    );
    expect(screen.getByRole("link", { name: /Execution/ })).toHaveAttribute(
      "href",
      "/execution/64Q/20261031-003",
    );
  });

  it("hides the execution link on request and closes on Escape", () => {
    mocks.result = failedResult;
    const onClose = vi.fn();
    render(
      <TaskResultPreviewSidebar taskId="task-9" onClose={onClose} showExecutionLink={false} />,
    );

    expect(screen.queryByRole("link", { name: /Execution/ })).toBeNull();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Close task result preview" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
