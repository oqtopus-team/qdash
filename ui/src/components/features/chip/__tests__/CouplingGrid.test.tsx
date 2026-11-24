import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CouplingGrid } from "../CouplingGrid";

const { taskResults, downloadFiguresAsZip, toastError } = vi.hoisted(() => ({
  taskResults: { current: {} as Record<string, unknown> },
  downloadFiguresAsZip: vi.fn(),
  toastError: vi.fn(),
}));

const wideQubits = Object.fromEntries(
  Array.from({ length: 24 }, (_, index) => [
    index,
    { row: Math.floor(index / 12), col: index % 12 },
  ]),
);

vi.mock("@/hooks/useTopologyConfig", () => ({
  useTopologyConfig: () => ({
    muxSize: 2,
    regionSize: 4,
    hasMux: false,
    layoutType: "grid",
    showMuxBoundaries: false,
    qubits: wideQubits,
    couplings: [[0, 1]],
    gridSize: 12,
  }),
}));

vi.mock("@/hooks/useCouplingTaskResults", () => ({
  useCouplingTaskResults: () => ({
    data: { data: { result: taskResults.current } },
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/hooks/useGridLayout", () => ({
  useGridLayout: () => ({
    containerRef: { current: null },
    cellSize: 40,
    isMobile: false,
    viewportHeight: 900,
    gap: 8,
    padding: 32,
  }),
}));

vi.mock("@/client/task-result/task-result", () => ({ downloadFiguresAsZip }));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: toastError }),
}));

vi.mock("@/components/charts/TaskFigure", () => ({
  TaskFigure: () => null,
}));

vi.mock("@/components/features/chip/modals/CouplingTaskHistoryModal", () => ({
  CouplingTaskHistoryModal: () => null,
}));

afterEach(cleanup);

beforeEach(() => {
  taskResults.current = {};
  downloadFiguresAsZip.mockReset();
  toastError.mockReset();
});

describe("CouplingGrid locked view", () => {
  it("wraps the locked grid in a scroller so overflowing cells stay reachable", () => {
    const { container } = render(
      <CouplingGrid
        chipId="chip"
        topologyId="wide"
        selectedTask="CheckZX90"
        selectedDate="latest"
        gridSize={12}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Lock" }));

    const scroller = container.querySelector<HTMLElement>(".overflow-auto.justify-center-safe");
    expect(scroller).not.toBeNull();
    const outerContainer = scroller?.parentElement;
    expect(outerContainer).toHaveClass("overflow-hidden");
    const fullscreenButton = screen.getByRole("button", { name: "Fullscreen" });
    expect(outerContainer?.contains(fullscreenButton)).toBe(true);
    expect(scroller?.firstElementChild).toHaveClass("relative", "flex-shrink-0");
    expect(scroller?.contains(fullscreenButton)).toBe(false);
  });
});

describe("CouplingGrid artifact download", () => {
  it("reports a failed download in a toast and keeps the dialog and selection for a retry", async () => {
    taskResults.current = {
      "0-1": {
        status: "completed",
        figure_path: [],
        json_figure_path: [],
        raw_data_path: ["/raw/a.nc"],
      },
    };
    downloadFiguresAsZip.mockRejectedValueOnce({
      response: {
        data: new Blob([JSON.stringify({ detail: "Archive too large" })]),
      },
    });
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => undefined);

    render(
      <CouplingGrid
        chipId="chip"
        topologyId="wide"
        selectedTask="CheckZX90"
        selectedDate="latest"
        gridSize={12}
      />,
    );

    fireEvent.click(screen.getByTitle("Select figures to download"));
    expect(screen.getByText("1 / 1 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Download" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Download" }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Archive too large"));
    expect(alertSpy).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("1 / 1 selected")).toBeInTheDocument();
    const retry = within(screen.getByRole("dialog")).getByRole("button", {
      name: "Download",
    });
    expect(retry).toBeEnabled();

    downloadFiguresAsZip.mockResolvedValueOnce({ data: new Blob(["zip"]) });
    const createObjectURL = vi.fn(() => "blob:zip");
    const revokeObjectURL = vi.fn();
    Object.assign(window.URL, { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    fireEvent.click(retry);

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(downloadFiguresAsZip).toHaveBeenCalledTimes(2);
    expect(downloadFiguresAsZip).toHaveBeenLastCalledWith(
      expect.objectContaining({ paths: ["/raw/a.nc"] }),
      { responseType: "blob" },
    );
    expect(click).toHaveBeenCalled();
    click.mockRestore();
    alertSpy.mockRestore();
  });
});
