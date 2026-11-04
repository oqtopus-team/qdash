import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskResultEvaluations } from "../TaskResultEvaluations";

const listEvaluations = vi.fn();
vi.mock("@/client/evaluation/evaluation", () => ({
  useListEvaluations: (...args: unknown[]) => listEvaluations(...args),
  useCreateEvaluationRun: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateKnowledgeDraft: () => ({ mutateAsync: vi.fn(), isPending: false }),
  getListEvaluationRunsQueryKey: () => ["/evaluations/runs"],
  getListEvaluationsQueryKey: (params: unknown) => ["/evaluations", params],
  useSetEvaluationVerdict: () => ({ mutate: vi.fn(), isPending: false }),
  getGetEvaluationRunQueryKey: (runId: string) => ["/evaluations/runs", runId],
}));
const getTaskResult = vi.fn();
vi.mock("@/client/task/task", () => ({
  useGetTaskResult: (...args: unknown[]) => getTaskResult(...args),
}));
const project = vi.hoisted(() => ({ canEdit: true }));
vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => project }));
const openTaskChat = vi.fn();
vi.mock("@/contexts/ChatDockContext", () => ({ useChatDock: () => ({ openTaskChat }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));

/** Renders the evaluations section with optional props. */
function renderSection(props: Partial<Parameters<typeof TaskResultEvaluations>[0]> = {}) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TaskResultEvaluations taskId="t1" {...props} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  listEvaluations.mockReset();
  getTaskResult.mockReset();
  openTaskChat.mockClear();
  project.canEdit = true;
});

describe("TaskResultEvaluations", () => {
  it("fetches the result when a modal only knows its id, then offers the same request flow", () => {
    listEvaluations.mockReturnValue({ data: { data: { evaluations: [] } } });
    getTaskResult.mockReturnValue({
      data: {
        data: {
          task_id: "t1",
          task_name: "CheckRabi",
          qid: "Q05",
          chip_id: "64Qv3",
          execution_id: "20261019-001",
        },
      },
    });
    renderSection();

    expect(getTaskResult).toHaveBeenCalledWith(
      "t1",
      expect.objectContaining({ query: expect.objectContaining({ enabled: true }) }),
    );
    const askAi = screen.getByRole("button", { name: /Ask AI/ });
    expect((askAi as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(askAi);
    // The chip page's modal, plus the chat as a third way to ask.
    expect(screen.getByText("Ask AI", { selector: "h2, [role=heading], div" })).toBeTruthy();
    expect(screen.getByLabelText(/Fixed prompt/)).toBeTruthy();
    expect(screen.getByLabelText(/Via Copilot/)).toBeTruthy();
    expect(screen.getByLabelText(/Chat with Copilot/)).toBeTruthy();
    expect(screen.getAllByText(/CheckRabi · Q05/).length).toBeGreaterThan(0);

    // Choosing the chat opens it about this result, with the dock by default.
    fireEvent.click(screen.getByLabelText(/Chat with Copilot/));
    fireEvent.click(screen.getByRole("button", { name: /Open chat/ }));
    expect(openTaskChat).toHaveBeenCalledWith({
      taskName: "CheckRabi",
      chipId: "64Qv3",
      qid: "Q05",
      executionId: "20261019-001",
      taskId: "t1",
    });
  });

  it("opens the chat the way the surface wants, when told how", () => {
    listEvaluations.mockReturnValue({ data: { data: { evaluations: [] } } });
    getTaskResult.mockReturnValue({ data: undefined });
    const onChat = vi.fn();
    renderSection({
      taskName: "CheckRabi",
      qid: "Q05",
      chipId: "64Qv3",
      executionId: "e1",
      onChat,
    });
    fireEvent.click(screen.getByRole("button", { name: /Ask AI/ }));
    fireEvent.click(screen.getByLabelText(/Chat with Copilot/));
    fireEvent.click(screen.getByRole("button", { name: /Open chat/ }));
    expect(onChat).toHaveBeenCalled();
    expect(openTaskChat).not.toHaveBeenCalled();
  });

  it("sends a viewer straight to the chat", () => {
    project.canEdit = false;
    listEvaluations.mockReturnValue({ data: { data: { evaluations: [] } } });
    getTaskResult.mockReturnValue({ data: undefined });
    renderSection({ taskName: "CheckRabi", qid: "Q05", chipId: "64Qv3", executionId: "e1" });
    fireEvent.click(screen.getByRole("button", { name: /Ask AI/ }));
    expect(screen.queryByLabelText(/Fixed prompt/)).toBeNull();
    expect(openTaskChat).toHaveBeenCalled();
  });

  it("does not fetch the result when the page already knows it", () => {
    listEvaluations.mockReturnValue({ data: { data: { evaluations: [] } } });
    getTaskResult.mockReturnValue({ data: undefined });
    renderSection({ taskName: "CheckRabi", qid: "Q05", chipId: "64Qv3", executionId: "e1" });
    expect(getTaskResult).toHaveBeenCalledWith(
      "t1",
      expect.objectContaining({ query: expect.objectContaining({ enabled: false }) }),
    );
    expect((screen.getByRole("button", { name: /Ask AI/ }) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("keeps Ask AI disabled until the result is known", () => {
    listEvaluations.mockReturnValue({ data: { data: { evaluations: [] } } });
    getTaskResult.mockReturnValue({ data: undefined });
    renderSection();
    expect((screen.getByRole("button", { name: /Ask AI/ }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("names what is missing in the Ask AI tooltip", () => {
    listEvaluations.mockReturnValue({ data: { data: { evaluations: [] } } });
    getTaskResult.mockReturnValue({ data: undefined });
    renderSection({ chipId: "64Qv3", taskName: "CheckRabi" });
    expect(screen.getByRole("button", { name: /Ask AI/ }).getAttribute("title")).toBe(
      "Missing qid",
    );
    cleanup();
    renderSection();
    expect(screen.getByRole("button", { name: /Ask AI/ }).getAttribute("title")).toBe(
      "Missing chip / task / qid",
    );
  });
});

describe("TaskResultEvaluations while an evaluation is on its way", () => {
  const known = { chipId: "64Qv3", taskName: "CheckRabi", qid: "Q05", executionId: "e1" };

  it("says so while a listed evaluation is still pending or running", () => {
    listEvaluations.mockReturnValue({
      data: {
        data: {
          evaluations: [
            { evaluation_id: "ev1", run_id: "r1", task_id: "t1", status: "running", output: null },
          ],
        },
      },
    });
    getTaskResult.mockReturnValue({ data: undefined });
    renderSection(known);

    expect(screen.getByRole("status")).toHaveTextContent("Evaluating");
  });

  it("shows nothing extra when every evaluation has finished", () => {
    listEvaluations.mockReturnValue({
      data: {
        data: {
          evaluations: [
            {
              evaluation_id: "ev1",
              run_id: "r1",
              task_id: "t1",
              status: "completed",
              output: { complete: true },
            },
          ],
        },
      },
    });
    getTaskResult.mockReturnValue({ data: undefined });
    renderSection(known);

    expect(screen.queryByRole("status")).toBeNull();
  });
});
