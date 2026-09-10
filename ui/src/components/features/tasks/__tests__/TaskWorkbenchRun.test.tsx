import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TaskInfo, TaskResultResponse } from "@/schemas";

import { TaskWorkbench } from "../TaskWorkbench";

const mocks = vi.hoisted(() => ({
  lock: vi.fn(),
  chips: vi.fn(),
  execution: vi.fn(),
  post: vi.fn(),
  qubit: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: mocks.chips,
  getChipCoupling: vi.fn(),
  getChipQubit: mocks.qubit,
}));
vi.mock("@/client/execution/execution", () => ({
  useGetExecutionLockStatus: mocks.lock,
  useGetExecution: mocks.execution,
  getGetExecutionLockStatusQueryKey: () => ["execution-lock"],
}));
vi.mock("@/lib/api/custom-instance", () => ({ AXIOS_INSTANCE: { post: mocks.post } }));
vi.mock("@/components/ui/Toast", () => ({ useToast: () => mocks.toast }));
vi.mock("@/components/charts/TaskFigure", () => ({ TaskFigure: () => null }));
vi.mock("@/components/features/metrics/ParametersTable", () => ({
  ParametersTable: () => null,
}));

const task: TaskInfo = {
  name: "CheckCoarseReadoutParams",
  class_name: "CheckCoarseReadoutParams",
  file_path: "one_qubit_coarse/check_coarse_readout_params.py",
  task_type: "qubit",
  enabled: true,
  input_parameters: {
    qubit_frequency: { resolution: "database_required", value_type: "float", unit: "GHz" },
  },
};

function renderWorkbench(
  taskOverrides: Partial<TaskInfo> = {},
  searchParams = "?chip=chip-1&target=0",
  sourceTask?: TaskResultResponse,
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <NuqsTestingAdapter searchParams={searchParams}>
      <QueryClientProvider client={queryClient}>
        <TaskWorkbench
          task={{ ...task, ...taskOverrides }}
          backend="qubex"
          sourceTask={sourceTask}
        />
      </QueryClientProvider>
    </NuqsTestingAdapter>,
  );
}

beforeEach(() => {
  mocks.chips.mockReturnValue({ data: { data: { chips: [{ chip_id: "chip-1" }] } } });
  mocks.lock.mockReturnValue({ data: { data: { lock: false } }, isLoading: false });
  mocks.execution.mockReturnValue({});
  mocks.post.mockResolvedValue({ data: { execution_id: "execution-1" } });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TaskWorkbench run availability", () => {
  const source: TaskResultResponse = {
    task_id: "source-task",
    task_name: task.name,
    qid: "2",
    chip_id: "source-chip",
    execution_id: "source-execution",
    status: "completed",
    input_parameters: { qubit_frequency: { value: 5.2, value_type: "float" } },
    output_parameters: {},
    figure_path: [],
    json_figure_path: [],
    raw_data_path: [],
  };

  it("prefills the current form and submits all entered values through the catalog API", async () => {
    renderWorkbench(
      {
        input_parameters: { qubit_frequency: { value: 5.2, value_type: "float" } },
        run_parameters: { shots: { value: 100, value_type: "int" } },
      },
      "?chip=chip-1&target=0",
      source,
    );
    expect(screen.getByRole("combobox", { name: "Chip" })).toHaveValue("source-chip");
    expect(screen.getByRole("combobox", { name: "Chip" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Qubit or coupling" })).toHaveValue("2");
    expect(screen.getByRole("textbox", { name: "Qubit or coupling" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "qubit_frequency" })).toHaveValue("5.2");
    fireEvent.change(screen.getByRole("textbox", { name: "shots" }), { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith("/tasks/CheckCoarseReadoutParams/execute", {
        chip_id: "source-chip",
        qid: "2",
        backend_name: "qubex",
        source_task_id: "source-task",
        run_parameter_overrides: { shots: 200 },
        input_parameter_overrides: { qubit_frequency: 5.2 },
        persist_output_parameters: true,
        update_params: true,
        reconfigure: false,
      }),
    );
    expect(mocks.post).toHaveBeenCalledTimes(1);
  });

  it("submits matching historical values and allows disabling backend updates", async () => {
    renderWorkbench(
      { input_parameters: { qubit_frequency: { value: 5.2, value_type: "float" } } },
      undefined,
      source,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /Update backend params/ }));
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith("/tasks/CheckCoarseReadoutParams/execute", {
        chip_id: "source-chip",
        qid: "2",
        backend_name: "qubex",
        source_task_id: "source-task",
        run_parameter_overrides: {},
        input_parameter_overrides: { qubit_frequency: 5.2 },
        persist_output_parameters: true,
        update_params: false,
        reconfigure: false,
      }),
    );
  });

  it("rejects invalid edited snapshot values before submitting", async () => {
    renderWorkbench(
      { run_parameters: { shots: { value: 100, value_type: "int" } } },
      undefined,
      source,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "shots" }), { target: { value: "1.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalled());
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("reloads current input values only on request and submits them as snapshot overrides", async () => {
    mocks.qubit.mockResolvedValue({ data: { data: { qubit_frequency: { value: 5.5 } } } });
    renderWorkbench(
      { input_parameters: { qubit_frequency: { value: 5.2, value_type: "float" } } },
      undefined,
      source,
    );
    expect(mocks.qubit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "qubit_frequency" })).toHaveValue("5.5"),
    );
    expect(mocks.qubit).toHaveBeenCalledWith("source-chip", "2");
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith(
        "/tasks/CheckCoarseReadoutParams/execute",
        expect.objectContaining({
          run_parameter_overrides: {},
          input_parameter_overrides: { qubit_frequency: 5.5 },
        }),
      ),
    );
  });

  it("keeps the source input when no current calibration value can be found", async () => {
    mocks.qubit.mockResolvedValue({ data: { data: {} } });
    renderWorkbench(
      { input_parameters: { qubit_frequency: { value: 5.2, value_type: "float" } } },
      undefined,
      source,
    );
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    await waitFor(() =>
      expect(mocks.toast.error).toHaveBeenCalledWith("No current value found for qubit_frequency"),
    );
    expect(screen.getByRole("textbox", { name: "qubit_frequency" })).toHaveValue("5.2");
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("skips incompatible historical fields and executes current defaults without old values", async () => {
    renderWorkbench(
      {
        input_parameters: {
          qubit_frequency: { value_type: "int" },
          added_input: { value_type: "float" },
        },
        run_parameters: { shots: { value: 100, value_type: "int" } },
      },
      undefined,
      {
        ...source,
        run_parameters: { removed: { value: 2 }, shots: { value: 1.5, value_type: "float" } },
      },
    );
    expect(screen.getByRole("textbox", { name: "qubit_frequency" })).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "added_input" })).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "shots" })).toHaveValue("100");
    expect(screen.queryByRole("textbox", { name: "removed" })).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(
      "input.qubit_frequency, run.removed, run.shots",
    );
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith(
        "/tasks/CheckCoarseReadoutParams/execute",
        expect.objectContaining({
          input_parameter_overrides: {},
          run_parameter_overrides: { shots: 100 },
        }),
      ),
    );
  });

  it("does not bypass a disabled current task when a source result is supplied", () => {
    renderWorkbench({ enabled: false }, undefined, source);
    expect(screen.getByRole("button", { name: "Run task" })).toBeDisabled();
  });

  it("explains when the selected task is disabled in backend configuration", () => {
    renderWorkbench({ enabled: false });
    const button = screen.getByRole("button", { name: "Run task" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("This task is not enabled for the qubex backend.");
    fireEvent.click(button);
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("allows blank calibration overrides and submits them for runtime resolution", async () => {
    renderWorkbench();
    expect(screen.getByPlaceholderText("Use current value")).toHaveValue("");
    const button = screen.getByRole("button", { name: "Run task" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith(
        "/tasks/CheckCoarseReadoutParams/execute",
        expect.objectContaining({ chip_id: "chip-1", qid: "0", input_parameter_overrides: {} }),
      ),
    );
  });

  it("explains the missing target", () => {
    renderWorkbench({}, "?chip=chip-1");
    expect(screen.getByRole("button", { name: "Run task" })).toHaveAccessibleDescription(
      "Enter a qubit or coupling to run this task.",
    );
    expect(screen.getByRole("button", { name: "Run task" })).toBeDisabled();
  });

  it("defaults to the newest active chip when none is selected", async () => {
    mocks.chips.mockReturnValue({
      data: {
        data: {
          chips: [
            {
              chip_id: "inactive-new",
              activity_status: "inactive",
              installed_at: "2026-06-01T00:00:00Z",
            },
            {
              chip_id: "active-old",
              activity_status: "active",
              installed_at: "2024-06-01T00:00:00Z",
            },
            {
              chip_id: "active-new",
              activity_status: "active",
              installed_at: "2025-06-01T00:00:00Z",
            },
          ],
        },
      },
    });

    renderWorkbench({}, "?target=0");

    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Chip" })).toHaveValue("active-new"),
    );
  });

  it("explains the missing chip", () => {
    mocks.chips.mockReturnValue({ data: { data: { chips: [] } } });
    renderWorkbench({}, "?target=0");
    expect(screen.getByRole("button", { name: "Run task" })).toHaveAccessibleDescription(
      "Select a chip to run this task.",
    );
  });

  it("retains the execution lock and explains why another run cannot start", () => {
    mocks.lock.mockReturnValue({ data: { data: { lock: true } }, isLoading: false });
    renderWorkbench();
    const button = screen.getByRole("button", { name: "Locked" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(/Another calibration execution is running/);
    fireEvent.click(button);
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("explains when lock status is still loading", () => {
    mocks.lock.mockReturnValue({ isLoading: true });
    renderWorkbench();
    expect(screen.getByRole("button", { name: "Run task" })).toHaveAccessibleDescription(
      "Checking whether another calibration is running…",
    );
    expect(screen.getByRole("button", { name: "Run task" })).toBeDisabled();
  });

  it("explains when a previous execution is still being awaited", () => {
    renderWorkbench({}, "?chip=chip-1&target=0&execution=execution-1");
    expect(screen.getByRole("button", { name: "Run task" })).toHaveAccessibleDescription(
      "Waiting for this execution to finish before starting another run.",
    );
    expect(screen.getByRole("button", { name: "Run task" })).toBeDisabled();
  });

  it("shows preparation status before the worker reports task progress", () => {
    mocks.execution.mockReturnValue({ data: { data: { status: "running", task: [] } } });
    renderWorkbench({}, "?chip=chip-1&target=0&execution=execution-1");
    expect(screen.getByText("Preparing measurement")).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("shows one labeled progress bar when measurements arrive", () => {
    mocks.execution.mockReturnValue({
      data: {
        data: {
          status: "running",
          task: [
            {
              name: task.name,
              qid: "0",
              status: "running",
              note: {
                progress: { current: 13, total: 26, updated_at: new Date().toISOString() },
              },
            },
          ],
        },
      },
    });
    renderWorkbench({}, "?chip=chip-1&target=0&execution=execution-1&executionTarget=0");
    expect(screen.getAllByRole("progressbar")).toHaveLength(1);
    expect(screen.getByRole("progressbar", { name: "Measurement progress" })).toHaveAttribute(
      "value",
      "50",
    );
    expect(screen.getByText("13 / 26 points")).toBeTruthy();
  });
});
