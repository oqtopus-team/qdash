import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TaskResultsPageContent } from "@/components/features/task-results/TaskResultsPageContent";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  params: new URLSearchParams(),
  items: [] as Array<Record<string, unknown>>,
  total: 0,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
  usePathname: () => "/task-results",
  // A stable reference per test, like the real hook between navigations.
  useSearchParams: () => mocks.params,
}));

vi.mock("@/client/task-result/task-result", () => ({
  useListTaskResults: () => ({
    data: {
      data: {
        items: mocks.items,
        total: mocks.total,
        status_counts: { failed: 1, completed: 0, running: 0, cancelled: 0 },
      },
    },
    isLoading: false,
    isError: false,
    isFetching: false,
  }),
}));

vi.mock("@/client/task-file/task-file", () => ({
  useGetTaskFileSettings: () => ({ data: undefined }),
  useListTaskInfo: () => ({
    data: { data: { tasks: [{ name: "CheckRabi" }, { name: "CheckT1" }] } },
  }),
}));

vi.mock("@/client/execution/execution", () => ({
  useListExecutions: () => ({ data: undefined, isLoading: false }),
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: { data: { chips: [{ chip_id: "64Q", activity_status: "active" }] } },
    isLoading: false,
    isError: false,
  }),
}));

// The preview sidebar has its own tests; a stub exposes which result is previewed.
vi.mock("@/components/features/task-results/TaskResultPreviewSidebar", async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import("@/components/features/task-results/TaskResultPreviewSidebar")
    >();
  return {
    ...actual,
    TaskResultPreviewSidebar: ({ taskId }: { taskId: string | null }) =>
      taskId ? <div data-testid="preview">{taskId}</div> : null,
  };
});

const failedItem = {
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
  has_stack_trace: true,
};

beforeEach(() => {
  mocks.push.mockReset();
  mocks.params = new URLSearchParams();
  mocks.items = [];
  mocks.total = 0;
});

afterEach(() => {
  cleanup();
});

describe("TaskResultsPageContent", () => {
  it("shows persistent labels that name the filter controls", () => {
    render(<TaskResultsPageContent />);

    expect(screen.getByLabelText("Chip")).toHaveAttribute("id", "task-result-filter-chip");
    expect(screen.getByLabelText("Execution")).toHaveAttribute(
      "id",
      "task-result-filter-execution",
    );
    expect(screen.getByLabelText("Task")).toHaveAttribute("id", "task-result-filter-task");

    fireEvent.click(screen.getByRole("button", { name: /More filters/ }));
    expect(screen.getByLabelText("QID")).toBeInTheDocument();
    expect(screen.getByLabelText("Message contains")).toBeInTheDocument();
  });

  it("keeps filter edits as a draft until Apply is pressed", () => {
    render(<TaskResultsPageContent />);
    expect(screen.queryByText("Unapplied changes")).not.toBeInTheDocument();

    const taskInput = screen.getByLabelText("Task");
    fireEvent.keyDown(taskInput, { key: "ArrowDown" });
    fireEvent.click(screen.getByText("CheckT1"));

    expect(mocks.push).not.toHaveBeenCalled();
    expect(screen.getByText("Unapplied changes")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(mocks.push).toHaveBeenCalledWith("/task-results?task_name=CheckT1");
  });

  it("offers a reset action when applied filters return no results", () => {
    mocks.params = new URLSearchParams("status=failed&task_name=CheckRabi");
    render(<TaskResultsPageContent />);

    expect(screen.getByText("No task results match these filters")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(mocks.push).toHaveBeenCalledWith("/task-results");
  });

  it("does not offer a reset action when no filter is applied", () => {
    render(<TaskResultsPageContent />);

    expect(screen.getByText("No task results yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
  });

  it("shows the result range once beside the status controls", () => {
    mocks.items = [failedItem];
    mocks.total = 1;
    render(<TaskResultsPageContent />);

    expect(screen.getAllByText("Showing 1-1 of 1")).toHaveLength(1);
    expect(screen.queryByText(/^results$/)).not.toBeInTheDocument();
    const statusGroup = screen.getByRole("group", { name: "Status" });
    expect(within(statusGroup).getByRole("button", { name: "All" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("applies a status tab immediately", () => {
    render(<TaskResultsPageContent />);

    fireEvent.click(screen.getByRole("button", { name: /^Failed/ }));
    expect(mocks.push).toHaveBeenCalledWith("/task-results?status=failed");
  });

  it("opens the preview from the keyboard but not from a nested link", () => {
    mocks.items = [failedItem];
    mocks.total = 1;
    render(<TaskResultsPageContent />);

    const row = screen.getByRole("button", {
      name: "Preview CheckRabi task result for 12",
    });
    const detailLink = within(row).getByRole("link", { name: /CheckRabi/ });
    expect(detailLink).toHaveAttribute("href", "/task-results/task-9");

    fireEvent.keyDown(detailLink, { key: "Enter" });
    expect(screen.queryByTestId("preview")).not.toBeInTheDocument();

    fireEvent.keyDown(row, { key: "Enter" });
    expect(screen.getByTestId("preview")).toHaveTextContent("task-9");
    expect(row).toHaveAttribute("aria-current", "true");
  });
});
