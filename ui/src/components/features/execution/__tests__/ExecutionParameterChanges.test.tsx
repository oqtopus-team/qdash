import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionParameterChanges } from "@/components/features/execution/ExecutionParameterChanges";

const mocks = vi.hoisted(() => ({
  executions: [] as Array<{ execution_id: string }>,
  compareParams: null as Record<string, unknown> | null,
  dialogTarget: null as Record<string, unknown> | null,
  changed: [] as Array<Record<string, unknown>>,
}));

function change(parameter_name: string, qid: string, delta_percent: number) {
  return {
    parameter_name,
    qid,
    value_before: 1,
    value_after: 1 + delta_percent / 100,
    delta_percent,
  };
}

vi.mock("@/client/provenance/provenance", () => ({
  useGetRecentExecutions: () => ({
    data: { data: { executions: mocks.executions } },
    isLoading: false,
    isError: false,
  }),
  useCompareExecutions: (
    params: Record<string, unknown>,
    options: { query: { enabled: boolean } },
  ) => {
    mocks.compareParams = options.query.enabled ? params : null;
    return {
      data: {
        data: {
          changed_parameters: mocks.changed,
          added_parameters: [{ parameter_name: "t2_echo", qid: "2", value_after: 30 }],
          removed_parameters: [],
          unchanged_count: 0,
        },
      },
      isLoading: false,
      isError: false,
    };
  },
}));

vi.mock("@/components/features/provenance/ParameterLineageDialog", () => ({
  ParameterLineageDialog: ({ target }: { target: Record<string, unknown> | null }) => {
    mocks.dialogTarget = target;
    return target ? <div>dialog:{String(target.parameterName)}</div> : null;
  },
}));

afterEach(() => {
  cleanup();
  mocks.executions = [];
  mocks.compareParams = null;
  mocks.dialogTarget = null;
  mocks.changed = [];
});

describe("ExecutionParameterChanges", () => {
  it("compares with the run published just before and groups changes by parameter", () => {
    mocks.executions = [{ execution_id: "003" }, { execution_id: "002" }, { execution_id: "001" }];
    mocks.changed = [
      change("t1", "0", 5),
      change("t1", "1", -1),
      change("t1", "2", 2),
      change("qubit_frequency", "1", 0.01),
    ];
    render(<ExecutionParameterChanges executionId="002" />);

    expect(mocks.compareParams).toEqual({ execution_id_before: "001", execution_id_after: "002" });
    expect(screen.getByText(/3 parameters differ on 5 targets/)).toBeTruthy();
    const summaries = screen.getAllByRole("group").map((group) => group.querySelector("summary"));
    const names = summaries.map((summary) => summary?.querySelector("span")?.textContent);
    // New values first, then the parameter with the largest relative change.
    expect(names).toEqual(["t2_echo", "t1", "qubit_frequency"]);
    const t1 = summaries[1]!;
    expect(t1).toHaveTextContent("3 changed");
    expect(t1).toHaveTextContent("+5.00 %");
    expect(t1).toHaveTextContent("median 2.00 %");
  });

  it("lists a parameter's targets by change size, folding long lists", () => {
    mocks.executions = [{ execution_id: "002" }, { execution_id: "001" }];
    mocks.changed = Array.from({ length: 12 }, (_, i) => change("t1", String(i), i + 1));
    render(<ExecutionParameterChanges executionId="002" />);

    const t1 = screen.getAllByRole("group")[1];
    const rows = within(t1).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(10);
    expect(rows[0]).toHaveTextContent("+12.00 %");

    fireEvent.click(within(t1).getByRole("button", { name: "Show all 12 targets" }));
    expect(within(t1).getAllByRole("row").slice(1)).toHaveLength(12);
  });

  it("opens the lineage of the selected target", () => {
    mocks.executions = [{ execution_id: "002" }, { execution_id: "001" }];
    mocks.changed = [change("qubit_frequency", "1", 0.5)];
    render(<ExecutionParameterChanges executionId="002" />);

    fireEvent.click(screen.getByRole("button", { name: "Lineage of qubit_frequency 1" }));

    expect(mocks.dialogTarget).toEqual({ parameterName: "qubit_frequency", qid: "1" });
  });

  it("explains a first run and a run without published values", () => {
    mocks.executions = [{ execution_id: "001" }];
    render(<ExecutionParameterChanges executionId="001" />);
    expect(screen.getByText(/no earlier run to compare against/)).toBeTruthy();
    expect(mocks.compareParams).toBeNull();

    cleanup();
    render(<ExecutionParameterChanges executionId="unknown" />);
    expect(screen.getByText(/No values published by this run/)).toBeTruthy();
  });
});
