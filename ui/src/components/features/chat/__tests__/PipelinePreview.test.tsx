import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApprovalCard } from "../ChatInteractionCards";
import { PipelinePreview, isPipelineSpec } from "../PipelinePreview";

const validate = vi.fn();
vi.mock("@/client/calibration-pipeline/calibration-pipeline", () => ({
  validateCalibrationPipeline: (...args: unknown[]) => validate(...args),
}));

afterEach(() => {
  cleanup();
  validate.mockReset();
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const SPEC = {
  name: "coarse-then-coherence",
  targets: { qids: ["0", "1"] },
  steps: [
    { type: "OneQubitCheck", mode: "scheduled" },
    { type: "FilterByStatus" },
    { type: "CustomOneQubit", step_name: "coherence", tasks: ["CheckT1", "CheckT2Echo"] },
  ],
};

const RESOLVED = {
  valid: true,
  problems: [],
  backend_name: "qubex",
  task_run_count: 12,
  steps: [
    {
      index: 1,
      type: "OneQubitCheck",
      name: "one_qubit_check",
      kind: "calibration",
      tasks: [
        "CheckRabi",
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CheckT1",
        "CheckT2Echo",
        "CheckRamsey",
      ],
    },
    { index: 2, type: "FilterByStatus", name: "filter_by_status", kind: "transform", tasks: [] },
    {
      index: 3,
      type: "CustomOneQubit",
      name: "coherence",
      kind: "calibration",
      tasks: ["CheckT1", "CheckT2Echo"],
    },
  ],
};

describe("isPipelineSpec", () => {
  it("recognises a steps list of typed steps and nothing else", () => {
    expect(isPipelineSpec(SPEC)).toBe(true);
    expect(isPipelineSpec({ steps: [] })).toBe(false);
    expect(isPipelineSpec({ steps: [{ tasks: [] }] })).toBe(false);
    expect(isPipelineSpec("steps")).toBe(false);
    expect(isPipelineSpec(null)).toBe(false);
  });
});

describe("PipelinePreview", () => {
  it("shows the spec as written while QDash checks it, then the resolved tasks", async () => {
    let resolve!: (value: unknown) => void;
    validate.mockReturnValue(new Promise((r) => (resolve = r)));
    wrap(<PipelinePreview chipId="64Qv3" spec={SPEC} />);

    expect(screen.getByText(/Pipeline · coarse-then-coherence/)).toBeTruthy();
    expect(screen.getByText(/Qubits 0, 1/)).toBeTruthy();
    expect(screen.getByText("Checking…")).toBeTruthy();
    // Before validation the default list is only named, not expanded.
    expect(screen.getByText("default task list")).toBeTruthy();
    expect(screen.getByText("coherence")).toBeTruthy();
    expect(validate).toHaveBeenCalledWith({ chip_id: "64Qv3", spec: SPEC });

    resolve({ data: RESOLVED });
    await waitFor(() => expect(screen.getByText(/Ready · 12 task runs/)).toBeTruthy());
    expect(screen.getByText("one_qubit_check")).toBeTruthy();
    expect(screen.queryByText("default task list")).toBeNull();
    // Ten tasks: eight shown, the rest behind "+2 more".
    expect(screen.getAllByText("CheckRabi")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "+2 more" }));
    expect(screen.getAllByText("CheckT2Echo")).toHaveLength(2);
  });

  it("lists problems with their paths", async () => {
    validate.mockResolvedValue({
      data: {
        ...RESOLVED,
        valid: false,
        problems: [{ path: "targets.qids[1]", message: "qubit '1' is not on chip 64Qv3" }],
      },
    });
    wrap(<PipelinePreview chipId="64Qv3" spec={SPEC} />);

    await waitFor(() => expect(screen.getByText("1 problem")).toBeTruthy());
    expect(screen.getByText("targets.qids[1]")).toBeTruthy();
    expect(screen.getByText(/not on chip 64Qv3/)).toBeTruthy();
  });

  it("falls back to the spec when the check fails or has no chip", async () => {
    validate.mockRejectedValue(new Error("offline"));
    wrap(<PipelinePreview chipId="64Qv3" spec={SPEC} />);
    await waitFor(() => expect(screen.getByText("Could not check with QDash")).toBeTruthy());
    expect(screen.getByText("coherence")).toBeTruthy();

    cleanup();
    validate.mockClear();
    wrap(<PipelinePreview chipId={null} spec={SPEC} />);
    expect(screen.getByText(/not checked/)).toBeTruthy();
    expect(validate).not.toHaveBeenCalled();
  });

  it("collapses and expands the step list", async () => {
    validate.mockResolvedValue({ data: RESOLVED });
    wrap(<PipelinePreview chipId="64Qv3" spec={SPEC} />);
    await waitFor(() => expect(screen.getByText("one_qubit_check")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /3 steps/ }));
    expect(screen.queryByText("one_qubit_check")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /3 steps/ }));
    expect(screen.getByText("one_qubit_check")).toBeTruthy();
  });
});

describe("ApprovalCard with a pipeline spec", () => {
  it("renders the preview instead of the raw spec JSON and keeps the other arguments", async () => {
    validate.mockResolvedValue({ data: RESOLVED });
    const onDecide = vi.fn();
    wrap(
      <ApprovalCard
        approval={{
          id: "call-9",
          tool: "qdash_run_pipeline",
          label: "Run calibration pipeline",
          args: { chipId: "64Qv3", spec: SPEC },
        }}
        state={{ active: true, onAnswer: vi.fn(), onDecide, onOther: vi.fn() }}
      />,
    );

    expect(screen.getByTestId("pipeline-preview")).toBeTruthy();
    expect(screen.getByText("chipId")).toBeTruthy();
    expect(screen.getByText("64Qv3")).toBeTruthy();
    expect(screen.queryByText("spec")).toBeNull();
    expect(validate).toHaveBeenCalledWith({ chip_id: "64Qv3", spec: SPEC });
    await waitFor(() => expect(screen.getByText(/Ready · 12 task runs/)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /Approve/ }));
    expect(onDecide).toHaveBeenCalledWith("call-9", true, "Approved: Run calibration pipeline");
  });
});
