import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PairMap } from "../render/PairMap";
import { QubitMap } from "../render/QubitMap";
import { evaluateResponse, pairCell, qubitCell } from "./fixtures";

vi.mock("@/hooks/useTopologyConfig", async () => {
  const { TOPOLOGY: topology } = await import("./fixtures");
  return { useTopologyConfig: () => topology };
});

const RED = "#dc2626";
const BLUE = "#2563eb";
const GRAY = "#737373";

afterEach(() => {
  cleanup();
});

describe("QubitMap", () => {
  it("colours qubits, marks cells without values and counts the legend", () => {
    const onSelect = vi.fn();
    const result = evaluateResponse(
      "qubit",
      [
        qubitCell("0", { value: 1.5, color: BLUE, label: "fine" }),
        qubitCell("1", { status: "missing", message: "t1 is missing" }),
        qubitCell("2", { status: "error", message: "boom" }),
      ],
      {
        legend: {
          kind: "categorical",
          items: [
            { color: BLUE, label: "Good" },
            { color: GRAY, label: "Not evaluated" },
          ],
        },
      },
    );
    render(<QubitMap result={result} topologyId="topo" onSelectCell={onSelect} />);

    expect(screen.getByTestId("metric-qubit-0")).toHaveAttribute("fill", BLUE);
    expect(screen.getByTestId("metric-qubit-1")).toHaveAttribute("fill", GRAY);
    expect(screen.getByTestId("metric-qubit-3")).toHaveAttribute("data-status", "none");
    // Q3 has no cell; it is drawn grey and counted under "Not evaluated" too.
    const legend = screen.getByRole("list", { name: "Legend" });
    expect(within(legend).getByText("Good").nextSibling).toHaveTextContent("1");
    expect(within(legend).getByText("Not evaluated").nextSibling).toHaveTextContent("3");
    expect(within(legend).getByText("Error").nextSibling).toHaveTextContent("1");

    fireEvent.click(screen.getByRole("button", { name: /^Q0: 1.5 us: fine/ }));
    expect(onSelect).toHaveBeenCalledWith(result.cells[0]);
  });
});

describe("PairMap", () => {
  const result = evaluateResponse(
    "pair",
    [
      pairCell("0", "1", { value: 99, color: BLUE }),
      pairCell("1", "0", { value: 91, color: RED }),
      pairCell("0", "3", { hops: 2, value: 95, color: BLUE }),
      pairCell("2", "3", { status: "empty", label: "fewer than min_samples observations" }),
      pairCell("3", "2", { status: "error", message: "KeyError" }),
    ],
    {
      legend: {
        kind: "categorical",
        items: [
          { color: BLUE, label: "Good" },
          { color: RED, label: "Bad" },
          { color: GRAY, label: "Not evaluated" },
        ],
      },
    },
  );

  function legendCount(label: string): string | null {
    const legend = screen.getByRole("list", { name: "Legend" });
    return within(legend).getByText(label).nextSibling?.textContent ?? null;
  }

  it("draws one edge per pair, dashed for two hops, and counts the legend", () => {
    render(<PairMap result={result} topologyId="topo" direction="both" onSelectCell={vi.fn()} />);

    expect(screen.getAllByTestId(/^metric-edge-/)).toHaveLength(5);
    expect(screen.getByTestId("metric-edge-0>1")).not.toHaveAttribute("stroke-dasharray");
    expect(screen.getByTestId("metric-edge-0>3")).toHaveAttribute("stroke-dasharray", "5 4");
    expect(screen.getByTestId("metric-edge-0>3")).toHaveAttribute("data-hops", "2");
    expect(screen.getByTestId("metric-edge-3>2")).toHaveAttribute("data-status", "error");
    expect(legendCount("Good")).toBe("2");
    expect(legendCount("Bad")).toBe("1");
    expect(legendCount("Not evaluated")).toBe("2");
  });

  it("filters by direction and pair distance and recounts", () => {
    const { rerender } = render(
      <PairMap result={result} topologyId="topo" direction="forward" onSelectCell={vi.fn()} />,
    );
    expect(
      screen.getAllByTestId(/^metric-edge-/).map((edge) => edge.getAttribute("data-testid")),
    ).toEqual(["metric-edge-0>1", "metric-edge-0>3", "metric-edge-2>3"]);
    expect(legendCount("Bad")).toBe("0");

    rerender(
      <PairMap
        result={result}
        topologyId="topo"
        direction="reverse"
        hops={[1]}
        onSelectCell={vi.fn()}
      />,
    );
    expect(
      screen.getAllByTestId(/^metric-edge-/).map((edge) => edge.getAttribute("data-testid")),
    ).toEqual(["metric-edge-1>0", "metric-edge-3>2"]);
    expect(legendCount("Error")).toBe("1");
  });

  it("offers the direction toggle only when it can change it", () => {
    const onDirectionChange = vi.fn();
    const { rerender } = render(
      <PairMap result={result} topologyId="topo" direction="both" onSelectCell={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: "Forward" })).not.toBeInTheDocument();

    rerender(
      <PairMap
        result={result}
        topologyId="topo"
        direction="both"
        onDirectionChange={onDirectionChange}
        onSelectCell={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Forward" }));
    expect(onDirectionChange).toHaveBeenCalledWith("forward");
  });
});
