import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildEvaluationRunRequest, EvaluationRequestModal } from "../EvaluationRequestModal";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("@/components/ui/Toast", () => ({ useToast: () => toast }));

const mutateAsync = vi.fn();
vi.mock("@/client/evaluation/evaluation", () => ({
  useCreateEvaluationRun: () => ({ mutateAsync, isPending: false }),
  getListEvaluationRunsQueryKey: () => ["/evaluations/runs"],
  getListEvaluationsQueryKey: (params: unknown) => ["/evaluations", params],
}));

const scope = {
  chipId: "64Qv3",
  taskName: "CheckRabi",
  entityType: "qubit" as const,
  trigger: "bulk" as const,
};

afterEach(() => {
  cleanup();
  mutateAsync.mockReset();
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("buildEvaluationRunRequest", () => {
  it("carries scope, mode and a trimmed question; omits what is not set", () => {
    expect(buildEvaluationRunRequest(scope, "direct", "  ")).toEqual({
      chip_id: "64Qv3",
      task: "CheckRabi",
      entity_type: "qubit",
      trigger: "bulk",
      mode: "direct",
    });
    expect(
      buildEvaluationRunRequest(
        { ...scope, trigger: "single", taskIds: ["t1"], date: "20261011" },
        "planner",
        " Why? ",
      ),
    ).toEqual({
      chip_id: "64Qv3",
      task: "CheckRabi",
      entity_type: "qubit",
      trigger: "single",
      mode: "planner",
      date: "20261011",
      task_ids: ["t1"],
      question: "Why?",
    });
  });
});

describe("EvaluationRequestModal", () => {
  it("starts a planner run with the question and offers to open it", async () => {
    mutateAsync.mockResolvedValue({
      data: {
        run: { run_id: "evr_9" },
        task_ids: ["t1", "t2"],
        skipped: { "7": "no figure" },
      },
    });
    const onClose = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <EvaluationRequestModal
          isOpen
          onClose={onClose}
          scope={scope}
          scopeLabel="all qubits on 64Qv3"
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByLabelText(/Planner/));
    fireEvent.change(screen.getByPlaceholderText(/Is the decay fit trustworthy/), {
      target: { value: "Is the fit trustworthy?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Evaluate$/ }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(mutateAsync).toHaveBeenCalledWith({
      data: {
        chip_id: "64Qv3",
        task: "CheckRabi",
        entity_type: "qubit",
        trigger: "bulk",
        mode: "planner",
        question: "Is the fit trustworthy?",
      },
    });
    expect(toast.success).toHaveBeenCalledWith(
      "Evaluation started: 2 task results queued",
      expect.objectContaining({ description: "1 skipped (no evaluable result)" }),
    );
    const options = toast.success.mock.calls[0][1] as { action: { onClick: () => void } };
    options.action.onClick();
    expect(push).toHaveBeenCalledWith("/evaluations/evr_9");
  });

  it("reports the API's reason when nothing could be queued", async () => {
    mutateAsync.mockRejectedValue({
      response: { data: { detail: "no evaluable result of CheckRabi on 64Qv3 (0: no figure)" } },
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <EvaluationRequestModal
          isOpen
          onClose={vi.fn()}
          scope={scope}
          scopeLabel="all qubits on 64Qv3"
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /^Evaluate$/ }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "no evaluable result of CheckRabi on 64Qv3 (0: no figure)",
      ),
    );
  });
});
