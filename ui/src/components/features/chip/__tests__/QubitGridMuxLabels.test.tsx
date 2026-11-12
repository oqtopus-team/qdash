import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QubitGrid } from "@/components/features/chip/QubitGrid";

// Synthetic, sparse, nonrectangular 10-qubit layout on an 8x8 grid (not
// modeled on any real chip). MUX 2 has only two members; most cells are empty.
const SYNTHETIC_QUBITS: Record<string, { row: number; col: number }> = {
  "0": { row: 0, col: 4 },
  "1": { row: 0, col: 5 },
  "2": { row: 1, col: 4 },
  "3": { row: 1, col: 5 },
  "4": { row: 2, col: 0 },
  "5": { row: 2, col: 1 },
  "6": { row: 3, col: 0 },
  "7": { row: 3, col: 1 },
  "8": { row: 5, col: 5 },
  "9": { row: 5, col: 6 },
};
const SYNTHETIC_MUXES: Record<string, number[]> = {
  "0": [0, 1, 2, 3],
  "1": [4, 5, 6, 7],
  "2": [8, 9],
};
const NUM_QUBITS = Object.keys(SYNTHETIC_QUBITS).length;

function syntheticTopology(withMuxes = true) {
  const groups: Record<string, number[]> = Object.fromEntries(
    Object.entries(SYNTHETIC_MUXES).map(([mux, qids]) => [mux, [...qids]]),
  );
  return {
    id: "synthetic-sparse-layout",
    name: "Synthetic sparse layout",
    description: "",
    grid_size: 8,
    num_qubits: NUM_QUBITS,
    layout_type: "grid",
    direction_convention: "checkerboard_cr",
    muxes: withMuxes ? groups : {},
    muxes_source: "muxes",
    qubits: { ...SYNTHETIC_QUBITS },
    couplings: [],
    visualization: { show_mux_boundaries: true, region_size: 4 },
  };
}

let topologyResponse: ReturnType<typeof syntheticTopology> = syntheticTopology();

vi.mock("@/client/topology/topology", () => ({
  useGetTopologyById: () => ({
    data: { data: { data: topologyResponse } },
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/client/task-result/task-result", () => ({
  downloadFiguresAsZip: vi.fn(),
}));

vi.mock("@/hooks/useQubitTaskResults", () => ({
  useQubitTaskResults: () => ({
    data: {
      data: {
        result: Object.fromEntries(
          Array.from({ length: NUM_QUBITS }, (_, qid) => [
            String(qid),
            { task_id: `t-${qid}`, qid: String(qid), name: "CheckRabi", status: "completed" },
          ]),
        ),
      },
    },
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/components/features/chip/modals/TaskHistoryModal", () => ({
  TaskHistoryModal: () => null,
}));

vi.mock("@/hooks/useGridLayout", () => ({
  useGridLayout: () => ({
    containerRef: { current: null },
    cellSize: 60,
    isMobile: false,
    viewportHeight: 1000,
    gap: 4,
    padding: 8,
  }),
}));

function renderGrid() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <QubitGrid
        chipId="chip-synthetic"
        topologyId="synthetic-sparse-layout"
        selectedTask="CheckRabi"
        selectedDate="latest"
        gridSize={8}
      />
    </QueryClientProvider>,
  );
}

function muxLabels(): HTMLElement[] {
  return screen.queryAllByText(/^MUX\d+$/);
}

beforeEach(() => {
  topologyResponse = syntheticTopology();
});

afterEach(() => {
  cleanup();
});

describe("QubitGrid MUX labels", () => {
  it("labels a sparse layout with its topology MUX IDs on the member cells", () => {
    renderGrid();

    const labels = muxLabels();
    expect(labels.map((label) => label.textContent)).toEqual(["MUX0", "MUX1", "MUX2"]);

    // MUX0 covers qubits 0-3 at rows 0-1, cols 4-5 (1-based CSS grid lines).
    const mux0 = screen.getByText("MUX0").parentElement as HTMLElement;
    expect(mux0.style.gridColumn).toBe("5 / span 2");
    expect(mux0.style.gridRow).toBe("1 / span 2");

    // MUX1 starts at the left edge of rows 2-3; no label sits on the empty top-left cell.
    const mux1 = screen.getByText("MUX1").parentElement as HTMLElement;
    expect(mux1.style.gridColumn).toBe("1 / span 2");
    expect(mux1.style.gridRow).toBe("3 / span 2");

    // MUX2 has two members in one row.
    const mux2 = screen.getByText("MUX2").parentElement as HTMLElement;
    expect(mux2.style.gridColumn).toBe("6 / span 2");
    expect(mux2.style.gridRow).toBe("6 / span 1");
  });

  it("uses sparse MUX IDs from the topology as labels", () => {
    const sparse = syntheticTopology();
    sparse.muxes = Object.fromEntries(
      Object.entries(sparse.muxes).map(([mux, group]) => [String(Number(mux) * 10 + 3), group]),
    );
    topologyResponse = sparse;

    renderGrid();

    expect(muxLabels().map((label) => label.textContent)).toEqual(["MUX3", "MUX13", "MUX23"]);
  });

  it("shows no MUX labels when the topology declares no MUX", () => {
    topologyResponse = syntheticTopology(false);

    renderGrid();

    expect(muxLabels()).toEqual([]);
    // Standalone qubits are still shown.
    expect(screen.getAllByText(/^Q\d+$|^\d+$/).length).toBeGreaterThan(0);
  });

  it("labels only declared MUXes and keeps standalone qubits visible", () => {
    const partial = syntheticTopology();
    // MUX 0 keeps three members; qubit 3 and all of MUX 1 become standalone.
    partial.muxes = { ...partial.muxes, "0": [0, 1, 2] };
    delete partial.muxes["1"];
    topologyResponse = partial;

    renderGrid();

    const labels = muxLabels().map((label) => label.textContent);
    expect(labels).toContain("MUX0");
    expect(labels).not.toContain("MUX1");
    expect(labels).toEqual(["MUX0", "MUX2"]);
    // MUX0's label still spans its members' bounding box.
    const mux0 = screen.getByText("MUX0").parentElement as HTMLElement;
    expect(mux0.style.gridColumn).toBe("5 / span 2");
  });

  it("keeps a single-member MUX label off the center of its cell", () => {
    const singleton = syntheticTopology();
    singleton.muxes = { ...singleton.muxes, "2": [8] };
    topologyResponse = singleton;

    renderGrid();

    const mux2 = screen.getByText("MUX2").parentElement as HTMLElement;
    expect(mux2.style.gridColumn).toBe("6 / span 1");
    expect(mux2.style.gridRow).toBe("6 / span 1");
    expect(mux2.className).toContain("items-end");
    expect(mux2.className).toContain("justify-start");
    // Multi-cell MUX labels stay centered.
    const mux0 = screen.getByText("MUX0").parentElement as HTMLElement;
    expect(mux0.className).toContain("justify-center");
  });

  it("hides labels when show_mux_boundaries is off, without changing membership", () => {
    const hidden = syntheticTopology();
    hidden.visualization = { show_mux_boundaries: false, region_size: 4 };
    topologyResponse = hidden;

    renderGrid();

    expect(muxLabels()).toEqual([]);
  });
});
