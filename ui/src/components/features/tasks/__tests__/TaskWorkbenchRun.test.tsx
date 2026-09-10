import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TaskInfo } from "@/schemas";

import { TaskWorkbench } from "../TaskWorkbench";

const mocks = vi.hoisted(() => ({
  lock: vi.fn(),
  chips: vi.fn(),
  execution: vi.fn(),
  post: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: mocks.chips,
  getChipCoupling: vi.fn(),
  getChipQubit: vi.fn(),
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
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <NuqsTestingAdapter searchParams={searchParams}>
      <QueryClientProvider client={queryClient}>
        <TaskWorkbench task={{ ...task, ...taskOverrides }} backend="qubex" />
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
