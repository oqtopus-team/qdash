import type { ReactNode } from "react";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionDAG } from "@/components/features/execution/ExecutionDAG";

const mocks = vi.hoisted(() => ({
  capturedProps: null as Record<string, unknown> | null,
  fitView: vi.fn(),
}));

vi.mock("@xyflow/react", () => {
  type FakeNode = { id: string; data: Record<string, unknown> };
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
    Controls: () => <div data-testid="controls" />,
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

vi.mock("react18-json-view", () => ({
  default: ({ src }: { src: unknown }) => <pre>{JSON.stringify(src)}</pre>,
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
  mocks.fitView.mockClear();
});

describe("ExecutionDAG view mode", () => {
  it("defaults to Region mode with wheel/drag navigation disabled", () => {
    render(<ExecutionDAG tasks={tasks} />);

    const regionTab = screen.getByRole("button", { name: "Region" });
    expect(regionTab).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "DOM" })).toHaveAttribute("aria-pressed", "false");

    expect(mocks.capturedProps).toMatchObject({
      zoomOnScroll: false,
      panOnScroll: false,
      panOnDrag: false,
      zoomOnPinch: false,
      zoomOnDoubleClick: false,
      preventScrolling: false,
      nodesDraggable: false,
    });
    expect(screen.queryByTestId("controls")).toBeNull();
  });

  it("enables interactive navigation when switching to DOM mode", () => {
    render(<ExecutionDAG tasks={tasks} />);

    fireEvent.click(screen.getByRole("button", { name: "DOM" }));

    expect(screen.getByRole("button", { name: "DOM" })).toHaveAttribute("aria-pressed", "true");
    expect(mocks.capturedProps).toMatchObject({
      zoomOnScroll: true,
      panOnScroll: true,
      panOnDrag: true,
      zoomOnPinch: true,
      zoomOnDoubleClick: true,
      preventScrolling: true,
      nodesDraggable: true,
    });
    expect(screen.getByTestId("controls")).toBeTruthy();
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
});

describe("ExecutionDAG node interaction", () => {
  it("opens the task detail panel when a node is clicked", () => {
    render(<ExecutionDAG tasks={tasks} />);

    expect(screen.queryByText("CheckT1")).toBeNull();

    fireEvent.click(screen.getByTestId("node-task-1"));

    expect(screen.getAllByText("CheckT1").length).toBeGreaterThan(0);
    expect(screen.getByText("completed")).toBeTruthy();
  });
});
