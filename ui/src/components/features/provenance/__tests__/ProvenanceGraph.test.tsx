import { useState, type ReactNode } from "react";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProvenanceGraph } from "@/components/features/provenance/ProvenanceGraph";
import type { LineageEdgeResponse, LineageNodeResponse } from "@/schemas";

const mocks = vi.hoisted(() => ({
  fitView: vi.fn(),
  flowProps: null as Record<string, unknown> | null,
}));

vi.mock("@xyflow/react", () => {
  type FakeNode = { id: string; type: string; data: Record<string, unknown> };
  type FakeProps = {
    nodes?: FakeNode[];
    children?: ReactNode;
    onNodeClick?: (event: unknown, node: FakeNode) => void;
  };
  return {
    ReactFlow: (props: FakeProps) => {
      mocks.flowProps = props as Record<string, unknown>;
      return (
        <div>
          {props.nodes?.map((node) => (
            <button
              key={node.id}
              type="button"
              data-testid={`node-${node.id}`}
              data-type={node.type}
              onClick={(event) => props.onNodeClick?.(event, node)}
            >
              {String(node.data.label)}
            </button>
          ))}
          {props.children}
        </div>
      );
    },
    ReactFlowProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
    Background: () => null,
    Controls: () => null,
    Handle: () => null,
    Position: { Top: "top", Bottom: "bottom" },
    MarkerType: { ArrowClosed: "arrowclosed" },
    useReactFlow: () => ({ fitView: mocks.fitView }),
    useNodesState: (initial: FakeNode[]) => {
      const [nodes, setNodes] = useState(initial);
      return [nodes, setNodes, vi.fn()];
    },
    useEdgesState: (initial: unknown[]) => {
      const [edges, setEdges] = useState(initial);
      return [edges, setEdges, vi.fn()];
    },
  };
});

vi.mock("@/components/charts/TaskFigure", () => ({ TaskFigure: () => null }));

function entity(id: string, name: string, version = 1, latest?: number): LineageNodeResponse {
  return {
    node_type: "entity",
    node_id: id,
    depth: 0,
    latest_version: latest ?? null,
    entity: {
      entity_id: id,
      parameter_name: name,
      qid: "1",
      value: 1.5,
      unit: "GHz",
      error: 0,
      version,
      execution_id: "e",
      task_id: "t",
      task_name: "T",
      project_id: "p",
    },
  } as unknown as LineageNodeResponse;
}

function activity(id: string, name: string): LineageNodeResponse {
  return {
    node_type: "activity",
    node_id: id,
    depth: 0,
    activity: {
      activity_id: id,
      execution_id: "e",
      task_id: id,
      task_name: name,
      qid: "1",
      status: "completed",
      project_id: "p",
    },
  } as unknown as LineageNodeResponse;
}

// origin <- A1 <- {in1, in2}; in1 <- A2 <- far; far <- A3 (five hops from the origin)
const nodes = [
  entity("origin", "t1"),
  activity("A1", "CheckT1"),
  entity("in1", "hpi_amplitude", 3, 5),
  entity("in2", "readout_frequency"),
  activity("A2", "CreateHPIPulse"),
  entity("far", "rabi_amplitude"),
  activity("A3", "CheckRabi"),
];
const edges: LineageEdgeResponse[] = [
  { relation_type: "wasGeneratedBy", source_id: "origin", target_id: "A1" },
  { relation_type: "used", source_id: "A1", target_id: "in1" },
  { relation_type: "used", source_id: "A1", target_id: "in2" },
  { relation_type: "wasDerivedFrom", source_id: "origin", target_id: "in1" },
  { relation_type: "wasGeneratedBy", source_id: "in1", target_id: "A2" },
  { relation_type: "used", source_id: "A2", target_id: "far" },
  { relation_type: "wasGeneratedBy", source_id: "far", target_id: "A3" },
];

afterEach(() => {
  cleanup();
  mocks.fitView.mockClear();
  mocks.flowProps = null;
});

describe("ProvenanceGraph", () => {
  it("shows three hops by default and reports stale direct inputs", () => {
    render(<ProvenanceGraph nodes={nodes} edges={edges} originId="origin" />);

    expect(screen.getByTestId("node-A2")).toBeTruthy();
    expect(screen.queryByTestId("node-far")).toBeNull();
    expect(screen.getByText(/5 of 7 nodes, 3 values and 2 tasks/)).toBeTruthy();
    expect(screen.getByText(/1 input updated since/)).toBeTruthy();
  });

  it("re-fits the viewport when the depth or the view changes, not when a task is selected", async () => {
    render(<ProvenanceGraph nodes={nodes} edges={edges} originId="origin" />);
    await waitFor(() => expect(mocks.fitView).toHaveBeenCalled());
    mocks.fitView.mockClear();

    fireEvent.click(screen.getByTestId("node-A1"));
    expect(screen.getByRole("complementary", { name: "Task details" })).toBeTruthy();
    // Opening the side panel narrows the canvas, so that one re-fit is expected.
    await waitFor(() => expect(mocks.fitView).toHaveBeenCalledTimes(1));
    mocks.fitView.mockClear();

    fireEvent.change(screen.getByRole("combobox", { name: "Depth" }), { target: { value: "all" } });
    expect(screen.getByTestId("node-far")).toBeTruthy();
    await waitFor(() =>
      expect(mocks.fitView).toHaveBeenCalledWith(expect.objectContaining({ duration: 300 })),
    );
    mocks.fitView.mockClear();

    fireEvent.click(screen.getByRole("tab", { name: "Tasks only" }));
    expect(screen.queryByTestId("node-origin")).toBeNull();
    expect(screen.getByTestId("node-A3")).toBeTruthy();
    await waitFor(() => expect(mocks.fitView).toHaveBeenCalledTimes(1));
  });

  it("fits the matches of a search and shows the whole graph while searching", async () => {
    render(<ProvenanceGraph nodes={nodes} edges={edges} originId="origin" />);
    await waitFor(() => expect(mocks.fitView).toHaveBeenCalled());
    mocks.fitView.mockClear();

    fireEvent.change(screen.getByRole("searchbox", { name: "Find a value or task" }), {
      target: { value: "rabi" },
    });

    expect(screen.getByTestId("node-far")).toBeTruthy();
    await waitFor(() =>
      expect(mocks.fitView).toHaveBeenCalledWith(
        expect.objectContaining({ nodes: [{ id: "A3" }, { id: "far" }] }),
      ),
    );
  });
});
