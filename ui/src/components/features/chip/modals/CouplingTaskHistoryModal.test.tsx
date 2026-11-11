import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

// Render the dynamically imported PlotlyRenderer as a probe exposing its props.
vi.mock("next/dynamic", () => ({
  default: () =>
    function PlotlyProbe(props: { fullPath: string; sizing?: string; className?: string }) {
      return (
        <div
          data-testid="plotly-renderer"
          data-path={props.fullPath}
          data-sizing={props.sizing ?? "figure"}
          className={props.className}
        />
      );
    },
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
  TaskFigure: ({ path }: { path?: string }) => <div data-testid="static-figure">{path}</div>,
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

describe("CouplingTaskHistoryModal interactive figures", () => {
  beforeEach(() => {
    mocks.task.json_figure_path = ["/fig/a.json", "/fig/b.json", "/fig/c.json"];
  });
  afterEach(() => cleanup());

  it("keeps the static strip with every figure by default", () => {
    renderModal();
    const details = desktopDetails();

    expect(details.getAllByTestId("static-figure")).toHaveLength(3);
    expect(details.queryByTestId("plotly-renderer")).toBeNull();
  });

  it("shows one container-sized interactive figure at a time in a bounded frame", () => {
    renderModal();
    const details = desktopDetails();
    fireEvent.click(details.getByRole("button", { name: "Interactive" }));

    const renderers = details.getAllByTestId("plotly-renderer");
    expect(renderers).toHaveLength(1);
    expect(renderers[0].dataset.sizing).toBe("container");
    expect(renderers[0].dataset.path).toContain(encodeURIComponent("/fig/a.json"));
    expect(renderers[0].className).toContain("h-full");

    const frame = renderers[0].parentElement as HTMLElement;
    expect(frame.className).toContain("w-full");
    expect(frame.className).toMatch(/max-h-\[/);
    expect(frame.className).toContain("overflow-hidden");
    expect(details.getByText("Figure 1 / 3")).toBeTruthy();
  });

  it("navigates between interactive figures without wrapping", () => {
    renderModal();
    const details = desktopDetails();
    fireEvent.click(details.getByRole("button", { name: "Interactive" }));

    const previous = details.getByRole("button", {
      name: "Previous figure",
    }) as HTMLButtonElement;
    const next = details.getByRole("button", {
      name: "Next figure",
    }) as HTMLButtonElement;
    expect(previous.disabled).toBe(true);

    fireEvent.click(next);
    expect(details.getByText("Figure 2 / 3")).toBeTruthy();
    expect(details.getByTestId("plotly-renderer").dataset.path).toContain(
      encodeURIComponent("/fig/b.json"),
    );

    fireEvent.click(next);
    expect(details.getByText("Figure 3 / 3")).toBeTruthy();
    expect(next.disabled).toBe(true);

    fireEvent.click(previous);
    expect(details.getByText("Figure 2 / 3")).toBeTruthy();
  });

  it("restarts at the first figure when interactive view is reopened", () => {
    renderModal();
    const details = desktopDetails();
    fireEvent.click(details.getByRole("button", { name: "Interactive" }));
    fireEvent.click(details.getByRole("button", { name: "Next figure" }));
    fireEvent.click(details.getByRole("button", { name: "Static" }));
    fireEvent.click(details.getByRole("button", { name: "Interactive" }));

    expect(details.getByText("Figure 1 / 3")).toBeTruthy();
  });

  it("omits figure navigation for a single interactive figure", () => {
    mocks.task.json_figure_path = ["/fig/a.json"];
    renderModal();
    const details = desktopDetails();
    fireEvent.click(details.getByRole("button", { name: "Interactive" }));

    expect(details.getByTestId("plotly-renderer")).toBeTruthy();
    expect(details.queryByRole("button", { name: "Next figure" })).toBeNull();
  });
});
