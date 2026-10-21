import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildEvaluationRunRequest,
  EvaluationRequestModal,
  evaluationTargets,
} from "../EvaluationRequestModal";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("@/components/ui/Toast", () => ({ useToast: () => toast }));

const mutateAsync = vi.fn();
const uploadDraft = vi.fn();
vi.mock("@/client/evaluation/evaluation", () => ({
  useCreateEvaluationRun: () => ({ mutateAsync, isPending: false }),
  useCreateKnowledgeDraft: () => ({ mutateAsync: uploadDraft, isPending: false }),
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
  uploadDraft.mockReset();
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("evaluationTargets", () => {
  it("lists the entities of a chip view in natural order, saying which cannot be judged", () => {
    expect(
      evaluationTargets({
        Q10: { task_id: "t10", status: "completed", figure_path: ["/f.png"] },
        Q2: { task_id: "t2", status: "running", figure_path: ["/f.png"] },
        Q1: { task_id: "t1", status: "failed", figure_path: [] },
        Q3: { task_id: "t3", status: "completed", figure_path: ["/f.png"] },
      }),
    ).toEqual([
      { qid: "Q1", blocked: "no figure" },
      { qid: "Q2", blocked: "not finished" },
      { qid: "Q3" },
      { qid: "Q10" },
    ]);
    expect(evaluationTargets(undefined)).toEqual([]);
  });
});

describe("buildEvaluationRunRequest", () => {
  it("narrows the run to chosen entities only when some are given", () => {
    expect(buildEvaluationRunRequest(scope, "direct", false, ["Q1", "Q3"]).qids).toEqual([
      "Q1",
      "Q3",
    ]);
    expect("qids" in buildEvaluationRunRequest(scope, "direct", false, [])).toBe(false);
  });

  it("asks for labeled examples only when the box is ticked", () => {
    expect(buildEvaluationRunRequest(scope, "direct", true).with_examples).toBe(true);
    expect("with_examples" in buildEvaluationRunRequest(scope, "direct")).toBe(false);
  });

  it("carries scope, mode and a knowledge draft; omits what is not set", () => {
    expect(buildEvaluationRunRequest(scope, "direct")).toEqual({
      chip_id: "64Qv3",
      task: "CheckRabi",
      entity_type: "qubit",
      trigger: "bulk",
      mode: "direct",
    });
    expect(
      buildEvaluationRunRequest(
        { ...scope, trigger: "single", taskIds: ["t1"], date: "20261011" },
        "direct",
        false,
        undefined,
        "ab12",
      ),
    ).toEqual({
      chip_id: "64Qv3",
      task: "CheckRabi",
      entity_type: "qubit",
      trigger: "single",
      mode: "direct",
      date: "20261011",
      task_ids: ["t1"],
      knowledge_draft_id: "ab12",
    });
  });
});

describe("EvaluationRequestModal", () => {
  it("starts a planner run and offers to open it", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: /^Evaluate$/ }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(mutateAsync).toHaveBeenCalledWith({
      data: {
        chip_id: "64Qv3",
        task: "CheckRabi",
        entity_type: "qubit",
        trigger: "bulk",
        mode: "planner",
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
    expect(screen.queryByTestId("knowledge-draft-input")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Open chat/ }));
    expect(onChat).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("lets the person narrow a chip-wide run to some entities", async () => {
    mutateAsync.mockResolvedValue({
      data: { run: { run_id: "evr_10" }, task_ids: ["t1"], skipped: {} },
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <EvaluationRequestModal
          isOpen
          onClose={vi.fn()}
          scope={{
            ...scope,
            targets: [{ qid: "Q1" }, { qid: "Q2", blocked: "no figure" }, { qid: "Q3" }],
          }}
          scopeLabel="all qubits on 64Qv3"
        />
      </QueryClientProvider>,
    );
    // Everything evaluable starts selected, and the blocked one cannot be ticked.
    const picker = screen.getByTestId("target-picker");
    expect(picker.textContent).toContain("2 of 2 selected");
    expect((screen.getByLabelText("Q2") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByTestId("request-summary").textContent).toContain("all qubits on 64Qv3");

    fireEvent.click(screen.getByLabelText("Q3"));
    expect(picker.textContent).toContain("1 of 2 selected");
    expect(screen.getByTestId("request-summary").textContent).toContain("1 of 2 qubits on 64Qv3");

    // Nothing chosen: nothing to evaluate.
    fireEvent.click(screen.getByRole("button", { name: /^None$/ }));
    expect((screen.getByRole("button", { name: /^Evaluate$/ }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: /^All$/ }));
    fireEvent.click(screen.getByLabelText("Q3"));

    fireEvent.click(screen.getByRole("button", { name: /^Evaluate$/ }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync).toHaveBeenCalledWith({
      data: expect.objectContaining({ qids: ["Q1"] }),
    });
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

  it("evaluates against an uploaded knowledge draft of the task, in direct mode", async () => {
    uploadDraft.mockResolvedValue({
      data: {
        draft_id: "ab".repeat(32),
        task_name: "CheckRabi",
        filename: "rabi.zip",
        uploaded_by: "alice",
        created_at: "2026-10-21T00:00:00Z",
        warnings: ["CheckRabi/examples/x.md: outcome '' must be one of expected"],
        reference: {
          statuses: { SUCCESS: "ok", LOW_CONTRAST: "small" },
          parameters: { f: "float" },
        },
        example_count: 2,
        figure_count: 3,
      },
    });
    mutateAsync.mockResolvedValue({
      data: { run: { run_id: "evr_d" }, task_ids: ["t1"], skipped: {} },
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
    fireEvent.click(screen.getByLabelText(/Via Copilot/));

    const file = new File(["zip"], "rabi.zip", { type: "application/zip" });
    fireEvent.change(screen.getByTestId("knowledge-draft-input"), { target: { files: [file] } });

    const draft = await screen.findByTestId("knowledge-draft");
    expect(uploadDraft).toHaveBeenCalledWith({ data: { file } });
    expect(draft.textContent).toContain("rabi.zip");
    expect(draft.textContent).toContain("SUCCESS, LOW_CONTRAST");
    expect(draft.textContent).toContain("must be one of expected");
    // Copilot reads the shared knowledge, so a draft runs with the fixed prompt.
    expect((screen.getByLabelText(/Fixed prompt/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/Via Copilot/) as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByTestId("request-summary").textContent).toContain(
      "against the knowledge draft rabi.zip",
    );

    fireEvent.click(screen.getByRole("button", { name: /^Evaluate$/ }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync).toHaveBeenCalledWith({
      data: expect.objectContaining({ mode: "direct", knowledge_draft_id: "ab".repeat(32) }),
    });
  });

  it("refuses a draft of another task and keeps the shared knowledge", async () => {
    uploadDraft.mockResolvedValue({
      data: {
        draft_id: "cd".repeat(32),
        task_name: "CheckT1",
        filename: "t1.zip",
        uploaded_by: "alice",
        created_at: "2026-10-21T00:00:00Z",
        reference: {},
        example_count: 0,
        figure_count: 0,
      },
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
    const file = new File(["zip"], "t1.zip", { type: "application/zip" });
    fireEvent.change(screen.getByTestId("knowledge-draft-input"), { target: { files: [file] } });

    expect(await screen.findByText("t1.zip describes CheckT1, not CheckRabi.")).toBeTruthy();
    expect(screen.queryByTestId("knowledge-draft")).toBeNull();
    expect(screen.getByTestId("request-summary").textContent).not.toContain("knowledge draft");
  });

  it("shows why an upload was refused", async () => {
    uploadDraft.mockRejectedValue({
      response: {
        data: { detail: "CheckRabi/run.py: only .jpeg, .jpg, .md, .png, .webp files are allowed" },
      },
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
    const file = new File(["zip"], "bad.zip", { type: "application/zip" });
    fireEvent.change(screen.getByTestId("knowledge-draft-input"), { target: { files: [file] } });

    expect(await screen.findByText(/run\.py: only/)).toBeTruthy();
  });
});
