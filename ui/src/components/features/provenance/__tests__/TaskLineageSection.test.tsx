import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskLineageSection } from "@/components/features/provenance/TaskLineageSection";

const mocks = vi.hoisted(() => ({ panelProps: [] as Array<Record<string, unknown>> }));

vi.mock("@/components/features/provenance/ParameterLineagePanel", () => ({
  ParameterLineagePanel: (props: Record<string, unknown>) => {
    mocks.panelProps.push(props);
    return <div>panel:{String(props.parameterName)}</div>;
  },
}));

afterEach(() => {
  cleanup();
  mocks.panelProps = [];
});

const outputs = {
  t1: { value: 20 },
  control_frequency: { value: 7.1, parameter_name: "qubit_frequency", qid_role: "control" },
};

describe("TaskLineageSection", () => {
  it("renders nothing for a task without published outputs", () => {
    const { container } = render(
      <TaskLineageSection taskId="t" executionId="e" qid="0" outputParameters={{}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("starts folded and only mounts the panel once opened", () => {
    render(<TaskLineageSection taskId="t" executionId="e" qid="0-1" outputParameters={outputs} />);

    expect(screen.getByText(/2 published values/)).toBeTruthy();
    expect(mocks.panelProps).toHaveLength(0);

    fireEvent.click(screen.getByText("Lineage"));

    expect(screen.getByText("panel:t1")).toBeTruthy();
    expect(mocks.panelProps[0]).toMatchObject({
      parameterName: "t1",
      qid: "0-1",
      entityId: "t1:0-1:e:t",
      hideInputs: true,
      currentTaskId: "t",
    });
  });

  it("switches between the published values", () => {
    render(<TaskLineageSection taskId="t" executionId="e" qid="0-1" outputParameters={outputs} />);
    fireEvent.click(screen.getByText("Lineage"));

    fireEvent.change(screen.getByRole("combobox", { name: "Published parameter" }), {
      target: { value: "1" },
    });

    expect(screen.getByText("panel:qubit_frequency")).toBeTruthy();
    expect(mocks.panelProps[mocks.panelProps.length - 1]).toMatchObject({
      qid: "0",
      entityId: "qubit_frequency:0:e:t",
    });
  });
});
