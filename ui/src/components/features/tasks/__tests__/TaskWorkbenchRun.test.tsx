import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TaskInfo, TaskResultResponse } from "@/schemas";

import { TaskWorkbench } from "../TaskWorkbench";

const mocks = vi.hoisted(() => ({
  availability: vi.fn(),
  refetchAvailability: vi.fn(),
  check: vi.fn(),
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
  checkExecutionAvailability: mocks.check,
  useGetExecution: mocks.execution,
  getGetExecutionLockStatusQueryKey: () => ["execution-lock"],
}));
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: "project-1" }),
}));
vi.mock("@/hooks/useExecutionAvailability", () => ({
  useExecutionAvailability: mocks.availability,
}));
vi.mock("@/lib/api/custom-instance", () => ({
  AXIOS_INSTANCE: { post: mocks.post },
}));
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
    qubit_frequency: {
      resolution: "database_required",
      value_type: "float",
      unit: "GHz",
    },
  },
};

function renderWorkbench(
  taskOverrides: Partial<TaskInfo> = {},
  searchParams = "?chip=chip-1&target=0",
  sourceTask?: TaskResultResponse,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <NuqsTestingAdapter searchParams={searchParams} hasMemory>
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
  mocks.chips.mockReturnValue({
    data: { data: { chips: [{ chip_id: "chip-1" }] } },
  });
  mocks.refetchAvailability.mockResolvedValue({});
  mocks.availability.mockReturnValue({
    disabledReason: null,
    refetch: mocks.refetchAvailability,
  });
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

  it("collapses input groups declared by task catalog metadata", () => {
    renderWorkbench({
      input_parameters: {
        qubit_frequency: { value_type: "float" },
        normalization_reference: {
          value_type: "float",
          ui_group: "Normalization context",
          ui_group_collapsed: true,
        },
      },
    });

    expect(screen.getByRole("textbox", { name: "qubit_frequency" })).toBeTruthy();
    const group = screen.getByText("Normalization context").closest("details");
    expect(group).not.toBeNull();
    expect(group).not.toHaveAttribute("open");
    expect(screen.getByRole("textbox", { name: "normalization_reference" })).toBeTruthy();
  });

  it("prefills the current form and submits all entered values through the catalog API", async () => {
    renderWorkbench(
      {
        input_parameters: {
          qubit_frequency: { value: 5.2, value_type: "float" },
        },
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
    fireEvent.change(screen.getByRole("textbox", { name: "shots" }), {
      target: { value: "200" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith("/tasks/CheckCoarseReadoutParams/execute", {
        chip_id: "source-chip",
        qid: "2",
        backend_name: "qubex",
        source_task_id: "source-task",
        run_parameter_overrides: { shots: 200 },
        input_parameter_overrides: { qubit_frequency: 5.2 },
        persist_output_parameters: false,
        update_params: false,
        reconfigure: false,
      }),
    );
    expect(mocks.post).toHaveBeenCalledTimes(1);
  });

  it("runs a sweep parameter in its declared form as a bare value", async () => {
    renderWorkbench({
      run_parameters: {
        time_range: { value: [0, 401, 8], value_type: "range", unit: "ns" },
      },
    });
    expect(screen.getByRole("combobox", { name: "time_range type" })).toHaveValue("range");
    expect(screen.getByRole("textbox", { name: "time_range start" })).toHaveValue("0");
    expect(screen.getByRole("textbox", { name: "time_range stop" })).toHaveValue("401");
    expect(screen.getByRole("textbox", { name: "time_range step" })).toHaveValue("8");
    expect(screen.getByText("51 points: 0 to 400")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "time_range step" }), {
      target: { value: "16" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith(
        "/tasks/CheckCoarseReadoutParams/execute",
        expect.objectContaining({
          run_parameter_overrides: { time_range: [0, 401, 16] },
        }),
      ),
    );
  });

  it("runs a sweep parameter in another form with its type", async () => {
    renderWorkbench({
      run_parameters: {
        time_range: { value: [0, 401, 8], value_type: "range", unit: "ns" },
      },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "time_range type" }), {
      target: { value: "np.linspace" },
    });
    // The new form starts from the same 51 points the range produced.
    expect(screen.getByRole("textbox", { name: "time_range stop" })).toHaveValue("400");
    expect(screen.getByRole("textbox", { name: "time_range num" })).toHaveValue("51");
    expect(screen.getByText("51 points: 0 to 400")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "time_range num" }), {
      target: { value: "11" },
    });
    expect(screen.getByText("11 points: 0 to 400")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith(
        "/tasks/CheckCoarseReadoutParams/execute",
        expect.objectContaining({
          run_parameter_overrides: {
            time_range: { value: [0, 400, 11], value_type: "np.linspace" },
          },
        }),
      ),
    );
  });

  it("switches a sweep to explicit values starting from the generated points", async () => {
    renderWorkbench({
      run_parameters: {
        time_range: { value: [0, 41, 10], value_type: "range", unit: "ns" },
      },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "time_range type" }), {
      target: { value: "list" },
    });
    expect(screen.getByRole("textbox", { name: "time_range values" })).toHaveValue(
      "[0,10,20,30,40]",
    );
    fireEvent.change(screen.getByRole("textbox", { name: "time_range values" }), {
      target: { value: "[0, 10, 40, 160]" },
    });
    expect(screen.getByText("4 points: 0 to 160")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith(
        "/tasks/CheckCoarseReadoutParams/execute",
        expect.objectContaining({
          run_parameter_overrides: {
            time_range: { value: [0, 10, 40, 160], value_type: "list" },
          },
        }),
      ),
    );
  });

  it("switches a sweep from explicit values to a form that spans them", () => {
    renderWorkbench({
      run_parameters: {
        time_range: { value: [0, 41, 10], value_type: "range", unit: "ns" },
      },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "time_range type" }), {
      target: { value: "list" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "time_range values" }), {
      target: { value: "[1, 10, 100, 1000]" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "time_range type" }), {
      target: { value: "np.logspace" },
    });
    expect(screen.getByRole("textbox", { name: "time_range start (10^)" })).toHaveValue("0");
    expect(screen.getByRole("textbox", { name: "time_range stop (10^)" })).toHaveValue("3");
    expect(screen.getByRole("textbox", { name: "time_range num" })).toHaveValue("4");
    expect(screen.getByText("4 points: 1 to 1000")).toBeInTheDocument();
  });

  it("keeps the typed arguments when the new form cannot express the sweep", () => {
    renderWorkbench({
      run_parameters: {
        time_range: {
          value: [0, 1, 11],
          value_type: "np.linspace",
          unit: "ns",
        },
      },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "time_range type" }), {
      target: { value: "range" },
    });
    expect(screen.getByRole("textbox", { name: "time_range stop" })).toHaveValue("1");
    expect(screen.getByRole("textbox", { name: "time_range step" })).toHaveValue("11");
  });

  it("rejects a sweep that produces no points before submitting", async () => {
    renderWorkbench({
      run_parameters: {
        time_range: { value: [0, 401, 8], value_type: "range", unit: "ns" },
      },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "time_range step" }), {
      target: { value: "0" },
    });
    expect(screen.getByText("Enter numbers that produce a sweep.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() =>
      expect(mocks.toast.error).toHaveBeenCalledWith(
        "Enter numbers that produce a range sweep for time_range",
      ),
    );
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("restores the sweep form of a source result", () => {
    renderWorkbench(
      {
        run_parameters: {
          time_range: { value: [0, 401, 8], value_type: "range", unit: "ns" },
        },
      },
      undefined,
      {
        ...source,
        run_parameters: {
          time_range: {
            value: [2, 5, 11],
            value_type: "np.logspace",
            unit: "ns",
          },
        },
      },
    );
    expect(screen.getByRole("combobox", { name: "time_range type" })).toHaveValue("np.logspace");
    expect(screen.getByRole("textbox", { name: "time_range start (10^)" })).toHaveValue("2");
    expect(screen.getByText("11 points: 100 to 100000")).toBeInTheDocument();
  });

  it("uses the same save and reconfigure controls for re-execution", async () => {
    renderWorkbench(
      {
        input_parameters: {
          qubit_frequency: { value: 5.2, value_type: "float" },
        },
      },
      undefined,
      source,
    );
    const save = screen.getByRole("checkbox", {
      name: /Save calibrated outputs to DB/,
    });
    const reconfigure = screen.getByRole("checkbox", {
      name: /Reconfigure hardware first/,
    });
    expect(save).not.toBeChecked();
    expect(reconfigure).not.toBeChecked();
    expect(screen.queryByRole("checkbox", { name: /Update backend params/ })).toBeNull();
    expect(
      screen.queryByText("This run can change the calibration values used by later tasks."),
    ).toBeNull();
    fireEvent.click(save);
    fireEvent.click(reconfigure);
    expect(
      screen.getByText("This run can change the calibration values used by later tasks."),
    ).toBeTruthy();
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
        reconfigure: true,
      }),
    );
  });

  it("rejects invalid edited snapshot values before submitting", async () => {
    renderWorkbench(
      { run_parameters: { shots: { value: 100, value_type: "int" } } },
      undefined,
      source,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "shots" }), {
      target: { value: "1.5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalled());
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("reloads current input values only on request and submits them as snapshot overrides", async () => {
    mocks.qubit.mockResolvedValue({
      data: { data: { qubit_frequency: { value: 5.5 } } },
    });
    renderWorkbench(
      {
        input_parameters: {
          qubit_frequency: { value: 5.2, value_type: "float" },
        },
      },
      undefined,
      source,
    );
    expect(mocks.qubit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "qubit_frequency" })).toHaveValue("5.5"),
    );
    expect(mocks.qubit).toHaveBeenCalledWith("source-chip", "2");
    expect(mocks.refetchAvailability).toHaveBeenCalledTimes(1);
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
      {
        input_parameters: {
          qubit_frequency: { value: 5.2, value_type: "float" },
        },
      },
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

  it("allows a missing optional database input when reloading a source task", async () => {
    mocks.qubit.mockResolvedValue({ data: { data: {} } });
    renderWorkbench(
      {
        input_parameters: {
          anharmonicity: {
            resolution: "database_optional",
            user_override: "forbidden",
            value_type: "float",
          },
        },
      },
      undefined,
      { ...source, input_parameters: {} },
    );

    fireEvent.click(screen.getByRole("button", { name: "Reload" }));

    await waitFor(() => expect(mocks.refetchAvailability).toHaveBeenCalledTimes(1));
    expect(mocks.toast.error).not.toHaveBeenCalledWith("No current value found for anharmonicity");
    expect(screen.getByRole("textbox", { name: "anharmonicity" })).toHaveValue("");
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
        run_parameters: {
          removed: { value: 2 },
          shots: { value: 1.5, value_type: "float" },
        },
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
        expect.objectContaining({
          chip_id: "chip-1",
          qid: "0",
          input_parameter_overrides: {},
        }),
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

  it("blocks conflicting targets and explains why", () => {
    mocks.availability.mockReturnValue({
      disabledReason: "Another calibration is using hardware required by this run.",
      isConflict: true,
    });
    renderWorkbench();
    const button = screen.getByRole("button", { name: "Run task" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(/Another calibration is using hardware/);
    expect(screen.getByRole("alert")).toHaveClass("alert-warning", "alert-soft");
    fireEvent.click(button);
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.availability).toHaveBeenCalledWith(
      { parameters: { chip_id: "chip-1", qid: "0" } },
      true,
    );
  });

  it("checks a loaded QID before allowing execution without a Run click", async () => {
    const { useExecutionAvailability } = await vi.importActual<
      typeof import("@/hooks/useExecutionAvailability")
    >("@/hooks/useExecutionAvailability");
    mocks.availability.mockImplementation(useExecutionAvailability);
    let resolve!: (value: unknown) => void;
    mocks.check.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    renderWorkbench();
    const button = screen.getByRole("button", { name: "Run task" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("Checking hardware availability…");
    expect(mocks.check).toHaveBeenCalledWith(
      { parameters: { chip_id: "chip-1", qid: "0" } },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    await act(async () => resolve({ data: { available: false, reason: "MUX is busy" } }));
    await waitFor(() => expect(button).toHaveAccessibleDescription("MUX is busy"));
    expect(screen.getByRole("alert")).toHaveTextContent("MUX is busy");
    expect(button).toBeDisabled();
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("keeps Run disabled until Reload has refreshed hardware availability", async () => {
    const { useExecutionAvailability } = await vi.importActual<
      typeof import("@/hooks/useExecutionAvailability")
    >("@/hooks/useExecutionAvailability");
    mocks.availability.mockImplementation(useExecutionAvailability);
    mocks.check.mockResolvedValueOnce({ data: { available: true } });
    mocks.qubit.mockResolvedValue({
      data: { data: { qubit_frequency: { value: 5.5 } } },
    });
    renderWorkbench();
    const button = screen.getByRole("button", { name: "Run task" });
    await waitFor(() => expect(button).toBeEnabled());
    let resolve!: (value: unknown) => void;
    mocks.check.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(button).toBeDisabled();
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /qubit_frequency/ })).toHaveValue("5.5"),
    );
    expect(button).toBeDisabled();
    await act(async () => resolve({ data: { available: false, reason: "MUX is busy" } }));
    await waitFor(() => expect(button).toHaveAccessibleDescription("MUX is busy"));
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("checks a changed QID before enabling Run", async () => {
    const { useExecutionAvailability } = await vi.importActual<
      typeof import("@/hooks/useExecutionAvailability")
    >("@/hooks/useExecutionAvailability");
    mocks.availability.mockImplementation(useExecutionAvailability);
    mocks.check.mockResolvedValueOnce({ data: { available: true } });
    renderWorkbench();
    const button = screen.getByRole("button", { name: "Run task" });
    await waitFor(() => expect(button).toBeEnabled());
    let resolve!: (value: unknown) => void;
    mocks.check.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Qubit or coupling" }), {
      target: { value: "4" },
    });
    expect(button).toBeDisabled();
    await waitFor(() =>
      expect(mocks.check).toHaveBeenLastCalledWith(
        { parameters: { chip_id: "chip-1", qid: "4" } },
        expect.anything(),
      ),
    );
    await act(async () => resolve({ data: { available: false, reason: "MUX is busy" } }));
    await waitFor(() => expect(button).toHaveAccessibleDescription("MUX is busy"));
    expect(button).toBeDisabled();
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it.each([
    "Checking hardware availability…",
    "Unable to check hardware availability. Retrying automatically…",
  ])("blocks starting when availability is unknown: %s", (disabledReason) => {
    mocks.availability.mockReturnValue({ disabledReason });
    renderWorkbench();
    const button = screen.getByRole("button", { name: "Run task" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(disabledReason);
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(button);
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("allows non-conflicting targets", () => {
    renderWorkbench();
    expect(screen.getByRole("button", { name: "Run task" })).toBeEnabled();
  });

  it("still displays a conflict rejected by final API admission", async () => {
    mocks.post.mockRejectedValueOnce({
      response: {
        data: {
          detail: "Another calibration execution is using overlapping hardware resources",
        },
      },
    });
    renderWorkbench();
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    await waitFor(() =>
      expect(mocks.toast.error).toHaveBeenCalledWith(
        "Another calibration execution is using overlapping hardware resources",
      ),
    );
  });

  it("explains when a previous execution is still being awaited", () => {
    renderWorkbench({}, "?chip=chip-1&target=0&execution=execution-1");
    expect(screen.getByRole("button", { name: "Starting…" })).toHaveAccessibleDescription(
      "Waiting for this execution to finish before starting another run.",
    );
    expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled();
  });

  it("shows Starting while submission is pending", async () => {
    let resolve!: (value: unknown) => void;
    mocks.post.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    renderWorkbench();
    fireEvent.click(screen.getByRole("button", { name: "Run task" }));
    expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled();
    await act(async () => resolve({ data: { execution_id: "execution-1" } }));
  });

  it.each([
    ["scheduled", "Starting…", true],
    ["pending", "Starting…", true],
    ["running", "Running…", true],
    ["cancelling", "Cancelling…", true],
    ["completed", "Run task", false],
    ["failed", "Run task", false],
    ["cancelled", "Run task", false],
  ])("labels a %s execution as %s", (status, label, disabled) => {
    mocks.execution.mockReturnValue({ data: { data: { status, task: [] } } });
    renderWorkbench({}, "?chip=chip-1&target=0&execution=execution-1");
    const button = screen.getByRole("button", { name: label });
    if (disabled) expect(button).toBeDisabled();
    else expect(button).toBeEnabled();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows preparation status before the worker reports task progress", () => {
    mocks.execution.mockReturnValue({
      data: { data: { status: "running", task: [] } },
    });
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
                progress: {
                  current: 13,
                  total: 26,
                  updated_at: new Date().toISOString(),
                },
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
