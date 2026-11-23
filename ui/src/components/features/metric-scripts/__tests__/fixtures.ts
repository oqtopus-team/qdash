import type { MetricCell, MetricScriptEvaluateResponse } from "@/schemas";

/** A 2x2 topology: qubits 0 1 / 2 3. */
export const TOPOLOGY = {
  qubits: {
    0: { row: 0, col: 0 },
    1: { row: 0, col: 1 },
    2: { row: 1, col: 0 },
    3: { row: 1, col: 1 },
  },
  gridSize: 2,
  muxGroups: [],
  hasMux: false,
  showMuxBoundaries: false,
  isLoading: false,
};

export function qubitCell(qid: string, overrides: Partial<MetricCell> = {}): MetricCell {
  return { key: qid, qid, status: "ok", value: null, references: [], ...overrides };
}

export function pairCell(
  source: string,
  target: string,
  overrides: Partial<MetricCell> = {},
): MetricCell {
  return {
    key: `${source}>${target}`,
    qid: null,
    source,
    target,
    hops: 1,
    status: "ok",
    value: null,
    references: [],
    ...overrides,
  };
}

export function evaluateResponse(
  target: "qubit" | "pair",
  cells: MetricCell[],
  overrides: Partial<MetricScriptEvaluateResponse> = {},
): MetricScriptEvaluateResponse {
  return {
    script_id: "ms_000000000001",
    revision: 3,
    metric: {
      id: target === "pair" ? "zx90_median" : "t1",
      title: target === "pair" ? "Median ZX90 gate fidelity" : "T1",
      unit: target === "pair" ? "%" : "us",
      target,
      hops: target === "pair" ? [1, 2] : [1, 2],
      parameters: {},
      has_legend: false,
    },
    chip_id: "chip-1",
    start: "2026-11-06T00:00:00Z",
    end: "2026-11-20T00:00:00Z",
    params: {},
    legend: null,
    cells,
    log: "",
    evaluated_at: "2026-11-20T00:00:05Z",
    truncated: false,
    ...overrides,
  };
}
