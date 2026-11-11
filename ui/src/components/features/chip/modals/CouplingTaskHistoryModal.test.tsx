import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CouplingTaskHistoryModal } from "@/components/features/chip/modals/CouplingTaskHistoryModal";

const mocks = vi.hoisted(() => ({
  task: {
    task_id: "task-1",
    name: "CheckCrossResonance",
    status: "completed",
    execution_id: "exec-1",
    qid: "0-1",
    end_at: "2026-11-10T00:00:00Z",
    figure_path: ["/fig/a.png", "/fig/b.png", "/fig/c.png"],
    json_figure_path: ["/fig/a.json", "/fig/b.json", "/fig/c.json"],
  } as Record<string, unknown>,
}));

vi.mock("@/client/task-result/task-result", () => ({
  useGetCouplingTaskHistory: () => ({
    data: { data: { data: { "task-1": mocks.task } } },
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("@/client/execution/execution", () => ({
  useGetExecution: () => ({
    data: { data: { task: [mocks.task] } },
    isLoading: false,
  }),
}));

vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({ openMiniChat: vi.fn() }),
}));
vi.mock("@/hooks/useManualOverrides", () => ({
  useManualOverrides: () => ({}),
}));
vi.mock("@/components/charts/TaskFigure", () => ({
  // Probe exposing the props the modal passes, as the lightbox flow lives in TaskFigure.
  TaskFigure: (props: { path?: string; jsonFigurePath?: string; taskId?: string }) => (
    <div
      data-testid="static-figure"
      data-path={props.path ?? ""}
      data-json-path={props.jsonFigurePath ?? ""}
      data-task-id={props.taskId ?? ""}
    />
  ),
}));
vi.mock("@/components/features/chip/TaskArtifactDownloads", () => ({
  TaskArtifactDownloads: () => null,
}));
vi.mock("@/components/features/metrics/ParametersTable", () => ({
  ParametersTable: () => null,
}));
vi.mock("@/components/features/evaluations/AskAiButton", () => ({
  AskAiButton: () => null,
}));
vi.mock("@/components/features/provenance/ParameterLineageDialog", () => ({
  LineageButton: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}));
vi.mock("@/components/features/evaluations/TaskResultEvaluations", () => ({
  TaskResultEvaluations: () => null,
}));
vi.mock("@/components/features/forum/TaskResultThreads", () => ({
  TaskResultThreads: () => null,
}));
vi.mock("@/components/features/metrics/TaskResultMemo", () => ({
  TaskResultMemo: () => null,
}));

// The modal renders the details column twice (mobile tab and desktop column); scope to one.
function desktopDetails() {
  const regions = screen.getAllByText("Task Details");
  return within(regions[regions.length - 1].closest(".flex.flex-col") as HTMLElement);
}

function renderModal() {
  return render(
    <CouplingTaskHistoryModal
      chipId="chip-1"
      couplingId="0-1"
      taskName="CheckCrossResonance"
      isOpen
      onClose={vi.fn()}
    />,
  );
}

describe("CouplingTaskHistoryModal figures", () => {
  beforeEach(() => {
    mocks.task.figure_path = ["/fig/a.png", "/fig/b.png", "/fig/c.png"];
    mocks.task.json_figure_path = ["/fig/a.json", "/fig/b.json", "/fig/c.json"];
  });
  afterEach(() => cleanup());

  it("pairs each static figure with its JSON figure, like the qubit modal", () => {
    renderModal();
    const figures = desktopDetails().getAllByTestId("static-figure");

    expect(figures.map((f) => f.dataset.path)).toEqual(["/fig/a.png", "/fig/b.png", "/fig/c.png"]);
    expect(figures.map((f) => f.dataset.jsonPath)).toEqual([
      "/fig/a.json",
      "/fig/b.json",
      "/fig/c.json",
    ]);
  });

  it("has no coupling-only interactive toggle; the lightbox owns that switch", () => {
    renderModal();
    const details = desktopDetails();

    expect(details.queryByRole("button", { name: "Interactive" })).toBeNull();
    expect(details.queryByRole("button", { name: "Static" })).toBeNull();
    expect(details.queryByRole("button", { name: "Next figure" })).toBeNull();
  });

  it("leaves a figure without a matching JSON figure static-only", () => {
    mocks.task.json_figure_path = ["/fig/a.json"];
    renderModal();
    const figures = desktopDetails().getAllByTestId("static-figure");

    expect(figures.map((f) => f.dataset.jsonPath)).toEqual(["/fig/a.json", "", ""]);
  });

  it("falls back to loading the figure by task ID when the task has no figure paths", () => {
    mocks.task.figure_path = [];
    renderModal();
    const figures = desktopDetails().getAllByTestId("static-figure");

    expect(figures).toHaveLength(1);
    expect(figures[0].dataset.taskId).toBe("task-1");
    expect(figures[0].dataset.path).toBe("");
  });
});
