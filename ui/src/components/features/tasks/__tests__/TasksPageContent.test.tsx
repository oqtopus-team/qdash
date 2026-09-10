import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TasksPageContent } from "../TasksPageContent";

const mocks = vi.hoisted(() => ({ source: vi.fn(), workbench: vi.fn(), tasks: vi.fn() }));
vi.mock("@/client/task/task", () => ({ useGetTaskResult: mocks.source }));
vi.mock("@/components/ui/Toast", () => ({ useToast: () => ({}) }));
vi.mock("@/client/task-file/task-file", () => ({
  getTaskFileSettings: async () => ({ data: { default_backend: "qubex" } }),
  listTaskFileBackends: async () => ({ data: { backends: [{ name: "qubex" }] } }),
  listTaskInfo: mocks.tasks,
}));
vi.mock("../TaskWorkbench", () => ({
  TaskWorkbench: (props: unknown) => {
    mocks.workbench(props);
    return <div>Shared workbench</div>;
  },
}));

const currentTask = {
  name: "CheckRabi",
  enabled: true,
  run_parameters: { shots: { value: 100, value_type: "int" } },
};
const source = { task_id: "old-result", task_name: "CheckRabi", run_parameters: { removed: 42 } };

beforeEach(() => {
  mocks.source.mockReturnValue({ data: { data: source } });
  mocks.tasks.mockResolvedValue({ data: { tasks: [currentTask] } });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderSource() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <NuqsTestingAdapter searchParams="?sourceTaskId=old-result&backend=qubex">
      <QueryClientProvider client={client}>
        <TasksPageContent />
      </QueryClientProvider>
    </NuqsTestingAdapter>,
  );
}

describe("tasks re-execution entry", () => {
  it("uses the current catalog definition and passes historical values separately", async () => {
    renderSource();
    await screen.findByText("Shared workbench");
    expect(mocks.workbench).toHaveBeenCalledWith(
      expect.objectContaining({
        task: currentTask,
        sourceTask: source,
        backend: "qubex",
      }),
    );
    expect(mocks.tasks).toHaveBeenCalledWith(expect.objectContaining({ backend: "qubex" }));
  });
  it("does not construct a historical form or select another task when the current task is missing", async () => {
    mocks.tasks.mockResolvedValue({ data: { tasks: [{ ...currentTask, name: "DifferentTask" }] } });
    renderSource();
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "not available in the current qubex catalog",
      ),
    );
    expect(mocks.workbench).not.toHaveBeenCalled();
  });
  it("waits for the current definition before exposing a form", async () => {
    mocks.tasks.mockReturnValue(new Promise(() => {}));
    renderSource();
    await screen.findByText("Loading current task definition…");
    expect(mocks.workbench).not.toHaveBeenCalled();
  });
  it("does not expose a runnable form while the source is loading", () => {
    mocks.source.mockReturnValue({ isLoading: true });
    renderSource();
    expect(screen.getByRole("status")).toHaveTextContent("Loading source task");
    expect(mocks.workbench).not.toHaveBeenCalled();
  });
  it("does not fall back to a different task when the source is inaccessible", () => {
    mocks.source.mockReturnValue({ error: new Error("Not found") });
    renderSource();
    expect(screen.getByText("Unable to load the source task result.")).toBeTruthy();
    expect(mocks.workbench).not.toHaveBeenCalled();
  });
});
