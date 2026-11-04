import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ParameterLineagePanel } from "@/components/features/provenance/ParameterLineagePanel";

const mocks = vi.hoisted(() => ({
  history: {} as Record<string, unknown[]>,
  lineageCalls: [] as Array<{ entityId: string; enabled: boolean }>,
  graphOpened: null as string | null,
  entity: {} as {
    data?: unknown;
    isLoading?: boolean;
    status?: number;
  },
  entityCalls: [] as Array<{ entityId: string; enabled: boolean }>,
}));

function version(
  parameterName: string,
  qid: string,
  executionId: string,
  value: number,
  versionNumber: number,
  extra: Record<string, unknown> = {},
) {
  return {
    entity_id: `${parameterName}:${qid}:${executionId}:task-${versionNumber}`,
    parameter_name: parameterName,
    qid,
    value,
    unit: "GHz",
    error: 0,
    version: versionNumber,
    valid_from: "2026-11-01T10:00:00Z",
    valid_until: versionNumber === 2 ? null : "2026-11-01T11:00:00Z",
    execution_id: executionId,
    task_id: `task-${versionNumber}`,
    task_name: "CheckRamsey",
    project_id: "p",
    chip_id: "64Q",
    ...extra,
  };
}

const current = version("qubit_frequency", "1", "20261101-051", 7.157231, 2);
const older = version("qubit_frequency", "1", "20261101-050", 7.157229, 1);
const input = version("readout_frequency", "1", "20261101-049", 10.1, 5);
const dependent = version("t1", "1", "20261101-051", 25.4, 3, { unit: "μs", task_name: "CheckT1" });

vi.mock("@/client/provenance/provenance", () => ({
  useGetParameterHistory: ({ parameter_name, qid }: { parameter_name: string; qid: string }) => ({
    data: { data: { versions: mocks.history[`${parameter_name}:${qid}`] ?? [] } },
    isLoading: false,
    isError: false,
  }),
  useGetProvenanceEntity: (entityId: string, options: { query: { enabled: boolean } }) => {
    mocks.entityCalls.push({ entityId, enabled: options.query.enabled });
    if (!options.query.enabled) return { data: undefined, isLoading: false, isError: false };
    const { data, isLoading = false, status } = mocks.entity;
    return {
      data: data ? { data } : undefined,
      isLoading,
      isError: status !== undefined,
      error: status !== undefined ? { isAxiosError: true, response: { status } } : null,
    };
  },
  useGetProvenanceLineage: (
    entityId: string,
    params: { max_depth: number },
    options: { query: { enabled: boolean } },
  ) => {
    mocks.lineageCalls.push({ entityId, enabled: options.query.enabled });
    if (params.max_depth > 1 && options.query.enabled) mocks.graphOpened = entityId;
    const isCurrent = entityId === current.entity_id;
    return {
      data: {
        data: {
          nodes: [
            { node_type: "entity", node_id: entityId, entity: isCurrent ? current : older },
            {
              node_type: "activity",
              node_id: "act",
              activity: { task_name: "CheckRamsey", task_type: "qubit" },
            },
            { node_type: "entity", node_id: input.entity_id, entity: input },
          ],
          edges: [
            { relation_type: "wasGeneratedBy", source_id: entityId, target_id: "act" },
            { relation_type: "wasDerivedFrom", source_id: entityId, target_id: input.entity_id },
          ],
        },
      },
      isLoading: false,
    };
  },
  useGetProvenanceImpact: (entityId: string) => ({
    data: {
      data: {
        nodes: [{ node_type: "entity", node_id: dependent.entity_id, entity: dependent }],
        edges: [
          { relation_type: "wasDerivedFrom", source_id: dependent.entity_id, target_id: entityId },
        ],
      },
    },
    isLoading: false,
  }),
}));

vi.mock("@/components/features/provenance/ProvenanceGraph", () => ({
  ProvenanceGraph: () => <div data-testid="graph" />,
}));

afterEach(() => {
  cleanup();
  mocks.history = {};
  mocks.lineageCalls = [];
  mocks.graphOpened = null;
  mocks.entity = {};
  mocks.entityCalls = [];
});

describe("ParameterLineagePanel", () => {
  it("shows the producer, the direct inputs and the dependents", () => {
    mocks.history["qubit_frequency:1"] = [current, older];
    render(<ParameterLineagePanel parameterName="qubit_frequency" qid="1" />);

    expect(screen.getByText(/Produced by/)).toHaveTextContent("CheckRamsey");
    const inputs = screen.getByRole("region", { name: "Inputs" });
    expect(within(inputs).getByText("readout_frequency")).toBeTruthy();
    const dependents = screen.getByRole("region", { name: "Depends on this value" });
    expect(within(dependents).getByText("t1")).toBeTruthy();
    expect(within(dependents).getByText("25.4 μs")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Execution/ })).toHaveAttribute(
      "href",
      "/execution/64Q/20261101-051",
    );
  });

  it("starts on the requested version and lets the user switch versions", () => {
    mocks.history["qubit_frequency:1"] = [current, older];
    render(
      <ParameterLineagePanel parameterName="qubit_frequency" qid="1" entityId={older.entity_id} />,
    );

    const select = screen.getByRole("combobox", { name: "Version" }) as HTMLSelectElement;
    expect(select.value).toBe(older.entity_id);
    expect(screen.getByText(/replaced/)).toBeTruthy();

    fireEvent.change(select, { target: { value: current.entity_id } });
    expect(select.value).toBe(current.entity_id);
    expect(mocks.lineageCalls.some((call) => call.entityId === current.entity_id)).toBe(true);
  });

  it("follows an input in place and comes back", () => {
    mocks.history["qubit_frequency:1"] = [current];
    mocks.history["readout_frequency:1"] = [input];
    render(<ParameterLineagePanel parameterName="qubit_frequency" qid="1" />);

    fireEvent.click(
      within(screen.getByRole("region", { name: "Inputs" })).getAllByRole("button")[0],
    );
    expect(screen.getAllByText("10.1 GHz").length).toBeGreaterThan(0);
    expect(screen.queryByText("7.15723 GHz")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Back to qubit_frequency/ }));
    expect(screen.getByText("7.15723 GHz")).toBeTruthy();
  });

  it("opens the full graph only on demand", () => {
    mocks.history["qubit_frequency:1"] = [current];
    render(<ParameterLineagePanel parameterName="qubit_frequency" qid="1" />);

    expect(mocks.graphOpened).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Full graph/ }));
    expect(mocks.graphOpened).toBe(current.entity_id);
    expect(screen.getByTestId("graph")).toBeTruthy();
  });

  it("explains when nothing was published", () => {
    render(<ParameterLineagePanel parameterName="t2_echo" qid="7" />);

    expect(screen.getByText(/No published version is recorded/)).toBeTruthy();
  });
});

describe("ParameterLineagePanel opened on a run", () => {
  it("shows the version that run published when only the execution id is known", () => {
    mocks.history["qubit_frequency:1"] = [current, older];
    render(
      <ParameterLineagePanel parameterName="qubit_frequency" qid="1" executionId="20261101-050" />,
    );

    const select = screen.getByRole("combobox", { name: "Version" }) as HTMLSelectElement;
    expect(select.value).toBe(older.entity_id);
  });
});

describe("ParameterLineagePanel on a task result", () => {
  it("hides the inputs the result's own table already lists, until another value is followed", () => {
    mocks.history["qubit_frequency:1"] = [current];
    mocks.history["t1:1"] = [dependent];
    render(<ParameterLineagePanel parameterName="qubit_frequency" qid="1" hideInputs />);

    expect(screen.queryByRole("region", { name: "Inputs" })).toBeNull();
    expect(screen.getByRole("region", { name: "Depends on this value" })).toBeTruthy();

    fireEvent.click(
      within(screen.getByRole("region", { name: "Depends on this value" })).getAllByRole(
        "button",
      )[0],
    );
    expect(screen.getByRole("region", { name: "Inputs" })).toBeTruthy();
  });

  it("shows the inputs again once another version is selected", () => {
    mocks.history["qubit_frequency:1"] = [current, older];
    render(
      <ParameterLineagePanel
        parameterName="qubit_frequency"
        qid="1"
        entityId={current.entity_id}
        hideInputs
      />,
    );
    expect(screen.queryByRole("region", { name: "Inputs" })).toBeNull();

    fireEvent.change(screen.getByRole("combobox", { name: "Version" }), {
      target: { value: older.entity_id },
    });

    expect(screen.getByRole("region", { name: "Inputs" })).toBeTruthy();
  });
});

describe("ParameterLineagePanel with a version outside the loaded history", () => {
  const unresolvedNotice = /not among the latest 50 versions loaded; showing the current version/;

  it("fetches an older requested entity and shows that version and its lineage", () => {
    mocks.history["qubit_frequency:1"] = [current];
    mocks.entity = { data: older };
    render(
      <ParameterLineagePanel parameterName="qubit_frequency" qid="1" entityId={older.entity_id} />,
    );

    expect(mocks.entityCalls).toContainEqual({ entityId: older.entity_id, enabled: true });
    const select = screen.getByRole("combobox", { name: "Version" }) as HTMLSelectElement;
    expect(select.value).toBe(older.entity_id);
    expect(screen.getByText(/replaced/)).toBeTruthy();
    expect(mocks.lineageCalls.some((call) => call.entityId === older.entity_id)).toBe(true);
    expect(mocks.lineageCalls.some((call) => call.entityId === current.entity_id)).toBe(false);
    expect(screen.queryByText(unresolvedNotice)).toBeNull();
    expect(screen.queryByText(/did not publish/)).toBeNull();
  });

  it("does not fetch the entity when the loaded history already holds it", () => {
    mocks.history["qubit_frequency:1"] = [current, older];
    render(
      <ParameterLineagePanel parameterName="qubit_frequency" qid="1" entityId={older.entity_id} />,
    );

    expect(mocks.entityCalls.every((call) => !call.enabled)).toBe(true);
  });

  it("waits for the entity lookup instead of showing the current lineage", () => {
    mocks.history["qubit_frequency:1"] = [current];
    mocks.entity = { isLoading: true };
    const { container } = render(
      <ParameterLineagePanel parameterName="qubit_frequency" qid="1" entityId={older.entity_id} />,
    );

    expect(container.querySelector(".loading")).toBeTruthy();
    expect(screen.queryByText("7.15723 GHz")).toBeNull();
    expect(mocks.lineageCalls.every((call) => !call.enabled)).toBe(true);
  });

  it("reports a failed entity lookup instead of showing the current version", () => {
    mocks.history["qubit_frequency:1"] = [current];
    mocks.entity = { status: 500 };
    render(
      <ParameterLineagePanel parameterName="qubit_frequency" qid="1" entityId={older.entity_id} />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "The requested version of qubit_frequency could not be loaded.",
    );
    expect(screen.queryByText("7.15723 GHz")).toBeNull();
    expect(mocks.lineageCalls.every((call) => !call.enabled)).toBe(true);
  });

  it("uses neutral wording when the entity does not exist", () => {
    mocks.history["qubit_frequency:1"] = [current];
    mocks.entity = { status: 404 };
    render(
      <ParameterLineagePanel
        parameterName="qubit_frequency"
        qid="1"
        entityId="qubit_frequency:1:other-run:task-x"
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(unresolvedNotice);
    expect(screen.queryByText(/did not publish/)).toBeNull();
    expect(screen.getByText("7.15723 GHz")).toBeTruthy();
  });

  it("ignores a fetched entity that belongs to another parameter", () => {
    mocks.history["qubit_frequency:1"] = [current];
    mocks.entity = { data: { ...input, entity_id: older.entity_id } };
    render(
      <ParameterLineagePanel parameterName="qubit_frequency" qid="1" entityId={older.entity_id} />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(unresolvedNotice);
    expect(screen.getByText("7.15723 GHz")).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: "Version" })).toBeNull();
  });

  it("uses neutral wording for a run outside the window, without an entity lookup", () => {
    mocks.history["qubit_frequency:1"] = [current];
    render(
      <ParameterLineagePanel parameterName="qubit_frequency" qid="1" executionId="20250101-001" />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(unresolvedNotice);
    expect(screen.queryByText(/did not publish/)).toBeNull();
    expect(mocks.entityCalls.every((call) => !call.enabled)).toBe(true);
  });
});
