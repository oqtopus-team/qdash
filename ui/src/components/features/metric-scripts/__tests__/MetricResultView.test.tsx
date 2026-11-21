import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MetricResultView } from "../render/MetricResultView";
import { evaluateResponse, qubitCell } from "./fixtures";

vi.mock("@/hooks/useTopologyConfig", async () => {
  const { TOPOLOGY: topology } = await import("./fixtures");
  return { useTopologyConfig: () => topology };
});
vi.mock("@/hooks/useMetricsConfig", () => ({
  useMetricsConfig: () => ({ colorScale: { colors: ["#000000", "#ffffff"] } }),
}));

function apiError(status: number, detail: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail } },
  });
}

afterEach(() => {
  cleanup();
});

describe("MetricResultView", () => {
  it("shows a worker failure's message, diagnostics with line jumps, and log", () => {
    const onJump = vi.fn();
    render(
      <MetricResultView
        result={undefined}
        error={apiError(422, {
          message: "Metric 't1' raised ZeroDivisionError",
          diagnostics: [{ message: "division by zero", line: 7, column: 12, function: "t1" }],
          log: "debug output",
        })}
        topologyId="topo"
        view="map"
        onJumpToLine={onJump}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Metric 't1' raised ZeroDivisionError");
    expect(screen.getByText("division by zero")).toBeInTheDocument();
    expect(screen.getByText("debug output")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Line 7:12 · t1()" }));
    expect(onJump).toHaveBeenCalledWith(7, 12);
    // A 422 is not retried: the same script would fail the same way.
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("asks to retry when the evaluation queue is full", () => {
    const onRetry = vi.fn();
    render(
      <MetricResultView
        result={undefined}
        error={apiError(429, "Metric script evaluation queue is full")}
        topologyId="topo"
        view="map"
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Metric script evaluation queue is full. Other evaluations are running; try again",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("shows plain string errors from other endpoints", () => {
    render(
      <MetricResultView
        result={undefined}
        error={apiError(409, "Chip 'chip-1' has no topology")}
        topologyId="topo"
        view="map"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Chip 'chip-1' has no topology");
  });

  it("shows the period used, a truncation notice, the log, and switches to a table", () => {
    const onViewChange = vi.fn();
    const result = evaluateResponse(
      "qubit",
      [qubitCell("0", { value: 12 }), qubitCell("1", { status: "missing" })],
      { truncated: true, log: "printed by the script" },
    );
    const { rerender } = render(
      <MetricResultView result={result} topologyId="topo" view="map" onViewChange={onViewChange} />,
    );

    expect(screen.getByText("T1 (us)")).toBeInTheDocument();
    expect(screen.getByText(/2026-11-06 09:00 – 2026-11-20 09:00/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("cut short");
    expect(screen.getByText("printed by the script")).toBeInTheDocument();
    expect(screen.getByText("OK 1 · Missing data 1")).toBeInTheDocument();
    expect(screen.getByTestId("qubit-map")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(onViewChange).toHaveBeenCalledWith("table");
    rerender(<MetricResultView result={result} topologyId="topo" view="table" />);
    expect(screen.getByTestId("result-table")).toBeInTheDocument();
  });

  it("opens the details of a selected cell", () => {
    const result = evaluateResponse("qubit", [
      qubitCell("0", {
        value: 12,
        label: "median of 3",
        assessment: { count: 3, checks: [{ label: "samples", value: 3 }], estimates: ["guess"] },
        references: [{ metric: "t1", target: "0", value: 12, unit: "us", task_id: "task-1" }],
      }),
    ]);
    render(<MetricResultView result={result} topologyId="topo" view="table" />);

    fireEvent.click(screen.getByRole("button", { name: "Q0" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("n = 3");
    expect(dialog).toHaveTextContent("samples");
    expect(dialog).toHaveTextContent("guess");
    expect(dialog).toHaveTextContent("task-1");
  });
});
