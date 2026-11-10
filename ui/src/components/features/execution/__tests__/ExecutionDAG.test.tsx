import type { ReactNode } from "react";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionDAG } from "@/components/features/execution/ExecutionDAG";

const mocks = vi.hoisted(() => ({
  capturedProps: null as Record<string, unknown> | null,
  capturedControlsProps: null as Record<string, unknown> | null,
  fitView: vi.fn(),
}));

vi.mock("@xyflow/react", () => {
  type FakeNode = {
    id: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
  };
  type FakeReactFlowProps = {
    nodes?: FakeNode[];
    children?: ReactNode;
    onNodeClick?: (event: unknown, node: FakeNode) => void;
    [key: string]: unknown;
  };
  return {
    ReactFlow: (props: FakeReactFlowProps) => {
      mocks.capturedProps = props;
      return (
        <div data-testid="react-flow">
          {props.nodes?.map((node) => (
            <button
              key={node.id}
              type="button"
              data-testid={`node-${node.id}`}
              onClick={(event) => props.onNodeClick?.(event, node)}
            >
              {node.id}
            </button>
          ))}
          {props.children}
        </div>
      );
    },
    Background: () => null,
    Controls: (props: {
      onInteractiveChange?: (interactive: boolean) => void;
      [key: string]: unknown;
    }) => {
      mocks.capturedControlsProps = props;
      const interactive = mocks.capturedProps?.zoomOnScroll === true;
      return (
        <button
          type="button"
          data-testid="controls-interactive"
          onClick={() => props.onInteractiveChange?.(!interactive)}
        >
          toggle-lock
        </button>
      );
    },
    Handle: () => null,
    Position: { Left: "left", Right: "right" },
    ReactFlowProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
    Panel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    MarkerType: { ArrowClosed: "arrowclosed" },
    useReactFlow: () => ({ fitView: mocks.fitView }),
  };
});

vi.mock("@/components/charts/TaskFigure", () => ({
  TaskFigure: () => <div>TaskFigure</div>,
}));

const results: Record<string, Record<string, unknown>> = {
  "task-1": {
    task_id: "task-1",
    task_name: "CheckT1",
    status: "completed",
    qid: "0",
    chip_id: "64Q",
    execution_id: "20261031-003",
    output_parameters: { t1: { value: 12.3, unit: "us" } },
  },
  "task-2": {
    task_id: "task-2",
    task_name: "CheckT2",
    status: "running",
    qid: "0",
    chip_id: "64Q",
    execution_id: "20261031-003",
  },
};

vi.mock("@/components/features/provenance/TaskLineageSection", () => ({
  TaskLineageSection: () => null,
}));

vi.mock("@/client/task/task", () => ({
  useGetTaskResult: (taskId: string) => ({
    data: taskId ? { data: results[taskId] } : undefined,
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("@/client/task-file/task-file", () => ({
  useGetTaskFileSettings: () => ({ data: undefined }),
  useListTaskInfo: () => ({ data: undefined }),
}));

const tasks = [
  {
    task_id: "task-1",
    name: "CheckT1",
    status: "completed",
    input_parameters: { shots: 1000 },
  },
  {
    task_id: "task-2",
    name: "CheckT2",
    status: "running",
    upstream_id: "task-1",
  },
];

afterEach(() => {
  cleanup();
  mocks.capturedProps = null;
  mocks.capturedControlsProps = null;
  mocks.fitView.mockClear();
});

describe("ExecutionDAG lock control", () => {
  it("starts unlocked with pan/zoom and dragging enabled", () => {
    render(<ExecutionDAG tasks={tasks} />);

    expect(screen.getByTestId("controls-interactive")).toBeTruthy();
    expect(mocks.capturedProps).toMatchObject({
      zoomOnScroll: true,
      panOnScroll: false,
      panOnDrag: true,
      zoomOnPinch: true,
      zoomOnDoubleClick: true,
      preventScrolling: true,
      nodesDraggable: true,
      nodesConnectable: false,
      elementsSelectable: true,
    });
    expect(mocks.capturedControlsProps).toMatchObject({
      showInteractive: true,
      showZoom: true,
      showFitView: true,
      fitViewOptions: { padding: 0.05, minZoom: 0.1, maxZoom: 1.5 },
    });
    expect(screen.getByTitle("Fit to view")).toBeTruthy();
  });

  it("locks pan/zoom and dragging when the lock control is toggled", () => {
    render(<ExecutionDAG tasks={tasks} />);
    mocks.fitView.mockClear();

    fireEvent.click(screen.getByTestId("controls-interactive"));

    expect(mocks.fitView).toHaveBeenCalledWith({
      padding: 0.05,
      minZoom: 0.1,
      maxZoom: 1.5,
      duration: 0,
    });
    expect(mocks.capturedProps).toMatchObject({
      zoomOnScroll: false,
      panOnScroll: false,
      panOnDrag: false,
      zoomOnPinch: false,
      zoomOnDoubleClick: false,
      preventScrolling: false,
      nodesDraggable: false,
      nodesConnectable: false,
      elementsSelectable: false,
    });
    expect(mocks.capturedControlsProps).toMatchObject({
      showInteractive: true,
      showZoom: false,
      showFitView: false,
    });
    expect(screen.queryByTitle("Fit to view")).toBeNull();
  });

  it("restores pan/zoom and the Controls buttons when unlocked again", () => {
    render(<ExecutionDAG tasks={tasks} />);

    fireEvent.click(screen.getByTestId("controls-interactive"));
    expect(mocks.capturedControlsProps).toMatchObject({ showZoom: false, showFitView: false });
    mocks.fitView.mockClear();

    fireEvent.click(screen.getByTestId("controls-interactive"));

    expect(mocks.fitView).not.toHaveBeenCalled();
    expect(mocks.capturedControlsProps).toMatchObject({
      showInteractive: true,
      showZoom: true,
      showFitView: true,
    });
    expect(screen.getByTitle("Fit to view")).toBeTruthy();
    expect(mocks.capturedProps).toMatchObject({
      zoomOnScroll: true,
      panOnDrag: true,
      nodesDraggable: true,
      elementsSelectable: true,
    });
  });
});

describe("ExecutionDAG node dragging", () => {
  type CapturedNode = {
    id: string;
    position: { x: number; y: number };
    data: Record<string, unknown>;
  };
  const capturedNode = (id: string) =>
    (mocks.capturedProps?.nodes as CapturedNode[] | undefined)?.find((node) => node.id === id);

  it("keeps a dragged node at its new position across selection changes", () => {
    render(<ExecutionDAG tasks={tasks} />);
    const onNodesChange = mocks.capturedProps?.onNodesChange as (changes: unknown[]) => void;
    const untouched = capturedNode("task-2")?.position;

    act(() => {
      onNodesChange([
        { type: "position", id: "task-1", position: { x: 500, y: 250 }, dragging: true },
      ]);
    });

    expect(capturedNode("task-1")?.position).toEqual({ x: 500, y: 250 });
    expect(capturedNode("task-2")?.position).toEqual(untouched);

    fireEvent.click(screen.getByTestId("node-task-1"));

    expect(capturedNode("task-1")?.data.isSelected).toBe(true);
    expect(capturedNode("task-1")?.position).toEqual({ x: 500, y: 250 });
  });

  it("ignores node changes that carry no position", () => {
    render(<ExecutionDAG tasks={tasks} />);
    const onNodesChange = mocks.capturedProps?.onNodesChange as (changes: unknown[]) => void;
    const before = capturedNode("task-1")?.position;

    act(() => {
      onNodesChange([
        { type: "position", id: "task-1", dragging: false },
        { type: "select", id: "task-1", selected: true },
      ]);
    });

    expect(capturedNode("task-1")?.position).toEqual(before);
  });
});

describe("ExecutionDAG fullscreen", () => {
  it("toggles the fullscreen overlay and exits on Escape", () => {
    const { container } = render(<ExecutionDAG tasks={tasks} />);

    const toggle = screen.getByRole("button", { name: "Fullscreen" });
    expect(container.firstChild).not.toHaveClass("fixed");

    fireEvent.click(toggle);

    expect(container.firstChild).toHaveClass("fixed");
    expect(container.firstChild).toHaveClass("inset-0");
    expect(screen.getByRole("button", { name: "Exit fullscreen" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.keyDown(window, { key: "Escape" });

    expect(container.firstChild).not.toHaveClass("fixed");
  });

  it("fits on mount but keeps the user's viewport when fullscreen toggles unlocked", () => {
    vi.useFakeTimers();
    try {
      render(<ExecutionDAG tasks={tasks} />);
      act(() => {
        vi.runAllTimers();
      });
      expect(mocks.fitView).toHaveBeenCalledWith(expect.objectContaining({ duration: 0 }));
      mocks.fitView.mockClear();

      fireEvent.click(screen.getByRole("button", { name: "Fullscreen" }));
      act(() => {
        vi.runAllTimers();
      });

      expect(mocks.fitView).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("re-fits the locked graph when fullscreen toggles", () => {
    vi.useFakeTimers();
    try {
      render(<ExecutionDAG tasks={tasks} />);
      fireEvent.click(screen.getByTestId("controls-interactive"));
      act(() => {
        vi.runAllTimers();
      });
      mocks.fitView.mockClear();

      fireEvent.click(screen.getByRole("button", { name: "Fullscreen" }));
      act(() => {
        vi.runAllTimers();
      });

      expect(mocks.fitView).toHaveBeenCalledWith(expect.objectContaining({ duration: 0 }));
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("ExecutionDAG node interaction", () => {
  it("opens the shared task result preview for the clicked node", () => {
    render(<ExecutionDAG tasks={tasks} />);

    const preview = screen.getByRole("complementary", { hidden: true });
    expect(preview).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByText("CheckT1")).toBeNull();

    fireEvent.click(screen.getByTestId("node-task-1"));

    expect(preview).toHaveAttribute("aria-hidden", "false");
    expect(screen.getByRole("heading", { name: "CheckT1" })).toBeTruthy();
    expect(screen.getByText("completed")).toBeTruthy();
    expect(screen.getByText("12.3 us")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open full page/ })).toHaveAttribute(
      "href",
      "/task-results/task-1",
    );
    // The preview already sits on the execution page.
    expect(screen.queryByRole("link", { name: /^Execution$/ })).toBeNull();
  });

  it("keeps the user's viewport when the preview opens on the unlocked canvas", () => {
    vi.useFakeTimers();
    try {
      render(<ExecutionDAG tasks={tasks} />);
      const canvas = screen.getByTestId("execution-flow-canvas");
      act(() => {
        vi.runAllTimers();
      });
      mocks.fitView.mockClear();

      fireEvent.click(screen.getByTestId("node-task-1"));
      expect(canvas).toHaveClass("lg:mr-[calc(40vw-2.5rem)]");
      act(() => {
        vi.runAllTimers();
      });

      expect(mocks.fitView).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("gives the canvas up to the preview and re-fits the locked graph afterwards", async () => {
    render(<ExecutionDAG tasks={tasks} />);
    fireEvent.click(screen.getByTestId("controls-interactive"));
    const canvas = screen.getByTestId("execution-flow-canvas");
    expect(canvas).not.toHaveClass("lg:mr-[calc(40vw-2.5rem)]");
    const fitCallsBefore = mocks.fitView.mock.calls.length;

    fireEvent.click(screen.getByTestId("node-task-1"));

    expect(canvas).toHaveClass("lg:mr-[calc(40vw-2.5rem)]");
    await waitFor(() =>
      expect(mocks.fitView).toHaveBeenCalledWith(expect.objectContaining({ duration: 300 })),
    );
    expect(mocks.fitView.mock.calls.length).toBeGreaterThan(fitCallsBefore);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(canvas).not.toHaveClass("lg:mr-[calc(40vw-2.5rem)]");
  });

  it("lets Escape close the preview before it exits fullscreen", () => {
    const { container } = render(<ExecutionDAG tasks={tasks} />);

    fireEvent.click(screen.getByRole("button", { name: "Fullscreen" }));
    fireEvent.click(screen.getByTestId("node-task-1"));
    const canvas = screen.getByTestId("execution-flow-canvas");
    expect(container.firstChild).toHaveClass("fixed");
    expect(canvas).toHaveClass("lg:mr-[calc(40vw-1rem)]");

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByText("CheckT1")).toBeNull();
    expect(container.firstChild).toHaveClass("fixed");

    fireEvent.keyDown(window, { key: "Escape" });

    expect(container.firstChild).not.toHaveClass("fixed");
  });

  it("marks the selected node and closes the preview on Escape", () => {
    render(<ExecutionDAG tasks={tasks} />);

    fireEvent.click(screen.getByTestId("node-task-2"));

    const nodes = mocks.capturedProps?.nodes as Array<{
      id: string;
      data: { isSelected: boolean };
    }>;
    expect(nodes.find((node) => node.id === "task-2")?.data.isSelected).toBe(true);
    expect(nodes.find((node) => node.id === "task-1")?.data.isSelected).toBe(false);
    expect(screen.getByRole("heading", { name: "CheckT2" })).toBeTruthy();

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.getByRole("complementary", { hidden: true })).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(screen.queryByText("CheckT2")).toBeNull();
    const nodesAfterClose = mocks.capturedProps?.nodes as Array<{ data: { isSelected: boolean } }>;
    expect(nodesAfterClose.every((node) => !node.data.isSelected)).toBe(true);
  });
});
