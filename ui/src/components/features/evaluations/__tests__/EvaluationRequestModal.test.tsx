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
  it("asks for labeled examples only when the box is ticked", () => {
    expect(buildEvaluationRunRequest(scope, "direct", "", true).with_examples).toBe(true);
    expect("with_examples" in buildEvaluationRunRequest(scope, "direct", "")).toBe(false);
  });

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

    fireEvent.click(screen.getByLabelText(/Via Copilot/));
    fireEvent.click(screen.getByLabelText(/In-context/));
    expect(screen.getByTestId("request-summary").textContent).toContain("Via Copilot · In-context");
    fireEvent.click(screen.getByLabelText(/Zero-shot/));
    expect(screen.getByTestId("request-summary").textContent).toContain(
      "all qubits on 64Qv3 with Via Copilot · Zero-shot",
    );
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
      "Evaluation started (Via Copilot · Zero-shot): 2 task results queued",
      expect.objectContaining({ description: "1 skipped (no evaluable result)" }),
    );
    const options = toast.success.mock.calls[0][1] as { action: { onClick: () => void } };
    options.action.onClick();
    expect(push).toHaveBeenCalledWith("/evaluations/evr_9");
  });

  it("offers the chat as a third way to ask only when the surface can open one", () => {
    const { unmount } = render(
      <QueryClientProvider client={new QueryClient()}>
        <EvaluationRequestModal
          isOpen
          onClose={vi.fn()}
          scope={scope}
          scopeLabel="all qubits on 64Qv3"
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Request AI evaluation")).toBeTruthy();
    expect(screen.getByText("Who prepares the prompt")).toBeTruthy();
    expect(screen.queryByText("What to do")).toBeNull();
    expect(screen.queryByLabelText(/Chat with Copilot/)).toBeNull();
    unmount();

    const onChat = vi.fn();
    const onClose = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <EvaluationRequestModal
          isOpen
          onClose={onClose}
          scope={{ ...scope, trigger: "single", taskIds: ["t1"] }}
          scopeLabel="CheckRabi · Q05"
          onChat={onChat}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("What to do")).toBeTruthy();
    expect(screen.getByText("Who prepares the prompt")).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/Chat with Copilot/));
    expect(screen.queryByText("Who prepares the prompt")).toBeNull();
    expect(screen.getByTestId("request-summary").textContent).toContain(
      "Will open a chat about CheckRabi · Q05",
    );
    // Evaluation-only settings step aside; the question is typed in the chat.
    expect(screen.queryByLabelText(/In-context/)).toBeNull();
    expect(screen.queryByPlaceholderText(/Is the decay fit trustworthy/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Open chat/ }));
    expect(onChat).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
    expect(mutateAsync).not.toHaveBeenCalled();
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
